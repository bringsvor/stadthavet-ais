#!/usr/bin/env python3
"""
Test to verify that ship info (length, width, callsign) is not overwritten
when processing ships that already have this data.

This test catches the critical bug where barents.py was calling get_ship_info()
for all ships every time, and when rate limiting kicked in, it would overwrite
existing length data with NULL values.
"""

import unittest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from lib.database import Database
from lib.barentswatch_api import fetch_and_store_track


class TestShipInfoPersistence(unittest.TestCase):
    """Test that ship info persists across multiple fetch_and_store_track calls"""

    def setUp(self):
        """Create a temporary SQLite database for testing"""
        self.db_fd, self.db_path = tempfile.mkstemp()

        # Create config with temp database and all required keys
        self.config = {
            'sqlite_db': self.db_path,
            'marinesia_key': 'test_key',
            'track_url': 'https://test.api/track',  # Not used in tests (mocked)
            'stad_line_start': (5.100380, 62.194513),
            'stad_line_end': (4.342984, 62.442407),
            'waiting_zone_east': {
                'center_lat': 62.25,
                'center_lon': 5.3,
                'radius_km': 10
            },
            'waiting_zone_west': {
                'center_lat': 62.25,
                'center_lon': 4.2,
                'radius_km': 10
            }
        }

        # Initialize database
        self.db = Database(self.config)
        self.db.connect()
        self.db.create_tables()

    def tearDown(self):
        """Clean up temporary database"""
        self.db.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    @patch('lib.barentswatch_api.get_ship_info')
    def test_ship_info_not_overwritten_on_second_fetch(self, mock_get_ship_info):
        """
        Test that when we process a ship twice, the second time doesn't overwrite
        the ship info (length, width, callsign) from the first time.

        This simulates:
        1. First run: Ship info is fetched successfully from Marinesia
        2. Second run: Same ship appears again, but we should NOT call Marinesia again
                       and we should NOT overwrite the existing data with NULL
        """

        test_mmsi = 257898600
        access_token = "test_token"

        # Mock the first call to return ship info
        mock_get_ship_info.return_value = {
            'length': 123.5,
            'width': 21.0,
            'callsign': 'LMRY'
        }

        # Mock positions data
        mock_positions = [
            {
                'mmsi': test_mmsi,
                'name': 'BERGSFJORD',
                'shipType': 60,
                'latitude': 62.0,
                'longitude': 5.0,
                'msgtime': '2024-10-24T10:00:00Z',
                'speedOverGround': 15.0,
                'courseOverGround': 180.0
            }
        ]

        # FIRST FETCH - Should call get_ship_info and store the data
        with patch('lib.barentswatch_api.requests.get') as mock_requests:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_positions
            mock_requests.return_value = mock_response

            result = fetch_and_store_track(
                self.db,
                access_token,
                test_mmsi,
                '2024-10-24T09:00:00Z',
                '2024-10-24T11:00:00Z',
                self.config
            )

        # Verify first fetch was successful
        self.assertIsNotNone(result)

        # Verify get_ship_info was called once
        self.assertEqual(mock_get_ship_info.call_count, 1)

        # Verify data was stored
        self.db.execute(
            'SELECT length, width, callsign, ship_info_fetched_at FROM ships WHERE mmsi = ?',
            (test_mmsi,)
        )
        row = self.db.fetchone()
        self.assertIsNotNone(row)
        length, width, callsign, fetched_at = row
        self.assertEqual(length, 123.5)
        self.assertEqual(width, 21.0)
        self.assertEqual(callsign, 'LMRY')
        self.assertIsNotNone(fetched_at)

        # Reset the mock
        mock_get_ship_info.reset_mock()

        # SECOND FETCH - Should NOT call get_ship_info again
        # Simulate that get_ship_info would return None (rate limited or API down)
        mock_get_ship_info.return_value = None

        with patch('lib.barentswatch_api.requests.get') as mock_requests:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_positions
            mock_requests.return_value = mock_response

            result = fetch_and_store_track(
                self.db,
                access_token,
                test_mmsi,
                '2024-10-24T11:00:00Z',
                '2024-10-24T13:00:00Z',
                self.config
            )

        # Verify second fetch was successful
        self.assertIsNotNone(result)

        # CRITICAL: Verify get_ship_info was NOT called (since we already have the data)
        self.assertEqual(mock_get_ship_info.call_count, 0,
                        "get_ship_info should NOT be called for ships we already have info for")

        # CRITICAL: Verify the original data is still intact
        self.db.execute(
            'SELECT length, width, callsign FROM ships WHERE mmsi = ?',
            (test_mmsi,)
        )
        row = self.db.fetchone()
        self.assertIsNotNone(row)
        length, width, callsign = row
        self.assertEqual(length, 123.5, "Length should NOT be overwritten with NULL")
        self.assertEqual(width, 21.0, "Width should NOT be overwritten with NULL")
        self.assertEqual(callsign, 'LMRY', "Callsign should NOT be overwritten with NULL")

    @patch('lib.barentswatch_api.get_ship_info')
    def test_new_ship_fetches_info(self, mock_get_ship_info):
        """
        Test that when we see a new ship (not in database), we DO fetch ship info
        """

        test_mmsi = 999999999
        access_token = "test_token"

        # Mock ship info response
        mock_get_ship_info.return_value = {
            'length': 50.0,
            'width': 10.0,
            'callsign': 'TEST'
        }

        # Mock positions data
        mock_positions = [
            {
                'mmsi': test_mmsi,
                'name': 'TEST SHIP',
                'shipType': 70,
                'latitude': 62.0,
                'longitude': 5.0,
                'msgtime': '2024-10-24T10:00:00Z',
                'speedOverGround': 10.0,
                'courseOverGround': 90.0
            }
        ]

        with patch('lib.barentswatch_api.requests.get') as mock_requests:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_positions
            mock_requests.return_value = mock_response

            result = fetch_and_store_track(
                self.db,
                access_token,
                test_mmsi,
                '2024-10-24T09:00:00Z',
                '2024-10-24T11:00:00Z',
                self.config
            )

        # Verify fetch was successful
        self.assertIsNotNone(result)

        # Verify get_ship_info WAS called for new ship
        self.assertEqual(mock_get_ship_info.call_count, 1,
                        "get_ship_info SHOULD be called for new ships")

        # Verify data was stored
        self.db.execute(
            'SELECT length, width, callsign FROM ships WHERE mmsi = ?',
            (test_mmsi,)
        )
        row = self.db.fetchone()
        self.assertIsNotNone(row)
        length, width, callsign = row
        self.assertEqual(length, 50.0)
        self.assertEqual(width, 10.0)
        self.assertEqual(callsign, 'TEST')


if __name__ == '__main__':
    unittest.main()
