"""
Unified Odds Engine
==================
PRIMARY → The Odds API (reliable, fast)
SECONDARY → SportsGameOdds (5s timeout - fail fast)
TERTIARY → OddsPortal (async only - too slow for live)

Rules:
- No simulated odds in production
- Source confidence scoring
- Return NO_VALID_ODDS if all fail (never simulate)
"""

# Source confidence scores (0-1 scale)
SOURCE_CONFIDENCE = {
    "oddsapi": 0.95,      # Working reliably
    "sportsgameodds": 0.75, # Unstable, needs fix
    "oddsportal": 0.45,   # JS rendering, async only
}

# Priority: OddsAPI first (fast + reliable), skip scraper for live
# SportsGameOdds has 5s timeout so won't stall
SPORT_PRIORITY = {
    "football": ["oddsapi", "sportsgameodds"],
    "nba": ["oddsapi", "sportsgameodds"],
    "mlb": ["oddsapi", "sportsgameodds"],
    "nfl": ["oddsapi", "sportsgameodds"],
}

import os
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
load_dotenv(override=False)

logger = logging.getLogger(__name__)


class UnifiedOddsEngine:
    """
    Unified odds engine with tiered priority:
    1. SportsGameOdds (primary for NBA/MLB/NFL)
    2. Odds API (primary for Football, secondary for others with quota)
    3. OddsPortal scraper (tertiary fallback)
    """
    
    # Sport-specific priority mapping
    # OddsAPI works reliably, SportsGameOdds returning 302 (endpoint issues)
    SPORT_PRIORITY = {
        "football": ["oddsapi", "oddsportal", "sportsgameodds"],
        "nba": ["oddsapi", "oddsportal", "sportsgameodds"],
        "mlb": ["oddsapi", "oddsportal", "sportsgameodds"],
        "nfl": ["oddsapi", "oddsportal", "sportsgameodds"],
    }
    
    def __init__(self):
        # Initialize adapters (lazy loaded in priority order)
        self._sportsgameodds = None
        self._oddsapi = None
        self._oddsportal = None
        
        # Stats
        self._total_requests = 0
        self._by_source = {
            "oddsportal": 0,
            "oddsapi": 0,
            "sportsgameodds": 0,
            "none": 0
        }
        self._latencies = []
        
        logger.info("[ODDS ENGINE] Unified Odds Engine initialized - PRIMARY: OddsPortal")
    
    @property
    def sportsgameodds(self):
        """Lazy load SportsGameOdds adapter"""
        if self._sportsgameodds is None:
            try:
                from src.data.sportsgameodds_adapter import SportsGameOddsAdapter
                self._sportsgameodds = SportsGameOddsAdapter()
            except Exception as e:
                logger.warning(f"[ODDS ENGINE] SportsGameOdds unavailable: {e}")
        return self._sportsgameodds
    
    @property
    def oddsapi(self):
        """Lazy load Odds API adapter"""
        if self._oddsapi is None:
            try:
                from src.data.oddsapi_adapter import OddsAPIAdapter
                self._oddsapi = OddsAPIAdapter()
            except Exception as e:
                logger.warning(f"[ODDS ENGINE] OddsAPI unavailable: {e}")
        return self._oddsapi
    
    @property
    def oddsportal(self):
        """Lazy load OddsPortal adapter - returns class, not instance"""
        # OddsPortal is async, so we return the class and create instance per call
        try:
            from src.data.oddsportal_adapter import OddsPortalAdapter
            return OddsPortalAdapter
        except Exception as e:
            logger.warning(f"[ODDS ENGINE] OddsPortal unavailable: {e}")
            return None
    
    def get_odds(
        self, 
        sport: str, 
        home_team: str, 
        away_team: str,
        league: str = None,
        force_refresh: bool = False
    ) -> Optional[Dict]:
        """
        Get odds using sport-specific tiered priority.
        
        League tier determines odds requirements:
        - Tier 1: Full odds (SportsGameOdds/OddsAPI)
        - Tier 2: Optional odds (OddsAPI)
        - Tier 3: Model-only (skip odds engine)
        
        Returns:
            Dict with unified schema OR None if unavailable
        """
        from src.data.league_tiers import get_league_tier, should_skip_odds_engine
        
        start_time = time.time()
        self._total_requests += 1
        
        # Check league tier
        tier = get_league_tier(league or "")
        
        # Tier 3 = model-only, skip odds API calls entirely
        if should_skip_odds_engine(tier):
            logger.debug(f"[ODDS ENGINE] Tier 3 league {league} - skipping odds engine")
            self._by_source["none"] += 1
            return None
        
        result = None
        source = "none"
        reason = ""
        
        # Get priority order for this sport
        priority_order = self.SPORT_PRIORITY.get(sport.lower(), 
                          self.SPORT_PRIORITY.get("nba", ["sportsgameodds", "oddsapi", "oddsportal"]))
        
        # Try sources in priority order
        for src in priority_order:
            if result:
                break
            print(f"[ODDS ENGINE DEBUG] Trying source: {src}")
            if src == "oddsportal" and self.oddsportal:
                try:
                    # OddsPortal is async - create instance and run in thread
                    adapter_class = self.oddsportal
                    if adapter_class:
                        # Create instance
                        adapter = adapter_class()
                        
                        # Run async methods in thread
                        import asyncio
                        from concurrent.futures import ThreadPoolExecutor
                        
                        def run_async(coro):
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            return loop.run_until_complete(coro)
                        
                        # Check availability
                        available = run_async(adapter.is_available())
                        if available:
                            result = run_async(
                                adapter.get_odds(
                                    sport, home_team, away_team,
                                    use_cache=not force_refresh
                                )
                            )
                            if result:
                                source = "oddsportal"
                        
                        # Close adapter
                        run_async(adapter.close())
                        
                except Exception as e:
                    logger.debug(f"[ODDS ENGINE] oddsportal failed: {e}")
                    continue
            elif src == "oddsapi" and self.oddsapi:
                try:
                    if self.oddsapi.quota.can_request():
                        result = self.oddsapi.get_odds(
                            sport, home_team, away_team,
                            use_cache=not force_refresh
                        )
                        if result:
                            source = "oddsapi"
                except Exception as e:
                    logger.debug(f"[ODDS ENGINE] oddsapi failed: {e}")
                    continue
            elif src == "sportsgameodds" and self.sportsgameodds:
                try:
                    result = self.sportsgameodds.get_odds(
                        sport, home_team, away_team, 
                        use_cache=not force_refresh
                    )
                    if result:
                        source = "sportsgameodds"
                except Exception as e:
                    logger.debug(f"[ODDS ENGINE] sportsgameodds failed: {e}")
                    continue
        
# Calculate latency
        latency = time.time() - start_time
        self._latencies.append(latency)
        
        # Record stats
        self._by_source[source] += 1
        
        # Get confidence based on tier
        from src.data.league_tiers import get_confidence_weight
        tier_confidence = get_confidence_weight(tier)
        
        # Get source confidence
        source_confidence = SOURCE_CONFIDENCE.get(source, 0.5)
        
        # Log final result
        if result:
            result["request_latency"] = latency
            result["priority_source"] = True
            result["cache_status"] = "fresh" if not force_refresh else "forced"
            result["league_tier"] = tier
            result["tier_confidence"] = tier_confidence
            result["source_confidence"] = source_confidence
            result["combined_confidence"] = round(tier_confidence * source_confidence, 2)
            
            # Archive odds for line tracking (Phase 2)
            try:
                from src.data.odds_archive import get_odds_archive
                archive = get_odds_archive()
                archive.save(result)
            except Exception as e:
                logger.debug(f"[ODDS ENGINE] Archive error: {e}")
            
            logger.info(f"[ODDS ENGINE] SUCCESS | {sport} | {home_team} vs {away_team} | "
                       f"Source: {source} | Tier: {tier} | Conf: {result['combined_confidence']} | Latency: {latency:.3f}s")
            
            return result
        else:
            logger.warning(f"[ODDS ENGINE] NO VALID ODDS | {sport} | {home_team} vs {away_team} | "
                           f"Tier: {tier} | All sources failed | Latency: {latency:.3f}s")
            return None
    
    def get_odds_batch(
        self, 
        sport: str, 
        fixtures: List[Dict],
        force_refresh: bool = False
    ) -> List[Dict]:
        """
        Fetch odds for multiple fixtures efficiently.
        
        Args:
            sport: football, mlb, nba
            fixtures: List of {home_team, away_team, fixture_id}
            force_refresh: Skip cache
        
        Returns:
            List of normalized odds data
        """
        results = []
        
        for fixture in fixtures[:30]:  # Limit batch
            home = fixture.get("home_team", "")
            away = fixture.get("away_team", "")
            fixture_id = fixture.get("fixture_id", "")
            
            odds = self.get_odds(sport, home, away, force_refresh=force_refresh)
            
            if odds:
                odds["fixture_id"] = fixture_id
                results.append(odds)
        
        logger.info(f"[ODDS ENGINE] Batch complete: {len(results)}/{len(fixtures)} odds fetched")
        return results
    
    def get_system_status(self) -> Dict:
        """Get system status for all sources"""
        return {
            "total_requests": self._total_requests,
            "by_source": self._by_source,
            "avg_latency": sum(self._latencies) / len(self._latencies) if self._latencies else 0,
            "sources": {
                "sportsgameodds": {
                    "available": self.sportsgameodds is not None,
                    "type": "primary"
                },
                "oddsapi": {
                    "available": self.oddsapi is not None,
                    "type": "secondary",
                    "quota": self.oddsapi.get_credits_info() if self.oddsapi else {}
                },
                "oddsportal": {
                    "available": self.oddsportal.is_available() if self.oddsportal else False,
                    "type": "tertiary"
                }
            }
        }
    
    def get_daily_report(self) -> str:
        """Generate daily summary report"""
        total = self._total_requests
        if total == 0:
            return "No odds requests today"
        
        report = [
            "=" * 60,
            "ODDS ENGINE DAILY REPORT",
            "=" * 60,
            f"Total Requests: {total}",
            "",
            "By Source:",
        ]
        
        for source, count in self._by_source.items():
            pct = (count / total) * 100 if total > 0 else 0
            report.append(f"  {source}: {count} ({pct:.1f}%)")
        
        report.extend([
            "",
            f"Average Latency: {sum(self._latencies)/len(self._latencies):.3f}s" if self._latencies else "N/A",
            "",
            "Source Priority:",
            "  1. SportsGameOdds (primary)",
            "  2. OddsAPI (quota-controlled)",
            "  3. OddsPortal (fallback)",
            "=" * 60
        ])
        
        return "\n".join(report)
    
    def close(self):
        """Close all adapters"""
        if self._sportsgameodds:
            self._sportsgameodds.close()
        if self._oddsapi:
            self._oddsapi.close()
        if self._oddsportal and hasattr(self._oddsportal, 'close'):
            self._oddsportal.close()
        
        logger.info("[ODDS ENGINE] Closed")


# Global singleton
_odds_engine = None


def get_odds_engine() -> UnifiedOddsEngine:
    """Get global odds engine instance"""
    global _odds_engine
    if _odds_engine is None:
        _odds_engine = UnifiedOddsEngine()
    return _odds_engine


def test_unified_engine():
    """Test unified odds engine"""
    print("Testing Unified Odds Engine...")
    
    engine = get_odds_engine()
    
    # Test all sports
    sports_teams = [
        ("football", "Arsenal", "Liverpool"),
        ("mlb", "Yankees", "Dodgers"),
        ("nba", "Lakers", "Celtics"),
    ]
    
    for sport, home, away in sports_teams:
        print(f"\n--- {sport}: {home} vs {away} ---")
        start = time.time()
        odds = engine.get_odds(sport, home, away)
        elapsed = time.time() - start
        
        if odds:
            print(f"Result: {odds.get('home_odds'):.2f} / {odds.get('away_odds'):.2f}")
            print(f"Source: {odds.get('source')}")
            print(f"Confidence: {odds.get('confidence')}")
        else:
            print("No odds available")
        
        print(f"Time: {elapsed:.2f}s")
    
    # Get stats
    print("\n" + engine.get_daily_report())
    
    engine.close()
    print("\nTest complete.")


if __name__ == "__main__":
    test_unified_engine()