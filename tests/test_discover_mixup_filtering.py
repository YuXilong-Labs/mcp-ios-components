"""组件发现过滤逻辑修复的测试。

覆盖：
- 多行 SUPPORT_MIXUP 数组应被正确解析并过滤
- BETA_SUPPORT_MIXUP 不应作为过滤依据
- _merge_multiline_arrays 合并逻辑

Created by yuxilong on 2026/03/25
"""

import os
import tempfile
import unittest

from mcp_app.indexing.discover import _merge_multiline_arrays, discover_components


def _noop_normalize(name: str) -> str:
    return name.lower()


def _noop_load_ac() -> dict:
    return {"exclude_from_index": set(), "api_only": set()}


def _extract_pod_name(spec_content: str, fallback: str) -> str:
    import re
    m = re.search(r"\.name\s*=\s*['\"](.+?)['\"]", spec_content)
    return m.group(1) if m else fallback


class TestMergeMultilineArrays(unittest.TestCase):
    """多行数组合并。"""

    def test_multiline_array_merged(self):
        content = (
            "SUPPORT_MIXUP = [\n"
            "  'PLA' => 'PLAHTLS',\n"
            "  'VO' => 'VOOStream',\n"
            "]\n"
        )
        merged = _merge_multiline_arrays(content)
        self.assertIn("SUPPORT_MIXUP = [", merged)
        self.assertIn("'PLA' => 'PLAHTLS'", merged)
        self.assertIn("]", merged)
        # 应合并为单行
        for line in merged.split("\n"):
            if "SUPPORT_MIXUP" in line:
                self.assertIn("]", line)

    def test_single_line_unchanged(self):
        content = "SUPPORT_MIXUP = ['BT']\nother = 1"
        merged = _merge_multiline_arrays(content)
        self.assertEqual(merged, content)

    def test_no_array(self):
        content = "s.name = 'Foo'\ns.version = '1.0'\n"
        merged = _merge_multiline_arrays(content)
        self.assertIn("s.name = 'Foo'", merged)


class TestDiscoverComponentFiltering(unittest.TestCase):
    """组件发现的 MIXUP 过滤逻辑。"""

    def _make_pods_dir(self, components: dict[str, str]) -> str:
        """创建临时 Pods 目录。components: {name: podspec_content}"""
        tmpdir = tempfile.mkdtemp()
        for name, spec in components.items():
            comp_dir = os.path.join(tmpdir, name)
            os.makedirs(comp_dir)
            with open(os.path.join(comp_dir, f"{name}.podspec"), "w") as f:
                f.write(spec)
        return tmpdir

    def test_beta_mixup_only_not_filtered(self):
        """BTBaseKit 场景：只有 BETA_SUPPORT_MIXUP，没有正式 SUPPORT_MIXUP，应被保留。"""
        pods_dir = self._make_pods_dir({
            "BTBaseKit": (
                "Pod::Spec.new do |s|\n"
                "  s.name = 'BTBaseKit'\n"
                "  s.summary = 'base'\n"
                "end\n"
                "BETA_SUPPORT_MIXUP = ['BT']\n"
            ),
        })
        found = discover_components(
            pods_dir,
            mixup_marker="SUPPORT_MIXUP",
            normalize_name=_noop_normalize,
            load_access_control_func=_noop_load_ac,
            extract_pod_name=_extract_pod_name,
        )
        self.assertIn("BTBaseKit", found)

    def test_multiline_support_mixup_filtered(self):
        """BTLiveRoom 场景：多行 SUPPORT_MIXUP 非空，应被过滤掉。"""
        pods_dir = self._make_pods_dir({
            "BTLiveRoom": (
                "Pod::Spec.new do |s|\n"
                "  s.name = 'BTLiveRoom'\n"
                "end\n"
                "SUPPORT_MIXUP = [\n"
                "  'PLA' => 'PLAHTLS',\n"
                "  'VO' => 'VOOStream',\n"
                "]\n"
            ),
        })
        found = discover_components(
            pods_dir,
            mixup_marker="SUPPORT_MIXUP",
            normalize_name=_noop_normalize,
            load_access_control_func=_noop_load_ac,
            extract_pod_name=_extract_pod_name,
        )
        self.assertNotIn("BTLiveRoom", found)

    def test_single_line_support_mixup_filtered(self):
        """单行 SUPPORT_MIXUP 非空也应被过滤。"""
        pods_dir = self._make_pods_dir({
            "BizComp": (
                "SUPPORT_MIXUP = ['BT', 'MNL']\n"
                "Pod::Spec.new do |s|\n"
                "  s.name = 'BizComp'\n"
                "end\n"
            ),
        })
        found = discover_components(
            pods_dir,
            mixup_marker="SUPPORT_MIXUP",
            normalize_name=_noop_normalize,
            load_access_control_func=_noop_load_ac,
            extract_pod_name=_extract_pod_name,
        )
        self.assertNotIn("BizComp", found)

    def test_empty_support_mixup_not_filtered(self):
        """SUPPORT_MIXUP = [] 空数组，应保留。"""
        pods_dir = self._make_pods_dir({
            "BaseLib": (
                "SUPPORT_MIXUP = []\n"
                "Pod::Spec.new do |s|\n"
                "  s.name = 'BaseLib'\n"
                "end\n"
            ),
        })
        found = discover_components(
            pods_dir,
            mixup_marker="SUPPORT_MIXUP",
            normalize_name=_noop_normalize,
            load_access_control_func=_noop_load_ac,
            extract_pod_name=_extract_pod_name,
        )
        self.assertIn("BaseLib", found)

    def test_no_mixup_at_all_not_filtered(self):
        """完全没有 MIXUP 标记，应保留。"""
        pods_dir = self._make_pods_dir({
            "PureBase": (
                "Pod::Spec.new do |s|\n"
                "  s.name = 'PureBase'\n"
                "end\n"
            ),
        })
        found = discover_components(
            pods_dir,
            mixup_marker="SUPPORT_MIXUP",
            normalize_name=_noop_normalize,
            load_access_control_func=_noop_load_ac,
            extract_pod_name=_extract_pod_name,
        )
        self.assertIn("PureBase", found)


if __name__ == "__main__":
    unittest.main()
