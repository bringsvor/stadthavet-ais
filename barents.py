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
from datetime import datetime, timedelta, timezone

# Import from lib
from lib.config import CONFIG, USE_POSTGRES
from lib.database import Database
from lib.barentswatch_api import get_access_token, get_mmsi_list, fetch_and_store_track
from lib.weather import store_weather_data
from lib.geo_utils import is_in_waiting_zone

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Import database drivers (needed for Database class)
if USE_POSTGRES:
    import psycopg2
else:
    import sqlite3


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


def find_oldest_missing_date(db, lookback_days=14):
    """
    Find the oldest date in the last lookback_days that has no position data.

    Returns: datetime object for the oldest missing date, or None if all dates have data
    """
    now = datetime.now(timezone.utc)
    target_start = now - timedelta(days=lookback_days)

    # Get all distinct dates we have data for in the target period
    db.execute('''
        SELECT DISTINCT DATE(timestamp) as date
        FROM positions
        WHERE timestamp >= %s
        ORDER BY date
    ''' if db.use_postgres else '''
        SELECT DISTINCT DATE(timestamp) as date
        FROM positions
        WHERE timestamp >= ?
        ORDER BY date
    ''', (target_start,))

    existing_dates = set()
    for row in db.fetchall():
        date_val = row[0]
        if isinstance(date_val, str):
            date_val = datetime.fromisoformat(date_val).date()
        existing_dates.add(date_val)

    # Check each day from target_start to now
    current = target_start.date()
    today = now.date()

    while current <= today:
        if current not in existing_dates:
            # Found oldest missing date
            return datetime.combine(current, datetime.min.time()).replace(tzinfo=timezone.utc)
        current += timedelta(days=1)

    # All dates have data
    return None


def determine_fetch_timerange(db):
    """
    Determine what time range to fetch based on existing data.
    Strategy: Fetch recent 48h, AND backfill oldest missing date if found.

    Returns: (msgtimefrom, msgtimeto) as ISO format strings
    """
    now = datetime.now(timezone.utc)

    # Find oldest missing date in last 14 days (excluding last 2 days which we'll fetch anyway)
    missing_date = find_oldest_missing_date(db, lookback_days=14)

    # Check if missing date is older than 2 days (to avoid overlap with recent 48h fetch)
    two_days_ago = now - timedelta(days=2)

    if missing_date and missing_date < two_days_ago:
        # Backfill mode: fetch old missing date
        msgtimefrom = missing_date.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        msgtimeto = (missing_date + timedelta(hours=48)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        logger.info(f"Backfilling missing data for {missing_date.date()} (48h window)")
        return msgtimefrom, msgtimeto

    # Normal mode: fetch recent 48 hours to keep data current
    msgtimefrom = (now - timedelta(hours=48)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    msgtimeto = now.strftime('%Y-%m-%dT%H:%M:%S+00:00')
    logger.info(f"Fetching recent 48 hours (current data)")
    return msgtimefrom, msgtimeto


def main():
    """Main execution"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Barentswatch AIS Data Collection - Stadthavet")
    logger.info(f"Database: {'PostgreSQL (render.com)' if USE_POSTGRES else 'SQLite (local)'}")
    logger.info(f"{'='*60}\n")

    # Initialize database
    db = Database(CONFIG)
    db.connect()
    db.create_tables()

    try:
        # Authenticate
        access_token = get_access_token(CONFIG)

        # Determine time range to fetch (backfill or recent)
        msgtimefrom, msgtimeto = determine_fetch_timerange(db)

        mmsi_list = get_mmsi_list(access_token, msgtimefrom, msgtimeto, CONFIG)

        # Fetch tracks for each MMSI
        logger.info(f"\nFetching tracks (this may take a while)...\n")

        processed = 0
        new_data = 0

        for i, mmsi in enumerate(mmsi_list):
            result = fetch_and_store_track(db, access_token, mmsi, msgtimefrom, msgtimeto, CONFIG)

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
        store_weather_data(db, msgtimefrom, msgtimeto, CONFIG)

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
