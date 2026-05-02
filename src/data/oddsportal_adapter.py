"""
OddsPortal Adapter - TERTIARY Fallback
===================================
Scrapes odds from OddsPortal using Playwright (async version) for JavaScript rendering.

Use as tertiary fallback when OddsAPI is unavailable.
Note: OddsPortal has complex JS rendering - may need updates as site changes.
"""

import logging
from datetime import datetime
from typing import Dict, Optional
import re

logger = logging.getLogger(__name__)


class OddsPortalAdapter:
    """
    OddsPortal scraper using Playwright Async.
    
    Use as tertiary fallback - works independently of OddsAPI.
    """
    
    BASE_URL = 'https://www.oddsportal.com'
    
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        
        # Stats
        self._requests = 0
        self._success = 0
        self._failed = 0
    
    async def _get_playwright(self):
        if self._playwright is None:
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
            except Exception as e:
                logger.warning(f"[ODDSPORTAL] Failed to start Playwright: {e}")
                raise
        return self._playwright
    
    async def _get_browser(self):
        if self._browser is None:
            pw = await self._get_playwright()
            self._browser = await pw.chromium.launch(
                headless=True,
                args=['--disable-gpu', '--no-sandbox']
            )
        return self._browser
    
    async def _get_page(self):
        if self._page is None:
            browser = await self._get_browser()
            self._page = await browser.new_page()
            await self._page.set_viewport_size({"width": 1920, "height": 1080})
        return self._page
    
    async def is_available(self) -> bool:
        try:
            page = await self._get_page()
            await page.goto(self.BASE_URL, timeout=15000)
            return True
        except Exception as e:
            logger.debug(f"[ODDSPORTAL] Availability check failed: {e}")
            return False
    
    async def get_odds(
        self,
        sport: str,
        home_team: str,
        away_team: str,
        league: str = None,
        use_cache: bool = True
    ) -> Optional[Dict]:
        """Scrape odds from OddsPortal."""
        from src.data.odds_cache import get_odds_cache
        cache = get_odds_cache()
        
        cache_key = f"oddsportal_{sport}_{home_team}_{away_team}"
        
        if use_cache:
            cached = cache.get(cache_key, "oddsportal")
            if cached:
                logger.debug(f"[ODDSPORTAL] Cache hit")
                return cached
        
        self._requests += 1
        
        try:
            odds_data = await self._search_and_get_odds(home_team, away_team, sport, league)
            
            if odds_data:
                self._success += 1
                cache.set(cache_key, odds_data, "oddsportal")
                logger.info(f"[ODDSPORTAL] SUCCESS: {home_team} vs {away_team}")
            else:
                self._failed += 1
                logger.debug(f"[ODDSPORTAL] Not found: {home_team} vs {away_team}")
            
            return odds_data
            
        except Exception as e:
            self._failed += 1
            logger.warning(f"[ODDSPORTAL] Error: {e}")
            return None
    
    async def _search_and_get_odds(self, home: str, away: str, sport: str, league: str) -> Optional[Dict]:
        """Search for match and extract odds"""
        page = await self._get_page()
        
        try:
            # Try to navigate using known URL patterns
            slug_home = home.lower().replace(' ', '-')
            slug_away = away.lower().replace(' ', '-')
            
            # Try different URL patterns
            urls_to_try = [
                f'{self.BASE_URL}/search/{slug_home}-vs-{slug_away}/',
            ]
            
            for url in urls_to_try:
                try:
                    await page.goto(url, timeout=30000)
                    await page.wait_for_timeout(3000)
                    
                    # Scroll to trigger lazy load
                    await page.evaluate('window.scrollBy(0, 300)')
                    await page.wait_for_timeout(1000)
                    
                    odds = await self._parse_current_page(page, home, away)
                    if odds:
                        return odds
                except Exception as e:
                    logger.debug(f"[ODDSPORTAL] URL {url} failed: {e}")
                    continue
                
        except Exception as e:
            logger.debug(f"[ODDSPORTAL] Search error: {e}")
        
        return None
    
    async def _parse_current_page(self, page, home: str, away: str) -> Optional[Dict]:
        """Parse odds from current page"""
        try:
            # Get page content
            html = await page.content()
            
            # Try to find odds using patterns
            # Look for decimal odds (numbers like 1.5, 2.0, 3.5 etc)
            import re
            odds_pattern = re.compile(r'(\d+\.\d+)')
            
            # Search in page text
            text = await page.inner_text('body')
            
            # Find all decimal odds
            all_odds = [float(m) for m in odds_pattern.findall(text) 
                      if 1.0 < float(m) < 20.0]
            
            # Remove duplicates
            all_odds = list(dict.fromkeys(all_odds))
            
            if len(all_odds) >= 2:
                return {
                    "sport": self._map_sport(sport),
                    "home_team": home,
                    "away_team": away,
                    "home_odds": all_odds[0],
                    "away_odds": all_odds[1],
                    "draw_odds": None,
                    "overround": None,
                    "timestamp": datetime.now().isoformat(),
                    "source": "oddsportal",
                    "confidence": 0.6,
                    "cache_status": "fresh"
                }
                
        except Exception as e:
            logger.debug(f"[ODDSPORTAL] Parse error: {e}")
        
        return None
    
    def _map_sport(self, sport: str) -> str:
        mapping = {
            "football": "football",
            "nba": "basketball",
            "mlb": "baseball",
        }
        return mapping.get(sport.lower(), "football")
    
    async def close(self):
        if self._page:
            await self._page.close()
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
    
    def get_stats(self) -> Dict:
        return {
            "requests": self._requests,
            "success": self._success,
            "failed": self._failed,
            "success_rate": self._success / max(self._requests, 1)
        }