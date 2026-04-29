"""NBA Closed-Loop Prediction System

Runs continuous predictions, tracks results, auto-settles.
Integrates with Phase 4 auto-settlement infrastructure.

Usage:
    python scripts/nba_closed_loop.py --once    # Run once
    python scripts/nba_closed_loop.py           # Continuous mode
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NBAClosedLoop:
    """NBA closed-loop prediction system"""
    
    def __init__(self, min_edge: float = 0.03, min_prob: float = 0.55):
        self.min_edge = min_edge
        self.min_prob = min_prob
        self.pending_bets = []
        
    def fetch_games(self) -> List[Dict]:
        """Fetch current games (live and upcoming)"""
        from src.data.nba_adapter import NBAAdapter
        
        adapter = NBAAdapter()
        
        # Get upcoming
        upcoming = adapter.get_fixtures(days_ahead=1)
        
        # Get live
        live = adapter.get_live_games()
        
        adapter.close()
        
        return upcoming + live
    
    def generate_signal(
        self,
        game: Dict,
        team_stats: Dict
    ) -> Dict:
        """Generate betting signal for a game"""
        from src.features.nba_features import NBAFeatureEngine
        
        engine = NBAFeatureEngine()
        
        home_id = game.get("home_team", {}).get("id")
        away_id = game.get("away_team", {}).get("id")
        
        home_stats = team_stats.get(home_id, {})
        away_stats = team_stats.get(away_id, {})
        
        features = engine.generate_all_features(
            home_team_id=home_id,
            away_team_id=away_id,
            home_stats=home_stats,
            away_stats=away_stats,
            game_date=datetime.fromisoformat(game.get("start_time", datetime.now().isoformat()))
        )
        
        # Simple heuristic signal
        home_prob = self._calculate_probability(features)
        home_odds = self._get_odds(game)
        edge = home_prob - (1/home_odds) if home_odds else 0
        
        return {
            "game_id": game.get("event_id"),
            "home_team": game.get("home_team", {}).get("name"),
            "away_team": game.get("away_team", {}).get("name"),
            "start_time": game.get("start_time"),
            "home_prob": home_prob,
            "away_prob": 1 - home_prob,
            "home_odds": home_odds,
            "edge": edge,
            "decision": self._decide_bet(home_prob, edge)
        }
    
    def _calculate_probability(self, features: Dict) -> float:
        """Calculate win probability from features"""
        
        home_win_pct = features.get("home_win_pct", 0.5)
        away_win_pct = features.get("away_win_pct", 0.5)
        
        rest_adj = features.get("rest_advantage", 0) * 0.02
        form_adj = features.get("home_form_advantage", 0) * 0.05
        
        prob = 0.5 + (home_win_pct - 0.5) * 0.5 + rest_adj + form_adj
        
        return max(0.1, min(0.9, prob))
    
    def _get_odds(self, game: Dict) -> float:
        """Get home team moneyline odds"""
        # Placeholder - would fetch from odds API
        return 1.95
    
    def _decide_bet(self, prob: float, edge: float) -> Dict:
        """Decide whether to bet"""
        
        if edge >= self.min_edge and prob >= self.min_prob:
            return {
                "action": "bet_home",
                "stake_pct": 0.01,
                "signal": "QUALIFYING"
            }
        elif edge >= self.min_edge and (1 - prob) >= self.min_prob:
            return {
                "action": "bet_away",
                "stake_pct": 0.01,
                "signal": "QUALIFYING"
            }
        else:
            return {
                "action": "no_bet",
                "stake_pct": 0,
                "signal": "WATCHLIST" if edge >= 0.01 else "NO_BET"
            }
    
    def record_bet(self, signal: Dict) -> None:
        """Record bet for tracking"""
        self.pending_bets.append({
            "game_id": signal["game_id"],
            "home_team": signal["home_team"],
            "away_team": signal["away_team"],
            "action": signal["decision"]["action"],
            "odds": signal.get("home_odds") if signal["decision"]["action"] == "bet_home" 
                    else signal.get("away_odds"),
            "recorded_at": datetime.now().isoformat(),
            "settled": False
        })
    
    def settle_bet(
        self,
        game_id: str,
        home_score: int,
        away_score: int
    ) -> Dict:
        """Settle a bet result"""
        
        for bet in self.pending_bets:
            if bet["game_id"] == game_id and not bet["settled"]:
                home_won = home_score > away_score
                bet_won = (
                    (bet["action"] == "bet_home" and home_won) or
                    (bet["action"] == "bet_away" and not home_won)
                )
                
                bet["settled"] = True
                bet["home_score"] = home_score
                bet["away_score"] = away_score
                bet["settled_at"] = datetime.now().isoformat()
                bet["won"] = bet_won
                
                if bet_won:
                    bet["profit"] = bet["odds"] - 1
                else:
                    bet["profit"] = -1
                
                return bet
        
        return None
    
    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary"""
        
        settled = [b for b in self.pending_bets if b.get("settled")]
        pending = [b for b in self.pending_bets if not b.get("settled")]
        
        if not settled:
            return {
                "total_bets": 0,
                "settled": 0,
                "pending": len(pending),
                "roi": 0,
                "win_rate": 0
            }
        
        wins = sum(1 for b in settled if b.get("won"))
        total_profit = sum(b.get("profit", 0) for b in settled)
        
        return {
            "total_bets": len(self.pending_bets),
            "settled": len(settled),
            "pending": len(pending),
            "wins": wins,
            "losses": len(settled) - wins,
            "win_rate": wins / len(settled) if settled else 0,
            "profit": total_profit,
            "roi": total_profit / len(settled) if settled else 0
        }


def run_once(engine: NBAClosedLoop) -> Dict:
    """Run prediction cycle once"""
    
    logger.info("=== NBA Closed-Loop Prediction ===")
    
    # Fetch games
    logger.info("Fetching games...")
    games = engine.fetch_games()
    logger.info(f"Found {len(games)} games")
    
    if not games:
        logger.warning("No games found")
        return {"games": 0}
    
    # Get team stats (would cache this)
    # For simplicity, using empty stats
    team_stats = {}
    
    # Generate signals
    signals = []
    for game in games:
        signal = engine.generate_signal(game, team_stats)
        signals.append(signal)
        
        # Record qualifying bets
        if signal["decision"]["signal"] == "QUALIFYING":
            engine.record_bet(signal)
    
    # Summary
    qualifying = [s for s in signals if s["decision"]["signal"] == "QUALIFYING"]
    watchlist = [s for s in signals if s["decision"]["signal"] == "WATCHLIST"]
    
    summary = {
        "games_analyzed": len(games),
        "qualifying_bets": len(qualifying),
        "watchlist": len(watchlist),
        "signals": signals,
        "portfolio": engine.get_portfolio_summary()
    }
    
    # Display
    print("\n" + "=" * 60)
    print("NBA CLOSED-LOOP PREDICTION SUMMARY")
    print("=" * 60)
    print(f"Games analyzed: {summary['games_analyzed']}")
    print(f"Qualifying bets: {summary['qualifying_bets']}")
    print(f"Watchlist: {summary['watchlist']}")
    
    if qualifying:
        print("\nQUALIFYING BETS:")
        for s in qualifying:
            print(f"  {s['away_team']} @ {s['home_team']}")
            print(f"    {s['decision']['action']} @ {s.get('home_odds', 2.0):.2f}")
            print(f"    Edge: {s['edge']:.2%}, Prob: {s['home_prob']:.1%}")
    
    if summary['portfolio']['total_bets'] > 0:
        print("\nPORTFOLIO:")
        p = summary['portfolio']
        print(f"  Total bets: {p['total_bets']}")
        print(f"  Settled: {p['settled']}, Pending: {p['pending']}")
        print(f"  Win rate: {p['win_rate']:.1%}")
        print(f"  ROI: {p['roi']:.1%}")
    
    return summary


def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(description="NBA Closed-Loop Prediction")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--min-edge", type=float, default=0.03, help="Minimum edge")
    parser.add_argument("--min-prob", type=float, default=0.55, help="Minimum probability")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between runs")
    
    args = parser.parse_args()
    
    engine = NBAClosedLoop(
        min_edge=args.min_edge,
        min_prob=args.min_prob
    )
    
    if args.once:
        run_once(engine)
        return
    
    # Continuous mode
    logger.info("Starting NBA closed-loop (Ctrl+C to stop)")
    
    while True:
        try:
            run_once(engine)
            logger.info(f"Sleeping {args.interval} seconds...")
            time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()