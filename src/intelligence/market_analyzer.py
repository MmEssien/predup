"""Market Intelligence - Inefficiency & Sharp Money Detection"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import logging
import numpy as np

logger = logging.getLogger(__name__)


class SignalType(Enum):
    EFFICIENT = "efficient"
    MISPRICING = "mispricing"
    SHARP_MONEY = "sharp_money"
    REVERSE_LINE = "reverse_line"
    STEAM_MOVE = "steam_move"


@dataclass
class MarketSignal:
    """Result of market analysis"""
    signal_type: SignalType
    confidence: float
    edge_estimate: float
    description: str
    recommended_action: str  # "back", "lay", "pass"
    details: Dict[str, Any]


class MarketAnalyzer:
    """Analyze market inefficiencies and detect sharp money"""
    
    # Sharp bookmakers (high limits, professional bettors)
    SHARP_BOOKS = ["pinnacle", "bet365", "williamhill", "unibet", "bwin"]
    
    # Soft bookmakers (retail, slower to react)
    SOFT_BOOKS = ["betway", "1xbet", "betano", "marathon", "various"]
    
    def __init__(
        self,
        # Inefficiency thresholds
        divergence_threshold: float = 0.15,      # 15% model vs market divergence
        inefficiency_confirm_threshold: float = 0.10,  # 10% to confirm signal
        
        # Sharp money settings
        sharp_movement_threshold: float = 0.08,  # 8% late movement
        steam_move_threshold: float = 0.10,      # 10% rapid movement
        
        # Bookmaker disagreement
        max_bookmaker_spread: float = 0.12         # 12% max spread
    ):
        self.divergence_threshold = divergence_threshold
        self.inefficiency_confirm_threshold = inefficiency_confirm_threshold
        self.sharp_movement_threshold = sharp_movement_threshold
        self.steam_move_threshold = steam_move_threshold
        self.max_bookmaker_spread = max_bookmaker_spread
    
    def analyze_market(
        self,
        model_probability: float,
        odds_history: List[Dict[str, Any]],
        news_signals: Optional[Dict[str, Any]] = None
    ) -> MarketSignal:
        """Comprehensive market analysis"""
        
        if not odds_history:
            return self._empty_signal()
        
        # Get current and opening odds
        current_odds = self._get_current_odds(odds_history)
        opening_odds = self._get_opening_odds(odds_history)
        
        if not current_odds or not opening_odds:
            return self._empty_signal()
        
        # Calculate market implied probability
        current_implied = 1 / current_odds.get("home_odds", 2.0)
        
        # Check divergence
        divergence = abs(model_probability - current_implied)
        
        # Detect sharp money movement
        sharp_signal = self._detect_sharp_movement(opening_odds, current_odds)
        
        # Check reverse line movement
        rlm_signal = self._detect_reverse_line_movement(
            model_probability, opening_odds, current_odds
        )
        
        # Bookmaker disagreement
        disagreement = self._calculate_disagreement(odds_history)
        
        # Combine signals
        return self._combine_signals(
            divergence=divergence,
            model_prob=model_probability,
            market_implied=current_implied,
            sharp_signal=sharp_signal,
            rlm_signal=rlm_signal,
            disagreement=disagreement,
            news_signals=news_signals
        )
    
    def _get_current_odds(self, odds_history: List[Dict]) -> Optional[Dict]:
        """Get most recent odds"""
        if not odds_history:
            return None
        return sorted(odds_history, key=lambda x: x.get("fetched_at", 0), reverse=True)[0]
    
    def _get_opening_odds(self, odds_history: List[Dict]) -> Optional[Dict]:
        """Get earliest odds"""
        if not odds_history:
            return None
        return sorted(odds_history, key=lambda x: x.get("fetched_at", 0))[0]
    
    def _detect_sharp_movement(
        self,
        opening: Dict,
        current: Dict
    ) -> Optional[Dict[str, Any]]:
        """Detect sharp money movement"""
        
        if not opening or not current:
            return None
        
        # Calculate percentage movement
        opening_home = opening.get("home_odds", 2.0)
        current_home = current.get("home_odds", 2.0)
        
        if opening_home > 0:
            home_movement = (current_home - opening_home) / opening_home
        else:
            home_movement = 0
        
        # Sharp movement: significant late movement toward one side
        # Positive = line moved toward home, negative = toward away
        if abs(home_movement) > self.sharp_movement_threshold:
            direction = "home" if home_movement > 0 else "away"
            
            # Check if it's sharp (moved toward sharp bookmaker consensus)
            return {
                "detected": True,
                "direction": direction,
                "movement_pct": home_movement * 100,
                "confidence": min(abs(home_movement) * 2, 1.0)
            }
        
        return {"detected": False}
    
    def _detect_reverse_line_movement(
        self,
        model_prob: float,
        opening: Dict,
        current: Dict
    ) -> Optional[Dict[str, Any]]:
        """Detect reverse line movement (RLM)"""
        
        if not opening or not current:
            return None
        
        # RLM: Line moves opposite to where sharp money is betting
        # If model likes home, but line moved toward away = RLM
        
        opening_home = opening.get("home_odds", 2.0)
        current_home = current.get("home_odds", 2.0)
        
        # Line moved toward away?
        line_moved_toward_away = current_home > opening_home
        
        # Model likes home?
        model_likes_home = model_prob > 0.5
        
        # If both true = reverse line movement (caution)
        if line_moved_toward_away and model_likes_home:
            return {
                "detected": True,
                "type": "warning",
                "description": "Line moved away from model pick",
                "confidence": min(abs(current_home - opening_home) / opening_home * 3, 1.0) if opening_home > 0 else 0
            }
        
        # Model likes away but line moved toward home
        if not line_moved_toward_away and not model_likes_home:
            return {
                "detected": True,
                "type": "warning", 
                "description": "Line moved toward model pick (confirming)",
                "confidence": min(abs(current_home - opening_home) / opening_home * 3, 1.0) if opening_home > 0 else 0
            }
        
        return {"detected": False}
    
    def _calculate_disagreement(self, odds_history: List[Dict]) -> float:
        """Calculate bookmaker disagreement (0-1)"""
        
        if len(odds_history) < 2:
            return 0
        
        # Group by bookmaker and get latest
        latest_by_book = {}
        for odds in odds_history:
            book = odds.get("bookmaker", "unknown")
            if book not in latest_by_book:
                latest_by_book[book] = odds
        
        if len(latest_by_book) < 2:
            return 0
        
        # Calculate spread
        home_odds = [o.get("home_odds", 2.0) for o in latest_by_book.values() if o.get("home_odds")]
        
        if len(home_odds) < 2:
            return 0
        
        # Normalized spread
        mean_odds = np.mean(home_odds)
        spread = (max(home_odds) - min(home_odds)) / mean_odds if mean_odds > 0 else 0
        
        return min(spread, 1.0)
    
    def _combine_signals(
        self,
        divergence: float,
        model_prob: float,
        market_implied: float,
        sharp_signal: Optional[Dict],
        rlm_signal: Optional[Dict],
        disagreement: float,
        news_signals: Optional[Dict]
    ) -> MarketSignal:
        """Combine all signals into final recommendation"""
        
        # Start with inefficiency check
        if divergence < self.divergence_threshold:
            return MarketSignal(
                signal_type=SignalType.EFFICIENT,
                confidence=1.0 - (divergence / self.divergence_threshold),
                edge_estimate=0,
                description="Market appears efficient",
                recommended_action="pass",
                details={"divergence": divergence}
            )
        
        # Check if divergence is justified by news
        if news_signals and news_signals.get("has_significant_news"):
            # News explains the movement
            edge_estimate = divergence
            action = "follow_market" if (model_prob < market_implied) else "fade_market"
            
            return MarketSignal(
                signal_type=SignalType.EFFICIENT,
                confidence=0.8,
                edge_estimate=edge_estimate,
                description=f"Divergence justified by news: {news_signals.get('summary', 'N/A')}",
                recommended_action=action,
                details={"divergence": divergence, "news_justified": True}
            )
        
        # Divergence without news justification = potential mispricing
        edge_estimate = divergence - self.inefficiency_confirm_threshold
        
        # Check sharp money signal
        if sharp_signal and sharp_signal.get("detected"):
            # Sharp money is on the other side = fade
            if (sharp_signal["direction"] == "home" and model_prob < 0.5) or \
               (sharp_signal["direction"] == "away" and model_prob > 0.5):
                # Sharp money opposite to model = fade
                return MarketSignal(
                    signal_type=SignalType.SHARP_MONEY,
                    confidence=sharp_signal.get("confidence", 0.5),
                    edge_estimate=-(edge_estimate * 0.5),  # Negative edge
                    description=f"Sharp money fading model: {sharp_signal['direction']}",
                    recommended_action="pass",
                    details={"sharp_signal": sharp_signal, "divergence": divergence}
                )
        
        # Check RLM
        if rlm_signal and rlm_signal.get("detected"):
            if rlm_signal.get("type") == "warning" and "confirming" in rlm_signal.get("description", ""):
                # Line confirming model = back
                return MarketSignal(
                    signal_type=SignalType.REVERSE_LINE,
                    confidence=rlm_signal.get("confidence", 0.5),
                    edge_estimate=edge_estimate,
                    description="Line movement confirms model",
                    recommended_action="back",
                    details={"rlm": rlm_signal, "divergence": divergence}
                )
        
        # Default: model has edge
        if model_prob > market_implied:
            return MarketSignal(
                signal_type=SignalType.MISPRICING,
                confidence=min(divergence * 2, 1.0),
                edge_estimate=edge_estimate,
                description=f"Potential mispricing: model {model_prob:.2%} vs market {market_implied:.2%}",
                recommended_action="back",
                details={
                    "divergence": divergence,
                    "model_prob": model_prob,
                    "market_implied": market_implied
                }
            )
        else:
            # Market has higher probability = pass or fade
            return MarketSignal(
                signal_type=SignalType.MISPRICING,
                confidence=min(divergence * 2, 1.0),
                edge_estimate=-edge_estimate,
                description=f"Market overvaluing: model {model_prob:.2%} vs market {market_implied:.2%}",
                recommended_action="fade" if divergence > 0.20 else "pass",
                details={
                    "divergence": divergence,
                    "model_prob": model_prob,
                    "market_implied": market_implied
                }
            )
    
    def _empty_signal(self) -> MarketSignal:
        """Return empty signal"""
        return MarketSignal(
            signal_type=SignalType.EFFICIENT,
            confidence=0,
            edge_estimate=0,
            description="Insufficient data",
            recommended_action="pass",
            details={}
        )
    
    def get_odds_movement_velocity(self, odds_history: List[Dict]) -> float:
        """Calculate how fast odds are moving (late movement = sharp indicator)"""
        
        if len(odds_history) < 2:
            return 0
        
        # Sort by time
        sorted_odds = sorted(odds_history, key=lambda x: x.get("fetched_at", 0))
        
        # Get odds from last 2 hours before match (if timestamp available)
        # Otherwise use first vs last
        first = sorted_odds[0]
        last = sorted_odds[-1]
        
        if first.get("home_odds") and last.get("home_odds"):
            movement = abs(last["home_odds"] - first["home_odds"]) / first["home_odds"]
            return movement
        
        return 0
    
    def identify_sharp_soft_split(
        self,
        odds_history: List[Dict]
    ) -> Dict[str, Any]:
        """Identify sharp vs soft bookmaker divergence"""
        
        sharp_odds = []
        soft_odds = []
        
        for odds in odds_history:
            book = odds.get("bookmaker", "").lower()
            if book in self.SHARP_BOOKS:
                sharp_odds.append(odds.get("home_odds", 2.0))
            elif book in self.SOFT_BOOKS:
                soft_odds.append(odds.get("home_odds", 2.0))
        
        if not sharp_odds or not soft_odds:
            return {"detected": False}
        
        sharp_avg = np.mean(sharp_odds)
        soft_avg = np.mean(soft_odds)
        
        divergence = abs(sharp_avg - soft_avg) / sharp_avg
        
        if divergence > 0.05:  # 5% divergence is significant
            return {
                "detected": True,
                "sharp_avg": sharp_avg,
                "soft_avg": soft_avg,
                "divergence_pct": divergence * 100,
                "direction": "soft_higher" if soft_avg > sharp_avg else "sharp_higher"
            }
        
        return {"detected": False}


class SharpMoneyDetector:
    """Dedicated sharp money detection"""
    
    def __init__(self):
        self.SHARP_BOOKS = MarketAnalyzer.SHARP_BOOKS.copy()
        self.SOFT_BOOKS = MarketAnalyzer.SOFT_BOOKS.copy()
    
    def detect(
        self,
        odds_at_1hr: Dict[str, float],      # Odds 1 hour before
        odds_at_30min: Dict[str, float],     # Odds 30 min before
        odds_at_kickoff: Dict[str, float],   # Closing odds
        sharp_book_odds: Dict[str, float],  # Sharp bookmaker odds
        soft_book_odds: Dict[str, float]    # Soft bookmaker odds
    ) -> Dict[str, Any]:
        """Comprehensive sharp money detection"""
        
        signals = []
        
        # 1. Late steam move (1hr -> 30min -> kickoff)
        if odds_at_1hr and odds_at_kickoff:
            movement_1hr = abs(odds_at_kickoff.get("home_odds", 2.0) - 
                              odds_at_1hr.get("home_odds", 2.0)) / odds_at_1hr.get("home_odds", 2.0)
            
            if movement_1hr > 0.10:
                signals.append({
                    "type": "steam_move",
                    "confidence": min(movement_1hr * 2, 1.0),
                    "direction": "home" if odds_at_kickoff["home_odds"] < odds_at_1hr["home_odds"] else "away"
                })
        
        # 2. Sharp vs soft divergence
        if sharp_book_odds and soft_book_odds:
            divergence = abs(sharp_book_odds.get("home_odds", 2.0) - 
                           soft_book_odds.get("home_odds", 2.0)) / sharp_book_odds.get("home_odds", 2.0)
            
            if divergence > 0.05:
                direction = "sharp_advantage" if sharp_book_odds["home_odds"] < soft_book_odds["home_odds"] else "soft_advantage"
                signals.append({
                    "type": "sharp_soft_divergence",
                    "confidence": min(divergence * 3, 1.0),
                    "direction": direction,
                    "divergence_pct": divergence * 100
                })
        
        # 3. Reverse line movement
        # (tracked elsewhere, check signals)
        
        # Determine overall signal
        if not signals:
            return {"signal": "none", "confidence": 0, "signals": []}
        
        strongest = max(signals, key=lambda x: x["confidence"])
        
        return {
            "signal": strongest["type"],
            "confidence": strongest["confidence"],
            "direction": strongest.get("direction"),
            "signals": signals,
            "recommendation": self._get_recommendation(strongest)
        }
    
    def _get_recommendation(self, signal: Dict) -> str:
        """Get recommendation based on sharp money signal"""
        
        sig_type = signal.get("type", "")
        
        if sig_type == "steam_move":
            # Follow steam early, fade late
            if signal.get("confidence", 0) > 0.7:
                return "follow_steam"
            return "caution"
        
        if sig_type == "sharp_soft_divergence":
            # Follow sharp books
            if "sharp" in signal.get("direction", ""):
                return "follow_sharp"
            return "fade_soft"
        
        return "neutral"