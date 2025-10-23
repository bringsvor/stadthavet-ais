"""
Tests for database module
"""

import pytest
import tempfile
import os
from lib.database import Database


@pytest.fixture
def sqlite_config():
    """Create temporary SQLite database for testing"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f:
        db_path = f.name

    config = {
        'sqlite_db': db_path,
        'postgres_url': None
    }

    yield config

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestDatabase:
    """Tests for Database class"""

    def test_sqlite_connection(self, sqlite_config):
        """Test SQLite database connection"""
        db = Database(sqlite_config, use_postgres=False)
        db.connect()
        assert db.conn is not None
        assert db.cursor is not None
        db.close()

    def test_create_tables(self, sqlite_config):
        """Test creating all tables"""
        db = Database(sqlite_config, use_postgres=False)
        db.connect()
        db.create_tables()

        # Check that tables exist
        db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in db.fetchall()]

        assert 'ships' in tables
        assert 'positions' in tables
        assert 'crossings' in tables
        assert 'weather' in tables
        assert 'waiting_events' in tables
        assert 'daily_stats' in tables

        db.close()

    def test_ships_table_columns(self, sqlite_config):
        """Test ships table has correct columns"""
        db = Database(sqlite_config, use_postgres=False)
        db.connect()
        db.create_tables()

        # Check ships table schema
        db.execute("PRAGMA table_info(ships)")
        columns = {row[1] for row in db.fetchall()}

        assert 'mmsi' in columns
        assert 'name' in columns
        assert 'ship_type' in columns
        assert 'ship_type_name' in columns
        assert 'destination' in columns
        assert 'callsign' in columns
        assert 'length' in columns
        assert 'width' in columns

        db.close()

    def test_insert_ship(self, sqlite_config):
        """Test inserting a ship record"""
        db = Database(sqlite_config, use_postgres=False)
        db.connect()
        db.create_tables()

        # Insert a ship
        db.execute('''
            INSERT INTO ships (mmsi, name, ship_type, ship_type_name, destination, callsign, length, width)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (123456789, 'Test Ship', 70, 'Cargo', 'Bergen', 'TEST1', 150.0, 25.0))
        db.commit()

        # Verify inserted
        db.execute('SELECT * FROM ships WHERE mmsi = ?', (123456789,))
        ship = db.fetchone()

        assert ship is not None
        assert ship[0] == 123456789  # mmsi
        assert ship[1] == 'Test Ship'  # name
        assert ship[4] == 'Bergen'  # destination

        db.close()

    def test_insert_position(self, sqlite_config):
        """Test inserting a position record"""
        db = Database(sqlite_config, use_postgres=False)
        db.connect()
        db.create_tables()

        # Insert ship first
        db.execute('''
            INSERT INTO ships (mmsi, name, ship_type, ship_type_name)
            VALUES (?, ?, ?, ?)
        ''', (123456789, 'Test Ship', 70, 'Cargo'))

        # Insert position
        db.execute('''
            INSERT INTO positions (mmsi, timestamp, latitude, longitude, sog, cog, heading)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (123456789, '2025-10-23T10:00:00Z', 62.3, 5.1, 12.5, 180, 175))
        db.commit()

        # Verify
        db.execute('SELECT * FROM positions WHERE mmsi = ?', (123456789,))
        pos = db.fetchone()

        assert pos is not None
        assert pos[1] == 123456789  # mmsi
        assert pos[3] == 62.3  # latitude
        assert pos[4] == 5.1  # longitude

        db.close()

    def test_insert_crossing(self, sqlite_config):
        """Test inserting a crossing record"""
        db = Database(sqlite_config, use_postgres=False)
        db.connect()
        db.create_tables()

        # Insert ship first
        db.execute('''
            INSERT INTO ships (mmsi, name, ship_type, ship_type_name)
            VALUES (?, ?, ?, ?)
        ''', (123456789, 'Test Ship', 70, 'Cargo'))

        # Insert crossing
        db.execute('''
            INSERT INTO crossings (mmsi, crossing_time, crossing_lat, crossing_lon, direction)
            VALUES (?, ?, ?, ?, ?)
        ''', (123456789, '2025-10-23T10:00:00Z', 62.3, 4.7, 'Westbound'))
        db.commit()

        # Verify
        db.execute('SELECT * FROM crossings WHERE mmsi = ?', (123456789,))
        crossing = db.fetchone()

        assert crossing is not None
        assert crossing[1] == 123456789  # mmsi
        assert crossing[5] == 'Westbound'  # direction

        db.close()

    def test_indexes_created(self, sqlite_config):
        """Test that indexes are created"""
        db = Database(sqlite_config, use_postgres=False)
        db.connect()
        db.create_tables()

        # Check that indexes exist
        db.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in db.fetchall()]

        assert 'idx_positions_mmsi' in indexes
        assert 'idx_positions_timestamp' in indexes
        assert 'idx_crossings_mmsi' in indexes
        assert 'idx_weather_timestamp' in indexes

        db.close()
