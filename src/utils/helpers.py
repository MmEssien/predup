"""Utilities package for PredUp - re-exports from __init__"""

import yaml
import os
from pathlib import Path
from typing import Any, Dict


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_env_var(key: str, default: Any = None) -> Any:
    """Get environment variable with optional default"""
    return os.getenv(key, default)


def ensure_dir(path: str) -> Path:
    """Ensure directory exists"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def format_date(date_str: str, input_format: str = "%Y-%m-%d", output_format: str = "%Y-%m-%d") -> str:
    """Format date string"""
    from datetime import datetime
    dt = datetime.strptime(date_str, input_format)
    return dt.strftime(output_format)


def convert_to_lagos_time(utc_dt: datetime) -> datetime:
    """Convert UTC datetime to Africa/Lagos (UTC+1)"""
    from datetime import timedelta
    if utc_dt is None:
        return None
    # Lagos is always UTC+1 (no DST)
    return utc_dt + timedelta(hours=1)


def get_today_range_utc() -> tuple[datetime, datetime]:
    """Get UTC start and end of the current day in Africa/Lagos"""
    from datetime import datetime, timedelta
    
    # Current time in Lagos
    now_lagos = convert_to_lagos_time(datetime.utcnow())
    
    # Start of today in Lagos
    start_lagos = now_lagos.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # End of today in Lagos
    end_lagos = start_lagos + timedelta(days=1)
    
    # Convert back to UTC for DB queries
    start_utc = start_lagos - timedelta(hours=1)
    end_utc = end_lagos - timedelta(hours=1)
    
    return start_utc, end_utc


__all__ = [
    "load_config",
    "get_env_var",
    "ensure_dir",
    "format_date",
    "convert_to_lagos_time",
    "get_today_range_utc",
]