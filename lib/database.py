"""
Database abstraction layer for Stadthavet AIS tracking system
Supports both SQLite (local development) and PostgreSQL (production)
"""

import os
import logging

logger = logging.getLogger(__name__)

# Database detection
USE_POSTGRES = os.environ.get('RENDER') is not None or os.environ.get('DATABASE_URL') is not None

# Always import both to avoid runtime errors
try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    import sqlite3
except ImportError:
    sqlite3 = None


class Database:
    """Database abstraction layer supporting both SQLite and PostgreSQL"""

    def __init__(self, config, use_postgres=USE_POSTGRES):
        """
        Initialize database connection

        Args:
            config: Configuration dict with 'sqlite_db' and 'postgres_url' keys
            use_postgres: If True, use PostgreSQL; otherwise SQLite
        """
        self.config = config
        self.use_postgres = use_postgres
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establish database connection"""
        if self.use_postgres:
            logger.info("Connecting to PostgreSQL...")
            self.conn = psycopg2.connect(self.config['postgres_url'])
            self.cursor = self.conn.cursor()
        else:
            logger.info(f"Connecting to SQLite: {self.config['sqlite_db']}")
            self.conn = sqlite3.connect(self.config['sqlite_db'])
            self.cursor = self.conn.cursor()

    def create_tables(self):
        """Create database tables if they don't exist"""
        if self.use_postgres:
            self._create_postgres_tables()
        else:
            self._create_sqlite_tables()

        self.conn.commit()

    def _create_postgres_tables(self):
        """Create PostgreSQL tables"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ships (
                mmsi BIGINT PRIMARY KEY,
                name TEXT,
                ship_type INTEGER,
                ship_type_name TEXT,
                destination TEXT,
                callsign TEXT,
                length REAL,
                width REAL
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
                FOREIGN KEY (mmsi) REFERENCES ships(mmsi),
                UNIQUE (mmsi, timestamp)
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
                FOREIGN KEY (mmsi) REFERENCES ships(mmsi),
                UNIQUE (mmsi, crossing_time)
            )
        ''')

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

        # Create indexes for performance
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_mmsi ON positions(mmsi)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_timestamp ON positions(timestamp)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_crossings_mmsi ON crossings(mmsi)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_weather_timestamp ON weather(timestamp)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_waiting_mmsi ON waiting_events(mmsi)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_waiting_start ON waiting_events(start_time)')

    def _create_sqlite_tables(self):
        """Create SQLite tables"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ships (
                mmsi INTEGER PRIMARY KEY,
                name TEXT,
                ship_type INTEGER,
                ship_type_name TEXT,
                destination TEXT,
                callsign TEXT,
                length REAL,
                width REAL
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

        # Create indexes
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_mmsi ON positions(mmsi)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_timestamp ON positions(timestamp)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_crossings_mmsi ON crossings(mmsi)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_weather_timestamp ON weather(timestamp)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_waiting_mmsi ON waiting_events(mmsi)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_waiting_start ON waiting_events(start_time)')

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
