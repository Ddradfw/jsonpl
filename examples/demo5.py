import json
import os
from jsonpl import send_json, rewrite

FOLDER = "files/data"
os.makedirs(FOLDER, exist_ok=True)

jsonpl_path = os.path.join(FOLDER, "rewrite_test.jsonpl")
with open(jsonpl_path, "w", encoding="utf-8") as f:
    f.write("""
Replace = True
{
    "as": int,
    "nested": { "x": str, "y": int },
    "tags": [str],
    "desc": str?
}
""")

json_path = os.path.join(FOLDER, "rewrite_target.json")

# 1) 模擬一個「舊版」json：缺 nested.y、缺 tags，還多了一個 legacy_field
old_data = {
    "as": 5,
    "nested": {"x": "hi"},
    "legacy_field": "should be handled by keep_other_line",
}
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(old_data, f, ensure_ascii=False, indent=4)

# --- keep_other_line=False（預設）：補齊缺的欄位，移除 legacy_field ---
out_path, added = rewrite(jsonpl_path, json_path, keep_other_line=False)
result = json.load(open(out_path, encoding="utf-8"))
print("keep_other_line=False 結果:")
print(json.dumps(result, ensure_ascii=False, indent=2))
print("補上的欄位:", added)
assert "legacy_field" not in result
assert result["nested"]["y"] == 0
assert result["tags"] == []
assert result["as"] == 5  # 已存在的值不變

# --- keep_other_line=True：重新製造一份帶 legacy_field 的 json，這次應該保留 ---
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(old_data, f, ensure_ascii=False, indent=4)

out_path, added = rewrite(jsonpl_path, json_path, keep_other_line=True)
result = json.load(open(out_path, encoding="utf-8"))
print("\nkeep_other_line=True 結果:")
print(json.dumps(result, ensure_ascii=False, indent=2))
assert result["legacy_field"] == "should be handled by keep_other_line"
assert result["nested"]["y"] == 0

# --- 既有值型別錯誤，rewrite 不應該悄悄改掉，要報錯 ---
bad_data = {"as": "not_int", "nested": {"x": "hi", "y": 1}, "tags": []}
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(bad_data, f, ensure_ascii=False, indent=4)

try:
    rewrite(jsonpl_path, json_path)
except TypeError as e:
    print("\n預期錯誤 (既有型別錯誤不會被自動修正):", e)

# --- 帶有 computed 欄位的既有 json：rewrite 不應該把它當多餘欄位刪掉 ---
expr_jsonpl_path = os.path.join(FOLDER, "rewrite_expr.jsonpl")
with open(expr_jsonpl_path, "w", encoding="utf-8") as f:
    f.write("""
Replace = True
{
    "as": int,
    "computed_field" = 1 + 1
}
""")

expr_json_path = os.path.join(FOLDER, "rewrite_expr_target.json")
with open(expr_json_path, "w", encoding="utf-8") as f:
    json.dump({"as": 3, "computed_field": 2}, f)

out_path, added = rewrite(expr_jsonpl_path, expr_json_path, keep_other_line=False)
result = json.load(open(out_path, encoding="utf-8"))
print("\n含 computed 欄位的 rewrite 結果:", result)
assert result["computed_field"] == 2  # 沒被當成多餘欄位移除

print("\n全部驗證通過")
