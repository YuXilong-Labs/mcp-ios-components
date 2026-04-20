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


def test_process_single_component_pull_generate_upload(fake_pods):
    fake_index = {"CompA": {"name": "CompA", "dir": "CompA", "apis": [], "files": []}}
    pull_mock = patch.object(gad, "git_pull_repo", return_value={"updated": True, "changes": ["a.h"], "error": None})
    gen_mock = patch.object(gad, "generate_component_doc", return_value="# CompA\n")
    lark_instance = SimpleNamespace(create_wiki_doc=lambda node, title, md: {"doc_id": "docX", "doc_url": "http://u"})

    with pull_mock as pull, gen_mock as gen, patch.object(gad, "_get_lark_cli", return_value=lark_instance):
        result = gad._process_single_component(
            component="CompA",
            comp_path=fake_pods + "/CompA",
            index=fake_index,
            pods_dir=fake_pods,
            wiki_node="wiki_Y",
            polish=False,
            dry_run=False,
        )

    pull.assert_called_once_with(fake_pods + "/CompA")
    gen.assert_called_once()
    assert result == {
        "status": "ok",
        "component": "CompA",
        "pull_changes": ["a.h"],
        "doc_id": "docX",
        "doc_url": "http://u",
    }


def test_process_single_component_pull_failure_returns_failed(fake_pods):
    fake_index = {"CompA": {"name": "CompA", "dir": "CompA", "apis": [], "files": []}}

    with (
        patch.object(gad, "git_pull_repo", return_value={"updated": False, "changes": [], "error": "auth denied"}),
        patch.object(gad, "generate_component_doc") as gen,
        patch.object(gad, "_get_lark_cli") as cli_factory,
    ):
        result = gad._process_single_component(
            component="CompA",
            comp_path=fake_pods + "/CompA",
            index=fake_index,
            pods_dir=fake_pods,
            wiki_node="w",
            polish=False,
            dry_run=False,
        )

    gen.assert_not_called()
    cli_factory.assert_not_called()
    assert result["status"] == "failed"
    assert result["component"] == "CompA"
    assert "pull failed" in result["reason"]


def test_process_single_component_upload_failure_isolated(fake_pods):
    from tools.lark_cli_wrapper import LarkCliError

    fake_index = {"CompA": {"name": "CompA", "dir": "CompA", "apis": [], "files": []}}

    def boom(*_args, **_kwargs):
        raise LarkCliError("lark cli crashed")

    lark_instance = SimpleNamespace(create_wiki_doc=boom)

    with (
        patch.object(gad, "git_pull_repo", return_value={"updated": False, "changes": [], "error": None}),
        patch.object(gad, "generate_component_doc", return_value="# A"),
        patch.object(gad, "_get_lark_cli", return_value=lark_instance),
    ):
        result = gad._process_single_component(
            component="CompA",
            comp_path=fake_pods + "/CompA",
            index=fake_index,
            pods_dir=fake_pods,
            wiki_node="w",
            polish=False,
            dry_run=False,
        )

    assert result["status"] == "failed"
    assert "upload failed" in result["reason"]
    assert "lark cli crashed" in result["reason"]


def test_batch_polish_flag_toggles_filler(fake_pods):
    fake_bootstrap = SimpleNamespace(build_index=lambda _d: {"A": {"name": "A"}})
    with (
        patch.object(gad, "_discover_base_components", return_value=["A"]),
        patch.object(gad, "get_git_repo_branch", return_value="main"),
        patch.object(gad, "_bootstrap_module", return_value=fake_bootstrap),
        patch.object(gad, "git_pull_repo", return_value={"updated": False, "changes": [], "error": None}),
        patch.object(gad, "generate_component_doc", return_value="# A"),
        patch.object(
            gad,
            "_get_lark_cli",
            return_value=SimpleNamespace(create_wiki_doc=lambda node, title, md: {"doc_id": "d", "doc_url": "u"}),
        ),
        patch("tools.ai_doc_filler.fill_missing_comments", return_value={"results": {}}) as fill,
    ):
        gad._run_batch_upload(pods_dir=fake_pods, wiki_node="w", polish=False, dry_run=False)
        fill.assert_not_called()

        gad._run_batch_upload(pods_dir=fake_pods, wiki_node="w", polish=True, dry_run=False)
        fill.assert_called_once()


def test_cli_batch_upload_dispatch(fake_pods):
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"ok": [], "skipped": [], "failed": []}

    with patch.object(gad, "_run_batch_upload", side_effect=fake_run):
        rc = gad.main(
            [
                "--batch-upload",
                "--pods-dir",
                fake_pods,
                "--wiki-node",
                "wikcn_Z",
                "--polish",
            ]
        )

    assert rc == 0
    assert captured["pods_dir"] == fake_pods
    assert captured["wiki_node"] == "wikcn_Z"
    assert captured["polish"] is True
    assert captured["dry_run"] is False


def test_cli_batch_upload_missing_wiki_node_errors(fake_pods):
    with patch.object(gad, "_run_batch_upload") as run:
        rc = gad.main(["--batch-upload", "--pods-dir", fake_pods])
    run.assert_not_called()
    assert rc == 2


def test_cli_batch_upload_reports_failures_as_exit_1(fake_pods):
    with patch.object(
        gad,
        "_run_batch_upload",
        return_value={"ok": [], "skipped": [], "failed": [{"component": "A", "reason": "boom"}]},
    ):
        rc = gad.main(["--batch-upload", "--pods-dir", fake_pods, "--wiki-node", "w"])
    assert rc == 1
