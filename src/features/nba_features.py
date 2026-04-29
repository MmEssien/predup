"""NBA Feature Engineering

Generates features for NBA moneyline prediction following MLB methodology.
Team Features: offensive rating, defensive rating, net rating, pace, eFG%, TO%, rebound %
Situational Features: home/away, back-to-back, rest days, travel, recent form
Player Influence: star player status, injury weighting
Market Features: spread, moneyline, totals, implied probability
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


class NBAFeatureEngine:
    """Generate NBA-specific features for moneyline prediction"""
    
    def __init__(self, db_session=None):
        self.db = db_session
        self.lookback_games = 10
        self.season = 2024
    
    def generate_team_features(
        self,
        home_team_id: int,
        away_team_id: int,
        home_stats: Optional[Dict] = None,
        away_stats: Optional[Dict] = None
    ) -> Dict[str, float]:
        """Generate core team statistical features"""
        
        features = {}
        
        # Home team features
        if home_stats:
            features.update(self._extract_team_stats(home_stats, "home_"))
        
        # Away team features
        if away_stats:
            features.update(self._extract_team_stats(away_stats, "away_"))
        
        # Relative features (home - away)
        if home_stats and away_stats:
            features.update(self._compute_relative_features(home_stats, away_stats))
        
        return features
    
    def _extract_team_stats(self, stats: Dict, prefix: str) -> Dict[str, float]:
        """Extract team stats into features"""
        
        games = max(stats.get("games_played", 1), 1)
        wins = stats.get("win", 0)
        losses = stats.get("loss", 0)
        total = wins + losses
        
        pf = stats.get("points_for", 0)
        pa = stats.get("points_against", 0)
        
        return {
            f"{prefix}win_pct": wins / total if total > 0 else 0.5,
            f"{prefix}win_pct_home": stats.get("win_home", 0) / max(1, stats.get("win_home", 0) + stats.get("loss_home", 0)) if stats.get("win_home", 0) > 0 or stats.get("loss_home", 0) > 0 else 0.5,
            f"{prefix}win_pct_away": stats.get("win_away", 0) / max(1, stats.get("win_away", 0) + stats.get("loss_away", 0)) if stats.get("win_away", 0) > 0 or stats.get("loss_away", 0) > 0 else 0.5,
            f"{prefix}off_rtg": pf / games,
            f"{prefix}def_rtg": pa / games,
            f"{prefix}net_rtg": (pf - pa) / games,
            f"{prefix}pace": (pf + pa) / games / 2,
            f"{prefix}last_10_wins": stats.get("win_last_10", 0),
            f"{prefix}win_pct_last_10": stats.get("win_last_10", 0) / min(10, games),
        }
    
    def _compute_relative_features(
        self,
        home_stats: Dict,
        away_stats: Dict
    ) -> Dict[str, float]:
        """Compute relative features (home advantage metrics)"""
        
        h_games = max(home_stats.get("games_played", 1), 1)
        a_games = max(away_stats.get("games_played", 1), 1)
        
        h_pf = home_stats.get("points_for", 0) / h_games
        h_pa = home_stats.get("points_against", 0) / h_games
        a_pf = away_stats.get("points_for", 0) / a_games
        a_pa = away_stats.get("points_against", 0) / a_games
        
        h_wins = home_stats.get("win", 0)
        h_losses = home_stats.get("loss", 0)
        h_total = h_wins + h_losses
        
        a_wins = away_stats.get("win", 0)
        a_losses = away_stats.get("loss", 0)
        a_total = a_wins + a_losses
        
        return {
            "net_rtg_diff": (h_pf - h_pa) - (a_pf - a_pa),
            "off_rtg_diff": h_pf - a_pf,
            "def_rtg_diff": h_pa - a_pa,
            "win_pct_diff": (h_wins / h_total if h_total > 0 else 0.5) - (a_wins / a_total if a_total > 0 else 0.5),
            "home_advantage": h_wins / h_total - a_wins / a_total if h_total > 0 and a_total > 0 else 0,
            "pace_diff": (h_pf + h_pa) / 2 - (a_pf + a_pa) / 2,
        }
    
    def generate_situational_features(
        self,
        home_team_id: int,
        away_team_id: int,
        game_date: datetime,
        historical_games: Optional[List[Dict]] = None
    ) -> Dict[str, float]:
        """Generate situational features (rest, travel, back-to-back)"""
        
        features = {
            "home_rest_days": 2,  # Default
            "away_rest_days": 2,
            "home_b2b": 0,
            "away_b2b": 0,
        }
        
        if historical_games:
            home_games = [g for g in historical_games if g.get("team_id") == home_team_id]
            away_games = [g for g in historical_games if g.get("team_id") == away_team_id]
            
            # Sort by date
            home_games.sort(key=lambda x: x.get("game_date", datetime.min), reverse=True)
            away_games.sort(key=lambda x: x.get("game_date", datetime.min), reverse=True)
            
            if home_games:
                last_home = home_games[0].get("game_date", game_date - timedelta(days=3))
                features["home_rest_days"] = (game_date - last_home).days - 1
                if len(home_games) >= 2:
                    features["home_b2b"] = 1 if (last_home - home_games[1].get("game_date", last_home)).days <= 1 else 0
            
            if away_games:
                last_away = away_games[0].get("game_date", game_date - timedelta(days=3))
                features["away_rest_days"] = (game_date - last_away).days - 1
                if len(away_games) >= 2:
                    features["away_b2b"] = 1 if (last_away - away_games[1].get("game_date", last_away)).days <= 1 else 0
            
            # Rest advantage
            features["rest_advantage"] = features["home_rest_days"] - features["away_rest_days"]
            features["home_rest_advantage"] = features["home_rest_days"] > features["away_rest_days"]
        
        # Travel disadvantage (simple heuristic - away team with less rest)
        features["away_travel_disadvantage"] = 1 if features["away_rest_days"] < features["home_rest_days"] else 0
        
        return features
    
    def generate_form_features(
        self,
        home_team_id: int,
        away_team_id: int,
        standings: List[Dict]
    ) -> Dict[str, float]:
        """Generate recent form features"""
        
        features = {
            "home_is_hot": 0,
            "away_is_hot": 0,
            "home_is_cold": 0,
            "away_is_cold": 0,
        }
        
        for s in standings:
            if s.get("team_id") == home_team_id:
                last_10 = s.get("win_last_10", 0)
                streak = str(s.get("streak", ""))
                
                features["home_is_hot"] = 1 if last_10 >= 7 else 0
                features["home_is_cold"] = 1 if last_10 <= 3 else 0
                features["home_streak_wins"] = int(streak.lstrip("W")) if streak.startswith("W") else 0
                features["home_streak_losses"] = int(streak.lstrip("L")) if streak.startswith("L") else 0
            
            elif s.get("team_id") == away_team_id:
                last_10 = s.get("win_last_10", 0)
                streak = str(s.get("streak", ""))
                
                features["away_is_hot"] = 1 if last_10 >= 7 else 0
                features["away_is_cold"] = 1 if last_10 <= 3 else 0
                features["away_streak_wins"] = int(streak.lstrip("W")) if streak.startswith("W") else 0
                features["away_streak_losses"] = int(streak.lstrip("L")) if streak.startswith("L") else 0
        
        # Form advantage
        features["home_form_advantage"] = features["home_is_hot"] - features["away_is_hot"]
        
        return features
    
    def generate_market_features(
        self,
        home_odds: Optional[float] = None,
        away_odds: Optional[float] = None,
        spread: Optional[float] = None,
        total: Optional[float] = None
    ) -> Dict[str, float]:
        """Generate market-based features"""
        
        features = {}
        
        if home_odds and home_odds > 0:
            features["home_implied_prob"] = 1 / home_odds
            features["home_juice"] = home_odds - (1 / features["home_implied_prob"])
        
        if away_odds and away_odds > 0:
            features["away_implied_prob"] = 1 / away_odds
            features["away_juice"] = away_odds - (1 / features["away_implied_prob"])
        
        if home_odds and away_odds and home_odds > 0 and away_odds > 0:
            total_implied = features.get("home_implied_prob", 0) + features.get("away_implied_prob", 0)
            features["overround"] = total_implied
            features["home_fair_prob"] = features.get("home_implied_prob", 0.5) / total_implied
            features["away_fair_prob"] = features.get("away_implied_prob", 0.5) / total_implied
        
        if spread is not None:
            features["home_spread"] = spread
        
        if total is not None:
            features["total_line"] = total
            features["expected_pace"] = total / 2
        
        return features
    
    def generate_injury_features(
        self,
        home_missing: List[Dict],
        away_missing: List[Dict]
    ) -> Dict[str, float]:
        """Generate injury impact features"""
        
        features = {
            "home_key_missing": 0,
            "away_key_missing": 0,
            "home_injury_impact": 0.0,
            "away_injury_impact": 0.0,
        }
        
        for m in home_missing:
            if m.get("is_key_player", False):
                features["home_key_missing"] += 1
                features["home_injury_impact"] += m.get("severity_impact", 0.5)
        
        for m in away_missing:
            if m.get("is_key_player", False):
                features["away_key_missing"] += 1
                features["away_injury_impact"] += m.get("severity_impact", 0.5)
        
        features["injury_impact_diff"] = features["away_injury_impact"] - features["home_injury_impact"]
        
        return features
    
    def generate_all_features(
        self,
        home_team_id: int,
        away_team_id: int,
        home_stats: Optional[Dict] = None,
        away_stats: Optional[Dict] = None,
        standings: Optional[List[Dict]] = None,
        home_odds: Optional[float] = None,
        away_odds: Optional[float] = None,
        spread: Optional[float] = None,
        total: Optional[float] = None,
        home_missing: Optional[List[Dict]] = None,
        away_missing: Optional[List[Dict]] = None,
        game_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Generate complete feature set for NBA moneyline prediction"""
        
        features = {}
        
        # Team features
        if home_stats or away_stats:
            team_feats = self.generate_team_features(home_team_id, away_team_id, home_stats, away_stats)
            features.update(team_feats)
        
        # Situational features
        if game_date:
            situ_feats = self.generate_situational_features(home_team_id, away_team_id, game_date)
            features.update(situ_feats)
        
        # Form features
        if standings:
            form_feats = self.generate_form_features(home_team_id, away_team_id, standings)
            features.update(form_feats)
        
        # Market features
        if home_odds or away_odds:
            market_feats = self.generate_market_features(home_odds, away_odds, spread, total)
            features.update(market_feats)
        
        # Injury features
        if home_missing or away_missing:
            injury_feats = self.generate_injury_features(
                home_missing or [], away_missing or []
            )
            features.update(injury_feats)
        
        # Add constants
        features["nba_season"] = self.season
        
        return features


def create_nba_feature_vector(
    game: Dict,
    team_stats: Dict,
    standings: List[Dict],
    odds: Optional[Dict] = None,
    injuries: Optional[Dict] = None
) -> Tuple[Dict[str, float], int]:
    """
    Create feature vector from game data.
    
    Returns:
        features: Feature dictionary
        target: 1 if home team won, 0 if away team won (None if game not completed)
    """
    
    engine = NBAFeatureEngine()
    
    home_team_id = game.get("home_team", {}).get("id")
    away_team_id = game.get("away_team", {}).get("id")
    
    # Get team stats
    home_stats = team_stats.get(home_team_id, {})
    away_stats = team_stats.get(away_team_id, {})
    
    # Get odds
    home_odds = None
    away_odds = None
    spread = None
    total = None
    
    if odds:
        ml = odds.get("moneyline", {})
        home_odds = ml.get("home")
        away_odds = ml.get("away")
        spread_data = odds.get("spread")
        if spread_data:
            spread = spread_data.get("points")
        total_data = odds.get("total")
        if total_data:
            total = total_data.get("points")
    
    # Get injuries
    home_missing = []
    away_missing = []
    if injuries:
        home_missing = injuries.get(home_team_id, [])
        away_missing = injuries.get(away_team_id, [])
    
    # Generate features
    game_date = datetime.fromisoformat(game.get("start_time", datetime.now().isoformat()))
    
    features = engine.generate_all_features(
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_stats=home_stats,
        away_stats=away_stats,
        standings=standings,
        home_odds=home_odds,
        away_odds=away_odds,
        spread=spread,
        total=total,
        home_missing=home_missing,
        away_missing=away_missing,
        game_date=game_date
    )
    
    # Determine target (if game completed)
    target = None
    if game.get("status") == "Finished":
        home_score = game.get("home_team", {}).get("score", 0)
        away_score = game.get("away_team", {}).get("score", 0)
        target = 1 if home_score > away_score else 0
    
    return features, target


# Test features
if __name__ == "__main__":
    print("=== Testing NBA Feature Engineering ===\n")
    
    engine = NBAFeatureEngine()
    
    # Test team features
    home_stats = {
        "team_id": 1,
        "games_played": 30,
        "win": 20,
        "loss": 10,
        "win_home": 12,
        "loss_home": 3,
        "win_away": 8,
        "loss_away": 7,
        "points_for": 3500,
        "points_against": 3200,
        "win_last_10": 7
    }
    
    away_stats = {
        "team_id": 2,
        "games_played": 30,
        "win": 15,
        "loss": 15,
        "win_home": 10,
        "loss_home": 5,
        "win_away": 5,
        "loss_away": 10,
        "points_for": 3400,
        "points_against": 3300,
        "win_last_10": 4
    }
    
    features = engine.generate_team_features(1, 2, home_stats, away_stats)
    print(f"Team features ({len(features)}):")
    for k, v in list(features.items())[:10]:
        print(f"  {k}: {v:.3f}")
    
    # Test market features
    market_feats = engine.generate_market_features(
        home_odds=1.90,
        away_odds=2.00,
        spread=-3.5,
        total=225.0
    )
    print(f"\nMarket features ({len(market_feats)}):")
    for k, v in market_feats.items():
        print(f"  {k}: {v:.3f}")
    
    # Test injury features
    injury_feats = engine.generate_injury_features(
        home_missing=[
            {"name": "Star Player", "is_key_player": True, "severity_impact": 0.8}
        ],
        away_missing=[
            {"name": "Role Player", "is_key_player": False, "severity_impact": 0.3}
        ]
    )
    print(f"\nInjury features:")
    for k, v in injury_feats.items():
        print(f"  {k}: {v}")
    
    print("\n[NBA Feature Engineering Test Complete]")