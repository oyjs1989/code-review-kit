import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "orchestrate_review",
    Path(__file__).parents[2] / "languages/go/tools/orchestrate-review.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_parse_args_defaults(monkeypatch):
    monkeypatch.setattr("sys.argv", ["orchestrate-review.py", "--mode", "prepare"])
    args = mod.parse_args()
    assert args.mode == "prepare"
    assert args.base == "main"
    assert args.session_dir == ""


def test_ensure_session_dir_creates_dir(tmp_path):
    session_dir = tmp_path / "run-abc123-1234"
    result = mod.ensure_session_dir(str(session_dir))
    assert result.exists()
    assert result == session_dir


def test_build_task_list_lite():
    classification = {
        "tier": "LITE",
        "agent_roster": ["safety", "quality", "observability"],
        "rules_source": "built_in",
        "rules_file": "",
    }
    tasks = mod.build_task_list(classification, session_dir="/tmp/fake-session")
    assert len(tasks) == 3
    assert tasks[0]["agent"] == "safety"
    assert "context_file" in tasks[0]
    assert "output_file" in tasks[0]


def test_build_task_list_full():
    classification = {
        "tier": "FULL",
        "agent_roster": ["safety", "data", "design", "quality", "observability", "business", "naming"],
        "rules_source": "built_in",
        "rules_file": "",
    }
    tasks = mod.build_task_list(classification, session_dir="/tmp/fake-session")
    assert len(tasks) == 7
