"""Scheduled update script for daily data sync"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.pipeline import DataPipeline
from src.utils.helpers import load_config


def main():
    config = load_config()
    pipeline = DataPipeline()

    today = datetime.now()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]

    for date in dates:
        try:
            df = pipeline.fetch_upcoming_matches(
                date=date,
                save_path=f"data/raw/upcoming_{date}.csv"
            )
            print(f"Fetched {len(df)} matches for {date}")
        except Exception as e:
            print(f"Error fetching {date}: {e}")

    pipeline.close()
    print("Scheduled update complete")


if __name__ == "__main__":
    main()