import json
import os
from jsonpl import add_back, parse_jsonpl

FOLDER = "files/data"
os.makedirs(FOLDER, exist_ok=True)

jsonpl_path = os.path.join(FOLDER, "addback_test.jsonpl")
with open(jsonpl_path, "w", encoding="utf-8") as f:
    f.write("""# 這是一個測試用的 schema
Replace = True

{
    "as": int,
    "old_field": str,
    "tags": [str],
    "note" = "hello" + "!"
}
""")

json_path = os.path.join(FOLDER, "addback_source.json")
new_data = {
    "as": "now_a_string",       # 型別改變: int -> str，應該更新 schema
    "old_field": "kept",         # 型別沒變
    "tags": [],                  # 空陣列，證據不足，不該把 [str] 降級成 list
    "new_field": 3.14,           # schema 沒有的新欄位，應該被補進去 (float)
    "new_nested": {"x": 1, "y": "hi"},  # 新的巢狀欄位
    # 注意：這裡故意沒有 "note"，因為它是運算式欄位，add_back 不該動它
}
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(new_data, f, ensure_ascii=False, indent=2)

out_path, added, updated, removed = add_back(json_path, jsonpl_path, keep_other=False)
print("added:", added)
print("updated:", updated)
print("removed:", removed)

print("\n重建後的 .jsonpl 內容:")
print(open(out_path, encoding="utf-8").read())

# 驗證重建後的檔案仍然合法可解析
declared_params, schema, computed, replace_flag = parse_jsonpl(out_path)
print("schema:", schema)
print("computed keys:", list(computed.keys()))
print("replace_flag:", replace_flag)

assert schema["as"] is str, "as 的型別應該被更新成 str"
assert schema["old_field"] is str
assert schema["tags"] == [str], "空陣列不該把既有的 [str] 降級"
assert schema["new_field"] is float
assert schema["new_nested"] == {"x": int, "y": str}
assert "note" in computed, "運算式欄位不該被搬到 schema"
assert "note" not in schema

print("\n全部驗證通過 (keep_other=False)")

# --- keep_other=True: 這次 json 沒有 old_field，應該仍保留在 schema ---
with open(jsonpl_path, "w", encoding="utf-8") as f:
    f.write("""
Replace = True
{
    "as": int,
    "old_field": str
}
""")
json_path2 = os.path.join(FOLDER, "addback_source2.json")
with open(json_path2, "w", encoding="utf-8") as f:
    json.dump({"as": 1}, f)  # 沒有 old_field

out_path, added, updated, removed = add_back(json_path2, jsonpl_path, keep_other=True)
_, schema2, _, _ = parse_jsonpl(out_path)
assert "old_field" in schema2, "keep_other=True 時 old_field 應該被保留"
print("keep_other=True 驗證通過:", schema2)

# keep_other=False 時應該被移除
with open(jsonpl_path, "w", encoding="utf-8") as f:
    f.write("""
Replace = True
{
    "as": int,
    "old_field": str
}
""")
out_path, added, updated, removed = add_back(json_path2, jsonpl_path, keep_other=False)
_, schema3, _, _ = parse_jsonpl(out_path)
assert "old_field" not in schema3, "keep_other=False 時 old_field 應該被移除"
print("removed:", removed)
print("keep_other=False 驗證通過:", schema3)
