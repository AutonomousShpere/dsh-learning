"""
技术指标计算模块（纯 Python 实现，不依赖 pandas/numpy）。

这里只做"数学计算"，输入是一串数字（比如收盘价列表），输出是等长的指标序列。
为了让指标序列和输入的 K 线一一对应，长度不足（还没有足够数据）的位置用 None 占位。

指标定义：
- EMA  : 指数移动平均   EMA_t = price_t * k + EMA_{t-1} * (1 - k)，k = 2 / (period + 1)
- RSI  : 相对强弱指标   RSI = 100 - 100 / (1 + RS)，RS = 平均涨幅 / 平均跌幅（Wilder 平滑）
- MACD : 快慢线差值     MACD 线 = EMA(fast) - EMA(slow)，信号线 = EMA(signal) of MACD 线，
         柱状图 = MACD 线 - 信号线
"""

from __future__ import annotations

from typing import List, Optional, Tuple


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """
    计算指数移动平均（EMA）。

    前 period-1 个位置没有 EMA，用 None 占位；
    第 period 个位置用前面 period 个值的简单平均（SMA）作为种子，之后按公式递推。
    """
    if period <= 0:
        raise ValueError("period 必须大于 0")
    if len(values) < period:
        return [None] * len(values)

    k = 2.0 / (period + 1.0)
    result: List[Optional[float]] = [None] * (period - 1)

    # 种子：前 period 个值的简单平均
    seed = sum(values[:period]) / period
    result.append(seed)

    prev = seed
    for price in values[period:]:
        prev = price * k + prev * (1.0 - k)
        result.append(prev)
    return result


def rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """
    计算相对强弱指标（RSI），使用 Wilder 平滑。

    前 period 个位置无法计算（需要 period 次涨跌），用 None 占位。
    """
    if period <= 0:
        raise ValueError("period 必须大于 0")
    if len(closes) < period + 1:
        return [None] * len(closes)

    # 先算相邻涨跌（第 0 个位置没有涨跌，用 None 占位）
    changes: List[Optional[float]] = [None]
    for i in range(1, len(closes)):
        changes.append(closes[i] - closes[i - 1])

    gains = [c if c is not None and c > 0 else 0.0 for c in changes]
    losses = [abs(c) if c is not None and c < 0 else 0.0 for c in changes]

    result: List[Optional[float]] = [None] * (period)  # 前 period 个位置（含第 0 个）无法计算

    # Wilder 平滑：先用前 period 次涨跌的简单平均做种子
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period

    def _to_rsi(g: float, l: float) -> float:
        if l == 0:
            return 100.0  # 没有下跌，RSI 记为 100
        rs = g / l
        return 100.0 - 100.0 / (1.0 + rs)

    result.append(_to_rsi(avg_gain, avg_loss))

    for i in range(period + 1, len(closes)):
        g = gains[i]
        l = losses[i]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        result.append(_to_rsi(avg_gain, avg_loss))

    return result


def macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """
    计算 MACD，返回三个等长序列：(macd 线, 信号线, 柱状图)。

    MACD 线   = EMA(fast) - EMA(slow)
    信号线    = EMA(signal) of MACD 线
    柱状图    = MACD 线 - 信号线
    """
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    # 逐点相减；只要有一个是 None，MACD 线也是 None
    macd_line: List[Optional[float]] = []
    for f, s in zip(ema_fast, ema_slow):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(f - s)

    # 信号线是对 MACD 线的 EMA，但 MACD 线里有 None，需要先把有效值提取出来
    valid: List[float] = [v for v in macd_line if v is not None]
    # 记录有效值对应的原始下标，方便把结果映射回去
    valid_indices = [i for i, v in enumerate(macd_line) if v is not None]

    signal_valid = ema(valid, signal)

    # 映射回原始长度
    signal_line: List[Optional[float]] = [None] * len(macd_line)
    for idx, val in zip(valid_indices, signal_valid):
        signal_line[idx] = val

    histogram: List[Optional[float]] = []
    for m, s in zip(macd_line, signal_line):
        if m is None or s is None:
            histogram.append(None)
        else:
            histogram.append(m - s)

    return macd_line, signal_line, histogram


def last(values: List[Optional[float]]) -> Optional[float]:
    """取指标序列里最后一个有效值（用于返回"最新"指标）。"""
    for v in reversed(values):
        if v is not None:
            return v
    return None
