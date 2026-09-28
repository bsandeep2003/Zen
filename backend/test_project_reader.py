"""
test_project_reader.py — Unit & Integration tests for Layer 1 Project Awareness.
"""
from pathlib import Path
from project_reader import (
    scan_project,
    detect_stack,
    get_git_activity,
    analyze_tests,
    build_llm_project_context,
    format_cli_summary,
)


def test_scan_project_zen():
    root = Path(__file__).resolve().parent.parent
    summary = scan_project(str(root))
    
    assert summary.total_files > 0
    assert summary.project_name == "Zen"
    assert summary.stack.primary_language in ["Python", "JavaScript"]
    assert "Fastapi" in summary.stack.frameworks or "React" in summary.stack.frameworks
    assert summary.git.is_git_repo is True
    assert summary.git.branch != ""


def test_build_llm_project_context():
    root = Path(__file__).resolve().parent.parent
    summary = scan_project(str(root))
    ctx = build_llm_project_context(summary, focus_file="backend/agent.py")
    
    assert "Project: Zen" in ctx
    assert "Git:" in ctx
    assert "Active File: backend/agent.py" in ctx
    # Keep it token-budgeted (< 400 chars)
    assert len(ctx) < 800


def test_format_cli_summary():
    root = Path(__file__).resolve().parent.parent
    summary = scan_project(str(root))
    report = format_cli_summary(summary)
    
    assert "LAYER 1: PROJECT AWARENESS SCAN" in report
    assert "Primary Stack" in report
    assert "Git Activity" in report


if __name__ == "__main__":
    test_scan_project_zen()
    test_build_llm_project_context()
    test_format_cli_summary()
    print("All Layer 1 Project Awareness tests passed successfully!")
