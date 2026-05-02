import os, httpx
log = open("/tmp/sportsgameodds_test.log", "w")

key = os.getenv("SPORTSGAMEODDS_KEY", "")
log.write(f"SportsGameOdds key set: {bool(key)}\n")
log.write(f"Key len: {len(key) if key else 0}\n")

# Test SportsGameOdds API
try:
    log.write("\n=== Testing SportsGameOdds API ===\n")
    r = httpx.get(
        "https://api.sportsgameodds.com/v2/events",
        params={
            "apiKey": key,
            "sport": "baseball/mlb",
            "region": "us"
        }
    )
    log.write(f"Status: {r.status_code}\n")
    log.write(f"Response (first 300 chars): {r.text[:300]}\n")
    
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list):
            log.write(f"Events returned: {len(data)}\n")
            if len(data) > 0:
                log.write(f"First event keys: {list(data[0].keys())}\n")
                log.write(f"First event: {data[0].get('home_team')} vs {data[0].get('away_team')}\n")
        else:
            log.write(f"Response: {data}\n")
except Exception as e:
    log.write(f"Error: {e}\n")
    import traceback
    traceback.print_exc(file=log)

log.write("\n=== TEST COMPLETE ===\n")
log.close()
print("Test complete, check /tmp/sportsgameodds_test.log")
