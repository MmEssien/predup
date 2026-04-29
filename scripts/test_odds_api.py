"""
Test and validate the Odds API integration
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.data.odds_client import OddsAPIClient
import json

print("=== Testing Odds API Integration ===\n")

client = OddsAPIClient()

# Check credits
info = client.get_credits_info()
print(f"API Enabled: {info['enabled']}")
print(f"Credits Used: {info['credits_used']}")
print(f"Credits Remaining: {info['credits_remaining']}")
print(f"Can Fetch: {info['can_fetch']}")

if info['can_fetch']:
    print("\n--- Fetching live odds for testing ---\n")
    
    # Map our leagues to Odds API sports
    SPORT_MAP = {
        "BL1": "soccer_germany_bundesliga",
        "PL": "soccer_england_premier_league",
        "SA": "soccer_italy_serie_a",
        "FL1": "soccer_france_ligue_1",
        "PD": "soccer_spain_la_liga"
    }
    
    for league, sport_key in SPORT_MAP.items():
        print(f"\n{league} ({sport_key}):")
        data = client.get_odds(sport_key)
        
        if data and "data" in data:
            events = data["data"][:3]  # Show first 3
            for event in events:
                home = event.get("home_team", "?")
                away = event.get("away_team", "?")
                commence = event.get("commence_time", "")[:19]
                
                # Get best h2h odds
                h2h = event.get("bookmakers", [{}])[0].get("markets", [{}])[0].get("outcomes", [])
                
                home_odds = None
                draw_odds = None
                away_odds = None
                
                for outcome in h2h:
                    if outcome.get("name") == home:
                        home_odds = outcome.get("price")
                    elif outcome.get("name") == away:
                        away_odds = outcome.get("price")
                    elif outcome.get("name") == "Draw":
                        draw_odds = outcome.get("price")
                
                print(f"  {home} vs {away} | {commence}")
                print(f"    Odds: {home_odds} | {draw_odds} | {away_odds}")
        else:
            print(f"  No data")
    
    print(f"\n--- Credits after fetch ---")
    info2 = client.get_credits_info()
    print(f"Credits Used: {info2['credits_used']}")
    print(f"Credits Remaining: {info2['credits_remaining']}")
else:
    print("\nOdds API not available - using simulated odds")

print("\n=== Complete ===")

client.close()