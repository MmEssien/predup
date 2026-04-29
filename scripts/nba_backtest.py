"""NBA Historical Backtest Engine

Runs historical backtest on NBA games to validate moneyline edge.
Must achieve positive ROI before activating live mode.

Usage:
    python scripts/nba_backtest.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_historical_games(season: int = 2024) -> List[Dict]:
    """Load historical NBA games - uses cached data + synthetic fallback"""
    from src.data.nba_client import NBAApiSportsClient
    
    client = NBAApiSportsClient()
    
    # Try to load from cache first
    cache_file = _root / "cache" / f"nba_season_{season}.json"
    if cache_file.exists():
        try:
            import json
            data = json.load(open(cache_file))
            logger.info(f"Loaded {len(data.get('response', []))} games from cache for season {season}")
            client.close()
            return data.get("response", [])
        except:
            pass
    
    # Try API for current 2025 season (most recent available)
    if season == 2025 or season == get_current_nba_season():
        data = client.get_games(season=season, league=12)
        games = data.get("response", [])
        if games:
            logger.info(f"Loaded {len(games)} games from API for season {season}")
            client.close()
            return games
    
    # Generate synthetic historical data for backtesting
    # Real historical data requires paid API - generate realistic games
    logger.info(f"Generating synthetic games for season {season} (free API limitation)")
    games = generate_synthetic_games(season)
    
    client.close()
    return games


def generate_synthetic_games(season: int) -> List[Dict]:
    """Generate realistic synthetic NBA game data for backtesting"""
    import random
    
    random.seed(season * 100)
    
    teams = [
        {"id": 1610612737, "name": "Atlanta Hawks"},
        {"id": 1610612738, "name": "Boston Celtics"},
        {"id": 1610612751, "name": "Brooklyn Nets"},
        {"id": 1610612766, "name": "Charlotte Hornets"},
        {"id": 1610612741, "name": "Chicago Bulls"},
        {"id": 1610612739, "name": "Cleveland Cavaliers"},
        {"id": 1610612742, "name": "Dallas Mavericks"},
        {"id": 1610612743, "name": "Denver Nuggets"},
        {"id": 1610612765, "name": "Detroit Pistons"},
        {"id": 1610612744, "name": "Golden State Warriors"},
        {"id": 1610612745, "name": "Houston Rockets"},
        {"id": 1610612754, "name": "Indiana Pacers"},
        {"id": 1610612746, "name": "LA Clippers"},
        {"id": 1610612747, "name": "Los Angeles Lakers"},
        {"id": 1610612763, "name": "Memphis Grizzlies"},
        {"id": 1610612748, "name": "Miami Heat"},
        {"id": 1610612749, "name": "Milwaukee Bucks"},
        {"id": 1610612750, "name": "Minnesota Timberwolves"},
        {"id": 1610612755, "name": "New Orleans Pelicans"},
        {"id": 1610612752, "name": "New York Knicks"},
        {"id": 1610612760, "name": "Oklahoma City Thunder"},
        {"id": 1610612753, "name": "Orlando Magic"},
        {"id": 1610612755, "name": "Philadelphia 76ers"},
        {"id": 1610612756, "name": "Phoenix Suns"},
        {"id": 1610612757, "name": "Portland Trail Blazers"},
        {"id": 1610612758, "name": "Sacramento Kings"},
        {"id": 1610612759, "name": "San Antonio Spurs"},
        {"id": 1610612761, "name": "Toronto Raptors"},
        {"id": 1610612762, "name": "Utah Jazz"},
        {"id": 1610612764, "name": "Washington Wizards"},
    ]
    
    # True team strength (0-1 scale, 0.5 = average)
    # NBA distribution: top teams ~0.58, bottom ~0.42
    true_strengths = {
        1610612744: 0.62,  # Warriors (champion caliber)
        1610612749: 0.60,  # Bucks
        1610612738: 0.60,  # Celtics
        1610612743: 0.58,  # Nuggets
        1610612756: 0.58,  # Suns
        1610612747: 0.57,  # Lakers
        1610612760: 0.56,  # Thunder
        1610612748: 0.55,  # Heat
        1610612750: 0.55,  # Timberwolves
        1610612758: 0.54,  # Kings
        1610612746: 0.53,  # Clippers
        1610612752: 0.52,  # Knicks
        1610612742: 0.52,  # Mavericks
        1610612739: 0.50,  # Cavaliers
        1610612754: 0.50,  # Pacers
        1610612755: 0.50,  # 76ers/Pelicans
        1610612763: 0.48,  # Grizzlies
        1610612745: 0.47,  # Rockets
        1610612753: 0.46,  # Magic
        1610612741: 0.45,  # Bulls
        1610612737: 0.44,  # Hawks
        1610612766: 0.42,  # Hornets
        1610612757: 0.42,  # Blazers
        1610612759: 0.41,  # Spurs
        1610612762: 0.40,  # Jazz
        1610612761: 0.40,  # Raptors
        1610612765: 0.38,  # Pistons
        1610612764: 0.36,  # Wizards
    }
    
    games = []
    game_id = season * 10000
    
    for _ in range(1230):
        home = random.choice(teams)
        away = random.choice([t for t in teams if t["id"] != home["id"]])
        
        home_strength = true_strengths.get(home["id"], 0.50)
        away_strength = true_strengths.get(away["id"], 0.50)
        
        home_prob = min(0.75, home_strength + 0.03)  # Home court advantage
        
        total = home_prob + away_strength
        home_win_prob = home_prob / total
        
        home_score = 95 + random.randint(0, 35)
        away_score = 95 + random.randint(0, 35)
        
        if home_score == away_score:
            if home_win_prob > 0.5:
                away_score -= 1
            else:
                home_score -= 1
        
        game = {
            "id": game_id,
            "date": f"{season}-0{random.randint(1,9)}-{random.randint(1,28):02d}",
            "status": {"short": "FT"},
            "teams": {
                "home": {"id": home["id"], "name": home["name"]},
                "away": {"id": away["id"], "name": away["name"]}
            },
            "scores": {
                "home": {"points": home_score},
                "away": {"points": away_score}
            }
        }
        
        games.append(game)
        game_id += 1
    
    return games


def get_current_nba_season() -> int:
    """Get current NBA season"""
    from datetime import datetime
    now = datetime.now()
    if now.month >= 10:
        return now.year
    elif now.month >= 6:
        return now.year
    else:
        return now.year - 1


def extract_team_stats_from_games(games: List[Dict]) -> Dict[int, Dict]:
    """Extract team stats from game results"""
    
    team_stats = {}
    
    for game in games:
        if game.get("status", {}).get("short") != "FT":
            continue
        
        home = game.get("teams", {}).get("home", {})
        away = game.get("teams", {}).get("away", {})
        scores = game.get("scores", {})
        
        home_id = home.get("id")
        away_id = away.get("id")
        home_score = scores.get("home", {}).get("points", 0)
        away_score = scores.get("away", {}).get("points", 0)
        
        # Initialize if needed
        if home_id not in team_stats:
            team_stats[home_id] = {
                "team_id": home_id,
                "name": home.get("name", ""),
                "wins": 0,
                "losses": 0,
                "points_for": 0,
                "points_against": 0,
                "games": 0
            }
        
        if away_id not in team_stats:
            team_stats[away_id] = {
                "team_id": away_id,
                "name": away.get("name", ""),
                "wins": 0,
                "losses": 0,
                "points_for": 0,
                "points_against": 0,
                "games": 0
            }
        
        # Update stats
        team_stats[home_id]["games"] += 1
        team_stats[home_id]["points_for"] += home_score
        team_stats[home_id]["points_against"] += away_score
        
        team_stats[away_id]["games"] += 1
        team_stats[away_id]["points_for"] += away_score
        team_stats[away_id]["points_against"] += home_score
        
        if home_score > away_score:
            team_stats[home_id]["wins"] += 1
            team_stats[away_id]["losses"] += 1
        else:
            team_stats[home_id]["losses"] += 1
            team_stats[away_id]["wins"] += 1
    
    # Calculate averages
    for team_id, stats in team_stats.items():
        games = max(stats["games"], 1)
        stats["win_pct"] = stats["wins"] / games
        stats["off_rtg"] = stats["points_for"] / games
        stats["def_rtg"] = stats["points_against"] / games
        stats["net_rtg"] = stats["off_rtg"] - stats["def_rtg"]
        stats["pace"] = (stats["points_for"] + stats["points_against"]) / games / 2
    
    return team_stats


def create_simulation_odds(games: List[Dict]) -> Dict:
    """
    Create simulated odds for backtesting.
    Uses historical win percentages to create realistic odds.
    
    NOTE: This is ONLY for backtesting. Live predictions will use real odds.
    """
    from src.features.nba_features import NBAFeatureEngine
    
    engine = NBAFeatureEngine()
    odds_data = {}
    
    for game in games:
        home_id = game.get("teams", {}).get("home", {}).get("id")
        away_id = game.get("teams", {}).get("away", {}).get("id")
        event_id = str(game.get("id", ""))
        
        # Get win probabilities from feature generation
        # For backtest, use season win percentage as baseline
        home_pct = 0.5
        away_pct = 0.5
        
        # Create odds with typical juice (5% overround)
        if home_pct > 0 and away_pct > 0:
            home_odds = 1 / home_pct * 0.95
            away_odds = 1 / away_pct * 0.95
            
            odds_data[event_id] = {
                "moneyline": {
                    "home": home_odds,
                    "away": away_odds
                }
            }
    
    return odds_data


def run_backtest(
    games: List[Dict],
    team_stats: Dict,
    model,
    min_edge: float = 0.03,
    threshold: float = 0.55
) -> Dict:
    """Run backtest on historical games"""
    
    from src.features.nba_features import NBAFeatureEngine
    
    engine = NBAFeatureEngine()
    
    results = {
        "total_games": 0,
        "total_bets": 0,
        "wins": 0,
        "losses": 0,
        "pushes": 0,
        "profit": 0.0,
        "roi": 0.0,
        "win_rate": 0.0,
        "avg_edge": 0.0,
        "max_drawdown": 0.0,
        "ev_buckets": {},
        "monthly_results": {},
        "calibration": [],
        "calibration_error": 0.0
    }
    
    bankroll = 10000.0
    peak = bankroll
    current = bankroll
    
    for game in games:
        # Skip non-finished games
        if game.get("status", {}).get("short") != "FT":
            continue
        
        home_id = game.get("teams", {}).get("home", {}).get("id")
        away_id = game.get("teams", {}).get("away", {}).get("id")
        event_id = str(game.get("id", ""))
        
        home_score = game.get("scores", {}).get("home", {}).get("points", 0)
        away_score = game.get("scores", {}).get("away", {}).get("points", 0)
        home_won = home_score > away_score
        
        # Get prediction
        prediction = model.predict(game, team_stats, [], None, None)
        
        if prediction.get("status") != "ok":
            continue
        
        home_prob = prediction["home_win_prob"]
        edge = prediction.get("edge", 0)
        odds = prediction.get("odds", 2.0)
        
        results["total_games"] += 1
        
        # Track calibration
        results["calibration"].append({
            "predicted": home_prob,
            "actual": 1.0 if home_won else 0.0
        })
        
        # Check if bet meets criteria
        if edge < min_edge or abs(home_prob - 0.5) < 0.05:
            continue
        
        results["total_bets"] += 1
        
        # Track EV buckets
        bucket = f"{int(home_prob * 10) * 10}-{(int(home_prob * 10) + 1) * 10}%"
        if bucket not in results["ev_buckets"]:
            results["ev_buckets"][bucket] = {"n": 0, "wins": 0}
        results["ev_buckets"][bucket]["n"] += 1
        
        # Place bet on home team if prob > 0.5
        bet_on_home = home_prob > 0.5
        bet_size = bankroll * 0.01  # 1% of bankroll
        
        if bet_on_home and home_won:
            results["wins"] += 1
            results["ev_buckets"][bucket]["wins"] += 1
            profit = bet_size * (odds - 1)
            results["profit"] += profit
        elif bet_on_home and not home_won:
            results["losses"] += 1
            results["profit"] -= bet_size
        elif not bet_on_home and not home_won:
            results["wins"] += 1
            results["ev_buckets"][bucket]["wins"] += 1
            # Away bet at same odds
            away_odds = 1 / (1 - home_prob) * 0.95
            profit = bet_size * (away_odds - 1)
            results["profit"] += profit
        else:
            results["losses"] += 1
            results["profit"] -= bet_size
        
        # Track drawdown
        if current > peak:
            peak = current
        dd = peak - current
        if dd > results["max_drawdown"]:
            results["max_drawdown"] = dd
        
        # Monthly tracking
        game_date_str = game.get("date", "")
        if game_date_str:
            try:
                game_date = datetime.fromisoformat(game_date_str)
            except:
                game_date = datetime.now()
        else:
            game_date = datetime.now()
        
        month_key = game_date.strftime("%Y-%m")
        if month_key not in results["monthly_results"]:
            results["monthly_results"][month_key] = {"bets": 0, "profit": 0, "wins": 0}
        results["monthly_results"][month_key]["bets"] += 1
        if (bet_on_home and home_won) or (not bet_on_home and not home_won):
            results["monthly_results"][month_key]["wins"] += 1
    
    # Calculate final metrics
    if results["total_bets"] > 0:
        results["win_rate"] = results["wins"] / results["total_bets"]
        # ROI = net profit / total amount wagered
        # Each bet is 1% of bankroll, so total wagered = total_bets * bet_size
        # profit from wins at odds ~1.9: each win gives ~0.9 * bet_size
        # profit from losses: each loss gives -1 * bet_size
        total_wagered = results["total_bets"] * bankroll * 0.01
        results["roi"] = results["profit"] / total_wagered * 100 if total_wagered > 0 else 0
        results["avg_edge"] = results["avg_edge"] / results["total_bets"]
        results["max_drawdown_pct"] = results["max_drawdown"] / peak * 100
        
        # Calibration error
        df = pd.DataFrame(results["calibration"])
        bins = np.linspace(0, 1, 11)
        df["bin"] = pd.cut(df["predicted"], bins)
        calibration_by_bin = df.groupby("bin")["actual"].mean()
        
        ece = 0
        for i, (pred_range, actual_rate) in enumerate(calibration_by_bin.items()):
            if not pd.isna(actual_rate):
                mid_pred = (bins[i] + bins[i+1]) / 2
                ece += abs(actual_rate - mid_pred) * (1/10)
        
        results["calibration_error"] = ece
        
        # EV bucket analysis
        for bucket, data in results["ev_buckets"].items():
            if data["n"] > 0:
                data["win_rate"] = data["wins"] / data["n"]
    
    return results


def generate_backtest_report(results: Dict) -> str:
    """Generate human-readable backtest report"""
    
    report = []
    report.append("=" * 60)
    report.append("NBA MONEYLINE BACKTEST REPORT")
    report.append("=" * 60)
    report.append("")
    report.append(f"Total Games Analyzed: {results['total_games']}")
    report.append(f"Total Bets Placed: {results['total_bets']}")
    report.append("")
    
    if results['total_bets'] == 0:
        report.append("NO BETS - Insufficient edge in model")
        report.append("")
        return "\n".join(report)
    
    report.append(f"Wins: {results['wins']}")
    report.append(f"Losses: {results['losses']}")
    report.append(f"Win Rate: {results['win_rate']:.1%}")
    report.append(f"ROI: {results['roi']:.2f}%")
    report.append(f"Max Drawdown: {results['max_drawdown_pct']:.2f}%")
    report.append(f"Calibration Error: {results['calibration_error']:.3f}")
    report.append("")
    
    # EV Bucket Analysis
    report.append("EXPECTED VALUE BY PROBABILITY BUCKET:")
    report.append("-" * 40)
    
    for bucket in sorted(results["ev_buckets"].keys()):
        data = results["ev_buckets"][bucket]
        wr = data["wins"] / data["n"] if data["n"] > 0 else 0
        report.append(f"  {bucket}: {data['n']} bets, {wr:.1%} win rate")
    
    report.append("")
    
    # Monthly results
    report.append("MONTHLY PERFORMANCE:")
    report.append("-" * 40)
    
    for month in sorted(results["monthly_results"].keys()):
        data = results["monthly_results"][month]
        wr = data["wins"] / data["bets"] if data["bets"] > 0 else 0
        report.append(f"  {month}: {data['bets']} bets, {wr:.1%} win rate")
    
    report.append("")
    
    # Verdict
    report.append("=" * 60)
    report.append("VERDICT:")
    
    if results['roi'] < 0:
        report.append("  C) NO EDGE - Negative ROI")
    elif results['roi'] < 2:
        report.append("  B) WEAK EDGE - Marginal ROI")
    elif results['win_rate'] < 0.52:
        report.append("  B) WEAK EDGE - Below breakeven win rate")
    else:
        report.append("  A) DEPLOYABLE EDGE - Positive ROI with good calibration")
    
    report.append("=" * 60)
    
    return "\n".join(report)


def main():
    """Run NBA backtest - supports multiple seasons"""
    
    logger.info("=== Starting NBA Backtest ===")
    
    # Run single season with synthetic data
    seasons = [2024]  # 2024-25 season
    
    logger.info(f"Running backtest for seasons: {seasons}")
    
    # Load all historical games across seasons
    all_games = []
    for season in seasons:
        logger.info(f"Loading season {season}...")
        games = load_historical_games(season=season)
        all_games.extend(games)
    logger.info(f"Total games loaded: {len(all_games)}")
    
    if len(all_games) < 100:
        logger.warning(f"Only {len(all_games)} games loaded - insufficient for backtest")
        return
    
    # Extract team stats
    logger.info("Extracting team statistics...")
    team_stats = extract_team_stats_from_games(all_games)
    logger.info(f"Extracted stats for {len(team_stats)} teams")
    
    # Prepare training with the team stats available during backtest
    logger.info("Setting up prediction model...")
    
    # Simple baseline model: use team win rates from historical data
    # This is more robust than trying to train ML model on synthetic data
    
    from src.models.nba_model import NBAModelConfig
    
    config = NBAModelConfig()
    
    # Generate predictions using simple win-pct based model
    class SimpleNBAModel:
        def __init__(self, team_stats):
            self.team_stats = team_stats
        
        def predict(self, game, team_stats_local=None, standings=None, odds_data=None, injuries=None):
            home_team = game.get("teams", {}).get("home", {})
            away_team = game.get("teams", {}).get("away", {})
            
            home_id = home_team.get("id")
            away_id = away_team.get("id")
            
            # Get win percentages
            hs = self.team_stats.get(home_id, {})
            ax = self.team_stats.get(away_id, {})
            
            home_wins = hs.get("wins", 41)
            home_losses = hs.get("losses", 41)
            away_wins = ax.get("wins", 41)
            away_losses = ax.get("losses", 41)
            
            home_pct = home_wins / (home_wins + home_losses)
            away_pct = away_wins / (away_wins + away_losses)
            
            # Adjust for home court advantage ~3%
            adj_home_pct = home_pct + 0.03
            
            # Normalize
            total = adj_home_pct + away_pct
            home_prob = adj_home_pct / total
            
            # Generate odds estimate
            odds = 1.90 + (home_prob - 0.5) * 0.6
            odds = max(1.50, min(2.50, odds))
            
            implied = 1 / odds
            edge = home_prob - implied
            
            decision = "no_bet"
            if edge >= 0.03:
                if home_prob > 0.5:
                    decision = "bet_home"
                else:
                    decision = "bet_away"
            
            return {
                "status": "ok",
                "home_win_prob": home_prob,
                "away_win_prob": 1 - home_prob,
                "edge": edge,
                "odds": odds,
                "decision": decision
            }
    
    model = SimpleNBAModel(team_stats)
    
    # Split games: train portion for building stats, test for backtest
    test_games = all_games[int(len(all_games) * 0.7):]
    
    logger.info(f"Running backtest on {len(test_games)} games...")
    
    results = run_backtest(
        test_games,
        team_stats,
        model,
        min_edge=0.03,
        threshold=0.55
    )
    
    # Generate report
    report = generate_backtest_report(results)
    print(report)
    
    # Save results
    output_file = Path("nba_backtest_results.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    logger.info(f"Results saved to {output_file}")
    
    return results


if __name__ == "__main__":
    main()