import os
import sys
sys.path.insert(0, "/app")

# Log to file
log = open("/tmp/odds_debug.log", "w")

def log_print(*args, sep=" "):
    msg = sep.join(str(a) for a in args) + "\n"
    log.write(msg)
    log.flush()
    print(*args, sep=sep)  # Also print to stdout

log_print("=== ODDS DEBUG SESSION ===")
log_print(f"ODDS_API_KEY set: {bool(os.getenv('ODDS_API_KEY'))}")
log_print(f"ODDS_API_KEY length: {len(os.getenv('ODDS_API_KEY') or '')}")

# Test 1: Import and initialize odds engine
log_print("\n=== Test 1: Initialize Odds Engine ===")
try:
    from src.data.unified_odds_engine import UnifiedOddsEngine
    engine = UnifiedOddsEngine()
    log_print("Engine initialized")
except Exception as e:
    log_print(f"Failed to initialize: {e}")
    import traceback
    traceback.print_exc(file=log)
    sys.exit(1)

# Test 2: Try to get odds for a specific fixture  
log_print("\n=== Test 2: Get odds for Chicago Cubs vs Arizona Diamondbacks ===")
try:
    result = engine.get_odds("mlb", "Chicago Cubs", "Arizona Diamondbacks")
    log_print(f"Result: {result}")
    if result:
        log_print(f"Source: {result.get('source')}")
        log_print(f"Home odds: {result.get('home_odds')}")
        log_print(f"Away odds: {result.get('away_odds')}")
    else:
        log_print("Result is None - no odds found")
except Exception as e:
    log_print(f"Error getting odds: {e}")
    import traceback
    traceback.print_exc(file=log)

# Test 3: Check what the OddsAPIAdapter returns
log_print("\n=== Test 3: Direct OddsAPIAdapter test ===")
try:
    from src.data.oddsapi_adapter import OddsAPIAdapter
    adapter = OddsAPIAdapter()
    log_print(f"Adapter initialized, api_key set: {bool(adapter.api_key)}")
    
    # Get all fixtures from API
    import httpx
    r = httpx.get(
        "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds",
        params={
            "apiKey": adapter.api_key,
            "regions": "us",
            "markets": "h2h"
        }
    )
    log_print(f"API status: {r.status_code}")
    data = r.json()
    log_print(f"API returned {len(data) if isinstance(data, list) else 'non-list'} fixtures")
    
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        log_print(f"First fixture: {first.get('home_team')} vs {first.get('away_team')}")
        
        # Try to find match
        for event in data:
            ht = event.get("home_team", "").lower()
            if "cubs" in ht or "chicago" in ht:
                log_print(f"Found match: {event.get('home_team')} vs {event.get('away_team')}")
                bookmakers = event.get("bookmakers", [])
                if bookmakers:
                    bm = bookmakers[0]
                    log_print(f"First bookmaker: {bm.get('title')}")
                    for m in bm.get("markets", []):
                        if m.get("key") == "h2h":
                            log_print(f"Found h2h market")
                            for o in m.get("outcomes", []):
                                log_print(f"Outcome: {o.get('name')} = {o.get('price')}")
                            break
                break
except Exception as e:
    log_print(f"Error in Test 3: {e}")
    import traceback
    traceback.print_exc(file=log)

log_print("\n=== DEBUG SESSION COMPLETE ===")
log.close()
log_print("Debug log written to /tmp/odds_debug.log")
