# PredUp - Sports Odds Intelligence System

## Overview
Production odds prediction engine with tiered source routing, caching, and line archiving.

## Architecture

### Source Priority (Live Path)
```python
SPORT_PRIORITY = {
    "football": ["oddsapi", "sportsgameodds"],
    "nba": ["oddsapi", "sportsgameodds"],
    "mlb": ["oddsapi", "sportsgameodds"],
    "nfl": ["oddsapi", "sportsgameodds"],
}
```

### Source Confidence
```python
SOURCE_CONFIDENCE = {
    "oddsapi": 0.95,       # Primary - working
    "sportsgameodds": 0.75,   # Secondary - unstable
    "oddsportal": 0.45,     # Tertiary - async only
}
```

---

## Key Files

### Core Engine
| File | Purpose |
|------|---------|
| `src/data/unified_odds_engine.py` | Main entry point, tiered priority |
| `src/data/league_tiers.py` | Tier 1/2/3 league classification |
| `src/data/odds_cache.py` | Central caching (TTL per source) |
| `src/data/odds_archive.py` | Historical line storage |

### Adapters
| File | Purpose |
|------|---------|
| `src/data/oddsapi_adapter.py` | The Odds API (primary) |
| `src/data/sportsgameodds_adapter.py` | SportsGameOdds (5s timeout) |
| `src/data/oddsportal_adapter.py` | OddsPortal (Playwright, async only) |

### Models
| File | Purpose |
|------|---------|
| `src/models/baseline_models.py` | Math baselines (Elo, runs, net rating) |

---

## Usage

### Get Odds
```python
from src.data.unified_odds_engine import UnifiedOddsEngine

engine = UnifiedOddsEngine()
result = engine.get_odds('football', 'Leeds United', 'Burnley', league='EPL')

if result:
    print(f"Home: {result['home_odds']} | Away: {result['away_odds']}")
    print(f"Source: {result['source']} | Confidence: {result['combined_confidence']}")
```

### Archive History
```python
from src.data.odds_archive import get_odds_archive

archive = get_odds_archive()
movement = archive.get_line_movement("Leeds United", "Burnley")
print(f"Line move: {movement['home_move']}")
```

---

## API Keys

| Source | Key | Status |
|--------|-----|--------|
| OddsAPI | `dca7069462322213519c88f447526adc` | Working (402 credits) |
| SportsGameOdds | `47a8f5cb3d3e693009505ff6aa54488f` | Timeout issues |

---

## League Tiers

### Tier 1 (Liquid) - Full Odds
EPL, NBA, MLB, UCL, Serie A, Bundesliga, Ligue 1

### Tier 2 (Semi-Liquid) - Optional Odds
Championship, MLS, Euroleague, Serie B

### Tier 3 (Illiquid) - Model Only
U18, U21, League 2, lower divisions, amateur

---

## Cache TTL

| Source | Default | Minimum |
|--------|---------|---------|
| oddsapi | 30 min | 15 min |
| sportsgameodds | 5 min | 2 min |
| oddsportal | 720 min | 60 min |

---

## Line Archive Format

Location: `.cache/odds_archive/odds_YYYY-MM-DD.jsonl`

```json
{"timestamp": "2026-04-28T20:12:08", "sport": "soccer_epl", "home_team": "Leeds United", "away_team": "Burnley", "home_odds": 1.41, "away_odds": 6.5, "source": "oddsapi", "confidence": 0.95}
```

---

## Dependencies

```
httpx>=0.27.0
beautifulsoup4>=4.14.0
playwright>=1.58.0
python-dotenv>=1.0.0
```

---

## Notes

1. **OddsPortal requires Playwright** for JavaScript rendering
2. **SportsGameOdds has 5s timeout** (fail fast)
3. **All odds archived** in `.cache/odds_archive/`
4. **No simulated odds** in production

---

Last Updated: 2026-04-28