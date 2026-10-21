"""
Unit tests for Model Registry and Certification Gates.
"""

import unittest
from v2.models import (
    ModelStatus,
    ModelMetadata,
    ModelRegistry,
    ModelCertificationBlockedError
)


class TestModelRegistry(unittest.TestCase):

    def test_model_registration_and_shadow_promotion(self):
        registry = ModelRegistry(is_data_blocked=True)
        model = ModelMetadata(
            model_id="MOD-5M-LGBM-V1",
            model_name="LightGBM 5m Regressor",
            version="1.0.0",
            horizon="5m",
            status=ModelStatus.CANDIDATE
        )
        registry.register(model)

        self.assertEqual(registry.get("MOD-5M-LGBM-V1").status, ModelStatus.CANDIDATE)

        registry.promote_to_shadow("MOD-5M-LGBM-V1")
        self.assertEqual(registry.get("MOD-5M-LGBM-V1").status, ModelStatus.SHADOW)

    def test_champion_promotion_blocked_by_data_blocked_gate(self):
        registry = ModelRegistry(is_data_blocked=True)
        model = ModelMetadata(
            model_id="MOD-5M-ENS-V1",
            model_name="Ensemble 5m Regressor",
            version="1.0.0",
            horizon="5m",
            status=ModelStatus.CANDIDATE
        )
        registry.register(model)

        # Attempting to promote to CHAMPION must fail
        with self.assertRaises(ModelCertificationBlockedError):
            registry.promote_to_champion("MOD-5M-ENS-V1")

        self.assertEqual(registry.get("MOD-5M-ENS-V1").status, ModelStatus.CANDIDATE)

    def test_champion_promotion_allowed_when_data_gate_cleared(self):
        registry = ModelRegistry(is_data_blocked=False)
        m1 = ModelMetadata("MOD-1", "Model 1", "1.0", status=ModelStatus.CANDIDATE)
        m2 = ModelMetadata("MOD-2", "Model 2", "1.0", status=ModelStatus.CANDIDATE)
        registry.register(m1)
        registry.register(m2)

        registry.promote_to_champion("MOD-1")
        self.assertEqual(registry.get("MOD-1").status, ModelStatus.CHAMPION)

        # Promoting MOD-2 retires MOD-1
        registry.promote_to_champion("MOD-2")
        self.assertEqual(registry.get("MOD-2").status, ModelStatus.CHAMPION)
        self.assertEqual(registry.get("MOD-1").status, ModelStatus.RETIRED)


if __name__ == "__main__":
    unittest.main()
