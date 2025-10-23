"""
Tests for geographical utility functions
"""

import pytest
from lib.geo_utils import (
    ccw,
    line_segments_intersect,
    haversine_distance,
    is_in_waiting_zone,
    distance_to_stad_line
)


class TestCCW:
    """Tests for counter-clockwise function"""

    def test_ccw_true(self):
        """Test counter-clockwise points"""
        A = (0, 0)
        B = (1, 0)
        C = (0, 1)
        assert ccw(A, B, C) is True

    def test_ccw_false(self):
        """Test clockwise points"""
        A = (0, 0)
        B = (0, 1)
        C = (1, 0)
        assert ccw(A, B, C) is False

    def test_ccw_collinear(self):
        """Test collinear points"""
        A = (0, 0)
        B = (1, 1)
        C = (2, 2)
        assert ccw(A, B, C) is False


class TestLineSegmentsIntersect:
    """Tests for line segment intersection"""

    def test_intersecting_lines(self):
        """Test clearly intersecting line segments"""
        A = (0, 0)
        B = (2, 2)
        C = (0, 2)
        D = (2, 0)
        assert line_segments_intersect(A, B, C, D) is True

    def test_non_intersecting_lines(self):
        """Test non-intersecting line segments"""
        A = (0, 0)
        B = (1, 0)
        C = (0, 1)
        D = (1, 1)
        assert line_segments_intersect(A, B, C, D) is False

    def test_parallel_lines(self):
        """Test parallel line segments"""
        A = (0, 0)
        B = (1, 0)
        C = (0, 1)
        D = (1, 1)
        assert line_segments_intersect(A, B, C, D) is False

    def test_stad_crossing_scenario(self):
        """Test realistic Stad crossing scenario"""
        # Stad line (simplified)
        stad_start = (5.1, 62.19)
        stad_end = (4.34, 62.44)

        # Ship path that crosses (going from east to west across the line)
        ship_start = (5.3, 62.25)  # East side
        ship_end = (4.1, 62.35)    # West side
        assert line_segments_intersect(stad_start, stad_end, ship_start, ship_end) is True

        # Ship path that doesn't cross
        ship_start2 = (5.2, 62.2)  # East side
        ship_end2 = (5.3, 62.3)    # Still east side
        assert line_segments_intersect(stad_start, stad_end, ship_start2, ship_end2) is False


class TestHaversineDistance:
    """Tests for Haversine distance calculation"""

    def test_zero_distance(self):
        """Test distance between same point"""
        dist = haversine_distance(62.0, 5.0, 62.0, 5.0)
        assert dist == 0.0

    def test_known_distance(self):
        """Test distance between known points (Oslo to Bergen approximately 300km)"""
        oslo_lat, oslo_lon = 59.9139, 10.7522
        bergen_lat, bergen_lon = 60.3913, 5.3221
        dist = haversine_distance(oslo_lat, oslo_lon, bergen_lat, bergen_lon)
        # Should be around 300km (allow 10% margin)
        assert 270 <= dist <= 330

    def test_stad_area_distance(self):
        """Test realistic distance in Stad area"""
        # Distance from Stad line start to end should be ~40-50km
        dist = haversine_distance(62.194513, 5.100380, 62.442407, 4.342984)
        assert 40 <= dist <= 60

    def test_symmetry(self):
        """Test that distance(A,B) == distance(B,A)"""
        lat1, lon1 = 62.0, 5.0
        lat2, lon2 = 62.5, 4.5
        dist1 = haversine_distance(lat1, lon1, lat2, lon2)
        dist2 = haversine_distance(lat2, lon2, lat1, lon1)
        assert abs(dist1 - dist2) < 0.001


class TestIsInWaitingZone:
    """Tests for waiting zone detection"""

    def test_inside_zone(self):
        """Test point inside waiting zone"""
        zone_config = {
            'center_lat': 62.25,
            'center_lon': 5.3,
            'radius_km': 10
        }
        # Point very close to center
        assert is_in_waiting_zone(62.25, 5.3, zone_config) is True
        # Point within radius
        assert is_in_waiting_zone(62.26, 5.31, zone_config) is True

    def test_outside_zone(self):
        """Test point outside waiting zone"""
        zone_config = {
            'center_lat': 62.25,
            'center_lon': 5.3,
            'radius_km': 10
        }
        # Point far away
        assert is_in_waiting_zone(63.0, 6.0, zone_config) is False

    def test_edge_of_zone(self):
        """Test point near edge of zone"""
        zone_config = {
            'center_lat': 62.0,
            'center_lon': 5.0,
            'radius_km': 10
        }
        # Point approximately 10km away (on edge)
        # Using simple approximation: 1 degree lat ≈ 111km
        lat_offset = 10 / 111
        # Should be on the edge (within small margin)
        dist = haversine_distance(62.0, 5.0, 62.0 + lat_offset, 5.0)
        assert 9 <= dist <= 11


class TestDistanceToStadLine:
    """Tests for distance to Stad line calculation"""

    def test_distance_to_start_point(self):
        """Test distance when at line start point"""
        stad_start = (5.100380, 62.194513)
        stad_end = (4.342984, 62.442407)
        lat, lon = 62.194513, 5.100380  # At start point
        dist = distance_to_stad_line(lat, lon, stad_start, stad_end)
        assert dist < 0.1  # Should be very close to 0

    def test_distance_to_end_point(self):
        """Test distance when at line end point"""
        stad_start = (5.100380, 62.194513)
        stad_end = (4.342984, 62.442407)
        lat, lon = 62.442407, 4.342984  # At end point
        dist = distance_to_stad_line(lat, lon, stad_start, stad_end)
        assert dist < 0.1  # Should be very close to 0

    def test_distance_far_from_line(self):
        """Test distance when far from line"""
        stad_start = (5.100380, 62.194513)
        stad_end = (4.342984, 62.442407)
        lat, lon = 63.0, 6.0  # Far away
        dist = distance_to_stad_line(lat, lon, stad_start, stad_end)
        assert dist > 50  # Should be more than 50km

    def test_distance_near_midpoint(self):
        """Test distance calculation uses midpoint"""
        stad_start = (5.100380, 62.194513)
        stad_end = (4.342984, 62.442407)
        # Calculate midpoint
        mid_lat = (62.194513 + 62.442407) / 2
        mid_lon = (5.100380 + 4.342984) / 2
        # Point at midpoint should have distance close to 0
        dist = distance_to_stad_line(mid_lat, mid_lon, stad_start, stad_end)
        assert dist < 1  # Should be very close
