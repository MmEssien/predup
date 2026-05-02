"""Test football-data.org API"""
from dotenv import load_dotenv
load_dotenv()

from src.data.api_client import FootballAPIClient

print("Testing football-data.org...")
client = FootballAPIClient()

print(f"API Key set: {bool(client.api_key)}")

# Try to get matches for today
data = client.get_matches(date='2026-05-02')
print(f"Response has matches: {'matches' in data if data else False}")

if data and 'matches' in data:
    matches = data['matches']
    print(f"Matches found: {len(matches)}")
    
    if matches:
        m = matches[0]
        print(f"Sample match: {m['homeTeam']['name']} vs {m['awayTeam']['name']}")
        print(f"Status: {m.get('status')}")
        print(f"Date: {m.get('utcDate')}")
    else:
        print("No matches today (may be off-season)")
        # Try without date
        data2 = client.get_matches()
        if data2 and 'matches' in data2:
            print(f"Total matches available: {len(data2['matches'])}")
            if data2['matches']:
                m = data2['matches'][0]
                print(f"Sample: {m['homeTeam']['name']} vs {m['awayTeam']['name']}")

client.close()
print("\nDone!")
