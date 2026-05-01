"""Test fixture fetching"""
from src.data.api_client import FootballAPIClient
from datetime import date, datetime, timedelta

print("Testing at", datetime.utcnow())
print("Today's date:", date.today())

client = FootballAPIClient()
print("\n--- Competitions ---")
comps = client.get_competitions()
print("Keys:", comps.keys())
print("Count:", len(comps.get("competitions", [])))

for comp in comps.get("competitions", [])[:5]:
    code = comp.get("code", "")
    comp_id = comp.get("id")
    print(f"  {code}: id={comp_id}")

print("\n--- Todays Matches ---")
found_any = False
for comp in comps.get("competitions", []):
    code = comp.get("code", "")
    comp_id = comp.get("id")
    
    if code not in ["PL", "BL1", "FL1", "PD", "SA", "EL"]:
        continue
    
    try:
        print(f"Fetching {code}...")
        matches = client.get_matches(comp_id=comp_id, date=date.today().isoformat())
        match_list = matches.get("matches", [])
        print(f"  Found: {len(match_list)} matches")
        
        for m in match_list[:3]:
            found_any = True
            home = m.get("homeTeam", {}).get("name", "TBD")
            away = m.get("awayTeam", {}).get("name", "TBD")
            status = m.get("status", "UNKNOWN")
            start = m.get("utcDate", "TBD")
            print(f"    {home} vs {away} | {status} | {start}")
            
    except Exception as e:
        print(f"  Error: {e}")

if not found_any:
    print("\nNo matches found for today!")
    print("Checking next few days...")
    
    for days_offset in range(1, 4):
        test_date = date.today() + timedelta(days=days_offset)
        print(f"\n--- {test_date} ---")
        for comp in comps.get("competitions", [])[:3]:
            code = comp.get("code", "")
            comp_id = comp.get("id")
            if code not in ["PL", "BL1"]:
                continue
            try:
                matches = client.get_matches(comp_id=comp_id, date=test_date.isoformat())
                match_list = matches.get("matches", [])
                if match_list:
                    print(f"  {code}: {len(match_list)} matches on {test_date}")
                    for m in match_list[:2]:
                        home = m.get("homeTeam", {}).get("name", "TBD")
                        away = m.get("awayTeam", {}).get("name", "TBD")
                        print(f"    {home} vs {away}")
            except Exception as e:
                print(f"  Error: {e}")

client.close()
print("\nDone!")