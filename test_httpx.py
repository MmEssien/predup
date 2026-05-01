from pathlib import Path
from dotenv import load_dotenv
_root = Path(__file__).parent
load_dotenv(_root / ".env")

import os
os.environ['DATABASE_URL'] = 'sqlite:///predup.db'

import httpx

print("=== Testing httpx directly ===")
api_key = os.getenv("FOOTBALL_DATA_KEY")
print(f"API Key present: {bool(api_key)}")
if api_key:
    print(f"API Key: {api_key[:10]}...")

try:
    client = httpx.Client(
        headers={"X-Auth-Token": api_key},
        timeout=30
    )
    resp = client.get("https://api.football-data.org/v4/competitions")
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Competitions: {len(data.get('competitions', []))}")
    else:
        print(f"Error: {resp.text[:200]}")
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()