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


def test_build_review_assumptions_full_tier():
    classification = {
        "tier": "FULL",
        "trigger_reason": "diff_lines=500",
        "rules_source": "built_in",
        "agent_roster": ["safety", "data", "quality"],
    }
    context_meta = {
        "estimated_tokens": 12000,
        "token_limit": 16000,
        "truncated_sections": [],
    }
    result = mod.build_review_assumptions(classification, context_meta)
    assert "FULL" in result
    assert "safety, data, quality" in result
    assert "12000" in result
    assert "**截断节**: 无" in result


def test_build_review_assumptions_with_truncation():
    classification = {
        "tier": "LITE",
        "trigger_reason": "diff_lines=100",
        "rules_source": "project_rules",
        "agent_roster": ["safety"],
    }
    context_meta = {
        "estimated_tokens": 14000,
        "token_limit": 16000,
        "truncated_sections": ["change_set"],
    }
    result = mod.build_review_assumptions(classification, context_meta)
    assert "change_set" in result


def test_auto_verify_confirms_with_rule_hit():
    f = mod.Finding("SAFE-003", "P0", "auth/login.go", 42, confidence=0.85)
    rule_hits = {
        "hits": [
            {"rule_id": "SAFE-003", "file": "auth/login.go", "line": 42}
        ]
    }
    mod.auto_verify([f], rule_hits)
    assert f.confidence == 1.0


def test_auto_verify_downgrades_without_hit():
    f = mod.Finding("SAFE-005", "P0", "service/user.go", 10, confidence=0.85)
    rule_hits = {"hits": []}
    original_confidence = f.confidence
    mod.auto_verify([f], rule_hits)
    assert f.confidence < original_confidence


def test_auto_verify_skips_high_confidence():
    f = mod.Finding("DATA-001", "P1", "repo/db.go", 5, confidence=0.95)
    rule_hits = {"hits": []}
    mod.auto_verify([f], rule_hits)
    assert f.confidence == 0.95  # unchanged — already high


def test_auto_verify_skips_p2():
    f = mod.Finding("QUAL-001", "P2", "util/helper.go", 20, confidence=0.8)
    rule_hits = {"hits": []}
    mod.auto_verify([f], rule_hits)
    assert f.confidence == 0.8  # P2 not affected
