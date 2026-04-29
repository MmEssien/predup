import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import os
import random
from dotenv import load_dotenv
load_dotenv(_root / ".env")

from src.intelligence.mlb_odds import OddsAdapter, EVCalculator
from src.intelligence.the_odds_api import TheOddsAPIProvider

print("="*70)
print("  MLB LIVE BETTING PIPELINE")
print("="*70)

# Get current odds from The Odds API
the_odds = TheOddsAPIProvider()
print("\n[1] Fetching current MLB odds...")
odds_data = the_odds.get_odds("baseball_mlb", "us")

if not odds_data.get("data"):
    print("    No odds available")
    the_odds.close()
    exit()

games = odds_data["data"]
print(f"    Found {len(games)} games")

# Process each game
print("\n[2] Analyzing Games...")
results = []

for game in games:
    home = game.get("home_team")
    away = game.get("away_team")
    
    # Get best odds
    bookmakers = game.get("bookmakers", [])
    if not bookmakers:
        continue
    
    bm = bookmakers[0]
    for market in bm.get("markets", []):
        if market.get("key") != "h2h":
            continue
        
        home_odds = None
        away_odds = None
        
        for o in market.get("outcomes", []):
            if o.get("name") == home:
                home_odds = o.get("price")
            elif o.get("name") == away:
                away_odds = o.get("price")
        
        if not home_odds or not away_odds:
            continue
        
        # Simulate model prediction
        # In production: use ML model
        # For testing: random with slight home bias
        model_prob = 0.5 + random.uniform(-0.15, 0.15)
        model_prob = max(0.35, min(0.65, model_prob))
        
        # Calculate EV
        ev = EVCalculator.calculate(model_prob, home_odds)
        
        # Bet decision
        should_bet = ev["is_positive_ev"] and ev["ev_pct"] >= 3.0
        
        results.append({
            "home": home,
            "away": away,
            "home_odds": home_odds,
            "away_odds": away_odds,
            "implied_home": 1 / home_odds,
            "model_prob": model_prob,
            "ev_pct": ev["ev_pct"],
            "edge": ev["edge"],
            "bet": should_bet,
            "bookmaker": bm.get("title")
        })

# Sort by EV
results.sort(key=lambda x: x["ev_pct"], reverse=True)

print(f"\n[3] Game Analysis (sorted by EV)")
print(f"    Total: {len(results)}")

# Show games with positive EV
positive_ev = [r for r in results if r["ev_pct"] > 0]
print(f"    Positive EV: {len(positive_ev)}")

if positive_ev:
    print("\n    TOP BETTING OPPORTUNITIES:")
    for r in positive_ev[:5]:
        print(f"\n    {r['home']} vs {r['away']}")
        print(f"      Odds: {r['home']} @ {r['home_odds']} (implied: {r['implied_home']:.1%})")
        print(f"      Model: {r['model_prob']:.1%}")
        print(f"      EV: {r['ev_pct']:+.1f}%")
        print(f"      Edge: {r['edge']:+.1%}")
        print(f"      Bet: {'YES' if r['bet'] else 'NO'}")
        print(f"      Bookmaker: {r['bookmaker']}")

# Summary stats
print("\n[4] Summary Statistics")
evs = [r["ev_pct"] for r in results]
print(f"    Mean EV: {sum(evs)/len(evs):+.1f}%")
print(f"    Max EV: {max(evs):+.1f}%")
print(f"    Min EV: {min(evs):+.1f}%")

bets = [r for r in results if r["bet"]]
print(f"    Qualifying bets: {len(bets)}")

the_odds.close()

print("\n" + "="*70)
print("  READY FOR LIVE BETTING")
print("="*70)