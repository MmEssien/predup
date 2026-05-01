import os
import httpx

key = os.getenv("ODDS_API_KEY")
print(f"KEY_SET: {bool(key)}")
print(f"KEY_LEN: {len(key) if key else 0}")

try:
    print("Making request to Odds API...")
    r = httpx.get(
        "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds",
        params={
            "apiKey": key,
            "regions": "us",
            "markets": "h2h"
        }
    )
    print(f"STATUS: {r.status_code}")
    data = r.json()
    print(f"DATA_LEN: {len(data)}")
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        print(f"FIRST_KEYS: {list(first.keys())}")
        print(f"HAS_BOOKMAKERS: {'bookmakers' in first}")
        if 'bookmakers' in first and len(first['bookmakers']) > 0:
            bm = first['bookmakers'][0]
            print(f"FIRST_BOOKMAKER: {bm.get('title')}")
            if 'markets' in bm and len(bm['markets']) > 0:
                market = bm['markets'][0]
                print(f"FIRST_MARKET: {market.get('key')}")
                if 'outcomes' in market and len(market['outcomes']) > 0:
                    outcome = market['outcomes'][0]
                    print(f"FIRST_OUTCOME: {outcome.get('name')} = {outcome.get('price')}")
                    print("SUCCESS: Odds API works!")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
