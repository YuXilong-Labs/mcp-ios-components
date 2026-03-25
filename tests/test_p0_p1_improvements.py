"""P0+P1 改进的测试用例。

覆盖：
- 多行 ObjC 方法声明合并
- NS_ENUM / NS_OPTIONS 解析
- Category 宿主类标记
- typedef 解析
- 废弃标注提取
- 文档生成按类聚合
- AI prompt 增强

Created by yuxilong on 2026/03/25
"""

import os
import tempfile
import unittest

from mcp_app.indexing.parser import extract_apis, _extract_deprecation
from tools.generate_api_docs import (
    _deprecated_tag,
    _group_apis_by_class,
    _kind_label,
    _split_abstract_discussion,
    generate_component_doc,
)
from tools.ai_doc_filler import build_prompt


class TestMultilineMethodDeclaration(unittest.TestCase):
    """P0-1: 多行 ObjC 方法声明合并。"""

    def test_multiline_method_merged(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write(
                "@interface Foo\n"
                "- (void)doSomethingWithA:(NSString *)a\n"
                "                       b:(NSInteger)b\n"
                "                       c:(BOOL)c;\n"
                "@end\n"
            )
            f.flush()
            apis = extract_apis(f.name, "Foo.h")
        os.unlink(f.name)

        methods = [a for a in apis if a["kind"] == "method"]
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0]["name"], "doSomethingWithA")
        self.assertIn("b:(NSInteger)b", methods[0]["declaration"])
        self.assertIn("c:(BOOL)c", methods[0]["declaration"])

    def test_single_line_method_still_works(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write("- (void)simple:(NSString *)s;\n")
            f.flush()
            apis = extract_apis(f.name, "Foo.h")
        os.unlink(f.name)

        methods = [a for a in apis if a["kind"] == "method"]
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0]["name"], "simple")


class TestNSEnumParsing(unittest.TestCase):
    """P0-2: NS_ENUM / NS_OPTIONS 解析。"""

    def test_ns_enum_with_members(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write(
                "/// 状态枚举\n"
                "typedef NS_ENUM(NSInteger, BTStatus) {\n"
                "    /// 空闲\n"
                "    BTStatusIdle = 0,\n"
                "    /// 加载中\n"
                "    BTStatusLoading,\n"
                "    BTStatusDone\n"
                "};\n"
            )
            f.flush()
            apis = extract_apis(f.name, "BT.h")
        os.unlink(f.name)

        enums = [a for a in apis if a["kind"] == "enum"]
        self.assertEqual(len(enums), 1)
        self.assertEqual(enums[0]["name"], "BTStatus")
        self.assertIn("状态枚举", enums[0]["comment"])

        cases = [a for a in apis if a["kind"] == "enum_case"]
        self.assertEqual(len(cases), 3)
        names = {c["name"] for c in cases}
        self.assertEqual(names, {"BTStatusIdle", "BTStatusLoading", "BTStatusDone"})
        # enum_type 字段
        for c in cases:
            self.assertEqual(c["enum_type"], "BTStatus")

    def test_ns_options(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write(
                "typedef NS_OPTIONS(NSUInteger, BTFlag) {\n"
                "    BTFlagNone = 0,\n"
                "    BTFlagA = 1 << 0,\n"
                "};\n"
            )
            f.flush()
            apis = extract_apis(f.name, "BT.h")
        os.unlink(f.name)

        enums = [a for a in apis if a["kind"] == "enum"]
        self.assertEqual(len(enums), 1)
        self.assertEqual(enums[0]["name"], "BTFlag")


class TestCategoryHostClass(unittest.TestCase):
    """P0-3: Category 宿主类标记。"""

    def test_category_methods_have_host_class(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write(
                "@interface UIImage (BTCornerRadius)\n"
                "- (UIImage *)bt_imageWithCornerRadius:(CGFloat)radius;\n"
                "@end\n"
            )
            f.flush()
            apis = extract_apis(f.name, "UIImage+BTCornerRadius.h")
        os.unlink(f.name)

        methods = [a for a in apis if a["kind"] == "method"]
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0]["host_class"], "UIImage")
        self.assertEqual(methods[0]["category"], "BTCornerRadius")

    def test_regular_interface_no_category(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write(
                "@interface BTManager\n"
                "- (void)start;\n"
                "@end\n"
            )
            f.flush()
            apis = extract_apis(f.name, "BTManager.h")
        os.unlink(f.name)

        methods = [a for a in apis if a["kind"] == "method"]
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0].get("host_class"), "BTManager")
        self.assertFalse(methods[0].get("category"))

    def test_end_resets_host_class(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write(
                "@interface UIImage (A)\n"
                "- (void)a;\n"
                "@end\n"
                "@interface BTFoo\n"
                "- (void)b;\n"
                "@end\n"
            )
            f.flush()
            apis = extract_apis(f.name, "Mixed.h")
        os.unlink(f.name)

        methods = [a for a in apis if a["kind"] == "method"]
        a_method = [m for m in methods if m["name"] == "a"][0]
        b_method = [m for m in methods if m["name"] == "b"][0]
        self.assertEqual(a_method["host_class"], "UIImage")
        self.assertEqual(a_method["category"], "A")
        self.assertEqual(b_method["host_class"], "BTFoo")
        self.assertFalse(b_method.get("category"))


class TestTypedefParsing(unittest.TestCase):
    """P1-6: typedef 解析。"""

    def test_block_typedef(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write("typedef void (^BTCompletionHandler)(BOOL success, NSError *error);\n")
            f.flush()
            apis = extract_apis(f.name, "BT.h")
        os.unlink(f.name)

        typedefs = [a for a in apis if a["kind"] == "typedef"]
        self.assertEqual(len(typedefs), 1)
        self.assertEqual(typedefs[0]["name"], "BTCompletionHandler")

    def test_struct_typedef(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write("typedef struct { CGFloat x; CGFloat y; } BTPoint;\n")
            f.flush()
            apis = extract_apis(f.name, "BT.h")
        os.unlink(f.name)

        typedefs = [a for a in apis if a["kind"] == "typedef"]
        self.assertEqual(len(typedefs), 1)
        self.assertEqual(typedefs[0]["name"], "BTPoint")


class TestDeprecationExtraction(unittest.TestCase):
    """P1-5: 废弃标注提取。"""

    def test_ns_deprecated_ios(self):
        decl = '- (void)old NS_DEPRECATED_IOS(8_0, 12_0, "Use new instead");'
        result = _extract_deprecation(decl)
        self.assertIsNotNone(result)
        self.assertEqual(result["since"], "8_0")
        self.assertEqual(result["until"], "12_0")
        self.assertEqual(result["message"], "Use new instead")

    def test_ns_deprecated_ios_no_message(self):
        decl = "- (void)old NS_DEPRECATED_IOS(8_0, 12_0);"
        result = _extract_deprecation(decl)
        self.assertIsNotNone(result)
        self.assertEqual(result["since"], "8_0")
        self.assertNotIn("message", result)

    def test_attribute_deprecated(self):
        decl = '__attribute__((deprecated("use newMethod"))) - (void)oldMethod;'
        result = _extract_deprecation(decl)
        self.assertIsNotNone(result)
        self.assertEqual(result["message"], "use newMethod")

    def test_attribute_deprecated_no_message(self):
        decl = "__attribute__((deprecated)) - (void)oldMethod;"
        result = _extract_deprecation(decl)
        self.assertIsNotNone(result)

    def test_swift_available_deprecated(self):
        decl = '@available(*, deprecated, message: "Use bar", renamed: "bar") public func foo()'
        result = _extract_deprecation(decl)
        self.assertIsNotNone(result)
        self.assertEqual(result["message"], "Use bar")
        self.assertEqual(result["replacement"], "bar")

    def test_no_deprecation(self):
        decl = "- (void)normalMethod;"
        result = _extract_deprecation(decl)
        self.assertIsNone(result)

    def test_deprecated_in_parsed_api(self):
        with tempfile.NamedTemporaryFile(suffix=".h", mode="w", delete=False) as f:
            f.write('- (void)old NS_DEPRECATED_IOS(8_0, 12_0, "Use new");\n')
            f.flush()
            apis = extract_apis(f.name, "A.h")
        os.unlink(f.name)

        self.assertEqual(len(apis), 1)
        self.assertIn("deprecated", apis[0])
        self.assertEqual(apis[0]["deprecated"]["since"], "8_0")


class TestGroupApisByClass(unittest.TestCase):
    """P0-4: 按类聚合。"""

    def test_groups_by_class(self):
        apis = [
            {"kind": "interface", "name": "Foo", "declaration": "@interface Foo"},
            {"kind": "method", "name": "bar", "host_class": "Foo", "declaration": "- (void)bar;"},
            {"kind": "property", "name": "name", "host_class": "Foo", "declaration": "@property NSString *name;"},
            {"kind": "func", "name": "helper", "declaration": "void helper();"},
        ]
        groups, enums, typedefs, standalone = _group_apis_by_class(apis)

        self.assertIn("Foo", groups)
        self.assertEqual(groups["Foo"]["definition"]["name"], "Foo")
        self.assertEqual(len(groups["Foo"]["members"]), 2)
        self.assertEqual(len(standalone), 1)
        self.assertEqual(standalone[0]["name"], "helper")

    def test_category_grouped_under_host(self):
        apis = [
            {"kind": "interface", "name": "UIImage", "host_class": "UIImage",
             "category": "Resize", "declaration": "@interface UIImage (Resize)"},
            {"kind": "method", "name": "resize", "host_class": "UIImage",
             "category": "Resize", "declaration": "- (UIImage *)resize;"},
        ]
        groups, _, _, _ = _group_apis_by_class(apis)

        self.assertIn("UIImage", groups)
        self.assertIn("Resize", groups["UIImage"]["categories"])
        self.assertEqual(len(groups["UIImage"]["categories"]["Resize"]), 1)

    def test_enum_grouping(self):
        apis = [
            {"kind": "enum", "name": "BTStatus", "declaration": "typedef NS_ENUM(...)"},
            {"kind": "enum_case", "name": "BTStatusIdle", "enum_type": "BTStatus", "declaration": "BTStatusIdle = 0"},
            {"kind": "enum_case", "name": "BTStatusDone", "enum_type": "BTStatus", "declaration": "BTStatusDone"},
        ]
        _, enums, _, _ = _group_apis_by_class(apis)

        self.assertEqual(len(enums), 1)
        self.assertEqual(enums[0]["definition"]["name"], "BTStatus")
        self.assertEqual(len(enums[0]["members"]), 2)

    def test_typedef_grouping(self):
        apis = [
            {"kind": "typedef", "name": "BTHandler", "declaration": "typedef void (^BTHandler)();"},
        ]
        _, _, typedefs, _ = _group_apis_by_class(apis)
        self.assertEqual(len(typedefs), 1)


class TestDeprecatedTag(unittest.TestCase):
    """废弃标签生成。"""

    def test_no_deprecated(self):
        self.assertEqual(_deprecated_tag({}), "")
        self.assertEqual(_deprecated_tag({"deprecated": None}), "")

    def test_with_since_until(self):
        tag = _deprecated_tag({"deprecated": {"since": "8_0", "until": "12_0"}})
        self.assertIn("已废弃", tag)
        self.assertIn("8_0", tag)

    def test_with_message(self):
        tag = _deprecated_tag({"deprecated": {"message": "Use bar"}})
        self.assertIn("Use bar", tag)

    def test_with_replacement(self):
        tag = _deprecated_tag({"deprecated": {"replacement": "newFunc"}})
        self.assertIn("newFunc", tag)


class TestSplitAbstractDiscussion(unittest.TestCase):
    """abstract/discussion 拆分。"""

    def test_single_line(self):
        abstract, discussion = _split_abstract_discussion("/// 简短说明")
        self.assertEqual(abstract, "简短说明")
        self.assertEqual(discussion, "")

    def test_multi_line(self):
        comment = "/// 摘要行\n/// 详细讨论第一行\n/// 详细讨论第二行"
        abstract, discussion = _split_abstract_discussion(comment)
        self.assertEqual(abstract, "摘要行")
        self.assertIn("详细讨论第一行", discussion)

    def test_block_comment(self):
        comment = "/** 摘要\n * 详细 */\n"
        abstract, discussion = _split_abstract_discussion(comment)
        self.assertEqual(abstract, "摘要")

    def test_empty(self):
        abstract, discussion = _split_abstract_discussion("")
        self.assertEqual(abstract, "")
        self.assertEqual(discussion, "")


class TestKindLabel(unittest.TestCase):
    """kind 标签映射。"""

    def test_new_kinds(self):
        self.assertIn("枚举值", _kind_label("enum_case"))
        self.assertIn("类型定义", _kind_label("typedef"))

    def test_existing_kinds(self):
        self.assertIn("方法", _kind_label("method"))
        self.assertIn("类", _kind_label("interface"))


class TestGenerateComponentDoc(unittest.TestCase):
    """文档生成集成测试。"""

    def test_class_aggregated_output(self):
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
                {"kind": "enum", "name": "TCStatus", "declaration": "typedef NS_ENUM(NSInteger, TCStatus)",
                 "file": "TCStatus.h", "line": 1, "comment": ""},
                {"kind": "enum_case", "name": "TCStatusIdle", "declaration": "TCStatusIdle = 0",
                 "file": "TCStatus.h", "line": 2, "comment": "/// 空闲", "enum_type": "TCStatus"},
            ],
        }
        doc = generate_component_doc(comp, {}, "")

        # 按类聚合：TCManager 章节
        self.assertIn("TCManager", doc)
        self.assertIn("start", doc)
        # 枚举章节
        self.assertIn("TCStatus", doc)
        self.assertIn("TCStatusIdle", doc)
        self.assertIn("空闲", doc)

    def test_deprecated_api_shown(self):
        comp = {
            "name": "DepComp",
            "summary": "",
            "description": "",
            "source_count": 1,
            "apis": [
                {"kind": "method", "name": "oldMethod", "declaration": "- (void)oldMethod;",
                 "host_class": "Foo", "file": "Foo.h", "line": 1, "comment": "",
                 "deprecated": {"since": "8_0", "until": "12_0", "message": "Use new"}},
            ],
        }
        doc = generate_component_doc(comp, {}, "")
        self.assertIn("已废弃", doc)
        self.assertIn("Use new", doc)


class TestAIPromptEnhancement(unittest.TestCase):
    """P1-8: AI prompt 增强。"""

    def test_prompt_includes_example_section(self):
        prompt = build_prompt("- (void)foo;", "// context", "TestComp")
        self.assertIn("示例", prompt)
        self.assertIn("调用示例代码", prompt)

    def test_prompt_includes_all_sections(self):
        prompt = build_prompt("- (void)bar:(NSString *)s;", "// src", "Comp")
        self.assertIn("参数", prompt)
        self.assertIn("返回值", prompt)
        self.assertIn("示例", prompt)
        self.assertIn("组件：Comp", prompt)


if __name__ == "__main__":
    unittest.main()
