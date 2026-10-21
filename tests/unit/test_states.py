"""
Unit tests for Research Lifecycle and Runtime Operational Safety State Machines.
"""

import unittest
from v2.state import (
    ResearchLifecycleState,
    ResearchLifecycleController,
    RuntimeSafetyState,
    RuntimeSafetyController
)
from v2.state.research_lifecycle import LifecycleTransitionError


class TestStateMachines(unittest.TestCase):

    def test_research_lifecycle_data_blocked_gate(self):
        controller = ResearchLifecycleController(initial_state=ResearchLifecycleState.DEVELOPMENT, is_data_blocked=True)

        # Development -> Research -> Backtest -> Data Validation
        controller.transition_to(ResearchLifecycleState.RESEARCH)
        controller.transition_to(ResearchLifecycleState.BACKTEST)
        controller.transition_to(ResearchLifecycleState.DATA_VALIDATION)

        # DATA_BLOCKED prevents transition to MODEL_VALIDATION
        with self.assertRaises(LifecycleTransitionError):
            controller.transition_to(ResearchLifecycleState.MODEL_VALIDATION)

        self.assertFalse(controller.can_certify_models())

        # Unblock data -> allows promotion
        controller.set_data_blocked(False)
        controller.transition_to(ResearchLifecycleState.MODEL_VALIDATION)
        self.assertEqual(controller.current_state, ResearchLifecycleState.MODEL_VALIDATION)
        self.assertTrue(controller.can_certify_models())

    def test_illegal_lifecycle_skips_fail(self):
        controller = ResearchLifecycleController(initial_state=ResearchLifecycleState.DEVELOPMENT)
        # Attempting to jump from DEVELOPMENT directly to LIVE
        with self.assertRaises(LifecycleTransitionError):
            controller.transition_to(ResearchLifecycleState.LIVE)

    def test_runtime_safety_auto_recovery(self):
        safety = RuntimeSafetyController()
        self.assertEqual(safety.current_state, RuntimeSafetyState.NORMAL)
        self.assertTrue(safety.is_operational)

        # Trigger data halt
        safety.trigger_data_halt("Stale market feed: no ticks for 45s")
        self.assertEqual(safety.current_state, RuntimeSafetyState.SAFE_DATA_HALT)
        self.assertFalse(safety.is_operational)
        self.assertIn("Stale market feed", safety.fault_reason)

        # Auto-recovery
        recovered = safety.auto_recover("Feed resumed with fresh tick seq#1001")
        self.assertTrue(recovered)
        self.assertEqual(safety.current_state, RuntimeSafetyState.NORMAL)
        self.assertTrue(safety.is_operational)
        self.assertIsNone(safety.fault_reason)

    def test_runtime_halt_does_not_alter_research_state(self):
        """Architectural Invariant: Runtime halts never regress the Research Lifecycle."""
        lifecycle = ResearchLifecycleController(initial_state=ResearchLifecycleState.DATA_VALIDATION, is_data_blocked=True)
        safety = RuntimeSafetyController()

        safety.trigger_data_halt("Temporary network timeout")
        self.assertEqual(safety.current_state, RuntimeSafetyState.SAFE_DATA_HALT)

        # Research lifecycle remains stable at DATA_VALIDATION
        self.assertEqual(lifecycle.current_state, ResearchLifecycleState.DATA_VALIDATION)
        self.assertTrue(lifecycle.is_data_blocked)


if __name__ == "__main__":
    unittest.main()
