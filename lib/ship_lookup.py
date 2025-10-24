"""
Ship lookup integration using Marinesia API for vessel static data
"""

import logging
import requests
import os

logger = logging.getLogger(__name__)


def get_ship_info(mmsi, config):
    """
    Fetch ship static data (length, width, etc.) from Marinesia API

    Args:
        mmsi: Ship MMSI number
        config: Configuration dict (not used currently, but kept for consistency)

    Returns:
        dict: Ship info with keys: length, width, imo, callsign, ship_type, country
              or None if fetch failed
    """
    api_key = os.environ.get('MARINESIA_KEY')

    if not api_key:
        logger.warning("MARINESIA_KEY not set in environment, skipping ship lookup")
        return None

    url = f'https://api.marinesia.com/api/v1/vessel/{mmsi}/profile'
    params = {'key': api_key}

    try:
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            result = response.json()

            if result.get('error') is False and result.get('data'):
                data = result['data']

                # Extract relevant fields
                ship_info = {
                    'length': data.get('length'),
                    'width': data.get('width'),
                    'imo': data.get('imo'),
                    'callsign': data.get('callsign'),
                    'country': data.get('country'),
                    'dimension_a': data.get('dimension_a'),
                    'dimension_b': data.get('dimension_b'),
                    'dimension_c': data.get('dimension_c'),
                    'dimension_d': data.get('dimension_d'),
                }

                logger.debug(f"Ship info for MMSI {mmsi}: length={ship_info.get('length')}m, width={ship_info.get('width')}m")
                return ship_info
            else:
                logger.debug(f"No ship data found for MMSI {mmsi}")
                return None

        elif response.status_code == 404:
            logger.debug(f"Ship not found in Marinesia: MMSI {mmsi}")
            return None
        else:
            logger.warning(f"Marinesia API error for MMSI {mmsi}: {response.status_code}")
            return None

    except requests.Timeout:
        logger.warning(f"Marinesia API timeout for MMSI {mmsi}")
        return None
    except Exception as e:
        logger.error(f"Error fetching ship info for MMSI {mmsi}: {e}")
        return None
