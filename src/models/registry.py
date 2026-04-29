"""Model registry for version management"""

import logging
import json
import pickle
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(self, storage_path: str = "models"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.versions: Dict[str, List[Dict]] = {}

    def register_model(
        self,
        model_name: str,
        model: Any,
        version: str,
        metrics: Dict[str, float],
        feature_names: List[str],
        config: Optional[Dict] = None,
        notes: str = ""
    ) -> str:
        """Register a new model version"""
        version_id = f"{model_name}_{version}"

        model_data = {
            "version_id": version_id,
            "model_name": model_name,
            "version": version,
            "metrics": metrics,
            "feature_names": feature_names,
            "config": config or {},
            "notes": notes,
            "registered_at": datetime.utcnow().isoformat(),
            "is_active": False,
        }

        if model_name not in self.versions:
            self.versions[model_name] = []

        self.versions[model_name].append(model_data)

        model_path = self.storage_path / f"{version_id}.pkl"
        with open(model_path, "wb") as f:
            pickle.dump({
                "model": model,
                "metadata": model_data,
            }, f)

        self._save_index()

        logger.info(f"Registered model {version_id}")

        return version_id

    def activate_version(self, model_name: str, version: str) -> bool:
        """Activate a specific model version"""
        if model_name not in self.versions:
            logger.error(f"Model {model_name} not found")
            return False

        for v in self.versions[model_name]:
            if v["version"] == version:
                v["is_active"] = True
            else:
                v["is_active"] = False

        self._save_index()

        logger.info(f"Activated {model_name} version {version}")

        return True

    def get_active_version(self, model_name: str) -> Optional[Dict]:
        """Get active version for a model"""
        if model_name not in self.versions:
            return None

        for v in self.versions[model_name]:
            if v["is_active"]:
                return v

        return None

    def get_version(self, model_name: str, version: str) -> Optional[Dict]:
        """Get specific version"""
        if model_name not in self.versions:
            return None

        for v in self.versions[model_name]:
            if v["version"] == version:
                return v

        return None

    def load_model(self, model_name: str, version: Optional[str] = None) -> Any:
        """Load model from registry"""
        if version is None:
            v = self.get_active_version(model_name)
            if v is None:
                raise ValueError(f"No active version for {model_name}")
            version = v["version"]

        version_id = f"{model_name}_{version}"
        model_path = self.storage_path / f"{version_id}.pkl"

        if not model_path.exists():
            raise FileNotFoundError(f"Model {version_id} not found")

        with open(model_path, "rb") as f:
            data = pickle.load(f)

        logger.info(f"Loaded model {version_id}")

        return data["model"]

    def list_versions(self, model_name: str) -> List[Dict]:
        """List all versions for a model"""
        return self.versions.get(model_name, [])

    def list_models(self) -> List[str]:
        """List all registered models"""
        return list(self.versions.keys())

    def get_best_version(self, model_name: str, metric: str = "roc_auc") -> Optional[Dict]:
        """Get best version by metric"""
        versions = self.list_versions(model_name)

        if not versions:
            return None

        best = None
        best_score = float("-inf")

        for v in versions:
            score = v.get("metrics", {}).get(metric, 0)
            if score > best_score:
                best_score = score
                best = v

        return best

    def archive_version(self, model_name: str, version: str) -> bool:
        """Archive a model version"""
        v = self.get_version(model_name, version)

        if v is None:
            return False

        version_id = f"{model_name}_{version}"
        model_path = self.storage_path / f"{version_id}.pkl"
        archive_path = self.storage_path / "archive" / f"{version_id}.pkl"

        if model_path.exists():
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.rename(archive_path)

        v["archived"] = True
        v["archived_at"] = datetime.utcnow().isoformat()

        self._save_index()

        logger.info(f"Archived {version_id}")

        return True

    def _save_index(self) -> None:
        """Save version index"""
        index_path = self.storage_path / "index.json"

        with open(index_path, "w") as f:
            json.dump(self.versions, f, indent=2, default=str)

    def _load_index(self) -> None:
        """Load version index"""
        index_path = self.storage_path / "index.json"

        if index_path.exists():
            with open(index_path, "r") as f:
                self.versions = json.load(f)

    def export_metrics(self, model_name: str, path: str) -> None:
        """Export model metrics to CSV"""
        import pandas as pd

        versions = self.list_versions(model_name)

        if not versions:
            return

        records = []
        for v in versions:
            record = {
                "version": v["version"],
                "is_active": v["is_active"],
                "registered_at": v["registered_at"],
            }
            record.update(v.get("metrics", {}))
            records.append(record)

        df = pd.DataFrame(records)
        df.to_csv(path, index=False)

        logger.info(f"Exported metrics to {path}")


def create_registry(storage_path: str = "models") -> ModelRegistry:
    """Create model registry"""
    registry = ModelRegistry(storage_path)
    registry._load_index()
    return registry