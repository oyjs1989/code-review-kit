import importlib.util
from pathlib import Path

# Load aggregate-findings.py via importlib (hyphen in filename prevents normal import)
spec = importlib.util.spec_from_file_location(
    "aggregate_findings",
    Path(__file__).parents[2] / "languages/go/tools/aggregate-findings.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

Finding = mod.Finding
SEVERITY_ORDER = mod.SEVERITY_ORDER


def test_finding_sort_key():
    f = Finding("SAFE-001", "P0", "main.go", 10)
    assert f.sort_key[0] == 0  # P0 → 0


def test_severity_order_complete():
    assert set(SEVERITY_ORDER.keys()) == {"P0", "P1", "P2", "P3"}
