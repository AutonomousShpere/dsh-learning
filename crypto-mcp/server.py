"""
MCP 服务入口：把 Binance 现货/合约的数据与指标能力暴露成 MCP 工具。

工具清单（8 个）：
  get_price          现货/合约最新价格
  get_candles        现货/合约 K 线（含 Base/Quote Volume）
  get_rsi            现货/合约 RSI
  get_ema            现货/合约 EMA
  get_macd           现货/合约 MACD
  get_funding_rate   合约资金费率
  get_open_interest  合约持仓量（张/币/USD）
  get_mark_price     合约标记价格

运行方式（默认 stdio，MCP 客户端直接调用）：
  python server.py
"""

from __future__ import annotations

from functools import wraps
from typing import Dict, List, Optional

from pydantic import Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import indicators
import market

mcp = MCPServer(
    "binance-indicators",
    title="Binance 现货/合约技术指标",
    description="查询 Binance 现货与 USDT 本位合约的价格、K 线、RSI、EMA、MACD、资金费率、持仓量和标记价格。",
)


# ---------------------------------------------------------------- 小工具函数

def _round(v: Optional[float], nd: int = 6) -> Optional[float]:
    """对浮点数四舍五入，避免输出过长的浮点噪声；None 原样返回。"""
    return round(v, nd) if v is not None else None


def _recent(candles: List[Dict], values: List[Optional[float]], n: int = 5) -> List[Dict]:
    """把指标序列与 K 线时间对齐，返回最近 n 个有效值 [{time, value}]。"""
    out = []
    for c, v in zip(candles, values):
        if v is not None:
            out.append({"time": c["time"], "value": _round(v)})
    return out[-n:]


def _closes(candles: List[Dict]) -> List[float]:
    """从 K 线列表里取出收盘价序列。"""
    return [c["close"] for c in candles]


def as_tool_error(fn):
    """
    装饰器：把工具内部抛出的普通异常统一转成 ToolError，
    这样 MCP 会把具体的错误信息（而不是笼统的 "Error executing tool ..."）透传给大模型。
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(str(exc)) from exc
    return wrapper


# ---------------------------------------------------------------- 现货 / 合约通用

@mcp.tool()
@as_tool_error
def get_price(
    market_type: str = Field(description="市场类型：spot 现货 / futures 合约"),
    symbol: str = Field(default="BTC/USDT", description="交易对，如 BTC/USDT、ETH/USDT"),
) -> Dict:
    """查询最新成交价格。现货和合约通用。"""
    return market.fetch_price(market_type, symbol)


@mcp.tool()
@as_tool_error
def get_candles(
    market_type: str = Field(description="市场类型：spot 现货 / futures 合约"),
    symbol: str = Field(default="BTC/USDT", description="交易对，如 BTC/USDT、ETH/USDT"),
    interval: str = Field(default="1h", description="K 线周期：1m / 5m / 15m / 1h / 4h / 1d"),
    limit: int = Field(default=100, description="返回的 K 线数量，最大 1500"),
) -> Dict:
    """查询 K 线，包含开高低收、Base Volume 和 Quote Volume。"""
    candles = market.fetch_candles(market_type, symbol, interval, limit)
    return {
        "market": market_type,
        "symbol": market.normalized_symbol(market_type, symbol),
        "interval": interval,
        "candles": candles,
    }


@mcp.tool()
@as_tool_error
def get_rsi(
    market_type: str = Field(description="市场类型：spot 现货 / futures 合约"),
    symbol: str = Field(default="BTC/USDT", description="交易对，如 BTC/USDT、ETH/USDT"),
    interval: str = Field(default="1h", description="K 线周期：1m / 5m / 15m / 1h / 4h / 1d"),
    period: int = Field(default=14, description="RSI 周期，常用 14"),
    limit: int = Field(default=200, description="取多少根 K 线来计算，需大于 period"),
) -> Dict:
    """计算相对强弱指标 RSI（Wilder 平滑）。返回最新值及最近若干值。"""
    candles = market.fetch_candles(market_type, symbol, interval, limit)
    rsi_values = indicators.rsi(_closes(candles), period)
    return {
        "market": market_type,
        "symbol": market.normalized_symbol(market_type, symbol),
        "interval": interval,
        "period": period,
        "latest": _round(indicators.last(rsi_values)),
        "recent": _recent(candles, rsi_values),
    }


@mcp.tool()
@as_tool_error
def get_ema(
    market_type: str = Field(description="市场类型：spot 现货 / futures 合约"),
    symbol: str = Field(default="BTC/USDT", description="交易对，如 BTC/USDT、ETH/USDT"),
    interval: str = Field(default="1h", description="K 线周期：1m / 5m / 15m / 1h / 4h / 1d"),
    period: int = Field(default=20, description="EMA 周期，常用 20"),
    limit: int = Field(default=200, description="取多少根 K 线来计算，需大于 period"),
) -> Dict:
    """计算指数移动平均 EMA。返回最新值及最近若干值。"""
    candles = market.fetch_candles(market_type, symbol, interval, limit)
    ema_values = indicators.ema(_closes(candles), period)
    return {
        "market": market_type,
        "symbol": market.normalized_symbol(market_type, symbol),
        "interval": interval,
        "period": period,
        "latest": _round(indicators.last(ema_values)),
        "recent": _recent(candles, ema_values),
    }


@mcp.tool()
@as_tool_error
def get_macd(
    market_type: str = Field(description="市场类型：spot 现货 / futures 合约"),
    symbol: str = Field(default="BTC/USDT", description="交易对，如 BTC/USDT、ETH/USDT"),
    interval: str = Field(default="1h", description="K 线周期：1m / 5m / 15m / 1h / 4h / 1d"),
    fast: int = Field(default=12, description="快线周期，常用 12"),
    slow: int = Field(default=26, description="慢线周期，常用 26"),
    signal: int = Field(default=9, description="信号线周期，常用 9"),
    limit: int = Field(default=200, description="取多少根 K 线来计算"),
) -> Dict:
    """计算 MACD（快慢线差值 + 信号线 + 柱状图）。返回最新值及最近若干值。"""
    candles = market.fetch_candles(market_type, symbol, interval, limit)
    macd_line, signal_line, hist = indicators.macd(_closes(candles), fast, slow, signal)

    recent = []
    for i in range(len(candles)):
        if macd_line[i] is not None:
            recent.append(
                {
                    "time": candles[i]["time"],
                    "macd": _round(macd_line[i]),
                    "signal": _round(signal_line[i]),
                    "histogram": _round(hist[i]),
                }
            )
    recent = recent[-5:]

    return {
        "market": market_type,
        "symbol": market.normalized_symbol(market_type, symbol),
        "interval": interval,
        "fast": fast,
        "slow": slow,
        "signal": signal,
        "latest": recent[-1] if recent else None,
        "recent": recent,
    }


# ---------------------------------------------------------------- 合约专属

@mcp.tool()
@as_tool_error
def get_funding_rate(
    symbol: str = Field(default="BTC/USDT", description="交易对，如 BTC/USDT、ETH/USDT"),
) -> Dict:
    """查询合约资金费率（Funding Rate），含下一次结算时间与标记价格。"""
    return market.fetch_funding_rate(symbol)


@mcp.tool()
@as_tool_error
def get_open_interest(
    symbol: str = Field(default="BTC/USDT", description="交易对，如 BTC/USDT、ETH/USDT"),
) -> Dict:
    """查询合约持仓量 Open Interest，返回 oi（张）、oiCcy（币）、oiUsd（USD）三种口径。"""
    return market.fetch_open_interest(symbol)


@mcp.tool()
@as_tool_error
def get_mark_price(
    symbol: str = Field(default="BTC/USDT", description="交易对，如 BTC/USDT、ETH/USDT"),
) -> Dict:
    """查询合约标记价格 Mark Price 与指数价格 Index Price。"""
    return market.fetch_mark_price(symbol)


# ---------------------------------------------------------------- 入口

if __name__ == "__main__":
    mcp.run()  # 默认 stdio，MCP 客户端通过标准输入输出与它通信
