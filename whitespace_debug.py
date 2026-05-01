import os
import sys
sys.path.insert(0, "/app")

log = open("/tmp/whitespace_debug.log", "w")

key = os.getenv("ODDS_API_KEY")
log.write(f"Key repr: {repr(key)}\n")
log.write(f"Key len: {len(key) if key else 0}\n")
log.write(f"Key bytes: {key.encode('utf-8') if key else b''}\n")

# Check for whitespace
if key:
    log.write(f"Has leading space: {key[0] == ' '}\n")
    log.write(f"Has trailing space: {key[-1] == ' '}\n")
    log.write(f"Has newline: {'\n' in key}\n")
    log.write(f"Has carriage return: {'\r' in key}\n")

# Test with stripped key
import httpx
stripped_key = key.strip() if key else ""
log.write(f"\nStripped key len: {len(stripped_key)}\n")

r = httpx.get(
    "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds",
    params={
        "apiKey": stripped_key,
        "regions": "us",
        "markets": "h2h"
    }
)
log.write(f"Status with stripped key: {r.status_code}\n")

# Compare with original
r2 = httpx.get(
    "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds",
    params={
        "apiKey": key,
        "regions": "us",
        "markets": "h2h"
    }
)
log.write(f"Status with original key: {r2.status_code}\n")

log.close()
print("Debug complete, check /tmp/whitespace_debug.log")
