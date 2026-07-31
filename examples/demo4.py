import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from jsonpl import send_json

# wao.jsonpl 宣告 Replace = False -> 同名時應該自動編號
file = {"as": 1, "nested": {"x": "a"}}
p1 = send_json("files/data/wao.jsonpl", file, required_name="dup")
p2 = send_json("files/data/wao.jsonpl", file, required_name="dup")
p3 = send_json("files/data/wao.jsonpl", file, required_name="dup")
print("Replace=False 連續產生三次:")
print(" ", p1)
print(" ", p2)
print(" ", p3)

# wao2.jsonpl 宣告 Replace = True -> 同名時應該直接覆蓋（路徑不變）
file2 = {"as": 1, "nested": {"x": "a"}, "tags": ["x"]}
q1 = send_json("files/data/wao2.jsonpl", file2, required_name="overwrite_me")
q2 = send_json("files/data/wao2.jsonpl", file2, required_name="overwrite_me")
print("Replace=True 連續產生兩次，路徑應相同:")
print(" ", q1)
print(" ", q2)
print(" 路徑相同?", q1 == q2)

# 不能從 send_json 覆寫 Replace
try:
    send_json("files/data/wao.jsonpl", file, required_name="x", Replace=True)
except ValueError as e:
    print("預期錯誤 (禁止用 kwargs 覆寫 Replace):", e)
