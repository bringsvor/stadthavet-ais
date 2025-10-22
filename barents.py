#!/usr/bin/env python3

"""
Barentswatch AIS Data Collection and Stad Peninsula Crossing Detection

This script:
1. Fetches AIS data from Barentswatch API for Stadthavet area
2. Stores ship positions and metadata in database (SQLite or PostgreSQL)
3. Detects when ships cross the Stad peninsula line
4. Can be run as a cron job to build historical data over time

https://www.barentswatch.no/minside/devaccess/ais
https://developer.barentswatch.no/docs/AIS/historic-ais-api
"""

import os
import sys
import logging
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Load .env file if it exists (for local development)
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

# Database detection - use PostgreSQL on render.com, SQLite locally
USE_POSTGRES = os.environ.get('RENDER') is not None or os.environ.get('DATABASE_URL') is not None

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import execute_values
    DB_URL = os.environ.get('DATABASE_URL')
else:
    import sqlite3

# Configuration
CONFIG = {
    'client_id': os.environ.get('BARENTSWATCH_CLIENT_ID'),
    'client_secret': os.environ.get('BARENTSWATCH_CLIENT_SECRET'),
    'auth_url': 'https://id.barentswatch.no/connect/token',
    'mmsi_area_url': 'https://historic.ais.barentswatch.no/v1/historic/mmsiinarea',
    'track_url': 'https://historic.ais.barentswatch.no/v1/historic/trackslast24hours',

    # Stadthavet bounding box
    'area_nw': (62.8, 4.5),  # (lat, lon) Northwest corner
    'area_se': (61.8, 7.0),  # (lat, lon) Southeast corner

    # Stad peninsula crossing line
    'stad_line_start': (5.100380, 62.194513),  # (lon, lat)
    'stad_line_end': (4.342984, 62.442407),

    # Waiting zones (ships waiting for weather to improve)
    # Positioned in open water, away from ports/quays
    # East side of Stad (waiting to cross westward) - between Stad and Ålesund
    'waiting_zone_east': {
        'center_lat': 62.25,
        'center_lon': 5.3,
        'radius_km': 10
    },
    # West side of Stad (waiting to cross eastward) - west of Stad in open ocean
    'waiting_zone_west': {
        'center_lat': 62.25,  # A bit south
        'center_lon': 4.2,    # Further west, clearly on ocean side
        'radius_km': 10
    },

    # Loitering thresholds
    'loitering_speed_threshold': 3.0,  # knots - below this is considered stationary/waiting
    'loitering_time_threshold': 120,   # minutes - must be in zone this long to count as waiting

    # Weather thresholds for considering waiting as weather-related
    'wind_threshold_ms': 10.0,         # m/s - above this is considered bad weather for crossing
    'require_bad_weather': True,       # Only count waiting if weather was actually bad

    # Weather API
    'met_api_url': 'https://frost.met.no/observations/v0.jsonld',
    'met_client_id': os.environ.get('MET_CLIENT_ID', ''),  # Optional: register at frost.met.no

    # Weather station near Stad (Svinøy Fyr - closest to Stad with full wind data)
    'weather_station': 'SN59800',  # Svinøy Fyr weather station

    # Database
    'sqlite_db': 'stadthavet_ais.db',
    'postgres_url': DB_URL if USE_POSTGRES else None
}

# Ship type mapping (AIS ship type codes)
SHIP_TYPES = {
    30: 'Fishing', 31: 'Towing', 32: 'Towing (large)',
    33: 'Dredging', 34: 'Diving', 35: 'Military',
    36: 'Sailing', 37: 'Pleasure craft',
    40: 'High speed craft', 41: 'High speed craft (hazardous)',
    42: 'High speed craft (hazardous)', 43: 'High speed craft (hazardous)',
    44: 'High speed craft (hazardous)',
    50: 'Pilot', 51: 'Search and rescue', 52: 'Tug',
    53: 'Port tender', 54: 'Anti-pollution',
    55: 'Law enforcement', 56: 'Spare', 57: 'Spare',
    58: 'Medical', 59: 'Non-combatant',
    60: 'Passenger', 61: 'Passenger (hazardous)',
    62: 'Passenger (hazardous)', 63: 'Passenger (hazardous)',
    64: 'Passenger (hazardous)',
    70: 'Cargo', 71: 'Cargo (hazardous)',
    72: 'Cargo (hazardous)', 73: 'Cargo (hazardous)',
    74: 'Cargo (hazardous)',
    80: 'Tanker', 81: 'Tanker (hazardous)',
    82: 'Tanker (hazardous)', 83: 'Tanker (hazardous)',
    84: 'Tanker (hazardous)',
    90: 'Other', 91: 'Other (hazardous)',
    92: 'Other (hazardous)', 93: 'Other (hazardous)',
    94: 'Other (hazardous)'
}


class Database:
    """Database abstraction layer supporting both SQLite and PostgreSQL"""

    def __init__(self, use_postgres=USE_POSTGRES):
        self.use_postgres = use_postgres
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establish database connection"""
        if self.use_postgres:
            logger.info(f"Connecting to PostgreSQL...")
            self.conn = psycopg2.connect(CONFIG['postgres_url'])
            self.cursor = self.conn.cursor()
        else:
            logger.info(f"Connecting to SQLite: {CONFIG['sqlite_db']}")
            self.conn = sqlite3.connect(CONFIG['sqlite_db'])
            self.cursor = self.conn.cursor()

    def create_tables(self):
        """Create database tables if they don't exist"""
        if self.use_postgres:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS ships (
                    mmsi BIGINT PRIMARY KEY,
                    name TEXT,
                    ship_type INTEGER,
                    ship_type_name TEXT
                )
            ''')

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    id SERIAL PRIMARY KEY,
                    mmsi BIGINT,
                    timestamp TIMESTAMP WITH TIME ZONE,
                    latitude REAL,
                    longitude REAL,
                    sog REAL,
                    cog REAL,
                    heading INTEGER,
                    FOREIGN KEY (mmsi) REFERENCES ships(mmsi)
                )
            ''')

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS crossings (
                    id SERIAL PRIMARY KEY,
                    mmsi BIGINT,
                    crossing_time TIMESTAMP WITH TIME ZONE,
                    crossing_lat REAL,
                    crossing_lon REAL,
                    direction TEXT,
                    FOREIGN KEY (mmsi) REFERENCES ships(mmsi)
                )
            ''')

            # Create indexes for performance
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_mmsi ON positions(mmsi)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_timestamp ON positions(timestamp)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_crossings_mmsi ON crossings(mmsi)')

        else:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS ships (
                    mmsi INTEGER PRIMARY KEY,
                    name TEXT,
                    ship_type INTEGER,
                    ship_type_name TEXT
                )
            ''')

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mmsi INTEGER,
                    timestamp TEXT,
                    latitude REAL,
                    longitude REAL,
                    sog REAL,
                    cog REAL,
                    heading INTEGER,
                    FOREIGN KEY (mmsi) REFERENCES ships(mmsi)
                )
            ''')

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS crossings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mmsi INTEGER,
                    crossing_time TEXT,
                    crossing_lat REAL,
                    crossing_lon REAL,
                    direction TEXT,
                    FOREIGN KEY (mmsi) REFERENCES ships(mmsi)
                )
            ''')

            # Create indexes
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_mmsi ON positions(mmsi)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_timestamp ON positions(timestamp)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_crossings_mmsi ON crossings(mmsi)')

        # Weather data table (same for both databases)
        if self.use_postgres:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS weather (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE,
                    station TEXT,
                    wind_speed REAL,
                    wind_direction REAL,
                    wind_gust REAL,
                    wave_height REAL,
                    air_temperature REAL,
                    pressure REAL
                )
            ''')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_weather_timestamp ON weather(timestamp)')

            # Waiting events table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS waiting_events (
                    id SERIAL PRIMARY KEY,
                    mmsi BIGINT,
                    zone TEXT,
                    start_time TIMESTAMP WITH TIME ZONE,
                    end_time TIMESTAMP WITH TIME ZONE,
                    duration_minutes INTEGER,
                    avg_speed REAL,
                    crossed BOOLEAN,
                    crossing_time TIMESTAMP WITH TIME ZONE,
                    FOREIGN KEY (mmsi) REFERENCES ships(mmsi)
                )
            ''')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_waiting_mmsi ON waiting_events(mmsi)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_waiting_start ON waiting_events(start_time)')

            # Daily statistics table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date DATE PRIMARY KEY,
                    total_crossings INTEGER,
                    avg_wind_speed REAL,
                    max_wind_gust REAL,
                    avg_wave_height REAL,
                    waiting_events INTEGER,
                    avg_waiting_time REAL
                )
            ''')
        else:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS weather (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    station TEXT,
                    wind_speed REAL,
                    wind_direction REAL,
                    wind_gust REAL,
                    wave_height REAL,
                    air_temperature REAL,
                    pressure REAL
                )
            ''')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_weather_timestamp ON weather(timestamp)')

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS waiting_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mmsi INTEGER,
                    zone TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    duration_minutes INTEGER,
                    avg_speed REAL,
                    crossed INTEGER,
                    crossing_time TEXT,
                    FOREIGN KEY (mmsi) REFERENCES ships(mmsi)
                )
            ''')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_waiting_mmsi ON waiting_events(mmsi)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_waiting_start ON waiting_events(start_time)')

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    total_crossings INTEGER,
                    avg_wind_speed REAL,
                    max_wind_gust REAL,
                    avg_wave_height REAL,
                    waiting_events INTEGER,
                    avg_waiting_time REAL
                )
            ''')

        self.conn.commit()

    def execute(self, query, params=None):
        """Execute a query"""
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)

    def fetchone(self):
        """Fetch one result"""
        return self.cursor.fetchone()

    def fetchall(self):
        """Fetch all results"""
        return self.cursor.fetchall()

    def commit(self):
        """Commit transaction"""
        self.conn.commit()

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


def get_access_token():
    """Authenticate with Barentswatch and get access token"""
    logger.info("Authenticating with Barentswatch...")

    data = {
        'client_id': CONFIG['client_id'],
        'client_secret': CONFIG['client_secret'],
        'scope': 'ais',
        'grant_type': 'client_credentials'
    }

    response = requests.post(
        CONFIG['auth_url'],
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )

    if response.status_code != 200:
        logger.error(f"Authentication failed: {response.status_code} - {response.text}")
        raise Exception(f"Authentication failed: {response.status_code} - {response.text}")

    token_data = response.json()
    logger.info("✓ Authenticated successfully")
    return token_data['access_token']


def get_mmsi_list(access_token, msgtimefrom, msgtimeto):
    """Get list of MMSIs in the Stadthavet area for given time range"""
    logger.info(f"Fetching MMSI list for {msgtimefrom} to {msgtimeto}...")

    lat_nw, lon_nw = CONFIG['area_nw']
    lat_se, lon_se = CONFIG['area_se']

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

    response = requests.post(CONFIG['mmsi_area_url'], headers=headers, json=data)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch MMSI list: {response.status_code} - {response.text}")

    mmsi_list = response.json()
    logger.info(f"✓ Found {len(mmsi_list)} MMSIs")
    return mmsi_list


def get_ship_type_name(ship_type):
    """Convert ship type code to human-readable name"""
    if ship_type is None:
        return 'Unknown'
    return SHIP_TYPES.get(ship_type, f'Type {ship_type}')


def ccw(A, B, C):
    """Check if three points are counter-clockwise"""
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])


def line_segments_intersect(A, B, C, D):
    """Check if line segment AB intersects with CD"""
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers using Haversine formula"""
    from math import radians, sin, cos, sqrt, atan2

    R = 6371  # Earth's radius in kilometers

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


def is_in_waiting_zone(lat, lon, zone_config):
    """Check if position is within a waiting zone"""
    distance = haversine_distance(
        lat, lon,
        zone_config['center_lat'],
        zone_config['center_lon']
    )
    return distance <= zone_config['radius_km']


def fetch_weather_data(start_time, end_time):
    """Fetch weather data from met.no Frost API"""
    # Frost API requires ISO format timestamps
    params = {
        'sources': CONFIG['weather_station'],
        'elements': 'wind_speed,wind_from_direction,max_wind_speed_of_gust(PT1H),air_temperature,air_pressure_at_sea_level',
        'referencetime': f"{start_time}/{end_time}"
    }

    # Frost API uses HTTP Basic Auth with client_id as username
    auth = None
    if CONFIG['met_client_id']:
        auth = (CONFIG['met_client_id'], '')  # client_id as username, empty password

    try:
        response = requests.get(CONFIG['met_api_url'], params=params, auth=auth, timeout=30)

        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Weather API error: {response.status_code}")
            if response.status_code == 401:
                logger.warning(f"  Authentication failed - check MET_CLIENT_ID")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch weather data: {e}")
        return None


def parse_weather_observations(weather_data):
    """Parse met.no weather data into simplified format"""
    if not weather_data or 'data' not in weather_data:
        return []

    observations = []
    for obs in weather_data.get('data', []):
        timestamp = obs.get('referenceTime')
        elements = {}

        for elem in obs.get('observations', []):
            elem_id = elem.get('elementId')
            value = elem.get('value')

            if elem_id == 'wind_speed':
                elements['wind_speed'] = value
            elif elem_id == 'wind_from_direction':
                elements['wind_direction'] = value
            elif elem_id == 'max_wind_speed_of_gust(PT1H)':
                elements['wind_gust'] = value
            elif elem_id == 'air_temperature':
                elements['air_temperature'] = value
            elif elem_id == 'air_pressure_at_sea_level':
                elements['pressure'] = value

        if timestamp and elements:
            observations.append({
                'timestamp': timestamp,
                'station': CONFIG['weather_station'],
                **elements
            })

    return observations


def fetch_and_store_track(db, access_token, mmsi):
    """Fetch track data for a single MMSI and store in database"""

    # Check if we already have recent data for this MMSI
    db.execute('SELECT COUNT(*) FROM positions WHERE mmsi = %s' if db.use_postgres
               else 'SELECT COUNT(*) FROM positions WHERE mmsi = ?', (mmsi,))

    if db.fetchone()[0] > 0:
        return False  # Already have data

    # Fetch track from API
    url = f"{CONFIG['track_url']}/{mmsi}"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    response = requests.get(url, headers=headers)

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

    # Store ship info
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
            INSERT OR REPLACE INTO ships (mmsi, name, ship_type, ship_type_name)
            VALUES (?, ?, ?, ?)
        ''', (mmsi, ship_name, ship_type, ship_type_name))

    # Process positions and check for crossings
    crossings_detected = 0
    prev_pos = None

    for pos in positions:
        lat = pos.get('latitude')
        lon = pos.get('longitude')
        timestamp = pos.get('msgtime')
        sog = pos.get('speedOverGround')
        cog = pos.get('courseOverGround')
        heading = pos.get('trueHeading')

        if lat is not None and lon is not None:
            # Store position
            db.execute('''
                INSERT INTO positions (mmsi, timestamp, latitude, longitude, sog, cog, heading)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''' if db.use_postgres else '''
                INSERT INTO positions (mmsi, timestamp, latitude, longitude, sog, cog, heading)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (mmsi, timestamp, lat, lon, sog, cog, heading))

            # Check for Stad crossing
            if prev_pos is not None:
                curr_point = (lon, lat)
                prev_point = (prev_pos['longitude'], prev_pos['latitude'])

                if line_segments_intersect(prev_point, curr_point,
                                         CONFIG['stad_line_start'],
                                         CONFIG['stad_line_end']):
                    direction = 'E->W' if prev_pos['longitude'] > lon else 'W->E'

                    db.execute('''
                        INSERT INTO crossings (mmsi, crossing_time, crossing_lat, crossing_lon, direction)
                        VALUES (%s, %s, %s, %s, %s)
                    ''' if db.use_postgres else '''
                        INSERT INTO crossings (mmsi, crossing_time, crossing_lat, crossing_lon, direction)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (mmsi, timestamp, lat, lon, direction))

                    crossings_detected += 1
                    logger.info(f"  *** CROSSING: {ship_name} ({direction}) at {timestamp}")

            prev_pos = pos

    db.commit()
    return True, ship_name, ship_type_name, len(positions), crossings_detected


def detect_waiting_events(db):
    """Analyze position data to detect ships waiting/loitering in zones"""
    logger.info("\nAnalyzing waiting events...")

    # Get all ships with positions
    db.execute('SELECT DISTINCT mmsi FROM positions')
    mmsi_list = [row[0] for row in db.fetchall()]

    waiting_events_detected = 0

    for mmsi in mmsi_list:
        # Get all positions for this ship, ordered by time
        db.execute('''
            SELECT timestamp, latitude, longitude, sog
            FROM positions
            WHERE mmsi = %s
            ORDER BY timestamp
        ''' if db.use_postgres else '''
            SELECT timestamp, latitude, longitude, sog
            FROM positions
            WHERE mmsi = ?
            ORDER BY timestamp
        ''', (mmsi,))

        positions = db.fetchall()
        if len(positions) < 2:
            continue

        # Track waiting periods
        waiting_start = None
        waiting_zone = None
        speeds_in_zone = []

        for i, pos in enumerate(positions):
            timestamp, lat, lon, sog = pos

            # Check if in waiting zone
            in_east = is_in_waiting_zone(lat, lon, CONFIG['waiting_zone_east'])
            in_west = is_in_waiting_zone(lat, lon, CONFIG['waiting_zone_west'])

            # Check speed threshold (if available)
            is_slow = sog is not None and sog < CONFIG['loitering_speed_threshold']

            if (in_east or in_west) and (sog is None or is_slow):
                # Ship is in waiting zone
                zone = 'east' if in_east else 'west'

                if waiting_start is None:
                    # Start of waiting period
                    waiting_start = timestamp
                    waiting_zone = zone
                    speeds_in_zone = [sog] if sog is not None else []
                elif zone == waiting_zone:
                    # Continuing to wait in same zone
                    if sog is not None:
                        speeds_in_zone.append(sog)
                else:
                    # Changed zones, reset
                    waiting_start = timestamp
                    waiting_zone = zone
                    speeds_in_zone = [sog] if sog is not None else []

            else:
                # Ship left waiting zone or sped up
                if waiting_start is not None:
                    # Calculate waiting duration
                    waiting_end = timestamp
                    try:
                        # Handle both string and datetime objects
                        if isinstance(waiting_start, str):
                            start_dt = datetime.fromisoformat(waiting_start.replace('Z', '+00:00'))
                        else:
                            start_dt = waiting_start

                        if isinstance(waiting_end, str):
                            end_dt = datetime.fromisoformat(waiting_end.replace('Z', '+00:00'))
                        else:
                            end_dt = waiting_end

                        duration_minutes = int((end_dt - start_dt).total_seconds() / 60)

                        # Check if duration meets threshold
                        if duration_minutes >= CONFIG['loitering_time_threshold']:
                            avg_speed = sum(speeds_in_zone) / len(speeds_in_zone) if speeds_in_zone else 0

                            # Check weather conditions during waiting period (if required)
                            weather_related = True
                            if CONFIG['require_bad_weather']:
                                db.execute('''
                                    SELECT AVG(wind_speed), MAX(wind_speed)
                                    FROM weather
                                    WHERE timestamp BETWEEN %s AND %s
                                ''' if db.use_postgres else '''
                                    SELECT AVG(wind_speed), MAX(wind_speed)
                                    FROM weather
                                    WHERE timestamp BETWEEN ? AND ?
                                ''', (waiting_start, waiting_end))

                                weather_row = db.fetchone()
                                if weather_row and weather_row[0] is not None:
                                    avg_wind = weather_row[0]
                                    max_wind = weather_row[1]
                                    # Only consider weather-related if wind exceeded threshold
                                    weather_related = max_wind >= CONFIG['wind_threshold_ms']
                                else:
                                    # No weather data available, skip this waiting event
                                    weather_related = False

                            if weather_related:
                                # Check if ship eventually crossed
                                db.execute('''
                                    SELECT crossing_time FROM crossings
                                    WHERE mmsi = %s AND crossing_time > %s
                                    ORDER BY crossing_time LIMIT 1
                                ''' if db.use_postgres else '''
                                    SELECT crossing_time FROM crossings
                                    WHERE mmsi = ? AND crossing_time > ?
                                    ORDER BY crossing_time LIMIT 1
                                ''', (mmsi, waiting_end))

                                crossing_row = db.fetchone()
                                crossed = crossing_row is not None
                                crossing_time = crossing_row[0] if crossed else None

                                # Store waiting event
                                db.execute('''
                                    INSERT INTO waiting_events
                                    (mmsi, zone, start_time, end_time, duration_minutes, avg_speed, crossed, crossing_time)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                ''' if db.use_postgres else '''
                                    INSERT INTO waiting_events
                                    (mmsi, zone, start_time, end_time, duration_minutes, avg_speed, crossed, crossing_time)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (mmsi, waiting_zone, waiting_start, waiting_end, duration_minutes,
                                      avg_speed, crossed, crossing_time))

                                waiting_events_detected += 1

                    except Exception as e:
                        logger.error(f"Error processing waiting event: {e}")

                # Reset waiting tracking
                waiting_start = None
                waiting_zone = None
                speeds_in_zone = []

    db.commit()
    logger.info(f"✓ Detected {waiting_events_detected} waiting events")
    return waiting_events_detected


def store_weather_data(db, start_time, end_time):
    """Fetch and store weather data for the time period"""
    logger.info(f"\nFetching weather data...")

    weather_data = fetch_weather_data(start_time, end_time)
    if not weather_data:
        logger.info("No weather data available")
        return 0

    observations = parse_weather_observations(weather_data)
    stored = 0

    for obs in observations:
        db.execute('''
            INSERT INTO weather (timestamp, station, wind_speed, wind_direction, wind_gust, air_temperature, pressure)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''' if db.use_postgres else '''
            INSERT INTO weather (timestamp, station, wind_speed, wind_direction, wind_gust, air_temperature, pressure)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (obs.get('timestamp'), obs.get('station'), obs.get('wind_speed'),
              obs.get('wind_direction'), obs.get('wind_gust'),
              obs.get('air_temperature'), obs.get('pressure')))
        stored += 1

    db.commit()
    logger.info(f"✓ Stored {stored} weather observations")
    return stored


def calculate_daily_stats(db):
    """Calculate and store daily statistics"""
    logger.info("\nCalculating daily statistics...")

    # Get date range from data
    db.execute('SELECT MIN(timestamp), MAX(timestamp) FROM positions')
    date_range = db.fetchone()
    if not date_range[0]:
        return

    # For each day, calculate stats
    db.execute('''
        SELECT DATE(crossing_time) as date,
               COUNT(*) as crossings
        FROM crossings
        GROUP BY DATE(crossing_time)
    ''' if db.use_postgres else '''
        SELECT DATE(crossing_time) as date,
               COUNT(*) as crossings
        FROM crossings
        GROUP BY DATE(crossing_time)
    ''')

    for row in db.fetchall():
        date, crossings = row

        # Get weather stats for this day
        db.execute('''
            SELECT AVG(wind_speed), MAX(wind_gust), AVG(wave_height)
            FROM weather
            WHERE DATE(timestamp) = %s
        ''' if db.use_postgres else '''
            SELECT AVG(wind_speed), MAX(wind_gust), AVG(wave_height)
            FROM weather
            WHERE DATE(timestamp) = ?
        ''', (date,))

        weather_row = db.fetchone()
        avg_wind = weather_row[0] if weather_row else None
        max_gust = weather_row[1] if weather_row else None
        avg_wave = weather_row[2] if weather_row else None

        # Get waiting stats for this day
        db.execute('''
            SELECT COUNT(*), AVG(duration_minutes)
            FROM waiting_events
            WHERE DATE(start_time) = %s
        ''' if db.use_postgres else '''
            SELECT COUNT(*), AVG(duration_minutes)
            FROM waiting_events
            WHERE DATE(start_time) = ?
        ''', (date,))

        waiting_row = db.fetchone()
        waiting_count = waiting_row[0] if waiting_row else 0
        avg_waiting = waiting_row[1] if waiting_row else None

        # Store daily stats
        db.execute('''
            INSERT INTO daily_stats
            (date, total_crossings, avg_wind_speed, max_wind_gust, avg_wave_height, waiting_events, avg_waiting_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE
            SET total_crossings = EXCLUDED.total_crossings,
                avg_wind_speed = EXCLUDED.avg_wind_speed,
                max_wind_gust = EXCLUDED.max_wind_gust,
                avg_wave_height = EXCLUDED.avg_wave_height,
                waiting_events = EXCLUDED.waiting_events,
                avg_waiting_time = EXCLUDED.avg_waiting_time
        ''' if db.use_postgres else '''
            INSERT OR REPLACE INTO daily_stats
            (date, total_crossings, avg_wind_speed, max_wind_gust, avg_wave_height, waiting_events, avg_waiting_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (date, crossings, avg_wind, max_gust, avg_wave, waiting_count, avg_waiting))

    db.commit()
    logger.info("✓ Daily statistics updated")


def print_summary(db):
    """Print summary statistics"""
    db.execute('SELECT COUNT(DISTINCT mmsi) FROM positions')
    ships_with_data = db.fetchone()[0]

    db.execute('SELECT COUNT(DISTINCT mmsi) FROM crossings')
    ships_crossed = db.fetchone()[0]

    db.execute('SELECT COUNT(*) FROM crossings')
    total_crossings = db.fetchone()[0]

    db.execute('SELECT COUNT(*) FROM waiting_events')
    total_waiting = db.fetchone()[0]

    db.execute('SELECT AVG(duration_minutes) FROM waiting_events')
    avg_wait_row = db.fetchone()
    avg_wait_time = avg_wait_row[0] if avg_wait_row[0] else 0

    logger.info(f'\n=== SUMMARY ===')
    logger.info(f'Ships with track data: {ships_with_data}')
    logger.info(f'Ships that crossed Stad: {ships_crossed}')
    logger.info(f'Total crossings: {total_crossings}')
    logger.info(f'Waiting events detected: {total_waiting}')
    if total_waiting > 0:
        logger.info(f'Average waiting time: {avg_wait_time:.1f} minutes ({avg_wait_time/60:.1f} hours)')

    if ships_crossed > 0:
        logger.info(f'\n=== SHIPS THAT CROSSED STAD ===')
        db.execute('''
            SELECT c.mmsi, s.name, s.ship_type_name, c.crossing_time, c.direction
            FROM crossings c
            JOIN ships s ON c.mmsi = s.mmsi
            ORDER BY c.crossing_time
        ''')

        for row in db.fetchall():
            logger.info(f'{row[0]:>10} | {row[1]:30} | {row[2]:20} | {row[3]} | {row[4]}')

    if total_waiting > 0:
        logger.info(f'\n=== WAITING EVENTS ===')
        db.execute('''
            SELECT w.mmsi, s.name, w.zone, w.start_time, w.duration_minutes, w.crossed
            FROM waiting_events w
            JOIN ships s ON w.mmsi = s.mmsi
            ORDER BY w.start_time
        ''')

        for row in db.fetchall():
            mmsi, name, zone, start_time, duration, crossed = row
            crossed_str = "✓ crossed" if crossed else "✗ did not cross"
            logger.info(f'{mmsi:>10} | {name:30} | {zone:5} | {duration:4}min | {crossed_str}')


def main():
    """Main execution"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Barentswatch AIS Data Collection - Stadthavet")
    logger.info(f"Database: {'PostgreSQL (render.com)' if USE_POSTGRES else 'SQLite (local)'}")
    logger.info(f"{'='*60}\n")

    # Initialize database
    db = Database()
    db.connect()
    db.create_tables()

    try:
        # Authenticate
        access_token = get_access_token()

        # Get MMSI list - use last 24-48 hours since that's what the API supports
        now = datetime.now(timezone.utc)
        msgtimefrom = (now - timedelta(hours=48)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        msgtimeto = now.strftime('%Y-%m-%dT%H:%M:%S+00:00')

        mmsi_list = get_mmsi_list(access_token, msgtimefrom, msgtimeto)

        # Fetch tracks for each MMSI
        logger.info(f"\nFetching tracks (this may take a while)...\n")

        processed = 0
        new_data = 0

        for i, mmsi in enumerate(mmsi_list):
            result = fetch_and_store_track(db, access_token, mmsi)

            if result is False:
                logger.info(f'[{i+1}/{len(mmsi_list)}] MMSI {mmsi} - already in database or no data')
            else:
                success, ship_name, ship_type, positions, crossings = result
                new_data += 1
                logger.info(f'[{i+1}/{len(mmsi_list)}] {ship_name} ({ship_type}) - {positions} positions')

            processed += 1

        logger.info(f"\n✓ Processed {processed} MMSIs ({new_data} new)")

        # Analyze waiting events
        detect_waiting_events(db)

        # Fetch and store weather data
        store_weather_data(db, msgtimefrom, msgtimeto)

        # Calculate daily statistics
        calculate_daily_stats(db)

        # Print summary
        print_summary(db)

    except Exception as e:
        logger.error(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        db.close()

    logger.info(f"\n{'='*60}")
    logger.info("Done!")
    logger.info(f"{'='*60}\n")


if __name__ == '__main__':
    main()
