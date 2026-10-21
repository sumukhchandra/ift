"""
AlphaNSE V3 — Multi-Model Registry Engine.
Manages registration, cryptographic verification, serialization, and isolation
for all 5 research models participating in Session 5.

STATUS: EXPERIMENT / VALIDATION
FAILURE ISOLATION PRINCIPLE:
  If a model fails pre-market sanity gating, it is marked INVALID_FOR_SESSION.
  It is NEVER silently substituted. The registry tracks valid_model_count and invalid_models.
"""

import os
import json
import pickle
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
from v3.config.multimodel_config import (
    V3_MULTIMODEL_DIR,
    V3_MULTIMODEL_REGISTRY_PATH,
    ACTIVE_MODEL_SPECS
)
from v3.models.base_model import FrozenModelMetadata

logger = logging.getLogger(__name__)


class MultiModelRegistryV3:
    """
    Cryptographic registry maintaining models, metadata, and status for Session 5.
    """

    def __init__(
        self,
        registry_dir: str = V3_MULTIMODEL_DIR,
        registry_file: str = V3_MULTIMODEL_REGISTRY_PATH
    ):
        self.registry_dir = registry_dir
        self.registry_file = registry_file
        self.artifacts_dir = os.path.join(registry_dir, "artifacts")
        os.makedirs(self.registry_dir, exist_ok=True)
        os.makedirs(self.artifacts_dir, exist_ok=True)

        self.models: Dict[str, Any] = {}
        self.metadata: Dict[str, FrozenModelMetadata] = {}

    def register_model(
        self,
        model_id: str,
        model_obj: Any,
        metadata: FrozenModelMetadata
    ) -> str:
        """
        Serializes model weights to disk, registers metadata, and computes SHA-256 hash.
        """
        model_bytes = pickle.dumps(model_obj)
        computed_hash = hashlib.sha256(model_bytes).hexdigest()

        if computed_hash != metadata.model_hash:
            raise ValueError(
                f"[REGISTRY INTEGRITY ERROR] Model hash mismatch for {model_id}: "
                f"{computed_hash} vs {metadata.model_hash}"
            )

        artifact_path = os.path.join(self.artifacts_dir, f"{model_id}_{metadata.model_version}.pkl")
        with open(artifact_path, "wb") as f:
            f.write(model_bytes)

        self.models[model_id] = model_obj
        self.metadata[model_id] = metadata

        self.save_registry()
        logger.info(f"[REGISTRY] Registered {model_id} (Version: {metadata.model_version}, Status: {metadata.status})")
        return artifact_path

    def register_failed_model(
        self,
        model_id: str,
        metadata: FrozenModelMetadata
    ) -> None:
        """
        Explicitly registers a model that failed sanity gates as INVALID_FOR_SESSION.
        No silent substitution allowed.
        """
        self.models[model_id] = None
        self.metadata[model_id] = metadata
        self.save_registry()
        logger.warning(f"[REGISTRY] Model {model_id} marked {metadata.status}!")

    def save_registry(self) -> None:
        """Saves registry metadata state to disk as JSON."""
        data = {
            model_id: meta.to_dict()
            for model_id, meta in self.metadata.items()
        }
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_registry(self) -> None:
        """Loads registry metadata and artifacts from disk."""
        if not os.path.exists(self.registry_file):
            return

        with open(self.registry_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        for model_id, meta_dict in data.items():
            meta = FrozenModelMetadata.from_dict(meta_dict)
            self.metadata[model_id] = meta

            if meta.status == "FROZEN":
                artifact_path = os.path.join(self.artifacts_dir, f"{model_id}_{meta.model_version}.pkl")
                if os.path.exists(artifact_path):
                    with open(artifact_path, "rb") as f:
                        model_bytes = f.read()
                    actual_hash = hashlib.sha256(model_bytes).hexdigest()
                    if actual_hash != meta.model_hash:
                        raise ValueError(f"Hash corrupted for {model_id} on disk!")
                    self.models[model_id] = pickle.loads(model_bytes)
                else:
                    self.models[model_id] = None
            else:
                self.models[model_id] = None

    def get_valid_models(self) -> Dict[str, Tuple[Any, FrozenModelMetadata]]:
        """Returns only models that passed pre-market gates and are FROZEN."""
        valid = {}
        for m_id, meta in self.metadata.items():
            if meta.status == "FROZEN" and self.models.get(m_id) is not None:
                valid[m_id] = (self.models[m_id], meta)
        return valid

    def get_status_summary(self) -> Dict[str, Any]:
        """Provides status breakdown for pre-market readiness."""
        valid_models = [m_id for m_id, meta in self.metadata.items() if meta.status == "FROZEN"]
        invalid_models = [m_id for m_id, meta in self.metadata.items() if meta.status != "FROZEN"]
        return {
            "total_registered": len(self.metadata),
            "valid_model_count": len(valid_models),
            "valid_models": valid_models,
            "invalid_models": invalid_models,
            "all_models_valid": len(valid_models) == len(ACTIVE_MODEL_SPECS) and len(invalid_models) == 0
        }
