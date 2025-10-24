"""
Barentswatch API integration for AIS data
"""

import logging
import requests
import time
from lib.geo_utils import line_segments_intersect, distance_to_stad_line
from lib.config import get_ship_type_name
from lib.ship_lookup import get_ship_info

logger = logging.getLogger(__name__)


def get_access_token(config):
    """
    Authenticate with Barentswatch and get access token

    Args:
        config: Configuration dict with client_id, client_secret, and auth_url

    Returns:
        str: Access token

    Raises:
        Exception: If authentication fails
    """
    logger.info("Authenticating with Barentswatch...")

    data = {
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'scope': 'ais',
        'grant_type': 'client_credentials'
    }

    response = requests.post(
        config['auth_url'],
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )

    if response.status_code != 200:
        logger.error(f"Authentication failed: {response.status_code} - {response.text}")
        raise Exception(f"Authentication failed: {response.status_code} - {response.text}")

    token_data = response.json()
    logger.info("✓ Authenticated successfully")
    return token_data['access_token']


def get_mmsi_list(access_token, msgtimefrom, msgtimeto, config):
    """
    Get list of MMSIs in the Stadthavet area for given time range

    Args:
        access_token: Barentswatch API access token
        msgtimefrom: Start time (ISO format string)
        msgtimeto: End time (ISO format string)
        config: Configuration dict with area bounds and API URL

    Returns:
        list: List of MMSI numbers

    Raises:
        Exception: If API request fails
    """
    logger.info(f"Fetching MMSI list for {msgtimefrom} to {msgtimeto}...")

    lat_nw, lon_nw = config['area_nw']
    lat_se, lon_se = config['area_se']

    data = {
        'msgtimefrom': msgtimefrom,
        'msgtimeto': msgtimeto,
        'polygon': {
            'coordinates': [[
                [lon_nw, lat_nw],  # Northwest
                [lon_se, lat_nw],  # Northeast
                [lon_se, lat_se],  # Southeast
                [lon_nw, lat_se],  # Southwest
                [lon_nw, lat_nw]   # Close polygon
            ]],
            'type': 'Polygon'
        }
    }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    response = requests.post(config['mmsi_area_url'], headers=headers, json=data)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch MMSI list: {response.status_code} - {response.text}")

    mmsi_list = response.json()
    logger.info(f"✓ Found {len(mmsi_list)} MMSIs")
    return mmsi_list


def fetch_and_store_track(db, access_token, mmsi, msgtimefrom, msgtimeto, config):
    """
    Fetch track data for a single MMSI and store in database

    Args:
        db: Database instance
        access_token: Barentswatch API access token
        mmsi: Ship MMSI number
        msgtimefrom: Start time (ISO format string)
        msgtimeto: End time (ISO format string)
        config: Configuration dict with API settings

    Returns:
        tuple: (success, ship_name, ship_type_name, positions_stored, crossings_detected)
               or False if fetch failed
    """
    start_time = time.time()

    # Fetch track from API with date range
    url = f"{config['track_url']}/{mmsi}/{msgtimefrom}/{msgtimeto}"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    api_start = time.time()
    response = requests.get(url, headers=headers)
    api_time = time.time() - api_start

    if response.status_code != 200:
        return False

    positions = response.json()

    if not positions or not isinstance(positions, list):
        return False

    # Extract ship info from first position
    ship_name = positions[0].get('name') or f'Unknown-{mmsi}'
    # Clean up empty/whitespace names
    if ship_name.strip() == '':
        ship_name = f'Unknown-{mmsi}'
    ship_type = positions[0].get('shipType')
    ship_type_name = get_ship_type_name(ship_type)

    # Check if we need to fetch ship info from Marinesia API
    # Only fetch if we haven't tried before (ship_info_fetched_at IS NULL)
    if db.use_postgres:
        db.execute('SELECT ship_info_fetched_at FROM ships WHERE mmsi = %s', (mmsi,))
    else:
        db.execute('SELECT ship_info_fetched_at FROM ships WHERE mmsi = ?', (mmsi,))

    existing_ship = db.fetchone()
    should_fetch_ship_info = (existing_ship is None or existing_ship[0] is None)

    if should_fetch_ship_info:
        # Fetch static ship data from Marinesia API
        # This includes length, width, destination, callsign, etc.
        ship_info = get_ship_info(mmsi, config)

        if ship_info:
            length = ship_info.get('length')
            width = ship_info.get('width')
            callsign = ship_info.get('callsign')
            destination = None
        else:
            destination = None
            callsign = None
            length = None
            width = None

        # Store ship info (and mark that we attempted to fetch ship info)
        if db.use_postgres:
            db.execute('''
                INSERT INTO ships (mmsi, name, ship_type, ship_type_name, destination, callsign, length, width, ship_info_fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (mmsi) DO UPDATE
                SET name = EXCLUDED.name,
                    ship_type = EXCLUDED.ship_type,
                    ship_type_name = EXCLUDED.ship_type_name,
                    destination = EXCLUDED.destination,
                    callsign = EXCLUDED.callsign,
                    length = EXCLUDED.length,
                    width = EXCLUDED.width,
                    ship_info_fetched_at = NOW()
            ''', (mmsi, ship_name, ship_type, ship_type_name, destination, callsign, length, width))
        else:
            db.execute('''
                INSERT OR REPLACE INTO ships (mmsi, name, ship_type, ship_type_name, destination, callsign, length, width, ship_info_fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (mmsi, ship_name, ship_type, ship_type_name, destination, callsign, length, width))
    else:
        # Ship info already fetched, just update basic info without touching length/width/callsign
        if db.use_postgres:
            db.execute('''
                INSERT INTO ships (mmsi, name, ship_type, ship_type_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (mmsi) DO UPDATE
                SET name = EXCLUDED.name,
                    ship_type = EXCLUDED.ship_type,
                    ship_type_name = EXCLUDED.ship_type_name
            ''', (mmsi, ship_name, ship_type, ship_type_name))
        else:
            db.execute('''
                INSERT INTO ships (mmsi, name, ship_type, ship_type_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (mmsi) DO UPDATE
                SET name = EXCLUDED.name,
                    ship_type = EXCLUDED.ship_type,
                    ship_type_name = EXCLUDED.ship_type_name
            ''', (mmsi, ship_name, ship_type, ship_type_name))

    # Process positions and check for crossings
    crossings_detected = 0
    prev_pos = None
    positions_stored = 0
    positions_filtered = 0

    for i, pos in enumerate(positions):
        lat = pos.get('latitude')
        lon = pos.get('longitude')
        timestamp = pos.get('msgtime')
        sog = pos.get('speedOverGround')
        cog = pos.get('courseOverGround')
        heading = pos.get('trueHeading')

        if lat is not None and lon is not None:
            # Check if this is the last position
            is_last_position = (i == len(positions) - 1)

            # Only store positions within 50km of Stad line, OR the last position (for map display)
            distance = distance_to_stad_line(lat, lon, config['stad_line_start'], config['stad_line_end'])
            if distance <= 50 or is_last_position:
                # Store position
                db.execute('''
                    INSERT INTO positions (mmsi, timestamp, latitude, longitude, sog, cog, heading)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (mmsi, timestamp) DO NOTHING
                ''' if db.use_postgres else '''
                    INSERT OR IGNORE INTO positions (mmsi, timestamp, latitude, longitude, sog, cog, heading)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (mmsi, timestamp, lat, lon, sog, cog, heading))
                positions_stored += 1
                if is_last_position and distance > 50:
                    logger.debug(f"  Stored last position even though >50km from Stad")
            else:
                positions_filtered += 1

            # Check for Stad crossing
            if prev_pos is not None:
                curr_point = (lon, lat)
                prev_point = (prev_pos['longitude'], prev_pos['latitude'])

                if line_segments_intersect(prev_point, curr_point,
                                         config['stad_line_start'],
                                         config['stad_line_end']):
                    direction = 'E->W' if prev_pos['longitude'] > lon else 'W->E'

                    db.execute('''
                        INSERT INTO crossings (mmsi, crossing_time, crossing_lat, crossing_lon, direction)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (mmsi, crossing_time) DO NOTHING
                    ''' if db.use_postgres else '''
                        INSERT OR IGNORE INTO crossings (mmsi, crossing_time, crossing_lat, crossing_lon, direction)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (mmsi, timestamp, lat, lon, direction))

                    crossings_detected += 1
                    logger.info(f"  *** CROSSING: {ship_name} ({direction}) at {timestamp}")

            prev_pos = pos

    db_start = time.time()
    db.commit()
    db_time = time.time() - db_start

    total_time = time.time() - start_time

    if positions_filtered > 0:
        logger.info(f"  📍 Filtered {positions_filtered}/{len(positions)} positions (>50km from Stad)")

    return True, ship_name, ship_type_name, positions_stored, crossings_detected
