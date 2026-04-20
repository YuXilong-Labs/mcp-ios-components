from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools import generate_api_docs as gad


@pytest.fixture
def fake_pods(tmp_path):
    (tmp_path / "CompA").mkdir()
    (tmp_path / "CompB").mkdir()
    return str(tmp_path)


def test_batch_discovers_and_filters_non_main(fake_pods):
    fake_bootstrap = SimpleNamespace(build_index=lambda _pods_dir: {"CompA": {"name": "CompA"}})

    with (
        patch.object(gad, "_discover_base_components", return_value=["CompA", "CompB"]),
        patch.object(
            gad,
            "get_git_repo_branch",
            side_effect=lambda path: "main" if "CompA" in path else "feature/x",
        ),
        patch.object(gad, "_bootstrap_module", return_value=fake_bootstrap),
        patch.object(gad, "_process_single_component", return_value={"status": "ok", "component": "CompA"}),
    ):
        summary = gad._run_batch_upload(
            pods_dir=fake_pods,
            wiki_node="wikcn_XYZ",
            polish=False,
            dry_run=True,
        )

    assert [item["component"] for item in summary["ok"]] == ["CompA"]
    assert [item["component"] for item in summary["skipped"]] == ["CompB"]
    assert summary["skipped"][0]["reason"].startswith("non-main")


def test_batch_build_index_failure_records_all_main_components(fake_pods):
    def fail_build(_pods_dir):
        raise RuntimeError("cache corrupt")

    fake_bootstrap = SimpleNamespace(build_index=fail_build)

    with (
        patch.object(gad, "_discover_base_components", return_value=["CompA", "CompB", "CompC"]),
        patch.object(
            gad,
            "get_git_repo_branch",
            side_effect=lambda path: "feature/x" if "CompB" in path else "main",
        ),
        patch.object(gad, "_bootstrap_module", return_value=fake_bootstrap),
        patch.object(gad, "_process_single_component") as proc,
    ):
        summary = gad._run_batch_upload(
            pods_dir=fake_pods,
            wiki_node="w",
            polish=False,
            dry_run=False,
        )

    proc.assert_not_called()
    assert [item["component"] for item in summary["skipped"]] == ["CompB"]
    failed_names = [item["component"] for item in summary["failed"]]
    assert failed_names == ["CompA", "CompC"]
    assert all("build_index failed" in item["reason"] for item in summary["failed"])
