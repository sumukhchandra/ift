"""
Unit tests for IncrementalFeatureEngine mechanics and bounded buffers.
"""

import unittest
from datetime import datetime, timedelta
from v2.data.schema import Bar
from v2.features.incremental_engine import IncrementalFeatureEngine


class TestIncrementalEngine(unittest.TestCase):

    def test_buffer_bounded_at_max_lookback(self):
        engine = IncrementalFeatureEngine(max_lookback=60)
        base_time = datetime(2026, 9, 18, 9, 15)

        # Feed 100 bars
        for i in range(100):
            bar = Bar(
                timestamp=base_time + timedelta(minutes=i),
                symbol="TATACAP.NS",
                open=350.0 + (i * 0.1),
                high=351.0 + (i * 0.1),
                low=349.5 + (i * 0.1),
                close=350.5 + (i * 0.1),
                volume=1000.0 + i
            )
            features = engine.update(bar)

        st = engine.get_state("TATACAP.NS")
        self.assertEqual(len(st.closes), 60)
        self.assertEqual(len(st.highs), 60)
        self.assertEqual(len(st.lows), 60)
        self.assertEqual(len(st.volumes), 60)
        self.assertEqual(len(features), 30)
        for k, v in features.items():
            self.assertFalse(math_is_nan(v), f"Feature {k} returned NaN")


def math_is_nan(val):
    import math
    return math.isnan(val)


if __name__ == "__main__":
    unittest.main()
