"""
Find what fixture data exists in API
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.data.api_football_client import ApiFootballClient
from datetime import datetime, timedelta

api_client = ApiFootballClient()

print("=== Checking API for available fixtures ===\n")

# Try different date ranges
LEAGUE_IDS = [7, 3]  # BL1, PL

for comp_id in LEAGUE_IDS:
    print(f"\nLeague {comp_id}:")
    
    # Check last 7 days and next 14 days
    dates_to_check = [
        (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") 
        for i in range(7, 0, -1)
    ]
    dates_to_check += [
        (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d") 
        for i in range(1, 15)
    ]
    
    for date in dates_to_check[:5]:  # Just check first few
        try:
            response = api_client.client.get(
                f"{api_client.base_url}/fixtures",
                params={"league": comp_id, "date": date}
            )
            data = response.json()
            count = len(data.get("response", []))
            if count > 0:
                print(f"  {date}: {count} fixtures")
                for f in data["response"][:2]:
                    print(f"    {f['teams']['home']['name']} vs {f['teams']['away']['name']} | Status:{f['fixture']['status']['short']}")
        except Exception as e:
            print(f"  {date}: Error - {e}")

api_client.close()