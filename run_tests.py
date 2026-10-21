"""
AlphaNSE V2 Comprehensive Test Runner.
Discovers and executes all Phase 1 unit, equivalence, risk, and execution test suites.
"""

import os
import sys
import time
import unittest

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.dirname(__file__))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)


def main():
    print("=" * 80)
    print(" ALPHANSE V2 — PHASE 1 & 2 AUTOMATED VERIFICATION SUITE")
    print("=" * 80)
    print(f"Workspace Root: {WORKSPACE_ROOT}")
    print(f"Python Version: {sys.version.split()[0]}")
    print("-" * 80)

    start_time = time.time()
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.join(WORKSPACE_ROOT, "tests"), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    elapsed = time.time() - start_time

    print("=" * 80)
    print(" TEST RUN SUMMARY")
    print("=" * 80)
    print(f" Total Tests Run:   {result.testsRun}")
    print(f" Total Passed:      {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f" Total Failures:    {len(result.failures)}")
    print(f" Total Errors:      {len(result.errors)}")
    print(f" Execution Time:    {elapsed:.3f} seconds")
    print("=" * 80)

    if result.wasSuccessful():
        print(" VERDICT: ALL PHASE 1 & 2 TESTS PASSED [SUCCESS]")
        print("=" * 80)
        sys.exit(0)
    else:
        print(" VERDICT: SOME TESTS FAILED [FAILURE]")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
