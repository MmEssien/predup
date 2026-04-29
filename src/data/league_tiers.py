"""
League Tiers System
=================
Defines which leagues have reliable odds coverage vs which use model-only predictions.

Tier 1 (Liquid) — Full odds coverage + EV pipeline
Tier 2 (Semi-liquid) — Odds optional, reduced confidence
Tier 3 (Illiquid) — Model-only, no odds required
"""

from typing import Dict, Set

# Tier 1: Major leagues with reliable odds (SportsGameOdds + OddsAPI)
TIER_1_LEAGUES: Set[str] = {
    # Football
    "EPL", "Premier League", " английская премьер лига",
    "La Liga", "Serie A", "Bundesliga", "Ligue 1", "UEFA Champions League",
    "UCL", "UEFA Europa League", "UEL",
    # NBA/Baseball
    "NBA", "MLB", "NFL", "NHL",
    # Major US Sports
    "NCAAF", "NCAAB",
    # International Football
    "World Cup", "Euro", "Copa America",
}

# Tier 2: Semi-liquid (some odds coverage)
TIER_2_LEAGUES: Set[str] = {
    # Football
    "Championship", "EFL Championship", "2. Bundesliga", "Ligue 2",
    "MLS", "US Major League Soccer",
    "Serie B", " Segunda División",
    "Eredivisie", "Belgian Pro League", "Portuguese Primeira",
    "Scottish Premiership", " SPL",
    "Copa Libertadores", "Copa Sudamericana",
    # Basketball
    "Euroleague", "EuroCup", "WNBA",
    "G-League", "NBA G League",
    # Baseball
    "KBO", "NPB", "Mexican League", "Cuban National Series",
    # Rugby/Cricket
    "Premiership Rugby", "Top 14", "Super Rugby",
    "IPL", "Big Bash", "County Championship",
}

# Tier 3: Everything else (model-only, no odds)
TIER_3_LEAGUES: Set[str] = {
    # All youth/reserve leagues
    "U21", "U20", "U19", "U18", "U23", "Reserve", "II", "Sub",
    "Championnat National 2", "Championnat National 3",
    "Serie C", "Serie D",
    "Regional", "Oberliga", "Landesliga", "Kreisiga",
    "Amateur", "Friendly", "International Friendly",
    # Lower divisions (auto-detect)
    "2. Liga", "3. Liga", "4. Liga", "Segunda B", "Tercera",
    "National 1", "National 2", "National 3",
    "League One", "League Two", "National League",
    "League 1", "League 2", "National",
    # Non-league
    "cups", "qualification", "play-offs", "playoffs",
}


def get_league_tier(league: str) -> int:
    """
    Determine league tier for odds requirements.
    
    Args:
        league: League name or ID
        
    Returns:
        1 (Tier 1 - full odds)
        2 (Tier 2 - optional odds)
        3 (Tier 3 - model only)
    """
    if not league:
        return 3
    
    league_clean = league.strip()
    league_lower = league_clean.lower()
    
    # FIRST: Check for youth/reserve/lower league patterns (Tier 3)
    # This MUST happen before other checks
    youth_indicators = ["u21", "u20", "u19", "u18", "u23", "reserve", "sub ", " ii", "amateur", "friendly", " 2", " 3", "division"]
    youth_found = any(ind in league_lower for ind in youth_indicators)
    if youth_found:
        # But check if it's a major league (epl, nba, etc)
        major_league = any(m in league_lower for m in ["epl", "nba", "mlb", "nfl", "ucl", "serie a", "bundesliga"])
        if not major_league:
            return 3
    
    # Tier 1 exact matches
    for t1 in TIER_1_LEAGUES:
        if league_lower == t1.lower():
            return 1
    
    # Tier 2 exact matches  
    for t2 in TIER_2_LEAGUES:
        if league_lower == t2.lower():
            return 2
    
    # Tier 1 partial (but not youth)
    for t1 in TIER_1_LEAGUES:
        if t1.lower() in league_lower:
            return 1
    
    # Tier 2 partial
    for t2 in TIER_2_LEAGUES:
        if t2.lower() in league_lower:
            return 2
    
    # Check explicit Tier 3 patterns
    for t3 in TIER_3_LEAGUES:
        if t3.lower() in league_lower:
            return 3
    
    # Default unknown to Tier 2
    return 2


def requires_odds(tier: int) -> bool:
    """Does this tier require odds for predictions?"""
    return tier <= 2


def get_confidence_weight(tier: int) -> float:
    """
    Confidence multiplier based on league tier.
    Lower tiers = less confidence in odds quality.
    """
    weights = {
        1: 1.0,  # Full confidence
        2: 0.7,  # Reduced confidence
        3: 0.0,  # No odds = no confidence from odds
    }
    return weights.get(tier, 0.0)


def should_skip_odds_engine(tier: int) -> bool:
    """
    Should we skip the odds engine entirely for this tier?
    Tier 3 leagues don't need odds API calls.
    """
    return tier >= 3