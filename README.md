# PredUp

Football Prediction Engine

## Setup

```bash
cd PredUp
pip install -r requirements.txt
cp .env.example .env
# Configure your API key in .env
```

## Project Structure

```
PredUp/
├── config/          # Configuration files
├── data/            # Data storage (raw, processed, features)
├── src/
│   ├── data/       # API client and pipelines
│   ├── features/   # Feature engineering
│   ├── models/     # Model training
│   ├── api/        # FastAPI server
│   ├── decisions/  # Decision engine
│   └── utils/      # Utilities
├── tests/           # Test suite
├── scripts/         # Ingestion scripts
└── notebooks/      # Jupyter notebooks
```

## Usage

```bash
# Ingest historical data
python scripts/ingest_historical.py

# Run scheduled updates
python scripts/scheduled_update.py
```