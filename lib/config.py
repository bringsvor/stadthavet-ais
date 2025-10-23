"""
Configuration module for Stadthavet AIS tracking system
"""

import os
from pathlib import Path

# Load .env file if it exists (for local development)
env_path = Path(__file__).parent.parent / '.env'
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
    DB_URL = os.environ.get('DATABASE_URL')
else:
    DB_URL = None

# Configuration
CONFIG = {
    'client_id': os.environ.get('BARENTSWATCH_CLIENT_ID'),
    'client_secret': os.environ.get('BARENTSWATCH_CLIENT_SECRET'),
    'auth_url': 'https://id.barentswatch.no/connect/token',
    'mmsi_area_url': 'https://historic.ais.barentswatch.no/v1/historic/mmsiinarea',
    'track_url': 'https://historic.ais.barentswatch.no/v1/historic/tracks',

    # Stadthavet bounding box - reduced to ~50km around Stad line
    # Stad line runs from (62.19, 5.10) to (62.44, 4.34)
    'area_nw': (62.75, 4.0),   # (lat, lon) Northwest corner - ~50km margin
    'area_se': (61.85, 5.5),   # (lat, lon) Southeast corner - ~50km margin

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
    'postgres_url': DB_URL
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
    65: 'Passenger', 66: 'Passenger', 67: 'Passenger',
    68: 'Passenger', 69: 'Passenger',
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


def get_ship_type_name(ship_type):
    """Convert ship type code to human-readable name"""
    if ship_type is None:
        return 'Unknown'
    return SHIP_TYPES.get(ship_type, f'Type {ship_type}')
