"""飞书文档格式转换器（lark_doc_formatter.py）的测试。

覆盖 Block 构建函数、组件转换、索引页转换。

Created by yuxilong on 2026/03/25
"""

import unittest

from tools.lark_doc_formatter import (
    _bullet_block,
    _code_block,
    _deprecated_text,
    _divider_block,
    _heading_block,
    _quote_block,
    _text_block,
    convert_component_to_blocks,
    convert_index_to_blocks,
)


class TestBlockBuilders(unittest.TestCase):
    """Block 构建辅助函数。"""

    def test_text_block(self):
        block = _text_block("hello")
        self.assertEqual(block["block_type"], 2)
        self.assertEqual(block["text"]["elements"][0]["text_run"]["content"], "hello")

    def test_text_block_bold(self):
        block = _text_block("bold text", bold=True)
        style = block["text"]["elements"][0]["text_run"]["text_element_style"]
        self.assertTrue(style["bold"])

    def test_heading_block_levels(self):
        for level in range(1, 5):
            block = _heading_block(level, f"H{level}")
            self.assertEqual(block["block_type"], level + 2)
            field = f"heading{level}"
            self.assertIn(field, block)
            self.assertEqual(block[field]["elements"][0]["text_run"]["content"], f"H{level}")

    def test_heading_block_clamp(self):
        block = _heading_block(0, "clamped")
        self.assertEqual(block["block_type"], 3)  # heading1

    def test_code_block_objc(self):
        block = _code_block("- (void)foo;", "objc")
        self.assertEqual(block["block_type"], 14)
        self.assertEqual(block["code"]["style"]["language"], 28)
        self.assertEqual(block["code"]["elements"][0]["text_run"]["content"], "- (void)foo;")

    def test_code_block_swift(self):
        block = _code_block("public func bar()", "swift")
        self.assertEqual(block["code"]["style"]["language"], 43)

    def test_code_block_unknown_lang(self):
        block = _code_block("some code", "unknown")
        self.assertEqual(block["code"]["style"]["language"], 1)  # plaintext fallback

    def test_bullet_block(self):
        block = _bullet_block("item")
        self.assertEqual(block["block_type"], 12)
        self.assertEqual(block["bullet"]["elements"][0]["text_run"]["content"], "item")

    def test_quote_block(self):
        block = _quote_block("quoted")
        self.assertEqual(block["block_type"], 15)

    def test_divider_block(self):
        block = _divider_block()
        self.assertEqual(block["block_type"], 22)


class TestDeprecatedText(unittest.TestCase):
    """废弃标注文本。"""

    def test_no_deprecated(self):
        self.assertEqual(_deprecated_text({}), "")

    def test_with_message(self):
        text = _deprecated_text({"deprecated": {"message": "Use new"}})
        self.assertIn("已废弃", text)
        self.assertIn("Use new", text)


class TestConvertComponentToBlocks(unittest.TestCase):
    """组件转 Block 列表。"""

    def test_basic_component(self):
        comp = {
            "name": "TestComp",
            "summary": "测试组件",
            "description": "",
            "source_count": 1,
            "apis": [
                {"kind": "interface", "name": "TCManager", "declaration": "@interface TCManager",
                 "file": "TCManager.h", "line": 1, "comment": "/// 管理器"},
                {"kind": "method", "name": "start", "declaration": "- (void)start;",
                 "host_class": "TCManager", "file": "TCManager.h", "line": 3, "comment": ""},
            ],
        }
        blocks = convert_component_to_blocks(comp, {}, "")

        # 应有 heading1（组件名）
        h1_blocks = [b for b in blocks if b.get("block_type") == 3]
        self.assertTrue(len(h1_blocks) >= 1)
        self.assertEqual(h1_blocks[0]["heading1"]["elements"][0]["text_run"]["content"], "TestComp")

        # 应有 code block（声明）
        code_blocks = [b for b in blocks if b.get("block_type") == 14]
        self.assertTrue(len(code_blocks) >= 1)

        # 应有 divider
        dividers = [b for b in blocks if b.get("block_type") == 22]
        self.assertTrue(len(dividers) >= 1)

    def test_enum_component(self):
        comp = {
            "name": "EnumComp",
            "summary": "",
            "description": "",
            "source_count": 1,
            "apis": [
                {"kind": "enum", "name": "Status", "declaration": "typedef NS_ENUM(NSInteger, Status)",
                 "file": "S.h", "line": 1, "comment": ""},
                {"kind": "enum_case", "name": "StatusIdle", "declaration": "StatusIdle = 0",
                 "file": "S.h", "line": 2, "comment": "/// 空闲", "enum_type": "Status"},
            ],
        }
        blocks = convert_component_to_blocks(comp, {}, "")

        # 应有枚举成员的 bullet
        bullets = [b for b in blocks if b.get("block_type") == 12]
        self.assertTrue(len(bullets) >= 1)
        bullet_text = bullets[0]["bullet"]["elements"][0]["text_run"]["content"]
        self.assertIn("StatusIdle", bullet_text)

    def test_empty_apis(self):
        comp = {"name": "Empty", "summary": "", "description": "", "source_count": 0, "apis": []}
        blocks = convert_component_to_blocks(comp, {}, "")
        texts = [b for b in blocks if b.get("block_type") == 2]
        any_empty_msg = any("未发现" in t["text"]["elements"][0]["text_run"]["content"] for t in texts)
        self.assertTrue(any_empty_msg)

    def test_deprecated_api_shown(self):
        comp = {
            "name": "DepComp",
            "summary": "",
            "description": "",
            "source_count": 1,
            "apis": [
                {"kind": "method", "name": "old", "declaration": "- (void)old;",
                 "host_class": "Foo", "file": "Foo.h", "line": 1, "comment": "",
                 "deprecated": {"message": "Use new"}},
            ],
        }
        blocks = convert_component_to_blocks(comp, {}, "")
        # heading4 应包含废弃标注
        h4_blocks = [b for b in blocks if b.get("block_type") == 6]
        any_deprecated = any("已废弃" in b["heading4"]["elements"][0]["text_run"]["content"] for b in h4_blocks)
        self.assertTrue(any_deprecated)


class TestConvertIndexToBlocks(unittest.TestCase):
    """索引页转 Block。"""

    def test_index_page(self):
        components = {
            "A": {"name": "A", "summary": "desc A", "apis": [1, 2], "source_count": 3},
            "B": {"name": "B", "summary": "", "apis": [], "source_count": 0},
        }
        blocks = convert_index_to_blocks(components)

        h1 = [b for b in blocks if b.get("block_type") == 3]
        self.assertTrue(len(h1) >= 1)

        bullets = [b for b in blocks if b.get("block_type") == 12]
        self.assertEqual(len(bullets), 2)


if __name__ == "__main__":
    unittest.main()
