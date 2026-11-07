"""Validation of the simulator and the research analysis."""

from pathlib import Path


class ValidationSuite:
    """Run the regression checks without a top-level tests directory."""

    def run(self):
        import pytest

        code = pytest.main([str(Path(__file__).with_name("checks")), "-q"])
        if code != 0:
            raise RuntimeError(f"regression verification failed: {code}")
        return {"status": "PASS", "returncode": int(code)}
