import os, httpx, json

log = open("/tmp/final_api_test.log", "w")

key = os.getenv("ODDS_API_KEY", "")
log.write(f"Key repr: {repr(key)}\n")
log.write(f"Key len: {len(key)}\n")

# Test 1: Minimal request
log.write("\n=== Test 1: Minimal request ===\n")
try:
    r = httpx.get(
        "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds",
        params={"apiKey": key, "regions": "us", "markets": "h2h"}
    )
    log.write(f"Status: {r.status_code}\n")
    log.write(f"Response (first 300 chars): {r.text[:300]}\n")
    log.write(f"Headers: {dict(r.headers)}\n")
except Exception as e:
    log.write(f"Error: {e}\n")
    import traceback
    traceback.print_exc(file=log)

# Test 2: Check quota remaining
log.write("\n=== Test 2: Check quota from last response ===\n")
try:
    r2 = httpx.get(
        "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds",
        params={"apiKey": key, "regions": "us", "markets": "h2h"}
    )
    remaining = r2.headers.get("X-odds-api-credits-remaining")
    log.write(f"Credits remaining: {remaining}\n")
except Exception as e:
    log.write(f"Error checking quota: {e}\n")

log.write("\n=== TEST COMPLETE ===\n")
log.close()
print("Test complete, check /tmp/final_api_test.log")
