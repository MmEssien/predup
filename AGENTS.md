# PredUp - Sports Odds Intelligence System

## Quick Start
```bash
# Backend
cd PredUp
python scripts/run_daily_intelligence.py

# Frontend (separate project)
cd ../predup-web
npm install
npm run dev
```

## Architecture
- **Primary Source**: The Odds API (402 credits, working)
- **Secondary**: SportsGameOdds (5s timeout, unstable)
- **Tertiary**: OddsPortal (async only)

## Frontend (predup-web)
Located at: `../predup-web`

### Tech Stack
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- shadcn/ui components
- Recharts

### Pages
- `/` - Dashboard Home (stats, top opportunities, alerts)
- `/predictions` - Live Predictions (filterable table)
- `/performance` - Performance charts (ROI, win rates, CLV)
- `/history` - Historical Picks (settled predictions)
- `/settings` - Settings & API Health

### API Endpoints Used
- `GET /api/v1/dashboard` - Dashboard stats
- `GET /api/v1/predictions/live` - Active predictions
- `GET /api/v1/predictions/history` - Historical picks
- `GET /api/v1/performance` - Metrics for charts
- `GET /api/v1/fixtures/{id}` - Fixture detail
- `GET /api/v1/health` - API health status
- `GET /api/v1/settings` - System settings

### Running Frontend
```bash
cd predup-web
npm install
npm run dev
# Opens at http://localhost:3000
```

## Key Commands
```bash
# Test odds engine
python -c "from src.data.unified_odds_engine import UnifiedOddsEngine; e = UnifiedOddsEngine(); print(e.get_odds('football', 'Leeds United', 'Burnley', league='EPL'))"

# Check archive
python -c "from src.data.odds_archive import get_odds_archive; print(get_odds_archive().get_line_movement('Leeds United', 'Burnley'))"
```

## API Keys (in .env)
- ODDS_API_KEY=dca7069462322213519c88f447526adc
- SPORTSGAMEODDS_KEY=47a8f5cb3d3e693009505ff6aa54488f

## Dependencies
```bash
pip install httpx beautifulsoup4 playwright python-dotenv
playwright install chromium
```

## Notes
- No simulated odds in production
- League Tiers enforce what gets odds (Tier 1-2)
- All pulls archived to .cache/odds_archive/
- SportsGameOdds has 5s timeout (fail fast)
- OddsPortal needs Playwright (async research only)