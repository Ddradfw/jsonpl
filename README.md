# jsonpl

`jsonpl` 是一個型別化的 JSON 模板產生器。用 `.jsonpl` 檔案定義一個 JSON 樣板（包含欄位型別、驗證規則、可執行運算式），再用 Python 把實際資料套進去，產生出標準 `.json` 檔案。

```python
from jsonpl import send_json

file = {"as": 4, "nested": {"x": "hello"}}
send_json("files/data/wao.jsonpl", file, required_name="aaa")
# -> 在 files/data/ 下建立 aaa.json
```

---

## 安裝

目前是單一檔案模組，還沒發佈到 PyPI。把 `jsonpl.py` 複製到你的專案裡即可：

```python
from jsonpl import send_json
```

---

## `.jsonpl` 檔案結構

一個 `.jsonpl` 檔案分兩塊：**宣告區**（選填 + 一個必填項）跟**樣板區**（必填）。

```
# 宣告區
Replace = True
required_name = str
grp = (
    wo = int,
    add_num = int
)

# 樣板區
{
    "as": int,
    "nested": { "x": str },
    "tags": [str],
    "desc": str?,
    "sas" = work(wo + add_num).repeat(i)
}
```

### 1. 宣告區

宣告區在檔案最前面，樣板區（第一個 `{`）之前。每一行（或用 `(...)` 包起來的一整段）是一條宣告，格式為 `name = value`。

#### `Replace`（保留字，必填）

```
Replace = True   # 或 False
```

- **必填**：沒寫這行，`.jsonpl` 直接解析失敗（`ValueError`）
- **不可從 `send_json` 傳入覆寫**：呼叫時如果傳了 `Replace=...` 這個 kwarg，會直接報錯
- 決定輸出檔案遇到同名時的行為：
  - `True` → 直接覆蓋同名檔案
  - `False` → 自動加上 `_1`、`_2`... 編號，不覆蓋既有檔案

#### 一般參數宣告

```
name = type
```

`type` 可以是 `int` / `str` / `float` / `bool` / `dict` / `list` / `any`。這種參數是給**樣板區的運算式**使用的變數，呼叫 `send_json` 時如果有傳同名的 kwarg，會檢查型別是否相符：

```python
send_json(path, file, wo=3)  # wo 必須是 int，否則 TypeError
```

宣告是選填的——就算沒宣告，只要樣板區的運算式用到這個變數名稱，`send_json` 呼叫時有傳入同名 kwarg 就能用（只是不會做型別檢查）。

#### 群組宣告

```
grp = (
    wo = int,
    add_num = int
)
```

`grp` 這個名字本身沒有作用，只是排版用的分組標籤；`wo`、`add_num` 會被攤平成獨立的變數，跟單一宣告等效。

#### 註解

以 `#` 開頭的整行會被忽略。

---

### 2. 樣板區

樣板區是最後一個（外層）`{ ... }`。裡面每個 `"key"` 後面接 `:` 或 `=`，意義完全不同：

| 語法 | 意義 |
|---|---|
| `"key": type` | **驗證用**。值必須從 `send_json` 的 `file` 參數傳入，並依型別驗證 |
| `"key" = expression` | **運算用**。值由 jsonpl 在產生當下自己算出來，不能出現在 `file` 裡 |

#### 型別（`:` 語法）

支援的型別：`int` / `str` / `float` / `bool` / `dict` / `list` / `any`

- **巢狀 dict**：`"nested": { "x": str }`
- **陣列＋元素型別**：`"tags": [str]`（陣列裡每個元素都要是 `str`）
- **裸 `list`**：`"tags": list`（只檢查是不是 list，不檢查元素型別）
- **選填欄位**：型別後面加 `?`，例如 `"desc": str?`——`file` 裡可以不給這個欄位

#### 嚴格模式（自動套用，無法關閉）

`file` 傳入的欄位**必須剛好等於**樣板宣告的欄位（選填欄位可以不給），多傳、少傳都會報錯：

- 少必填欄位 → `KeyError`
- 型別不對 → `TypeError`
- 多傳樣板沒定義的欄位 → `ValueError`

#### 運算式（`=` 語法）

運算式的值不是從 `file` 傳入，而是用 `send_json` 的 kwargs 當變數，即時算出來。

**支援的東西：**
- 變數代入（`send_json` 傳入的任何 kwarg）
- 基本四則運算：`+ - * / // % **`
- `work(expr).repeat(n)` —— 把 `expr` 重新求值 `n` 次，包成一個 list。因為每次都是**重新求值**（不是算一次複製 n 份），如果 `expr` 裡有 `random.xxx()`，n 次結果會各自不同
- `random.xxx(...)` —— 白名單：`random` / `randint` / `uniform` / `choice` / `gauss` / `randrange` / `sample`

```
{
    "sas" = work(wo + add_num).repeat(i),
    "loot" = work(random.randint(1, 100)).repeat(i)
}
```

**不支援（刻意封鎖，見下方「安全性」）：**
- 任意函式呼叫（只能呼叫 `work()` 或 `random.xxx()`）
- `import`、屬性鏈逃逸（如 `(1).__class__...`）
- list comprehension、lambda、條件表達式等進階語法

---

## Python API

### `send_json(path, file, **kwargs) -> str`

- `path`：`.jsonpl` 檔案路徑
- `file`：符合樣板 `:` 欄位的資料
- `**kwargs`：
  - `required_name`（選填）：輸出檔名（不含副檔名）。不給的話用 `.jsonpl` 檔案本身的檔名
  - 其他 kwargs：提供給樣板區運算式（`=` 欄位）當變數
- 回傳：實際輸出的 `.json` 路徑（字串）

輸出資料夾＝ `.jsonpl` 檔案所在的資料夾。

### `parse_jsonpl(path)`

回傳 `(declared_params, schema, computed, replace_flag)`，通常不需要直接呼叫，`send_json` 內部會用到。想寫額外的驗證工具（例如批次檢查整個資料夾的 `.jsonpl` 語法對不對）時可以用這個。

### `rewrite(jsonpl_path, json_path, keep_other_line=False) -> (json_path, added_keys)`

用 `.jsonpl` 的 schema 對照**既有**的 `.json` 檔案，補齊缺少的欄位——典型用途是：你在 schema 裡新加了一個欄位，但手上已經有幾百個舊版 `.json`（比如遊戲道具設定、配方檔案），想批次補齊而不用一個個手動改。

```python
from jsonpl import rewrite

out_path, added = rewrite("schema/item.jsonpl", "items/sword_001.json")
print(added)  # ex: ['root.rarity', 'root.stats.crit_rate']
```

行為規則：

- **`:` 型別欄位缺失** → 自動補上型別預設值：`int→0`、`str→""`、`float→0.0`、`bool→False`、`dict/巢狀→遞迴補齊`、`list`／`[type]→[]`
- **`:` 型別欄位已存在但型別錯誤** → **不會被自動修正**，直接丟出 `TypeError`。這是刻意的：`rewrite` 只負責「補缺的」，不負責「改錯的」，避免悄悄改壞你手上的資料
- **`=` 運算式欄位**（如 `work().repeat()` 算出來的結果）→ 視為已知欄位，不會被當成多餘欄位刪掉；但因為 `rewrite` 沒有 kwargs、沒有變數可用，缺失時**不會**被重新計算補上
- **`keep_other_line=False`（預設）**：json 裡完全沒在 `.jsonpl` 定義過的欄位（不屬於 `:` 也不屬於 `=`）會被移除
- **`keep_other_line=True`**：這些多餘欄位會被保留

回傳值是 `(json_path, added_keys)`，`added_keys` 是這次補上的欄位路徑列表（如 `["root.nested.y", "root.tags"]`），方便你在批次跑的時候印出來看哪些檔案被動到、動了哪裡。

`rewrite` 是直接原地覆寫 `json_path`，沒有 `Replace`/`required_name` 那套檔名衝突機制（因為目標檔案本來就是指定好的）。

### `add_back(json_path, jsonpl_path, keep_other=False) -> (jsonpl_path, added_keys, updated_keys, removed_keys)`

跟 `rewrite`方向相反：用**既有的 `.json`** 反過來更新 `.jsonpl` 的 schema。典型用途是你手動改了一個 `.json`（加了新欄位、改了某個值的型別），想把這個變化同步回 schema 定義，而不是手動去改 `.jsonpl` 文字。

```python
from jsonpl import add_back

out_path, added, updated, removed = add_back("items/sword_001.json", "schema/item.jsonpl")
print("新增:", added, "型別更新:", updated, "移除:", removed)
```

行為規則：

- **json 裡有、schema 沒定義的欄位** → 依實際值反推型別，補進 schema（`int`/`str`/`float`/`bool`、巢狀 `dict` 遞迴推斷、陣列元素型別一致時推成 `[type]`）
- **json 裡的值型別跟 schema 既有宣告不符** → 用這次的值更新 schema 型別。例外：如果這次的證據只是「空陣列」或「陣列元素型別不一致」（只能反推出裸 `list`），而原本 schema 已經是更明確的型別（例如 `[str]`），**不會被降級覆蓋**——避免一次不完整的資料把 schema 洗成模糊的型別
- **`=` 運算式欄位完全不受影響**，原封不動寫回，不會被誤判成新欄位或被移除
- **`keep_other=False`（預設）**：schema 裡有、但這次 `json` 沒有的欄位，直接從 schema 移除
- **`keep_other=True`**：保留這些欄位

**已知限制**：`add_back` 重建 `.jsonpl` 時，宣告區（`Replace`、參數宣告、註解）會保留原始文字；但**樣板區會整個用固定排版重新產生**，原本樣板區裡的排版/註解不會被保留。寫回後會自動重新 parse 一次做合法性檢查，如果重建結果不合法會直接丟出例外，不會留下壞掉的檔案。

---

## 錯誤類型速查

| 情況 | Exception |
|---|---|
| 缺少必要欄位 | `KeyError` |
| 型別不符 | `TypeError` |
| 多傳未定義欄位 / `Replace` 從 kwargs 傳入 / schema 與 computed 欄位衝突 | `ValueError` |
| 運算式用到未宣告也未傳入的變數 | `NameError` |
| `.jsonpl` 語法本身寫錯（缺 `{`、缺 `Replace`、型別關鍵字打錯等） | `ValueError` |

---

## 安全性

樣板區的 `=` 運算式**不是用 Python 的 `eval()` 執行的**。是用 `ast` 模組解析成語法樹後，自己寫的白名單求值器（見 `jsonpl.py` 裡的 `_eval_node` / `_eval_call`），只允許：

- 常數（數字/字串/布林）
- 變數查找（僅限傳入的 kwargs）
- `work()` / `random.xxx()`（白名單函式）
- 加減乘除等基本運算子

任何其他語法節點（`import`、`lambda`、`comprehension`、任意函式呼叫、dunder 屬性鏈等）都會在解析或求值階段被拒絕。`tests/test_jsonpl.py` 的 `TestSandboxSecurity` 類別針對常見的沙盒逃逸手法（`__import__`、`(1).__class__.__bases__...` 等）都有對應測試。

---

## 測試

```bash
python3 -m unittest tests.test_jsonpl -v
```

（環境若能安裝 pytest，同一份檔案可直接用 `pytest tests/test_jsonpl.py -v` 執行，不需修改。目前共 50 個測試。）

