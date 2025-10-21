#!/usr/bin/env python3
"""Check available elements for weather stations near Stad"""

import requests
import os
from pathlib import Path
from datetime import datetime, timedelta

# Load .env
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

client_id = os.environ.get('MET_CLIENT_ID', '')
auth = (client_id, '') if client_id else None

# Test three stations
stations = [
    ('SN59800', 'Svinøy Fyr'),
    ('SN59450', 'Stadlandet'),
    ('SN59110', 'Kråkenes'),
]

end_time = datetime.utcnow()
start_time = end_time - timedelta(hours=24)

for station_id, station_name in stations:
    print(f"\n{'='*60}")
    print(f"{station_name} ({station_id})")
    print(f"{'='*60}")

    params = {
        'sources': station_id,
        'referencetime': f"{start_time.strftime('%Y-%m-%d')}/{end_time.strftime('%Y-%m-%d')}",
    }

    response = requests.get('https://frost.met.no/observations/availableTimeSeries/v0.jsonld',
                           params=params, auth=auth)

    if response.status_code == 200:
        data = response.json()
        elements = set()
        for series in data.get('data', []):
            elem_id = series.get('elementId', 'Unknown')
            elements.add(elem_id)

        print(f"\nTilgjengelege element ({len(elements)}):")
        for elem in sorted(elements):
            print(f"  ✓ {elem}")

        # Check specifically for what we want
        important = ['wind_speed', 'max(wind_speed_of_gust', 'sea_surface_wave_height', 'air_temperature']
        print(f"\nViktige element:")
        for imp in important:
            found = [e for e in elements if imp in e]
            if found:
                print(f"  ✓ {', '.join(found)}")
            else:
                print(f"  ✗ {imp} (ikkje funne)")
    else:
        print(f"Error {response.status_code}")
