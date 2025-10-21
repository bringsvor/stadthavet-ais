# Barentswatch AIS Data Collection & Weather Impact Analysis

Collects AIS (Automatic Identification System) data from the Barentswatch API for the Stadthavet area and analyzes maritime traffic patterns around the Stad peninsula to quantify the impact of weather on shipping.

## Features

### Core Data Collection
- Fetches AIS data for ships in Stadthavet (Norwegian coastal area)
- Stores ship positions, metadata, and timestamps
- Detects when ships cross the Stad peninsula line
- Supports both SQLite (local) and PostgreSQL (render.com)
- Designed to run as a cron job to build historical data

### Weather Impact Analysis
- **Loitering/Waiting Detection**: Identifies ships waiting in designated zones (likely due to bad weather)
- **Weather Data Integration**: Fetches historical weather data from met.no Frost API (wind speed, gusts, temperature, pressure)
- **Crossing Frequency Analysis**: Correlates daily crossing counts with weather conditions
- **Daily Statistics**: Tracks crossing rates, waiting times, and weather patterns over time

### Use Case: Stad Ship Tunnel Project

This tool enables quantitative analysis of:
- How many ships wait before crossing Stad
- Average waiting times during storms
- Correlation between reduced crossings and bad weather
- Ships that avoid Stad entirely during bad weather (route changes)
- Economic impact of weather-related delays (ship-hours lost)
- Evidence for/against the Stad Ship Tunnel (Stad Skipstunnel) project

## Database Detection

The script automatically detects the environment:
- **Local**: Uses SQLite (`stadthavet_ais.db`)
- **render.com**: Uses PostgreSQL (via `DATABASE_URL` or `RENDER` env var)

## Configuration

Set these environment variables (or use defaults):

```bash
# Required for render.com PostgreSQL
DATABASE_URL=postgresql://...

# Barentswatch API credentials
BARENTSWATCH_CLIENT_ID=your_client_id
BARENTSWATCH_CLIENT_SECRET=your_client_secret

# Optional: met.no Frost API client ID (for weather data)
# Register at https://frost.met.no/auth/requestCredentials.html
MET_CLIENT_ID=your_met_client_id
```

### Tuning Waiting Detection

Edit the `CONFIG` dict in `barents.py`:

```python
'loitering_speed_threshold': 3.0,  # knots - below this is considered stationary
'loitering_time_threshold': 120,   # minutes - minimum time to count as waiting
'waiting_zone_east': {'center_lat': 62.3, 'center_lon': 5.8, 'radius_km': 15},
'waiting_zone_west': {'center_lat': 62.3, 'center_lon': 4.8, 'radius_km': 15},
```

## Usage

### Local Development

```bash
pip install -r requirements.txt
python3 barents.py
```

### Deploy to render.com

1. Push code to GitHub
2. Create a PostgreSQL database on render.com
3. Create a new Cron Job service linked to your GitHub repo
4. Set environment variables:
   - `DATABASE_URL` (auto-populated when you link the database)
   - `BARENTSWATCH_CLIENT_ID`
   - `BARENTSWATCH_CLIENT_SECRET`
   - `MET_CLIENT_ID` (optional)
5. Set schedule: `0 */12 * * *` (every 12 hours recommended)
6. Set build command: `pip install -r requirements.txt`
7. Set run command: `python3 barents.py`

## Database Schema

### Ships Table
- `mmsi` (PRIMARY KEY) - Maritime Mobile Service Identity
- `name` - Ship name
- `ship_type` - AIS ship type code
- `ship_type_name` - Human-readable ship type

### Positions Table
- `id` (PRIMARY KEY)
- `mmsi` - Foreign key to ships
- `timestamp` - Position timestamp
- `latitude`, `longitude` - Position coordinates
- `sog` - Speed over ground (knots)
- `cog` - Course over ground (degrees)
- `heading` - True heading (degrees)

### Crossings Table
- `id` (PRIMARY KEY)
- `mmsi` - Foreign key to ships
- `crossing_time` - When the crossing occurred
- `crossing_lat`, `crossing_lon` - Crossing coordinates
- `direction` - E->W or W->E

### Waiting Events Table (NEW)
- `id` (PRIMARY KEY)
- `mmsi` - Foreign key to ships
- `zone` - 'east' or 'west' waiting zone
- `start_time`, `end_time` - Waiting period
- `duration_minutes` - How long the ship waited
- `avg_speed` - Average speed while waiting (should be low)
- `crossed` - Whether ship eventually crossed after waiting
- `crossing_time` - When crossing occurred (if crossed)

### Weather Table (NEW)
- `id` (PRIMARY KEY)
- `timestamp` - Observation time
- `station` - Weather station ID (Måløy: SN44560)
- `wind_speed` - m/s
- `wind_direction` - degrees
- `wind_gust` - m/s (max gust in last hour)
- `air_temperature` - °C
- `pressure` - hPa

### Daily Stats Table (NEW)
- `date` (PRIMARY KEY)
- `total_crossings` - Number of crossings that day
- `avg_wind_speed`, `max_wind_gust`, `avg_wave_height` - Weather conditions
- `waiting_events` - Number of waiting events detected
- `avg_waiting_time` - Average minutes waited

## Analysis Queries

### Ships that waited but didn't cross
```sql
SELECT s.name, w.duration_minutes, w.start_time
FROM waiting_events w
JOIN ships s ON w.mmsi = s.mmsi
WHERE w.crossed = FALSE
ORDER BY w.duration_minutes DESC;
```

### Correlation: crossings vs wind speed
```sql
SELECT d.date, d.total_crossings, d.avg_wind_speed, d.max_wind_gust
FROM daily_stats d
WHERE d.avg_wind_speed IS NOT NULL
ORDER BY d.date;
```

### Total ship-hours lost to waiting
```sql
SELECT
    SUM(duration_minutes) / 60.0 as total_hours_waited,
    AVG(duration_minutes) / 60.0 as avg_hours_per_event,
    COUNT(*) as total_events
FROM waiting_events;
```

## Limitations

- Barentswatch API only keeps data for **14 days**
- The `/trackslast24hours` endpoint only returns **last 24 hours** of detailed position data
- **Must run regularly (cron job)** to build up historical data over months/years
- Geographic coverage: Norwegian economic zone only
- Weather data from Måløy station (closest to Stad but not perfect)
- Waiting detection is heuristic-based (low speed + in zone = waiting)

## Stad Peninsula Line

The crossing detection uses a line from:
- Start: 62.194513°N, 5.100380°E
- End: 62.442407°N, 4.342984°E

This represents the shortest crossing path of the Stad peninsula.

## Waiting Zones

- **East zone**: Center at 62.3°N, 5.8°E, radius 15km (ships waiting to go west)
- **West zone**: Center at 62.3°N, 4.8°E, radius 15km (ships waiting to go east)

## Contributing

This is a research/analysis tool for studying maritime traffic impact at Stad. Contributions welcome for:
- Better waiting zone definitions
- Additional weather data sources
- Improved waiting detection algorithms
- Visualization tools
- Statistical analysis methods

## License

Open source - use freely for research and analysis.
