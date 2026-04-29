"""Test API connections"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


def test_football_data():
    """Test football-data.org API"""
    from src.data.api_client import FootballAPIClient

    client = FootballAPIClient(
        api_key=os.getenv("FOOTBALL_DATA_KEY"),
        base_url=os.getenv("FOOTBALL_DATA_URL", "https://api.football-data-org/v4")
    )

    try:
        data = client.get_competitions()
        print(f"✓ football-data.org: {len(data.get('competitions', []))} competitions")
        return True
    except Exception as e:
        print(f"✗ football-data.org: {e}")
        return False
    finally:
        client.close()


def test_api_football():
    """Test api-football.com API"""
    from src.data.api_football_client import ApiFootballClient

    client = ApiFootballClient(
        api_key=os.getenv("API_FOOTBALL_COM_KEY"),
        base_url=os.getenv("API_FOOTBALL_COM_URL", "https://v3.football.api-sports.io")
    )

    try:
        data = client.get_leagues()
        print(f"✓ api-football.com: {len(data.get('response', []))} leagues")
        return True
    except Exception as e:
        print(f"✗ api-football.com: {e}")
        return False
    finally:
        client.close()


def test_weather():
    """Test Open-Meteo API"""
    from src.data.weather_client import WeatherAPIClient

    client = WeatherAPIClient(
        base_url=os.getenv("WEATHER_API_BASE_URL", "https://api.open-meteo.com/v1")
    )

    try:
        data = client.get_forecast(51.5074, -0.1278)
        print(f"✓ Open-Meteo: {data.get('latitude')}, {data.get('longitude')}")
        return True
    except Exception as e:
        print(f"✗ Open-Meteo: {e}")
        return False
    finally:
        client.close()


def test_odds():
    """Test the-odds-api.com"""
    from src.data.odds_client import OddsAPIClient

    client = OddsAPIClient(api_key=os.getenv("ODDS_API_KEY"))

    try:
        credits = client.get_credits_remaining()
        data = client.get_odds("soccer_england_premier_league")
        print(f"✓ the-odds-api.com: {len(data.get('data', []))} events, {credits} credits")
        return True
    except Exception as e:
        print(f"✗ the-odds-api.com: {e}")
        return False
    finally:
        client.close()


def test_unified_client():
    """Test unified client"""
    from src.data.unified_client import get_unified_client

    client = get_unified_client()
    try:
        competitions = client.get_competitions()
        fixtures = client.get_upcoming_fixtures(days_ahead=1)
        print(f"✓ Unified Client: {len(competitions)} comps, {len(fixtures)} fixtures")
        return True
    except Exception as e:
        print(f"✗ Unified Client: {e}")
        return False
    finally:
        client.close()


def main():
    print("Testing API Connections...\n")

    results = {
        "football-data.org": test_football_data(),
        "api-football.com": test_api_football(),
        "Open-Meteo (Weather)": test_weather(),
        "the-odds-api.com": test_odds(),
        "Unified Client": test_unified_client(),
    }

    print(f"\n{'='*40}")
    passed = sum(results.values())
    total = len(results)
    print(f"Results: {passed}/{total} APIs working")

    if passed == total:
        print("All APIs connected successfully!")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()