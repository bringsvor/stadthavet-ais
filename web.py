#!/usr/bin/env python3
"""
Web frontend for Stadthavet AIS data visualization
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
import markdown

# Load .env file if it exists
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

# Database detection
USE_POSTGRES = os.environ.get('RENDER') is not None or os.environ.get('DATABASE_URL') is not None

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_URL = os.environ.get('DATABASE_URL')
else:
    import sqlite3

app = Flask(__name__)

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Enable CORS - only allow requests from same origin in production
# In development, allow all origins for testing
allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*')
CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
logger.info(f"CORS enabled for origins: {allowed_origins}")

def get_db():
    """Get database connection"""
    try:
        if USE_POSTGRES:
            logger.debug("Connecting to PostgreSQL database")
            return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
        else:
            logger.debug("Connecting to SQLite database")
            conn = sqlite3.connect('stadthavet_ais.db')
            conn.row_factory = sqlite3.Row
            return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/about')
def about():
    """About page with markdown content"""
    about_file = Path(__file__).parent / 'ABOUT.md'
    if about_file.exists():
        with open(about_file, 'r', encoding='utf-8') as f:
            content = f.read()
            html_content = markdown.markdown(content, extensions=['extra', 'codehilite'])
    else:
        html_content = '<p>About page not found.</p>'

    return render_template('about.html', content=html_content)

@app.route('/api/stats')
def api_stats():
    """Get summary statistics"""
    conn = get_db()
    cursor = conn.cursor()

    # Overall stats
    cursor.execute('SELECT COUNT(DISTINCT mmsi) as count FROM ships')
    row = cursor.fetchone()
    total_ships = row['count'] if USE_POSTGRES else row[0]

    cursor.execute('SELECT COUNT(*) as count FROM crossings')
    row = cursor.fetchone()
    total_crossings = row['count'] if USE_POSTGRES else row[0]

    cursor.execute('SELECT COUNT(*) as count FROM waiting_events')
    row = cursor.fetchone()
    total_waiting = row['count'] if USE_POSTGRES else row[0]

    cursor.execute('SELECT AVG(duration_minutes) as avg FROM waiting_events')
    row = cursor.fetchone()
    avg_wait = (row['avg'] if USE_POSTGRES else row[0]) or 0

    cursor.execute('SELECT COUNT(*) as count FROM positions')
    row = cursor.fetchone()
    total_positions = row['count'] if USE_POSTGRES else row[0]

    # Recent activity (last 24 hours)
    cursor.execute('''
        SELECT COUNT(*) as count FROM crossings
        WHERE crossing_time > datetime('now', '-24 hours')
    ''' if not USE_POSTGRES else '''
        SELECT COUNT(*) as count FROM crossings
        WHERE crossing_time > NOW() - INTERVAL '24 hours'
    ''')
    row = cursor.fetchone()
    recent_crossings = row['count'] if USE_POSTGRES else row[0]

    # Get last data collection time (newest position timestamp)
    cursor.execute('SELECT MAX(timestamp) as max_time FROM positions')
    row = cursor.fetchone()
    last_data_time = row['max_time'] if USE_POSTGRES else row[0]

    # Top 10 ships by crossings
    cursor.execute('''
        SELECT s.mmsi, s.name, s.ship_type_name, COUNT(*) as crossing_count
        FROM crossings c
        JOIN ships s ON c.mmsi = s.mmsi
        GROUP BY s.mmsi, s.name, s.ship_type_name
        ORDER BY crossing_count DESC
        LIMIT 10
    ''')

    top_ships = []
    for row in cursor.fetchall():
        if USE_POSTGRES:
            top_ships.append({
                'mmsi': row['mmsi'],
                'name': row['name'],
                'ship_type': row['ship_type_name'],
                'crossings': row['crossing_count']
            })
        else:
            top_ships.append({
                'mmsi': row[0],
                'name': row[1],
                'ship_type': row[2],
                'crossings': row[3]
            })

    conn.close()

    return jsonify({
        'total_ships': total_ships,
        'total_crossings': total_crossings,
        'total_waiting_events': total_waiting,
        'avg_waiting_time_minutes': round(avg_wait, 1),
        'total_positions': total_positions,
        'recent_crossings_24h': recent_crossings,
        'last_data_collection': last_data_time,
        'top_ships_by_crossings': top_ships
    })

@app.route('/api/crossings')
def api_crossings():
    """Get all crossing events"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            c.mmsi,
            s.name,
            s.ship_type_name,
            c.crossing_time,
            c.crossing_lat,
            c.crossing_lon,
            c.direction
        FROM crossings c
        JOIN ships s ON c.mmsi = s.mmsi
        ORDER BY c.crossing_time DESC
        LIMIT 1000
    ''')

    crossings = []
    for row in cursor.fetchall():
        crossing = dict(row)
        # Handle null/empty ship names
        if not crossing.get('name') or crossing['name'].strip() == '':
            crossing['name'] = f"Ukjent ({crossing['mmsi']})"
        if not crossing.get('ship_type_name') or crossing['ship_type_name'] == 'Type 0':
            crossing['ship_type_name'] = 'Ukjent'
        crossings.append(crossing)

    conn.close()

    return jsonify(crossings)

@app.route('/api/waiting')
def api_waiting():
    """Get waiting events"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            w.mmsi,
            s.name,
            s.ship_type_name,
            w.zone,
            w.start_time,
            w.end_time,
            w.duration_minutes,
            w.avg_speed,
            w.crossed,
            w.crossing_time
        FROM waiting_events w
        JOIN ships s ON w.mmsi = s.mmsi
        ORDER BY w.start_time DESC
    ''')

    waiting = []
    for row in cursor.fetchall():
        event = dict(row)
        # Handle null/empty ship names
        if not event.get('name') or event['name'].strip() == '':
            event['name'] = f"Ukjent ({event['mmsi']})"
        if not event.get('ship_type_name') or event['ship_type_name'] == 'Type 0':
            event['ship_type_name'] = 'Ukjent'
        waiting.append(event)

    conn.close()

    return jsonify(waiting)

@app.route('/api/daily-stats')
def api_daily_stats():
    """Get daily statistics for charts"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            date,
            total_crossings,
            avg_wind_speed,
            max_wind_gust,
            waiting_events,
            avg_waiting_time
        FROM daily_stats
        ORDER BY date DESC
        LIMIT 90
    ''')

    stats = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Reverse to get chronological order for charts
    stats.reverse()

    return jsonify(stats)

@app.route('/api/active-ships')
def api_active_ships():
    """Get currently active ships with their latest position"""
    conn = get_db()
    cursor = conn.cursor()

    # Get latest position for each ship in the last 48 hours with last crossing info
    cursor.execute('''
        WITH latest_positions AS (
            SELECT
                p.mmsi,
                p.latitude,
                p.longitude,
                p.sog,
                p.cog,
                p.heading,
                p.timestamp,
                ROW_NUMBER() OVER (PARTITION BY p.mmsi ORDER BY p.timestamp DESC) as rn
            FROM positions p
            WHERE p.timestamp > datetime('now', '-48 hours')
        ),
        last_crossings AS (
            SELECT
                mmsi,
                MAX(crossing_time) as last_crossing_time,
                (SELECT direction FROM crossings c2
                 WHERE c2.mmsi = crossings.mmsi
                 ORDER BY crossing_time DESC LIMIT 1) as last_direction
            FROM crossings
            GROUP BY mmsi
        )
        SELECT
            s.mmsi,
            s.name,
            s.ship_type_name,
            s.destination,
            s.callsign,
            s.length,
            s.width,
            lp.latitude,
            lp.longitude,
            lp.sog,
            lp.cog,
            lp.heading,
            lp.timestamp,
            lc.last_crossing_time,
            lc.last_direction
        FROM latest_positions lp
        JOIN ships s ON lp.mmsi = s.mmsi
        LEFT JOIN last_crossings lc ON lp.mmsi = lc.mmsi
        WHERE lp.rn = 1
        ORDER BY lp.timestamp DESC
    ''' if not USE_POSTGRES else '''
        WITH latest_positions AS (
            SELECT
                p.mmsi,
                p.latitude,
                p.longitude,
                p.sog,
                p.cog,
                p.heading,
                p.timestamp,
                ROW_NUMBER() OVER (PARTITION BY p.mmsi ORDER BY p.timestamp DESC) as rn
            FROM positions p
            WHERE p.timestamp > NOW() - INTERVAL '48 hours'
        ),
        last_crossings AS (
            SELECT
                mmsi,
                MAX(crossing_time) as last_crossing_time,
                (SELECT direction FROM crossings c2
                 WHERE c2.mmsi = crossings.mmsi
                 ORDER BY crossing_time DESC LIMIT 1) as last_direction
            FROM crossings
            GROUP BY mmsi
        )
        SELECT
            s.mmsi,
            s.name,
            s.ship_type_name,
            s.destination,
            s.callsign,
            s.length,
            s.width,
            lp.latitude,
            lp.longitude,
            lp.sog,
            lp.cog,
            lp.heading,
            lp.timestamp,
            lc.last_crossing_time,
            lc.last_direction
        FROM latest_positions lp
        JOIN ships s ON lp.mmsi = s.mmsi
        LEFT JOIN last_crossings lc ON lp.mmsi = lc.mmsi
        WHERE lp.rn = 1
        ORDER BY lp.timestamp DESC
    ''')

    ships = []
    for row in cursor.fetchall():
        ship = dict(row)
        # Handle null/empty ship names
        if not ship.get('name') or ship['name'].strip() == '':
            ship['name'] = f"Ukjent ({ship['mmsi']})"
        # Handle unknown ship types
        if not ship.get('ship_type_name') or ship['ship_type_name'] == 'Type 0':
            ship['ship_type_name'] = 'Ukjent'
        ships.append(ship)

    conn.close()

    return jsonify(ships)

@app.route('/api/tracks/<int:mmsi>')
def api_tracks(mmsi):
    """Get position track for a specific ship"""
    conn = get_db()
    cursor = conn.cursor()

    # Get ship info
    cursor.execute('SELECT * FROM ships WHERE mmsi = %s' if USE_POSTGRES else 'SELECT * FROM ships WHERE mmsi = ?', (mmsi,))
    ship = dict(cursor.fetchone() or {})

    # Get positions
    cursor.execute('''
        SELECT timestamp, latitude, longitude, sog, cog, heading
        FROM positions
        WHERE mmsi = %s
        ORDER BY timestamp
        LIMIT 5000
    ''' if USE_POSTGRES else '''
        SELECT timestamp, latitude, longitude, sog, cog, heading
        FROM positions
        WHERE mmsi = ?
        ORDER BY timestamp
        LIMIT 5000
    ''', (mmsi,))

    positions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        'ship': ship,
        'positions': positions
    })

@app.route('/api/weather')
def api_weather():
    """Get recent weather data"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT timestamp, wind_speed, wind_direction, wind_gust, air_temperature, pressure
        FROM weather
        ORDER BY timestamp DESC
        LIMIT 1000
    ''')

    weather = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Reverse for chronological order
    weather.reverse()

    return jsonify(weather)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Debug mode only for local development
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
