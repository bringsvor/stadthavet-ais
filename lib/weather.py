"""
Weather data integration from met.no Frost API
"""

import logging
import requests

logger = logging.getLogger(__name__)


def fetch_weather_data(start_time, end_time, config):
    """
    Fetch weather data from met.no Frost API

    Args:
        start_time: Start time (ISO format string)
        end_time: End time (ISO format string)
        config: Configuration dict with weather API settings

    Returns:
        dict: Weather data JSON or None if failed
    """
    # Frost API requires ISO format timestamps
    params = {
        'sources': config['weather_station'],
        'elements': 'wind_speed,wind_from_direction,max_wind_speed_of_gust(PT1H),air_temperature,air_pressure_at_sea_level',
        'referencetime': f"{start_time}/{end_time}"
    }

    # Frost API uses HTTP Basic Auth with client_id as username
    auth = None
    if config['met_client_id']:
        auth = (config['met_client_id'], '')  # client_id as username, empty password

    try:
        response = requests.get(config['met_api_url'], params=params, auth=auth, timeout=30)

        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Weather API error: {response.status_code}")
            if response.status_code == 401:
                logger.warning("  Authentication failed - check MET_CLIENT_ID")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch weather data: {e}")
        return None


def parse_weather_observations(weather_data, station_id):
    """
    Parse met.no weather data into simplified format

    Args:
        weather_data: Raw weather data from Frost API
        station_id: Weather station ID

    Returns:
        list: List of observation dicts with timestamp and weather elements
    """
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
                'station': station_id,
                **elements
            })

    return observations


def store_weather_data(db, start_time, end_time, config):
    """
    Fetch and store weather data in database

    Args:
        db: Database instance
        start_time: Start time (ISO format string)
        end_time: End time (ISO format string)
        config: Configuration dict with weather settings

    Returns:
        int: Number of observations stored
    """
    logger.info(f"Fetching weather data for {start_time} to {end_time}...")

    weather_data = fetch_weather_data(start_time, end_time, config)
    if not weather_data:
        logger.warning("No weather data returned")
        return 0

    observations = parse_weather_observations(weather_data, config['weather_station'])
    logger.info(f"✓ Got {len(observations)} weather observations")

    # Store in database
    stored = 0
    for obs in observations:
        if db.use_postgres:
            db.execute('''
                INSERT INTO weather (timestamp, station, wind_speed, wind_direction, wind_gust, air_temperature, pressure)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            ''', (obs['timestamp'], obs['station'],
                  obs.get('wind_speed'), obs.get('wind_direction'),
                  obs.get('wind_gust'), obs.get('air_temperature'),
                  obs.get('pressure')))
        else:
            db.execute('''
                INSERT OR IGNORE INTO weather (timestamp, station, wind_speed, wind_direction, wind_gust, air_temperature, pressure)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (obs['timestamp'], obs['station'],
                  obs.get('wind_speed'), obs.get('wind_direction'),
                  obs.get('wind_gust'), obs.get('air_temperature'),
                  obs.get('pressure')))
        stored += 1

    db.commit()
    logger.info(f"✓ Stored {stored} weather observations")
    return stored
