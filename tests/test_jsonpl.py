"""
jsonpl 正式測試套件（使用 stdlib unittest，可直接被 pytest 收集執行）

跑法：
    python3 -m unittest tests/test_jsonpl.py -v
或（若環境有安裝 pytest）：
    pytest tests/test_jsonpl.py -v
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jsonpl
from jsonpl import send_json, parse_jsonpl, rewrite, add_back, _eval_node, _Deferred


def write(folder, filename, content):
    path = os.path.join(folder, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class JsonplTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# 基本型別驗證
# ---------------------------------------------------------------------------

class TestTypeValidation(JsonplTestCase):
    def test_valid_file_passes(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{
    "as": int,
    "nested": { "x": str }
}
""")
        out = send_json(p, {"as": 4, "nested": {"x": "hi"}})
        self.assertTrue(os.path.exists(out))
        data = load_json(out)
        self.assertEqual(data, {"as": 4, "nested": {"x": "hi"}})

    def test_missing_required_field_raises(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "as": int, "nested": { "x": str } }
""")
        with self.assertRaises(KeyError):
            send_json(p, {"as": 4})

    def test_wrong_type_raises(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "as": int }
""")
        with self.assertRaises(TypeError):
            send_json(p, {"as": "not_int"})

    def test_extra_field_strict_mode_raises(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "as": int }
""")
        with self.assertRaises(ValueError):
            send_json(p, {"as": 1, "bonus": 2})

    def test_optional_field_can_be_missing(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "as": int, "desc": str? }
""")
        out = send_json(p, {"as": 1})
        self.assertEqual(load_json(out), {"as": 1})

    def test_optional_field_validated_when_present(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "as": int, "desc": str? }
""")
        with self.assertRaises(TypeError):
            send_json(p, {"as": 1, "desc": 123})

    def test_list_of_type_ok(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "tags": [str] }
""")
        out = send_json(p, {"tags": ["a", "b", "c"]})
        self.assertEqual(load_json(out), {"tags": ["a", "b", "c"]})

    def test_list_of_type_wrong_element_raises(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "tags": [str] }
""")
        with self.assertRaises(TypeError):
            send_json(p, {"tags": ["a", 1]})

    def test_bare_list_accepts_any_elements(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "tags": list }
""")
        out = send_json(p, {"tags": ["a", 1, True]})
        self.assertEqual(load_json(out)["tags"], ["a", 1, True])

    def test_nested_dict_schema(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "outer": { "inner": { "x": int } } }
""")
        with self.assertRaises(KeyError):
            send_json(p, {"outer": {"inner": {}}})


# ---------------------------------------------------------------------------
# 檔名 / Replace
# ---------------------------------------------------------------------------

class TestReplace(JsonplTestCase):
    def test_replace_true_overwrites(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "as": int }
""")
        out1 = send_json(p, {"as": 1}, required_name="x")
        out2 = send_json(p, {"as": 2}, required_name="x")
        self.assertEqual(out1, out2)
        self.assertEqual(load_json(out2), {"as": 2})

    def test_replace_false_auto_numbers(self):
        p = write(self.folder, "a.jsonpl", """
Replace = False
{ "as": int }
""")
        outs = [send_json(p, {"as": 1}, required_name="x") for _ in range(3)]
        self.assertEqual(len(set(outs)), 3)
        self.assertTrue(outs[0].endswith("x.json"))
        self.assertTrue(outs[1].endswith("x_1.json"))
        self.assertTrue(outs[2].endswith("x_2.json"))

    def test_missing_replace_declaration_raises(self):
        p = write(self.folder, "a.jsonpl", """
{ "as": int }
""")
        with self.assertRaises(ValueError):
            parse_jsonpl(p)

    def test_replace_cannot_be_overridden_via_kwargs(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "as": int }
""")
        with self.assertRaises(ValueError):
            send_json(p, {"as": 1}, Replace=False)

    def test_invalid_replace_literal_raises(self):
        p = write(self.folder, "a.jsonpl", """
Replace = yes
{ "as": int }
""")
        with self.assertRaises(ValueError):
            parse_jsonpl(p)

    def test_default_output_name_matches_jsonpl_stem(self):
        p = write(self.folder, "myfile.jsonpl", """
Replace = True
{ "as": int }
""")
        out = send_json(p, {"as": 1})
        self.assertTrue(out.endswith("myfile.json"))


# ---------------------------------------------------------------------------
# 宣告區（單一 / 群組參數）
# ---------------------------------------------------------------------------

class TestDeclarations(JsonplTestCase):
    def test_declared_param_type_checked(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
wo = int
{ "as": int }
""")
        with self.assertRaises(TypeError):
            send_json(p, {"as": 1}, wo="not_int")

    def test_grouped_declaration_parses(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
grp = (
    wo = int,
    add_num = int
)
{ "as" = wo + add_num }
""")
        out = send_json(p, {}, wo=2, add_num=3)
        self.assertEqual(load_json(out), {"as": 5})

    def test_comment_lines_ignored(self):
        p = write(self.folder, "a.jsonpl", """
# 這是註解
Replace = True
# 另一行註解
{ "as": int }
""")
        out = send_json(p, {"as": 1})
        self.assertTrue(os.path.exists(out))


# ---------------------------------------------------------------------------
# 運算式：work().repeat() / random / 四則運算
# ---------------------------------------------------------------------------

class TestExpressions(JsonplTestCase):
    def test_basic_arithmetic(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
a = int
b = int
{ "sum" = a + b, "diff" = a - b, "prod" = a * b }
""")
        out = send_json(p, {}, a=10, b=3)
        data = load_json(out)
        self.assertEqual(data, {"sum": 13, "diff": 7, "prod": 30})

    def test_work_repeat_deterministic(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
a = int
b = int
n = int
{ "vals" = work(a + b).repeat(n) }
""")
        out = send_json(p, {}, a=1, b=2, n=5)
        data = load_json(out)
        self.assertEqual(data["vals"], [3, 3, 3, 3, 3])

    def test_work_repeat_with_random_varies(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
n = int
{ "vals" = work(random.randint(1, 1000000)).repeat(n) }
""")
        out = send_json(p, {}, n=20)
        data = load_json(out)
        self.assertEqual(len(data["vals"]), 20)
        # 幾乎不可能 20 個隨機數全部一樣
        self.assertGreater(len(set(data["vals"])), 1)

    def test_unknown_variable_raises_nameerror(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "x" = unknown_var + 1 }
""")
        with self.assertRaises(NameError):
            send_json(p, {})

    def test_computed_and_schema_key_overlap_raises_at_parse(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "as": int, "as" = 1 + 1 }
""")
        with self.assertRaises(ValueError):
            parse_jsonpl(p)

    def test_passing_computed_key_in_file_is_rejected(self):
        # computed 欄位不屬於 schema，file 裡出現它會被當成多餘欄位擋下
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "base": int, "doubled" = base * 2 }
""")
        with self.assertRaises(ValueError):
            send_json(p, {"base": 2, "doubled": 4})


# ---------------------------------------------------------------------------
# 對抗性測試：確認運算式沙盒真的擋得住
# ---------------------------------------------------------------------------

class TestSandboxSecurity(JsonplTestCase):
    def _expect_blocked(self, expr):
        p = write(self.folder, "a.jsonpl", f"""
Replace = True
{{ "x" = {expr} }}
""")
        with self.assertRaises((ValueError, NameError, TypeError, SyntaxError)):
            send_json(p, {})

    def test_blocks_dunder_class_chain(self):
        self._expect_blocked("(1).__class__.__bases__[0]")

    def test_blocks_import(self):
        self._expect_blocked("__import__('os').system('echo hacked')")

    def test_blocks_arbitrary_function_call(self):
        self._expect_blocked("open('/etc/passwd')")

    def test_blocks_list_comprehension(self):
        self._expect_blocked("[x for x in range(10)]")

    def test_blocks_lambda(self):
        self._expect_blocked("(lambda: 1)()")

    def test_blocks_random_disallowed_attr(self):
        self._expect_blocked("random.seed(1)")

    def test_blocks_attribute_on_non_deferred_non_random(self):
        self._expect_blocked("(1 + 2).bit_length()")

    def test_blocks_work_without_call(self):
        self._expect_blocked("work")

    def test_blocks_repeat_without_int(self):
        p = write(self.folder, "a.jsonpl", """
Replace = True
{ "x" = work(1).repeat("3") }
""")
        with self.assertRaises(TypeError):
            send_json(p, {})

    def test_blocks_multiple_args_to_work(self):
        self._expect_blocked("work(1, 2)")


class TestRewrite(JsonplTestCase):
    def _write_schema(self):
        return write(self.folder, "s.jsonpl", """
Replace = True
{
    "as": int,
    "nested": { "x": str, "y": int },
    "tags": [str],
    "desc": str?
}
""")

    def test_missing_fields_get_backfilled(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "t.json", json.dumps({
            "as": 5, "nested": {"x": "hi"}
        }))
        out_path, added = rewrite(schema_path, json_path, keep_other_line=False)
        data = load_json(out_path)
        self.assertEqual(data["nested"]["y"], 0)
        self.assertEqual(data["tags"], [])
        self.assertEqual(data["desc"], "")
        self.assertEqual(data["as"], 5)  # 既有值不變
        self.assertIn("root.nested.y", added)

    def test_keep_other_line_false_removes_extra(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "t.json", json.dumps({
            "as": 1, "nested": {"x": "a", "y": 1}, "tags": [], "legacy": "old"
        }))
        out_path, _ = rewrite(schema_path, json_path, keep_other_line=False)
        self.assertNotIn("legacy", load_json(out_path))

    def test_keep_other_line_true_preserves_extra(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "t.json", json.dumps({
            "as": 1, "nested": {"x": "a", "y": 1}, "tags": [], "legacy": "old"
        }))
        out_path, _ = rewrite(schema_path, json_path, keep_other_line=True)
        self.assertEqual(load_json(out_path)["legacy"], "old")

    def test_existing_wrong_type_not_silently_fixed(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "t.json", json.dumps({
            "as": "not_int", "nested": {"x": "a", "y": 1}, "tags": []
        }))
        with self.assertRaises(TypeError):
            rewrite(schema_path, json_path)

    def test_computed_field_not_treated_as_extra(self):
        schema_path = write(self.folder, "s2.jsonpl", """
Replace = True
{ "as": int, "computed" = 1 + 1 }
""")
        json_path = write(self.folder, "t2.json", json.dumps({"as": 3, "computed": 2}))
        out_path, _ = rewrite(schema_path, json_path, keep_other_line=False)
        self.assertEqual(load_json(out_path)["computed"], 2)

    def test_non_dict_json_raises(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "t.json", json.dumps([1, 2, 3]))
        with self.assertRaises(TypeError):
            rewrite(schema_path, json_path)


class TestAddBack(JsonplTestCase):
    def _write_schema(self, folder=None):
        return write(folder or self.folder, "s.jsonpl", """
Replace = True
{
    "as": int,
    "old_field": str,
    "tags": [str],
    "note" = "hi" + "!"
}
""")

    def test_new_field_is_added_with_inferred_type(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "d.json", json.dumps({
            "as": 1, "old_field": "x", "tags": [], "new_field": 3.14
        }))
        out_path, added, updated, removed = add_back(json_path, schema_path, keep_other=False)
        _, schema, _, _ = parse_jsonpl(out_path)
        self.assertIn("new_field", added)
        self.assertIs(schema["new_field"], float)

    def test_nested_new_field_inferred_recursively(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "d.json", json.dumps({
            "as": 1, "old_field": "x", "tags": [],
            "nested_new": {"x": 1, "y": "hi"}
        }))
        out_path, added, _, _ = add_back(json_path, schema_path, keep_other=False)
        _, schema, _, _ = parse_jsonpl(out_path)
        self.assertEqual(schema["nested_new"], {"x": int, "y": str})

    def test_type_change_updates_schema(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "d.json", json.dumps({
            "as": "now_str", "old_field": "x", "tags": []
        }))
        out_path, added, updated, removed = add_back(json_path, schema_path, keep_other=False)
        _, schema, _, _ = parse_jsonpl(out_path)
        self.assertIn("as", updated)
        self.assertIs(schema["as"], str)

    def test_empty_array_does_not_downgrade_existing_type(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "d.json", json.dumps({
            "as": 1, "old_field": "x", "tags": []
        }))
        out_path, added, updated, removed = add_back(json_path, schema_path, keep_other=False)
        _, schema, _, _ = parse_jsonpl(out_path)
        self.assertEqual(schema["tags"], [str])
        self.assertNotIn("tags", updated)

    def test_computed_field_untouched(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "d.json", json.dumps({
            "as": 1, "old_field": "x", "tags": []
        }))
        out_path, _, _, _ = add_back(json_path, schema_path, keep_other=False)
        _, schema, computed, _ = parse_jsonpl(out_path)
        self.assertIn("note", computed)
        self.assertNotIn("note", schema)

    def test_keep_other_false_removes_missing_field(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "d.json", json.dumps({"as": 1, "tags": []}))
        out_path, _, _, removed = add_back(json_path, schema_path, keep_other=False)
        _, schema, _, _ = parse_jsonpl(out_path)
        self.assertNotIn("old_field", schema)
        self.assertIn("old_field", removed)

    def test_keep_other_true_preserves_missing_field(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "d.json", json.dumps({"as": 1, "tags": []}))
        out_path, _, _, removed = add_back(json_path, schema_path, keep_other=True)
        _, schema, _, _ = parse_jsonpl(out_path)
        self.assertIn("old_field", schema)
        self.assertEqual(removed, [])

    def test_rewritten_jsonpl_is_still_parseable(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "d.json", json.dumps({
            "as": 1, "old_field": "x", "tags": ["a"], "extra": True
        }))
        out_path, _, _, _ = add_back(json_path, schema_path, keep_other=False)
        # 不應丟出例外
        parse_jsonpl(out_path)

    def test_non_dict_json_raises(self):
        schema_path = self._write_schema()
        json_path = write(self.folder, "d.json", json.dumps([1, 2]))
        with self.assertRaises(TypeError):
            add_back(json_path, schema_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
