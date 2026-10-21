"""
Unit tests for Point-in-Time AsOfClock and Replay Lookahead Invariants.
"""

import unittest
from datetime import datetime, timedelta
from v2.replay import AsOfClock, LookaheadViolationError, ReplayEngine
from v2.data.schema import Bar
from v2.data.adapters.replay_adapter import HistoricalReplayAdapter


class TestNoLookahead(unittest.TestCase):

    def test_clock_prevents_future_data_access(self):
        t0 = datetime(2026, 9, 18, 9, 30)
        clock = AsOfClock(start_time=t0)

        # Bar at 09:30 (current time) is accessible
        clock.assert_accessible(t0)

        # Bar at 09:29 (past) is accessible
        past_t = t0 - timedelta(minutes=1)
        clock.assert_accessible(past_t)

        # Bar at 09:31 (future) must raise LookaheadViolationError
        future_t = t0 + timedelta(minutes=1)
        with self.assertRaises(LookaheadViolationError):
            clock.assert_accessible(future_t)

    def test_clock_cannot_move_backward(self):
        t0 = datetime(2026, 9, 18, 10, 0)
        clock = AsOfClock(start_time=t0)

        # Forward movement is valid
        clock.set_time(t0 + timedelta(minutes=5))

        # Backward movement is rejected
        with self.assertRaises(ValueError):
            clock.set_time(t0 - timedelta(minutes=1))

    def test_replay_engine_chronological_stepping(self):
        base_t = datetime(2026, 9, 18, 9, 15)
        bars = [
            Bar(base_t + timedelta(minutes=i), "TATACAP.NS", 350.0, 351.0, 349.0, 350.5, 1000.0)
            for i in range(5)
        ]
        adapter = HistoricalReplayAdapter(bars)
        engine = ReplayEngine(adapter)

        observed_timestamps = []
        def listener(bar, clock):
            observed_timestamps.append(clock.current_time)
            # Clock must equal the bar timestamp
            self.assertEqual(clock.current_time, bar.timestamp)

        engine.add_listener(listener)
        steps = engine.run_all()

        self.assertEqual(steps, 5)
        self.assertEqual(len(observed_timestamps), 5)
        self.assertEqual(observed_timestamps, sorted(observed_timestamps))


if __name__ == "__main__":
    unittest.main()
