"""
Model Registry for AlphaNSE V2.
Enforces the lifecycle states: CANDIDATE -> SHADOW -> CHAMPION -> RETIRED / REJECTED.
Enforces that under DATA_BLOCKED status, CHAMPION promotion is unconditionally blocked.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime
from typing import Dict, Optional, List


class ModelStatus(Enum):
    CANDIDATE = auto()
    SHADOW = auto()
    CHAMPION = auto()
    RETIRED = auto()
    REJECTED = auto()


class ModelCertificationBlockedError(Exception):
    """Raised when an unauthorized promotion to CHAMPION is attempted."""
    pass


@dataclass
class ModelMetadata:
    model_id: str
    model_name: str
    version: str
    horizon: str = "5m"
    status: ModelStatus = ModelStatus.CANDIDATE
    metrics: Dict[str, float] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=datetime.now)
    promotion_notes: str = ""


class ModelRegistry:
    """
    Central repository of all candidate, shadow, and production models.
    """

    def __init__(self, is_data_blocked: bool = True):
        self._models: Dict[str, ModelMetadata] = {}
        self._is_data_blocked = is_data_blocked

    @property
    def is_data_blocked(self) -> bool:
        return self._is_data_blocked

    def set_data_blocked(self, blocked: bool) -> None:
        self._is_data_blocked = blocked

    def register(self, model: ModelMetadata) -> None:
        if model.model_id in self._models:
            raise ValueError(f"Model {model.model_id} already registered.")
        if model.status == ModelStatus.CHAMPION and self._is_data_blocked:
            raise ModelCertificationBlockedError(
                "Cannot register a model directly as CHAMPION while repository is classified as DATA_BLOCKED."
            )
        self._models[model.model_id] = model

    def get(self, model_id: str) -> Optional[ModelMetadata]:
        return self._models.get(model_id)

    def list_by_status(self, status: ModelStatus) -> List[ModelMetadata]:
        return [m for m in self._models.values() if m.status == status]

    def promote_to_shadow(self, model_id: str) -> None:
        model = self.get(model_id)
        if not model:
            raise KeyError(f"Model {model_id} not found.")
        model.status = ModelStatus.SHADOW
        model.promotion_notes = f"Promoted to SHADOW on {datetime.now().isoformat()}"

    def promote_to_champion(self, model_id: str) -> None:
        """
        Promote a model to CHAMPION.
        CRITICAL GATE: Blocked unconditionally if repository is DATA_BLOCKED.
        """
        if self._is_data_blocked:
            raise ModelCertificationBlockedError(
                f"Cannot promote model '{model_id}' to CHAMPION: Repository is classified as DATA_BLOCKED. "
                "Candidate models cannot be certified until multi-month historical validation passes."
            )

        model = self.get(model_id)
        if not model:
            raise KeyError(f"Model {model_id} not found.")

        # Demote existing CHAMPION to RETIRED
        for existing in self._models.values():
            if existing.status == ModelStatus.CHAMPION and existing.model_id != model_id:
                existing.status = ModelStatus.RETIRED
                existing.promotion_notes = f"Retired on {datetime.now().isoformat()} when {model_id} became CHAMPION"

        model.status = ModelStatus.CHAMPION
        model.promotion_notes = f"Promoted to CHAMPION on {datetime.now().isoformat()}"
