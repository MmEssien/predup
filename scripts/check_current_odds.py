import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import os
from dotenv import load_dotenv
load_dotenv(_root / ".env")

from src.intelligence.mlb_odds import OddsAdapter, EVCalculator

print("="*70)
print("  THE ODDS API - CURRENT GAMES")
print("="*70)

adapter = OddsAdapter()

print("\n[1] Provider Status")
print(f"    Primary: {adapter.current_provider()}")

# Check The Odds API directly
from src.intelligence.the_odds_api import TheOddsAPIProvider

the_odds = TheOddsAPIProvider()
print(f"    The Odds API available: {the_odds.is_available()}")

# Get current odds
print("\n[2] Fetching current MLB odds from The Odds API...")
odds_data = the_odds.get_odds("baseball_mlb", "us")

if odds_data.get("data"):
    games = odds_data["data"]
    print(f"    Found {len(games)} games")
    
    print("\n[3] Current games with odds:")
    for game in games[:5]:
        home = game.get("home_team")
        away = game.get("away_team")
        
        bookmakers = game.get("bookmakers", [])
        if bookmakers:
            bm = bookmakers[0]
            for market in bm.get("markets", []):
                if market.get("key") == "h2h":
                    home_odds = None
                    away_odds = None
                    for o in market.get("outcomes", []):
                        if o.get("name") == home:
                            home_odds = o.get("price")
                        elif o.get("name") == away:
                            away_odds = o.get("price")
                    
                    if home_odds and away_odds:
                        print(f"\n    {home} vs {away}")
                        print(f"      {home}: {home_odds} (implied: {1/home_odds:.1%})")
                        print(f"      {away}: {away_odds} (implied: {1/away_odds:.1%})")
                        print(f"      Bookmaker: {bm.get('title')}")
else:
    print("    No odds data returned")

the_odds.close()

print("\n" + "="*70)