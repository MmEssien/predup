"""
Sport-Specific Prediction Engines
Each engine handles sport-specific logic and probability calculation
"""

import logging
from typing import Dict, List, Optional
from src.intelligence.base_prediction_engine import (
    BasePredictionEngine, UnifiedPrediction, register_sport
)
from src.intelligence.fixture_normalizer import normalize_fixtures, NormalizedFixture

logger = logging.getLogger(__name__)


@register_sport("football")
class FootballPredictionEngine(BasePredictionEngine):
    """Football prediction engine with model integration"""
    
    sport_name = "football"
    league_name = "EPL"
    _fixtures_cache = []
    
    def __init__(self, api_key: Optional[str] = None, odds_adapter=None):
        super().__init__(api_key, odds_adapter)
        self._client = None
        self._model = None
    
    @property
    def client(self):
        if self._client is None:
            from src.data.api_football_client import ApiFootballClient
            self._client = ApiFootballClient(self.api_key or "")
        return self._client
    
    def get_fixtures(self, days_ahead: int = 1) -> List[Dict]:
        """Fetch and normalize football fixtures"""
        from datetime import datetime
        from src.intelligence.fixture_normalizer import normalize_fixtures
        
        # Get today's fixtures
        today = datetime.now().strftime("%Y-%m-%d")
        data = self.client.get_fixtures(date=today)
        raw_fixtures = data.get("response", [])
        
        # Normalize
        normalized = normalize_fixtures(raw_fixtures, "football")
        
        logger.info(f"[FOOTBALL] Fetched {len(raw_fixtures)} fixtures, normalized {len(normalized)}")
        
        # Convert back to dict for adapter compatibility
        return [n.to_dict() for n in normalized]
    
    def build_features(self, fixture: Dict) -> Dict:
        """Build features from normalized fixture"""
        return {
            "home_team": fixture.get("home_team", ""),
            "away_team": fixture.get("away_team", ""),
            "league": fixture.get("league", ""),
            "venue": fixture.get("venue"),
            "home_advantage": 0.03,  # Typical home advantage
        }
    
    def compute_probability(self, features: Dict) -> float:
        """Compute probability using model if available, else skip"""
        # Try to load and use trained model
        if self._model is None:
            self._load_model()
        
        if self._model:
            # Use model prediction
            return self._model.predict_proba(features)[0]
        
        # NO MODEL = NO PREDICTION
        # Don't fall back to baseline - that corrupts everything
        logger.warning(f"[FOOTBALL] No trained model available - SKIP")
        return None
    
    def _load_model(self):
        """Load trained football model if exists"""
        import os
        model_path = "models/football_model.pkl"
        if os.path.exists(model_path):
            try:
                import pickle
                with open(model_path, "rb") as f:
                    self._model = pickle.load(f)
                logger.info(f"[FOOTBALL] Model loaded")
            except Exception as e:
                logger.warning(f"[FOOTBALL] Model load failed: {e}")
    
    def predict_batch(self, fixtures: List[Dict]) -> List[UnifiedPrediction]:
        """Generate predictions with STRICT model requirement"""
        predictions = []
        
        for fixture in fixtures:
            try:
                # Skip if missing teams
                if not fixture.get("home_team") or not fixture.get("away_team"):
                    continue
                
                # Get odds
                home = fixture.get("home_team", "")
                away = fixture.get("away_team", "")
                
                odds_data = self.fetch_odds(home, away)
                
                if not odds_data:
                    logger.warning(f"[FOOTBALL] ODDS MISSING: {home} vs {away} - SKIP")
                    continue
                
                # Compute probability using model
                features = self.build_features(fixture)
                model_prob = self.compute_probability(features)
                
                if model_prob is None:
                    # No model - skip this game
                    continue
                
                # Build prediction
                pred = self._build_prediction(fixture, model_prob, odds_data)
                if pred:
                    predictions.append(pred)
                    
            except Exception as e:
                logger.error(f"[FOOTBALL] Prediction error: {e}")
        
        logger.info(f"[FOOTBALL] Generated {len(predictions)} predictions")
        return predictions
    
    def _build_prediction(self, fixture: Dict, model_prob: float, odds_data: Dict) -> Optional[UnifiedPrediction]:
        """Build unified prediction"""
        home = fixture.get("home_team", "")
        away = fixture.get("away_team", "")
        
        home_odds = odds_data.get("home_odds", 2.0)
        away_odds = odds_data.get("away_odds", 2.0)
        
        implied_home = 1 / home_odds
        implied_away = 1 / away_odds
        total = implied_home + implied_away
        
        devig_home = implied_home / total
        
        edge_home, ev_home = self.compute_ev(devig_home, home_odds, implied_home)
        edge_away, ev_away = self.compute_ev(1 - devig_home, away_odds, implied_away)
        
        if ev_home >= ev_away:
            bet_on = "home"
            final_prob = devig_home
            final_odds = home_odds
            final_edge = edge_home
            final_ev = ev_home
            implied_prob = implied_home
        else:
            bet_on = "away"
            final_prob = 1 - devig_home
            final_odds = away_odds
            final_edge = edge_away
            final_ev = ev_away
            implied_prob = implied_away
        
        confidence = self.determine_confidence(final_prob)
        
        return UnifiedPrediction(
            sport=self.sport_name,
            fixture_id=str(fixture.get("fixture_id", "")),
            home_team=home,
            away_team=away,
            bet_on=bet_on,
            model_probability=final_prob,
            odds=final_odds,
            implied_probability=implied_prob,
            edge=final_edge,
            ev=final_ev,
            ev_pct=final_ev * 100,
            confidence=confidence,
            start_time=fixture.get("start_time", ""),
            league=self.league_name
        )


@register_sport("mlb")
class MLBPredictionEngine(BasePredictionEngine):
    """MLB prediction engine"""
    
    sport_name = "mlb"
    league_name = "MLB"
    
    def __init__(self, api_key: Optional[str] = None, odds_adapter=None):
        super().__init__(api_key, odds_adapter)
        self._adapter = None
        self._model = None
    
    @property
    def adapter(self):
        if self._adapter is None:
            from src.data.mlb_adapter import MLBAdapter
            self._adapter = MLBAdapter()
        return self._adapter
    
    def get_fixtures(self, days_ahead: int = 1) -> List[Dict]:
        """Fetch MLB fixtures and normalize"""
        raw = self.adapter.get_fixtures(days_ahead=days_ahead)
        
        # Normalize via fixture normalizer
        normalized = normalize_fixtures(raw, "mlb")
        
        logger.info(f"[MLB] Fetched {len(raw)} fixtures, normalized {len(normalized)}")
        
        return [n.to_dict() for n in normalized]
    
    def build_features(self, fixture: Dict) -> Dict:
        """Build MLB-specific features"""
        return {
            "home_team": fixture.get("home_team", ""),
            "away_team": fixture.get("away_team", ""),
            "venue": fixture.get("venue"),
        }
    
    def compute_probability(self, features: Dict) -> float:
        """Compute probability - requires ML model"""
        if self._model is None:
            self._load_model()
        
        if self._model:
            return self._model.predict_proba(features)[0]
        
        logger.warning(f"[MLB] No trained model - SKIP")
        return None
    
    def _load_model(self):
        """Load MLB model"""
        import os
        model_path = "models/mlb_model.pkl"
        if os.path.exists(model_path):
            try:
                import pickle
                with open(model_path, "rb") as f:
                    self._model = pickle.load(f)
                logger.info(f"[MLB] Model loaded")
            except:
                pass
    
    def predict_batch(self, fixtures: List[Dict]) -> List[UnifiedPrediction]:
        """Generate predictions with STRICT model requirement"""
        predictions = []
        
        for fixture in fixtures:
            try:
                if not fixture.get("home_team") or not fixture.get("away_team"):
                    continue
                
                home = fixture.get("home_team", "")
                away = fixture.get("away_team", "")
                
                odds_data = self.fetch_odds(home, away)
                
                if not odds_data:
                    logger.warning(f"[MLB] ODDS MISSING: {home} vs {away} - SKIP")
                    continue
                
                features = self.build_features(fixture)
                model_prob = self.compute_probability(features)
                
                if model_prob is None:
                    continue
                
                pred = self._build_prediction(fixture, model_prob, odds_data)
                if pred:
                    predictions.append(pred)
                    
            except Exception as e:
                logger.error(f"[MLB] Error: {e}")
        
        logger.info(f"[MLB] Generated {len(predictions)} predictions")
        return predictions
    
    def _build_prediction(self, fixture: Dict, model_prob: float, odds_data: Dict) -> Optional[UnifiedPrediction]:
        """Build prediction"""
        home = fixture.get("home_team", "")
        away = fixture.get("away_team", "")
        
        home_odds = odds_data.get("home_odds", 2.0)
        away_odds = odds_data.get("away_odds", 2.0)
        
        implied_home = 1 / home_odds
        implied_away = 1 / away_odds
        total = implied_home + implied_away
        
        devig_home = implied_home / total
        
        edge_home, ev_home = self.compute_ev(devig_home, home_odds, implied_home)
        edge_away, ev_away = self.compute_ev(1 - devig_home, away_odds, implied_away)
        
        if ev_home >= ev_away:
            bet_on = "home"
            final_prob = devig_home
            final_odds = home_odds
            final_edge = edge_home
            final_ev = ev_home
            implied_prob = implied_home
        else:
            bet_on = "away"
            final_prob = 1 - devig_home
            final_odds = away_odds
            final_edge = edge_away
            final_ev = ev_away
            implied_prob = implied_away
        
        confidence = self.determine_confidence(final_prob)
        
        return UnifiedPrediction(
            sport=self.sport_name,
            fixture_id=str(fixture.get("fixture_id", "")),
            home_team=home,
            away_team=away,
            bet_on=bet_on,
            model_probability=final_prob,
            odds=final_odds,
            implied_probability=implied_prob,
            edge=final_edge,
            ev=final_ev,
            ev_pct=final_ev * 100,
            confidence=confidence,
            start_time=fixture.get("start_time", ""),
            league=self.league_name
        )


@register_sport("nba")
class NBAPredictionEngine(BasePredictionEngine):
    """NBA prediction engine"""
    
    sport_name = "nba"
    league_name = "NBA"
    
    def __init__(self, api_key: Optional[str] = None, odds_adapter=None):
        super().__init__(api_key, odds_adapter)
        self._adapter = None
        self._model = None
    
    @property
    def adapter(self):
        if self._adapter is None:
            from src.data.nba_adapter import NBAAdapter
            self._adapter = NBAAdapter(self.api_key)
        return self._adapter
    
    def get_fixtures(self, days_ahead: int = 1) -> List[Dict]:
        """Fetch NBA fixtures"""
        raw = self.adapter.get_fixtures(days_ahead=days_ahead)
        
        if not raw:
            logger.info(f"[NBA] No fixtures (off-season)")
            return []
        
        normalized = normalize_fixtures(raw, "nba")
        logger.info(f"[NBA] Fetched {len(raw)} fixtures, normalized {len(normalized)}")
        
        return [n.to_dict() for n in normalized]
    
    def build_features(self, fixture: Dict) -> Dict:
        """Build NBA features"""
        return {
            "home_team": fixture.get("home_team", ""),
            "away_team": fixture.get("away_team", ""),
        }
    
    def compute_probability(self, features: Dict) -> float:
        """Compute probability - requires NBA model"""
        if self._model is None:
            self._load_model()
        
        if self._model:
            return self._model.predict_proba(features)[0]
        
        logger.warning(f"[NBA] No trained model - SKIP")
        return None
    
    def _load_model(self):
        """Load NBA model"""
        import os
        model_path = "models/nba_model.pkl"
        if os.path.exists(model_path):
            try:
                import pickle
                with open(model_path, "rb") as f:
                    self._model = pickle.load(f)
                logger.info(f"[NBA] Model loaded")
            except:
                pass
    
    def predict_batch(self, fixtures: List[Dict]) -> List[UnifiedPrediction]:
        """Generate predictions"""
        predictions = []
        
        for fixture in fixtures:
            try:
                if not fixture.get("home_team") or not fixture.get("away_team"):
                    continue
                
                home = fixture.get("home_team", "")
                away = fixture.get("away_team", "")
                
                odds_data = self.fetch_odds(home, away)
                
                if not odds_data:
                    logger.warning(f"[NBA] ODDS MISSING: {home} vs {away} - SKIP")
                    continue
                
                features = self.build_features(fixture)
                model_prob = self.compute_probability(features)
                
                if model_prob is None:
                    continue
                
                pred = self._build_prediction(fixture, model_prob, odds_data)
                if pred:
                    predictions.append(pred)
                    
            except Exception as e:
                logger.error(f"[NBA] Error: {e}")
        
        logger.info(f"[NBA] Generated {len(predictions)} predictions")
        return predictions
    
    def _build_prediction(self, fixture: Dict, model_prob: float, odds_data: Dict) -> Optional[UnifiedPrediction]:
        """Build prediction"""
        home = fixture.get("home_team", "")
        away = fixture.get("away_team", "")
        
        home_odds = odds_data.get("home_odds", 2.0)
        away_odds = odds_data.get("away_odds", 2.0)
        
        implied_home = 1 / home_odds
        implied_away = 1 / away_odds
        total = implied_home + implied_away
        
        devig_home = implied_home / total
        
        edge_home, ev_home = self.compute_ev(devig_home, home_odds, implied_home)
        edge_away, ev_away = self.compute_ev(1 - devig_home, away_odds, implied_away)
        
        if ev_home >= ev_away:
            bet_on = "home"
            final_prob = devig_home
            final_odds = home_odds
            final_edge = edge_home
            final_ev = ev_home
            implied_prob = implied_home
        else:
            bet_on = "away"
            final_prob = 1 - devig_home
            final_odds = away_odds
            final_edge = edge_away
            final_ev = ev_away
            implied_prob = implied_away
        
        confidence = self.determine_confidence(final_prob)
        
        return UnifiedPrediction(
            sport=self.sport_name,
            fixture_id=str(fixture.get("fixture_id", "")),
            home_team=home,
            away_team=away,
            bet_on=bet_on,
            model_probability=final_prob,
            odds=final_odds,
            implied_probability=implied_prob,
            edge=final_edge,
            ev=final_ev,
            ev_pct=final_ev * 100,
            confidence=confidence,
            start_time=fixture.get("start_time", ""),
            league=self.league_name
        )