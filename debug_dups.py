"""Check leagues"""
import requests

r = requests.get("https://predup-api.up.railway.app/api/v1/predictions/live")
data = r.json().get("data", [])

leagues = {}
for m in data:
    league = m.get("league", "UNK")
    leagues[league] = leagues.get(league, 0) + 1

print("Leagues:", leagues)
print("\nAll fixtures:")
for m in data:
    print(f"  {m.get('home_team')} vs {m.get('away_team')} [{m.get('league')}] @ {m.get('start_time')}")