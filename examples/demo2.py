import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from jsonpl import send_json

base = {"as": 4, "nested": {"x": "hi"}, "tags": ["a", "b"]}

# 1) 沒給 desc（optional），應該成功
out = send_json("files/data/wao2.jsonpl", base, required_name="opt_ok")
print("OK 不給 desc:", out)

# 2) 有給 desc，應該成功
with_desc = dict(base, desc="hello")
out = send_json("files/data/wao2.jsonpl", with_desc, required_name="opt_with_desc")
print("OK 給 desc:", out)

# 3) tags 元素型別錯誤，應該報錯
try:
    send_json("files/data/wao2.jsonpl", dict(base, tags=["a", 123]), required_name="bad_tags")
except TypeError as e:
    print("預期錯誤 (list 元素型別):", e)

# 4) 多餘欄位，應該報錯（嚴格模式）
try:
    send_json("files/data/wao2.jsonpl", dict(base, extra_field="oops"), required_name="bad_extra")
except ValueError as e:
    print("預期錯誤 (多餘欄位):", e)
