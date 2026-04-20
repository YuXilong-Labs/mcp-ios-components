from __future__ import annotations

import pytest

from tools import generate_api_docs as gad


def test_cli_batch_upload_argument_removed():
    """--batch-upload 已退场：argparse 应直接拒识并以 SystemExit(2) 终止。"""
    with pytest.raises(SystemExit) as exc:
        gad.main(["--batch-upload"])
    assert exc.value.code == 2


def test_cli_polish_flag_removed():
    """--polish 已退场：批量语义已迁移到 /wk-lark-wiki-batch skill。"""
    with pytest.raises(SystemExit) as exc:
        gad.main(["--polish"])
    assert exc.value.code == 2


def test_batch_helpers_removed():
    """批量辅助函数已删除，避免内部复用残留代码。"""
    for name in (
        "_run_batch_upload",
        "_process_single_component",
        "_discover_base_components",
        "_print_batch_summary",
        "_get_lark_cli",
        "_bootstrap_module",
    ):
        assert not hasattr(gad, name), f"{name} should be removed from generate_api_docs"
