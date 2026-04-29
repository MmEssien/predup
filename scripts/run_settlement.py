"""
Settlement Job Scheduler

Run this script periodically (e.g., every 15 minutes) to:
1. Find completed matches
2. Auto-settle predictions
3. Generate health reports (weekly)

Usage:
    python scripts/run_settlement.py
    python scripts/run_settlement.py --once  # Run once and exit
"""

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.connection import DatabaseManager
from src.intelligence.health_report import generate_weekly_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_settlement_cycle(days_back: int = 1) -> dict:
    """Run a settlement cycle"""
    
    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()
    
    with db_manager.session() as session:
        from src.intelligence.settlement_service import SettlementScheduler
        scheduler = SettlementScheduler(session)
        
        result = scheduler.run_settlement_cycle(
            api_client=None,  # Would pass actual API client
            days_back=days_back
        )
        
        return result


def run_health_report(weeks_back: int = 4) -> dict:
    """Generate health report"""
    
    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()
    
    with db_manager.session() as session:
        report = generate_weekly_report(session)
        return report


def should_run_health_report() -> bool:
    """Check if it's time to run weekly health report"""
    now = datetime.utcnow()
    return now.weekday() == 6 and now.hour == 6  # Sunday at 6 AM


def main():
    parser = argparse.ArgumentParser(description="Run settlement job")
    parser.add_argument("--once", action="store_true", 
                       help="Run once and exit (for cron)")
    parser.add_argument("--days-back", type=int, default=1,
                       help="Days to look back for settlements")
    parser.add_argument("--interval", type=int, default=900,
                       help="Seconds between runs (default: 900 = 15 min)")
    parser.add_argument("--no-report", action="store_true",
                       help="Skip health report generation")
    
    args = parser.parse_args()
    
    logger.info("Starting settlement job scheduler")
    
    if args.once:
        logger.info("Running single settlement cycle")
        result = run_settlement_cycle(days_back=args.days_back)
        logger.info(f"Settlement result: {result}")
        
        if not args.no_report and should_run_health_report():
            logger.info("Generating weekly health report")
            report = run_health_report()
            logger.info(f"Health report: {report}")
        
        return
    
    # Continuous mode
    import time
    while True:
        try:
            result = run_settlement_cycle(days_back=args.days_back)
            logger.info(f"Settlement result: {result}")
            
            if not args.no_report and should_run_health_report():
                logger.info("Generating weekly health report")
                report = run_health_report()
                logger.info(f"Health report: {report}")
                
        except Exception as e:
            logger.error(f"Error in settlement cycle: {e}")
        
        logger.info(f"Sleeping for {args.interval} seconds")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()