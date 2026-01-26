"""Storage Service - Persistent storage for runs and artifacts."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class StorageService:
    """Handles persistent storage for runs and slidespecs."""

    def __init__(self, storage_dir: str = None):
        """Initialize storage service.

        Args:
            storage_dir: Directory for storing data. Defaults to ./data
        """
        if storage_dir is None:
            storage_dir = os.getenv("STORAGE_DIR", "./data")

        self.storage_dir = Path(storage_dir)
        self.runs_dir = self.storage_dir / "runs"
        self.slidespecs_dir = self.storage_dir / "slidespecs"

        # Ensure directories exist
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.slidespecs_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self._runs_cache: dict[str, dict] = {}
        self._slidespecs_cache: dict[str, dict] = {}

        # Load existing data
        self._load_all()

    def _load_all(self):
        """Load all existing data from storage."""
        # Load runs
        for file_path in self.runs_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    run_id = file_path.stem
                    self._runs_cache[run_id] = data
            except Exception as e:
                logger.error(f"Failed to load run {file_path}: {e}")

        # Load slidespecs
        for file_path in self.slidespecs_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    artifact_id = file_path.stem
                    self._slidespecs_cache[artifact_id] = data
            except Exception as e:
                logger.error(f"Failed to load slidespec {file_path}: {e}")

        logger.info(f"Loaded {len(self._runs_cache)} runs and {len(self._slidespecs_cache)} slidespecs from storage")

    def _datetime_handler(self, obj):
        """JSON serializer for datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    # === Run Operations ===

    def save_run(self, run_id: str, run_data: dict) -> bool:
        """Save a run to storage."""
        try:
            file_path = self.runs_dir / f"{run_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(run_data, f, default=self._datetime_handler, ensure_ascii=False, indent=2)
            self._runs_cache[run_id] = run_data
            return True
        except Exception as e:
            logger.error(f"Failed to save run {run_id}: {e}")
            return False

    def get_run(self, run_id: str) -> Optional[dict]:
        """Get a run from storage."""
        return self._runs_cache.get(run_id)

    def delete_run(self, run_id: str) -> bool:
        """Delete a run from storage."""
        try:
            file_path = self.runs_dir / f"{run_id}.json"
            if file_path.exists():
                file_path.unlink()
            if run_id in self._runs_cache:
                del self._runs_cache[run_id]
            return True
        except Exception as e:
            logger.error(f"Failed to delete run {run_id}: {e}")
            return False

    def list_runs(self, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        """List all runs with pagination."""
        runs = list(self._runs_cache.values())
        # Sort by created_at descending
        runs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        total = len(runs)
        return runs[offset:offset + limit], total

    def get_all_runs(self) -> dict[str, dict]:
        """Get all runs (for internal use)."""
        return self._runs_cache

    # === Slidespec Operations ===

    def save_slidespec(self, artifact_id: str, slidespec: dict) -> bool:
        """Save a slidespec to storage."""
        try:
            file_path = self.slidespecs_dir / f"{artifact_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(slidespec, f, ensure_ascii=False, indent=2)
            self._slidespecs_cache[artifact_id] = slidespec
            return True
        except Exception as e:
            logger.error(f"Failed to save slidespec {artifact_id}: {e}")
            return False

    def get_slidespec(self, artifact_id: str) -> Optional[dict]:
        """Get a slidespec from storage."""
        return self._slidespecs_cache.get(artifact_id)

    def delete_slidespec(self, artifact_id: str) -> bool:
        """Delete a slidespec from storage."""
        try:
            file_path = self.slidespecs_dir / f"{artifact_id}.json"
            if file_path.exists():
                file_path.unlink()
            if artifact_id in self._slidespecs_cache:
                del self._slidespecs_cache[artifact_id]
            return True
        except Exception as e:
            logger.error(f"Failed to delete slidespec {artifact_id}: {e}")
            return False

    def list_slidespecs(self, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        """List all slidespecs with pagination."""
        items = []
        for artifact_id, spec in self._slidespecs_cache.items():
            items.append({
                "artifact_id": artifact_id,
                "title": spec.get("deck", {}).get("title", "Untitled"),
                "slide_count": len(spec.get("slides", [])),
                "created_at": spec.get("created_at"),
            })
        # Sort by title
        items.sort(key=lambda x: x.get("title", ""))
        total = len(items)
        return items[offset:offset + limit], total

    def get_all_slidespecs(self) -> dict[str, dict]:
        """Get all slidespecs (for internal use)."""
        return self._slidespecs_cache

    def update_slidespec_slide(self, artifact_id: str, slide_index: int, slide_data: dict) -> bool:
        """Update a specific slide within a slidespec."""
        slidespec = self._slidespecs_cache.get(artifact_id)
        if not slidespec:
            return False

        slides = slidespec.get("slides", [])
        if slide_index < 0 or slide_index >= len(slides):
            return False

        slides[slide_index] = slide_data
        return self.save_slidespec(artifact_id, slidespec)


# Singleton instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get the storage service singleton."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
