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
import requests
from datetime import datetime, timedelta, timezone

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
    'client_id': os.environ.get('BARENTSWATCH_CLIENT_ID', 'bringsvor@bringsvor.com:tunell1'),
    'client_secret': os.environ.get('BARENTSWATCH_CLIENT_SECRET', 'hemmelegvemmeleg'),
    'auth_url': 'https://id.barentswatch.no/connect/token',
    'mmsi_area_url': 'https://historic.ais.barentswatch.no/v1/historic/mmsiinarea',
    'track_url': 'https://historic.ais.barentswatch.no/v1/historic/trackslast24hours',

    # Stadthavet bounding box
    'area_nw': (62.8, 4.5),  # (lat, lon) Northwest corner
    'area_se': (61.8, 7.0),  # (lat, lon) Southeast corner

    # Stad peninsula crossing line
    'stad_line_start': (5.100380, 62.194513),  # (lon, lat)
    'stad_line_end': (4.342984, 62.442407),

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
            print(f"Connecting to PostgreSQL...")
            self.conn = psycopg2.connect(CONFIG['postgres_url'])
            self.cursor = self.conn.cursor()
        else:
            print(f"Connecting to SQLite: {CONFIG['sqlite_db']}")
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
    print("Authenticating with Barentswatch...")

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
        raise Exception(f"Authentication failed: {response.status_code} - {response.text}")

    token_data = response.json()
    print("✓ Authenticated successfully")
    return token_data['access_token']


def get_mmsi_list(access_token, msgtimefrom, msgtimeto):
    """Get list of MMSIs in the Stadthavet area for given time range"""
    print(f"Fetching MMSI list for {msgtimefrom} to {msgtimeto}...")

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
    print(f"✓ Found {len(mmsi_list)} MMSIs")
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
    ship_name = positions[0].get('name', 'Unknown')
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
                    print(f"  *** CROSSING: {ship_name} ({direction}) at {timestamp}")

            prev_pos = pos

    db.commit()
    return True, ship_name, ship_type_name, len(positions), crossings_detected


def print_summary(db):
    """Print summary statistics"""
    db.execute('SELECT COUNT(DISTINCT mmsi) FROM positions')
    ships_with_data = db.fetchone()[0]

    db.execute('SELECT COUNT(DISTINCT mmsi) FROM crossings')
    ships_crossed = db.fetchone()[0]

    db.execute('SELECT COUNT(*) FROM crossings')
    total_crossings = db.fetchone()[0]

    print(f'\n=== SUMMARY ===')
    print(f'Ships with track data: {ships_with_data}')
    print(f'Ships that crossed Stad: {ships_crossed}')
    print(f'Total crossings: {total_crossings}')

    if ships_crossed > 0:
        print(f'\n=== SHIPS THAT CROSSED STAD ===')
        db.execute('''
            SELECT c.mmsi, s.name, s.ship_type_name, c.crossing_time, c.direction
            FROM crossings c
            JOIN ships s ON c.mmsi = s.mmsi
            ORDER BY c.crossing_time
        ''')

        for row in db.fetchall():
            print(f'{row[0]:>10} | {row[1]:30} | {row[2]:20} | {row[3]} | {row[4]}')


def main():
    """Main execution"""
    print(f"\n{'='*60}")
    print(f"Barentswatch AIS Data Collection - Stadthavet")
    print(f"Database: {'PostgreSQL (render.com)' if USE_POSTGRES else 'SQLite (local)'}")
    print(f"{'='*60}\n")

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
        print(f"\nFetching tracks (this may take a while)...\n")

        processed = 0
        new_data = 0

        for i, mmsi in enumerate(mmsi_list):
            result = fetch_and_store_track(db, access_token, mmsi)

            if result is False:
                print(f'[{i+1}/{len(mmsi_list)}] MMSI {mmsi} - already in database or no data')
            else:
                success, ship_name, ship_type, positions, crossings = result
                new_data += 1
                print(f'[{i+1}/{len(mmsi_list)}] {ship_name} ({ship_type}) - {positions} positions')

            processed += 1

        print(f"\n✓ Processed {processed} MMSIs ({new_data} new)")

        # Print summary
        print_summary(db)

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        db.close()

    print(f"\n{'='*60}")
    print("Done!")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
