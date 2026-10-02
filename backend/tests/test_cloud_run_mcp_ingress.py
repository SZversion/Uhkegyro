import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cloud_run_mcp_ingress.py"


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        (None, "mcp"),
        ({"spec": {"template": {"spec": {"containers": [{"name": "legacy", "ports": [{"containerPort": 8000}]}]}}}}, "legacy"),
        ({"spec": {"template": {"spec": {"containers": [{"image": "old", "ports": [{"containerPort": 8000}]}]}}}}, "__default__"),
    ],
)
def test_selects_mcp_ingress_for_new_named_and_unnamed_services(tmp_path, service, expected):
    config = tmp_path / "service.json"
    if service is not None:
        config.write_text(json.dumps(service), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(config) if service is not None else ""],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == expected


def test_rejects_multiple_ingress_containers(tmp_path):
    config = tmp_path / "service.json"
    config.write_text(json.dumps({"spec": {"template": {"spec": {"containers": [
        {"name": "one", "ports": [{"containerPort": 8000}]},
        {"name": "two", "ports": [{"containerPort": 8001}]},
    ]}}}}), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(config)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "exactly one ingress container" in result.stderr
