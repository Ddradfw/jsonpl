import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from jsonpl import send_json

file = {"as": 4, "nested": {"x": "hello"}}

# 1) 有指定 required_name
out1 = send_json("files/data/wao.jsonpl", file, required_name="aaa")
print("輸出:", out1)

# 2) 不指定 required_name，預設用 wao.json
out2 = send_json("files/data/wao.jsonpl", file)
print("輸出:", out2)

# 3) 故意漏欄位，測試驗證是否會噴錯
try:
    send_json("files/data/wao.jsonpl", {"as": 4})
except KeyError as e:
    print("預期錯誤 (缺欄位):", e)

# 4) 故意型別錯誤，測試驗證
try:
    send_json("files/data/wao.jsonpl", {"as": "not_an_int", "nested": {"x": "hi"}})
except TypeError as e:
    print("預期錯誤 (型別錯誤):", e)
