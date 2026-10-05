"""余额查询（与界面无关）。

各中转站的返回格式不统一：若中转站配置了 balance_field 则按其计算，
支持字段路径（如 "data.balance"）及其加减表达式（如 "quota - quota_used"）；
否则在返回的 JSON 中按常见字段名自动查找。
"""
import logging
import re
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Optional

import requests

log = logging.getLogger(__name__)

# 自动识别时按优先级查找的字段名（不区分大小写）
BALANCE_KEYS = (
    "balance", "remaining_balance", "available_balance", "total_balance",
    "remaining", "remain", "remain_quota", "remaining_quota", "credit", "credits", "quota",
)


@dataclass
class Relay:
    name: str
    url: str
    api_key: str = ""
    balance_field: str = ""   # 可选，余额字段路径或加减表达式，如 "quota - quota_used"

    @classmethod
    def from_dict(cls, data: dict) -> "Relay":
        return cls(name=str(data.get("name", "")), url=str(data.get("url", "")),
                   api_key=str(data.get("api_key", "")), balance_field=str(data.get("balance_field", "")))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BalanceResult:
    relay: Relay
    amount: float
    raw: Any


class BalanceError(Exception):
    """short 为显示在牌子上的简短文字，str(e) 为详细原因。"""

    def __init__(self, short: str, detail: str = ""):
        super().__init__(detail or short)
        self.short = short


def _to_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().lstrip("$¥￥"))
        except ValueError:
            return None
    return None


def _get_path(data: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        else:
            return None
    return data


def _find_balance(data: Any) -> Optional[float]:
    """广度优先查找，浅层字段优先。"""
    queue = deque([data])
    while queue:
        node = queue.popleft()
        if isinstance(node, dict):
            lowered = {str(k).lower(): v for k, v in node.items()}
            for key in BALANCE_KEYS:
                number = _to_number(lowered.get(key))
                if number is not None:
                    return number
            queue.extend(node.values())
        elif isinstance(node, list):
            queue.extend(node)
    return None


def _eval_field(data: Any, expression: str) -> Optional[float]:
    """计算由字段路径和 +、- 组成的表达式，如 "quota - quota_used"。任一字段缺失则返回 None。"""
    tokens = re.findall(r"[+-]|[^\s+-]+", expression)
    total, sign, expect_operand = 0.0, 1, True
    for token in tokens:
        if token in "+-":
            if expect_operand:
                return None
            sign, expect_operand = (1 if token == "+" else -1), True
            continue
        if not expect_operand:
            return None
        value = _to_number(token)
        if value is None:
            value = _to_number(_get_path(data, token))
        if value is None:
            return None
        total += sign * value
        expect_operand = False
    return None if expect_operand else total


def extract_amount(data: Any, balance_field: str = "") -> Optional[float]:
    if balance_field.strip():
        return _eval_field(data, balance_field)
    return _find_balance(data)


def format_amount(amount: float) -> str:
    if amount.is_integer() and abs(amount) >= 10000:
        return f"{amount:,.0f}"
    return f"{amount:,.2f}"


def fetch_balance(relay: Relay, timeout: float = 15.0) -> BalanceResult:
    if not relay.api_key:
        raise BalanceError("未填写Key")
    try:
        resp = requests.get(relay.url, headers={"Authorization": f"Bearer {relay.api_key}"}, timeout=timeout)
    except requests.RequestException as e:
        raise BalanceError("网络错误", str(e)) from e

    try:
        data = resp.json()
    except ValueError:
        data = None
    if resp.status_code != 200:
        message = data.get("message", "") if isinstance(data, dict) else resp.text[:200]
        short = "Key无效" if resp.status_code in (401, 403) else f"HTTP {resp.status_code}"
        raise BalanceError(short, f"HTTP {resp.status_code}: {message}")
    if data is None:
        raise BalanceError("格式未知", f"返回的不是 JSON: {resp.text[:200]}")

    amount = extract_amount(data, relay.balance_field)
    if amount is None:
        log.warning("未能在返回数据中识别余额，可在中转站设置中填写“余额字段”。返回内容: %s", data)
        raise BalanceError("格式未知", f"未找到余额字段: {data}")
    return BalanceResult(relay, amount, data)
