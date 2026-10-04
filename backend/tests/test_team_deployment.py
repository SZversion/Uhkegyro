"""Guard background processing settings; a healthy HTTP service can still stall jobs."""
from pathlib import Path

import yaml


def test_api_worker_runs_without_http_and_preserves_observability_target():
    config = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "cloudbuild.yaml").read_text(encoding="utf-8")
    )
    steps = {step["id"]: step for step in config["steps"]}
    api = steps["deploy-api"]["args"][1]
    for flag in (
        "--min=1", "--max=1", "--no-cpu-throttling",
        "--min-instances=default", "--max-instances=default",
    ):
        assert flag in api
    assert "--min-instances=0" not in api
    # Replacing all env vars would discard the configured shared Langfuse URL.
    assert "--set-env-vars=" not in api
    assert "--update-env-vars=" in api
    for setting in (
        "MCP_ENABLED=true", "WORKER_CONCURRENCY=5", "ENVIRONMENT=production",
        "INTERPRETER_PROMPT_PATH=/app/prompts/uhkegryo-interpreter-v4.md",
        "INTERPRETER_PROMPT_VERSION=uhkegryo-interpreter-v4",
        "STRUCTURED_OUTPUT_SKILL_PATH=/app/skills/structured-output/SKILL.md",
        "TERM_CARDS_PATH=/app/term-cards",
    ):
        assert setting in api
    mcp = steps["deploy-mcp"]["args"][1]
    assert "--no-allow-unauthenticated" in mcp
    assert "--no-cpu-throttling" not in mcp
