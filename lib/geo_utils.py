"""
Geographical utility functions for Stadthavet AIS tracking
"""

from math import radians, sin, cos, sqrt, atan2


def ccw(A, B, C):
    """Check if three points are counter-clockwise"""
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])


def line_segments_intersect(A, B, C, D):
    """
    Check if line segment AB intersects with CD

    Args:
        A, B: Endpoints of first line segment (tuples of (x, y))
        C, D: Endpoints of second line segment (tuples of (x, y))

    Returns:
        bool: True if segments intersect, False otherwise
    """
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two points in kilometers using Haversine formula

    Args:
        lat1, lon1: First point coordinates (decimal degrees)
        lat2, lon2: Second point coordinates (decimal degrees)

    Returns:
        float: Distance in kilometers
    """
    R = 6371  # Earth's radius in kilometers

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


def is_in_waiting_zone(lat, lon, zone_config):
    """
    Check if position is within a waiting zone

    Args:
        lat, lon: Position coordinates (decimal degrees)
        zone_config: Dict with 'center_lat', 'center_lon', 'radius_km'

    Returns:
        bool: True if within zone, False otherwise
    """
    distance = haversine_distance(
        lat, lon,
        zone_config['center_lat'],
        zone_config['center_lon']
    )
    return distance <= zone_config['radius_km']


def distance_to_stad_line(lat, lon, stad_line_start, stad_line_end):
    """
    Calculate minimum distance from a point to the Stad crossing line.

    Args:
        lat, lon: Point coordinates (decimal degrees)
        stad_line_start: Tuple of (lon, lat) for line start
        stad_line_end: Tuple of (lon, lat) for line end

    Returns:
        float: Distance in kilometers (approximate)
    """
    # Get endpoints of Stad line
    lon1, lat1 = stad_line_start
    lon2, lat2 = stad_line_end

    # Calculate distance to both endpoints
    dist_to_start = haversine_distance(lat, lon, lat1, lon1)
    dist_to_end = haversine_distance(lat, lon, lat2, lon2)

    # Calculate distance to midpoint (approximate distance to line)
    mid_lat = (lat1 + lat2) / 2
    mid_lon = (lon1 + lon2) / 2
    dist_to_mid = haversine_distance(lat, lon, mid_lat, mid_lon)

    # Return minimum distance to line (simplified - uses closest of start/mid/end)
    return min(dist_to_start, dist_to_mid, dist_to_end)
