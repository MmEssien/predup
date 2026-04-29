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


__all__ = [
    "load_config",
    "get_env_var",
    "ensure_dir",
    "format_date",
]