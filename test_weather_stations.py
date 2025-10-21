#!/usr/bin/env python3
"""Test script to find weather stations near Stad"""

import requests
import os
from pathlib import Path

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

# Search for stations near Stad (62.3N, 5.0E)
params = {
    'geometry': 'nearest(POINT(5.0 62.3))',
    'nearestmaxcount': 10
}

auth = (client_id, '') if client_id else None

response = requests.get('https://frost.met.no/sources/v0.jsonld', params=params, auth=auth)

if response.status_code == 200:
    data = response.json()
    print(f"Found {len(data.get('data', []))} stations near Stad:\n")

    for station in data.get('data', []):
        name = station.get('name', 'Unknown')
        station_id = station.get('id', 'Unknown')
        lat = station.get('geometry', {}).get('coordinates', [None, None])[1]
        lon = station.get('geometry', {}).get('coordinates', [None, None])[0]

        print(f"  {name} ({station_id})")
        print(f"    Location: {lat}°N, {lon}°E")
        print(f"    Valid from: {station.get('validFrom', 'N/A')}")
        print(f"    Valid to: {station.get('validTo', 'ongoing')}")
        print()
else:
    print(f"Error {response.status_code}: {response.text}")
