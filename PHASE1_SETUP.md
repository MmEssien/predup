# PredUp - Phase 1 Setup Guide

## Prerequisites

### 1. Install Python 3.10+
```bash
# Windows
choco install python

# macOS
brew install python

# Linux
sudo apt install python3.10 python3-pip
```

### 2. Install PostgreSQL
```bash
# Windows - Download from https://www.postgresql.org/download/

# macOS
brew install postgresql@15
brew services start postgresql@15

# Linux
sudo apt install postgresql-15
sudo systemctl start postgresql
```

### 3. Create Database
```bash
psql -U postgres
CREATE USER predup WITH PASSWORD 'predup';
CREATE DATABASE predup OWNER predup;
GRANT ALL PRIVILEGES ON DATABASE predup TO predup;
\q

# Or run the init script
python scripts/init_db.py
```

### 4. Setup Environment
```bash
cd PredUp
cp .env.example .env
# Edit .env with your API keys (already configured)

pip install -r requirements.txt
```

### 5. Run Database Migrations
```bash
python scripts/init_db.py
```

### 6. Test API Connectivity
```bash
python -c "
from src.data.api_client import FootballAPIClient
from src.data.weather_client import WeatherAPIClient

# Test football-data.org
fd = FootballAPIClient()
comps = fd.get_competitions()
print(f'Competitions: {len(comps.get(\"competitions\", []))}')
fd.close()

# Test Weather API (free, no key)
w = WeatherAPIClient()
print('Weather API: OK')
w.close()
"
```

### 7. Initial Data Ingestion
```bash
# Ingest competitions and teams
python scripts/ingest_data.py

# Ingest historical data (last 2 seasons)
python scripts/ingest_historical.py --seasons 2

# Generate features
python scripts/generate_features.py --validate

# Train baseline model
python scripts/train_model.py --train

# Run backtest
python scripts/backtest.py --run

# Start API server
python -m uvicorn src.api.main:app --reload
```

## API Usage Optimization

### football-data.org (free tier: 100 calls/minute)
✅ Already optimized - uses football-data.org (generous free tier)

### Odds API (500 credits/month)
- Implemented: 1-hour cache to avoid redundant calls
- Only fetch upcoming matches (not historical)
- Use `get_upcoming()` for efficiency

### Weather API (Open-Meteo - free, unlimited)
✅ No API key required, unlimited usage

## Docker Alternative (optional)
```bash
cd PredUp
docker-compose up -d  # Starts PostgreSQL only
# Then run Python locally
```

## Quick Start (one-liner)
```bash
python scripts/ingest_data.py && python scripts/train_model.py --train && python scripts/backtest.py --run
```

## Monitoring
- API logs: `logs/api_*.log`
- Job history: `logs/jobs/`
- Models: `models/` directory