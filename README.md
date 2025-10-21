# Barentswatch AIS Data Collection

Collects AIS (Automatic Identification System) data from the Barentswatch API for the Stadthavet area and detects ships crossing the Stad peninsula.

## Features

- Fetches AIS data for ships in Stadthavet (Norwegian coastal area)
- Stores ship positions, metadata, and timestamps
- Detects when ships cross the Stad peninsula line
- Supports both SQLite (local) and PostgreSQL (render.com)
- Designed to run as a cron job to build historical data

## Database Detection

The script automatically detects the environment:
- **Local**: Uses SQLite (`stadthavet_ais.db`)
- **render.com**: Uses PostgreSQL (via `DATABASE_URL` env var)

## Configuration

Set these environment variables (or use defaults):

```bash
# Required for render.com
DATABASE_URL=postgresql://...

# Barentswatch API credentials (optional, defaults available for testing)
BARENTSWATCH_CLIENT_ID=your_client_id
BARENTSWATCH_CLIENT_SECRET=your_client_secret
```

## Usage

### Local Development

```bash
pip install -r requirements.txt
python barents_refactored.py
```

### Deploy to render.com

1. Create a PostgreSQL database on render.com
2. Create a new Cron Job service
3. Set environment variables:
   - `DATABASE_URL` (auto-populated from database)
   - `BARENTSWATCH_CLIENT_ID` (your credentials)
   - `BARENTSWATCH_CLIENT_SECRET` (your credentials)
4. Set schedule: `0 */12 * * *` (every 12 hours)
5. Set build command: `pip install -r requirements.txt`
6. Set run command: `python barents_refactored.py`

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
- `sog` - Speed over ground
- `cog` - Course over ground
- `heading` - True heading

### Crossings Table
- `id` (PRIMARY KEY)
- `mmsi` - Foreign key to ships
- `crossing_time` - When the crossing occurred
- `crossing_lat`, `crossing_lon` - Crossing coordinates
- `direction` - E->W or W->E

## Limitations

- Barentswatch API only keeps data for **14 days**
- The `/trackslast24hours` endpoint only returns **last 24 hours** of detailed position data
- **Must run regularly (cron job)** to build up historical data
- Geographic coverage: Norwegian economic zone only

## Stad Peninsula Line

The crossing detection uses a line from:
- Start: 62.194513°N, 5.100380°E
- End: 62.442407°N, 4.342984°E

This represents the shortest crossing path of the Stad peninsula.
