import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from jsonpl import send_json
import json

file = {"nested": {"x": "hi"}}

out = send_json(
    "files/data/expr.jsonpl", file,
    required_name="expr_out",
    wo=3, add_num=5, i=4,
)
print("輸出:", out)
print(json.dumps(json.load(open(out, encoding="utf-8")), ensure_ascii=False, indent=2))

# 型別檢查：wo 傳錯型別應該報錯
try:
    send_json("files/data/expr.jsonpl", file, wo="not_int", add_num=5, i=4)
except TypeError as e:
    print("預期錯誤 (參數型別):", e)

# 未宣告變數：expr 用到沒傳的變數應該報錯
try:
    send_json("files/data/expr.jsonpl", file, wo=3, add_num=5)  # 缺 i
except NameError as e:
    print("預期錯誤 (缺變數):", e)
