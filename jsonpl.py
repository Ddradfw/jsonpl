"""
jsonpl - 一個極簡的 .jsonpl 模板系統
============================================

.jsonpl 檔案格式：

    # 宣告區（選填）
    #   單一參數: name = type
    #   群組參數: name = ( sub1 = type1, sub2 = type2 )
    required_name = str
    required_else = (
        wo = int,
        add_num = int
    )

    # 樣板區
    #   "key": type        -> 驗證用，值必須從 send_json 的 file 參數傳入
    #   "key" = expression  -> 運算用，值由 jsonpl 在產生當下自己算出來
    {
        "as": int,
        "nested": { "x": str },
        "tags": [str],
        "desc": str?,
        "sas" = work(wo + add_num).repeat(i)
    }

運算式支援：已註冊函式呼叫（目前是 work().repeat() 與 random.xxx()）
+ 基本四則運算 + 變數代入（變數 = send_json 傳入的 kwargs）。

用法：
    from jsonpl import send_json

    file = {"as": 4, "nested": {"x": "hello"}, "tags": ["a"]}
    send_json("files/data/wao.jsonpl", file, required_name="aaa", wo=3, add_num=5, i=4)
"""

__version__ = "0.1.0"

import re
import ast
import json
import os
import random as _random_module

TYPE_MAP = {
    "int": int,
    "str": str,
    "float": float,
    "bool": bool,
    "dict": dict,
    "list": list,
    "any": object,
}

_ALLOWED_RANDOM_FUNCS = {"random", "randint", "uniform", "choice", "gauss", "randrange", "sample"}


class Optional:
    """包住一個型別，代表這個欄位可有可無（語法: str?）"""
    __slots__ = ("type",)

    def __init__(self, type_):
        self.type = type_

    def __repr__(self):
        return f"Optional({getattr(self.type, '__name__', self.type)})"


# ---------------------------------------------------------------------------
# 低階：括號 / 字串 感知的切割工具
# ---------------------------------------------------------------------------

_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")": "(", "]": "[", "}": "{"}


def _split_top_level(text: str, sep: str = ","):
    """依括號/字串深度，只切割最外層（depth==0）的 sep。"""
    parts = []
    depth = 0
    buf = []
    in_str = None
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = ch
            buf.append(ch)
        elif ch in _OPEN:
            depth += 1
            buf.append(ch)
        elif ch in _CLOSE:
            depth -= 1
            buf.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


def _find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    in_str = None
    i = open_index
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("找不到對應的結尾 '}'")


def _strip_comment_lines(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("#")]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 型別 token 化 / 還原（給 ":" 型別樣板用）
# ---------------------------------------------------------------------------

_TYPE_PATTERN = re.compile(
    r'\b(' + '|'.join(TYPE_MAP.keys()) + r')\b(\?)?(?=\s*[,\}\]]|\s*$)'
)


def _tokenize_types(text: str) -> str:
    def repl(m):
        type_name, optional_mark = m.group(1), m.group(2)
        marker = f"__opt__{type_name}" if optional_mark else f"__type__{type_name}"
        return f'"{marker}"'
    return _TYPE_PATTERN.sub(repl, text)


def _detokenize(node):
    if isinstance(node, dict):
        return {k: _detokenize(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_detokenize(v) for v in node]
    if isinstance(node, str):
        if node.startswith("__type__"):
            return TYPE_MAP[node[len("__type__"):]]
        if node.startswith("__opt__"):
            return Optional(TYPE_MAP[node[len("__opt__"):]])
    return node


def _parse_type_spec(value_text: str):
    tokenized = _tokenize_types(value_text)
    try:
        raw = json.loads(tokenized)
    except json.JSONDecodeError as e:
        raise ValueError(f"型別樣板解析失敗: {value_text!r} ({e})") from e
    return _detokenize(raw)


# ---------------------------------------------------------------------------
# 宣告區解析（支援單一 / 群組參數）
# ---------------------------------------------------------------------------

_BOOL_LITERALS = {"True": True, "False": False}


def _parse_declarations(decl_text: str):
    """回傳 (declared_params, replace_flag)。'Replace' 是保留字，必填，不可為群組。"""
    decl_text = _strip_comment_lines(decl_text)
    declared_params = {}
    replace_flag = None

    for stmt in _split_top_level(decl_text, sep="\n"):
        if "=" not in stmt:
            raise ValueError(f"無法解析宣告: {stmt!r}")
        name, rest = stmt.split("=", 1)
        name, rest = name.strip(), rest.strip()

        if name == "Replace":
            if rest not in _BOOL_LITERALS:
                raise ValueError(
                    f"'Replace' 只能是 True 或 False，收到 '{rest}'"
                )
            replace_flag = _BOOL_LITERALS[rest]
            continue

        if rest.startswith("(") and rest.endswith(")"):
            inner = rest[1:-1]
            for sub in _split_top_level(inner, sep=","):
                if "=" not in sub:
                    raise ValueError(f"群組宣告 '{name}' 中的項目格式錯誤: {sub!r}")
                sub_name, sub_type = (x.strip() for x in sub.split("=", 1))
                if sub_type not in TYPE_MAP:
                    raise ValueError(f"未知型別 '{sub_type}'，於 '{name}.{sub_name}'")
                declared_params[sub_name] = TYPE_MAP[sub_type]
        else:
            if rest not in TYPE_MAP:
                raise ValueError(f"未知型別 '{rest}'，於宣告 '{stmt}'")
            declared_params[name] = TYPE_MAP[rest]

    if replace_flag is None:
        raise ValueError(
            "缺少必填宣告 'Replace = True' 或 'Replace = False'"
            "（決定同名檔案要覆蓋還是自動編號）"
        )

    return declared_params, replace_flag


# ---------------------------------------------------------------------------
# 樣板區解析：拆成 schema（":"）與 computed（"="）
# ---------------------------------------------------------------------------

_KEY_PATTERN = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*([:=])\s*(.*)$', re.DOTALL)


def _split_key_and_value(item: str):
    m = _KEY_PATTERN.match(item)
    if not m:
        raise ValueError(f"無法解析樣板項目: {item!r}")
    key, sep, value_text = m.group(1), m.group(2), m.group(3)
    return key, sep, value_text.strip()


def _parse_template_items(path: str):
    """讀取 .jsonpl，回傳 (decl_text, items)。items 是 [(key, sep, raw_value_text), ...]，
    保留原始文字片段（給 add_back 重建檔案用）。"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    brace_index = content.find("{")
    if brace_index == -1:
        raise ValueError(f"{path} 找不到 JSON 樣板區塊（缺少 '{{'）")

    decl_text = content[:brace_index]
    close_index = _find_matching_brace(content, brace_index)
    template_text = content[brace_index + 1:close_index]

    items = []
    for item in _split_top_level(template_text, sep=","):
        key, sep, value_text = _split_key_and_value(item)
        items.append((key, sep, value_text))
    return decl_text, items


def parse_jsonpl(path: str):
    """讀取 .jsonpl，回傳 (declared_params, schema, computed, replace_flag)"""
    decl_text, items = _parse_template_items(path)

    declared_params, replace_flag = _parse_declarations(decl_text)

    schema = {}
    computed = {}
    for key, sep, value_text in items:
        if sep == ":":
            schema[key] = _parse_type_spec(value_text)
        else:
            try:
                node = ast.parse(value_text, mode="eval").body
            except SyntaxError as e:
                raise ValueError(f"'{key}' 的運算式無法解析: {value_text!r} ({e})") from e
            computed[key] = node

    overlap = set(schema) & set(computed)
    if overlap:
        raise ValueError(f"欄位不可同時是型別宣告又是運算式: {', '.join(sorted(overlap))}")

    return declared_params, schema, computed, replace_flag


# ---------------------------------------------------------------------------
# 驗證（":" 欄位用，file 傳入的值必須符合）
# ---------------------------------------------------------------------------

def _validate(data, schema, path="root", strict=True):
    if isinstance(schema, dict):
        if not isinstance(data, dict):
            raise TypeError(f"'{path}' 應該是 dict，但收到 {type(data).__name__}")

        if strict:
            extra_keys = set(data.keys()) - set(schema.keys())
            if extra_keys:
                raise ValueError(
                    f"'{path}' 有未在樣板中定義的欄位: {', '.join(sorted(extra_keys))}"
                )

        for key, expected in schema.items():
            if isinstance(expected, Optional):
                if key not in data:
                    continue
                _validate(data[key], expected.type, f"{path}.{key}", strict)
                continue
            if key not in data:
                raise KeyError(f"缺少必要欄位 '{path}.{key}'")
            _validate(data[key], expected, f"{path}.{key}", strict)
    elif isinstance(schema, list):
        if not isinstance(data, list):
            raise TypeError(f"'{path}' 應該是 list，但收到 {type(data).__name__}")
        if schema:
            for i, item in enumerate(data):
                _validate(item, schema[0], f"{path}[{i}]", strict)
    else:
        if schema is object:  # any
            return
        if not isinstance(data, schema):
            raise TypeError(f"'{path}' 應該是 {schema.__name__}，但收到 {type(data).__name__}")


# ---------------------------------------------------------------------------
# 運算式求值（限制型 AST evaluator，不用 eval()）
# ---------------------------------------------------------------------------

class _Deferred:
    """work(expr) 的結果：先不算，等 .repeat(n) 時才逐次重新求值"""
    __slots__ = ("node", "env")

    def __init__(self, node, env):
        self.node = node
        self.env = env


class _RandomProxy:
    pass


_RANDOM_SENTINEL = _RandomProxy()


def _eval_node(node, env):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, str, bool)) or node.value is None:
            return node.value
        raise ValueError("運算式中出現不支援的常數")

    if isinstance(node, ast.Name):
        if node.id == "random":
            return _RANDOM_SENTINEL
        if node.id == "work":
            raise ValueError("'work' 必須被呼叫，例如 work(expr)")
        if node.id in env:
            return env[node.id]
        raise NameError(f"未知的變數 '{node.id}'（記得在宣告區宣告，並在 send_json 呼叫時傳入）")

    if isinstance(node, ast.UnaryOp):
        val = _eval_node(node.operand, env)
        if isinstance(node.op, ast.USub):
            return -val
        if isinstance(node.op, ast.UAdd):
            return +val
        raise ValueError("不支援的一元運算")

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, env)
        right = _eval_node(node.right, env)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        if isinstance(op, ast.FloorDiv):
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.Pow):
            return left ** right
        raise ValueError("不支援的運算子")

    if isinstance(node, ast.Call):
        return _eval_call(node, env)

    raise ValueError(f"運算式中出現不支援的語法: {type(node).__name__}")


def _eval_call(node, env):
    func = node.func

    if isinstance(func, ast.Name) and func.id == "work":
        if len(node.args) != 1 or node.keywords:
            raise ValueError("work() 只接受一個位置參數，例如 work(wo + add_num)")
        return _Deferred(node.args[0], env)

    if isinstance(func, ast.Attribute):
        base = _eval_node(func.value, env)
        attr = func.attr

        if isinstance(base, _Deferred):
            if attr != "repeat":
                raise ValueError(f"work(...) 之後只支援 .repeat()，收到 .{attr}()")
            if len(node.args) != 1 or node.keywords:
                raise ValueError(".repeat() 只接受一個位置參數（次數）")
            times = _eval_node(node.args[0], base.env)
            if not isinstance(times, int):
                raise TypeError(".repeat() 的參數必須是 int")
            # 關鍵：每次重新求值，讓 random 等具有隨機性的運算式每次結果不同
            return [_eval_node(base.node, base.env) for _ in range(times)]

        if base is _RANDOM_SENTINEL:
            if attr not in _ALLOWED_RANDOM_FUNCS:
                raise ValueError(f"random.{attr} 未被允許使用")
            if node.keywords:
                raise ValueError("random 函式不支援關鍵字參數")
            args = [_eval_node(a, env) for a in node.args]
            return getattr(_random_module, attr)(*args)

        raise ValueError(f"不支援對 {base!r} 呼叫 .{attr}()")

    raise ValueError("只允許呼叫 work(...) 或 random.xxx(...)")


# ---------------------------------------------------------------------------
# 對外主函式
# ---------------------------------------------------------------------------

_DEFAULT_VALUES = {
    int: 0,
    str: "",
    float: 0.0,
    bool: False,
    dict: {},
    list: [],
    object: None,  # any
}


def _default_for(expected):
    """依 schema 型別產生一個預設值，補齊缺失欄位用。"""
    if isinstance(expected, Optional):
        return _default_for(expected.type)
    if isinstance(expected, dict):  # 巢狀 schema
        return {k: _default_for(v) for k, v in expected.items()}
    if isinstance(expected, list):  # [type] 陣列 schema
        return []
    return _DEFAULT_VALUES.get(expected, None)


def _backfill(data, schema, path="root"):
    """回傳 (補齊後的 dict, 補上了哪些欄位的路徑列表)。只補缺的，不動已存在的值。"""
    if not isinstance(data, dict):
        raise TypeError(f"'{path}' 應該是 dict，但收到 {type(data).__name__}，無法自動補齊")

    result = dict(data)
    added = []
    for key, expected in schema.items():
        expected_type = expected.type if isinstance(expected, Optional) else expected
        if key not in result:
            result[key] = _default_for(expected_type)
            added.append(f"{path}.{key}")
            continue
        if isinstance(expected_type, dict):
            sub, sub_added = _backfill(result[key], expected_type, f"{path}.{key}")
            result[key] = sub
            added.extend(sub_added)
    return result, added


def rewrite(jsonpl_path: str, json_path: str, keep_other_line: bool = False):
    """
    用 jsonpl_path 的 schema 對照既有的 json_path：
      - json 裡缺少 .jsonpl 定義（":" 欄位）的東西，自動補上型別預設值
        （int->0, str->"", float->0.0, bool->False, dict/巢狀->遞迴補, list/[type]->[]）
      - 已存在但型別不符的欄位不會被自動修改，會直接丟出例外（避免悄悄改壞資料）
      - "=" 運算式定義的欄位視為已知欄位（不會被當多餘欄位刪掉），但缺失時無法自動補
        （rewrite 沒有 kwargs，沒有變數可以重新運算）
      - keep_other_line=False（預設）: 移除 json 裡完全沒在 .jsonpl 定義過的欄位
      - keep_other_line=True: 保留這些多餘欄位

    直接原地覆寫 json_path，回傳 (json_path, added_keys)。
    """
    _, schema, computed, _replace_flag = parse_jsonpl(jsonpl_path)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise TypeError(f"{json_path} 的內容不是 JSON object，無法補齊")

    known_keys = set(schema.keys()) | set(computed.keys())
    if not keep_other_line:
        data = {k: v for k, v in data.items() if k in known_keys}

    backfilled, added = _backfill(data, schema)

    # 只檢查 schema 定義的型別是否正確；不檢查多餘欄位（computed / keep 下來的欄位都合法存在）
    _validate(backfilled, schema, strict=False)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(backfilled, f, ensure_ascii=False, indent=4)

    return json_path, added


# ---------------------------------------------------------------------------
# add_back：反過來，用既有的 .json 更新 .jsonpl 的 schema
# ---------------------------------------------------------------------------

_TYPE_NAME = {v: k for k, v in TYPE_MAP.items()}


def _infer_type_spec(value):
    """依 json 的實際值反推一個 schema 型別。"""
    if isinstance(value, bool):
        return bool
    if isinstance(value, int):
        return int
    if isinstance(value, float):
        return float
    if isinstance(value, str):
        return str
    if isinstance(value, dict):
        return {k: _infer_type_spec(v) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return list  # 空陣列，證據不足
        first = _infer_type_spec(value[0])
        if all(_type_spec_eq(_infer_type_spec(v), first) for v in value[1:]):
            return [first]
        return list  # 元素型別不一致，退回裸 list
    return object  # None 或其他 -> any


def _type_spec_eq(a, b):
    """比較兩個 schema 型別是否等價（型別物件、巢狀 dict schema、[type] schema 都要能比）。"""
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a.keys()) == set(b.keys()) and all(
            _type_spec_eq(a[k], b[k]) for k in a
        )
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_type_spec_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) != isinstance(b, dict):
        return False
    if isinstance(a, list) != isinstance(b, list):
        return False
    return a is b


def _type_to_text(expected):
    """把 schema 型別序列化回 .jsonpl 的型別宣告文字。"""
    if isinstance(expected, Optional):
        return _type_to_text(expected.type) + "?"
    if isinstance(expected, dict):
        inner = ", ".join(f'"{k}": {_type_to_text(v)}' for k, v in expected.items())
        return "{ " + inner + " }"
    if isinstance(expected, list):
        if expected:
            return "[" + _type_to_text(expected[0]) + "]"
        return "list"
    return _TYPE_NAME.get(expected, "any")


def add_back(json_path: str, jsonpl_path: str, keep_other: bool = False):
    """
    跟 rewrite 相反方向：用既有的 json_path 更新 jsonpl_path 的 schema。
      - json 裡有、schema 沒定義的欄位 -> 依實際值反推型別，補進 schema
      - json 裡的值型別跟 schema 既有宣告不符 -> 用這次的值更新 schema 型別
        （但如果新證據只是「空陣列/元素型別不一致」的裸 list，且原本 schema 已經是更明確
        的型別，不會被降級覆蓋）
      - keep_other=False（預設）: schema 有、但這次 json 沒有的欄位，從 schema 移除
      - keep_other=True: 保留
      - "=" 運算式欄位完全不動，原樣寫回

    直接原地覆寫 jsonpl_path，回傳 (jsonpl_path, added_keys, updated_keys, removed_keys)。
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"{json_path} 的內容不是 JSON object，無法反向更新 schema")

    decl_text, items = _parse_template_items(jsonpl_path)

    schema_text = {}     # key -> 原始型別文字（":" 欄位）
    computed_text = {}   # key -> 原始運算式文字（"=" 欄位），完全不動
    order = []
    for key, sep, value_text in items:
        order.append(key)
        if sep == ":":
            schema_text[key] = value_text
        else:
            computed_text[key] = value_text

    current_schema = {k: _parse_type_spec(v) for k, v in schema_text.items()}

    added_keys, updated_keys, removed_keys = [], [], []

    for key, value in data.items():
        if key in computed_text:
            continue  # 運算式欄位不受 add_back 影響

        inferred = _infer_type_spec(value)

        if key not in current_schema:
            schema_text[key] = _type_to_text(inferred)
            order.append(key)
            added_keys.append(key)
            continue

        existing = current_schema[key]
        existing_optional = isinstance(existing, Optional)
        existing_type = existing.type if existing_optional else existing

        if _type_spec_eq(existing_type, inferred):
            continue

        # 空陣列/元素型別不一致只能反推出裸 list，屬於「證據不足」，
        # 若原本 schema 已經是更明確的型別就不覆蓋
        if inferred is list and existing_type is not list:
            continue

        text = _type_to_text(inferred)
        if existing_optional:
            text += "?"
        schema_text[key] = text
        updated_keys.append(key)

    if not keep_other:
        for key in list(schema_text.keys()):
            if key not in data and key not in computed_text:
                del schema_text[key]
                if key in order:
                    order.remove(key)
                removed_keys.append(key)

    seen = set()
    lines = []
    for key in order:
        if key in seen:
            continue
        seen.add(key)
        if key in computed_text:
            lines.append(f'    "{key}" = {computed_text[key]}')
        elif key in schema_text:
            lines.append(f'    "{key}": {schema_text[key]}')

    template_block = "{\n" + ",\n".join(lines) + "\n}\n"
    new_content = decl_text.rstrip("\n") + "\n\n" + template_block

    with open(jsonpl_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # 寫回後自我檢查，確保重建出來的 .jsonpl 仍然是合法可解析的
    parse_jsonpl(jsonpl_path)

    return jsonpl_path, added_keys, updated_keys, removed_keys


def _resolve_output_path(folder: str, base_name: str, replace: bool) -> str:
    """依 Replace 決定：True -> 直接覆蓋同名檔；False -> 自動加上 _1, _2... 編號"""
    path = os.path.join(folder, f"{base_name}.json")
    if replace or not os.path.exists(path):
        return path
    n = 1
    while True:
        candidate = os.path.join(folder, f"{base_name}_{n}.json")
        if not os.path.exists(candidate):
            return candidate
        n += 1


def send_json(path: str, file: dict, **kwargs) -> str:
    """
    依照 path 指向的 .jsonpl：
      1. 驗證 file 是否符合 ":" 型別欄位
      2. 用 kwargs 當變數環境，算出 "=" 運算式欄位
      3. 依 .jsonpl 內宣告的 Replace 決定覆蓋或自動編號
      4. 合併輸出成 .json，回傳輸出路徑
    """
    if "Replace" in kwargs:
        raise ValueError(
            "'Replace' 只能寫在 .jsonpl 檔案內宣告，不能透過 send_json 傳入覆寫"
        )

    declared_params, schema, computed, replace_flag = parse_jsonpl(path)

    for name, expected_type in declared_params.items():
        if name in kwargs and not isinstance(kwargs[name], expected_type):
            raise TypeError(f"參數 '{name}' 應該是 {expected_type.__name__}")

    _validate(file, schema)

    output = dict(file)
    for key, node in computed.items():
        output[key] = _eval_node(node, kwargs)

    folder = os.path.dirname(path)
    base_name = kwargs.get("required_name") or os.path.splitext(os.path.basename(path))[0]
    output_path = _resolve_output_path(folder, base_name, replace_flag)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

    return output_path
