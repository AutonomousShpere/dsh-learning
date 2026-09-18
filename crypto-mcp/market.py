"""
数据层：通过 ccxt 查询 Binance 现货与 USDT 本位永续合约的数据。

本文件只负责"取数"，不负责计算指标（指标在 indicators.py）。
对外暴露一组纯函数，server.py 直接调用。

两个交易所实例：
- spot     -> ccxt.binance()       Binance 现货
- futures  -> ccxt.binanceusdm()   Binance U 本位合约（USDT-M 永续）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import ccxt

# 支持的 K 线周期
INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")

# Binance 单次请求 K 线数量上限
MAX_LIMIT = 1500
DEFAULT_LIMIT = 100

# 支持的市场类型
MARKET_TYPES = ("spot", "futures")

# 交易所实例（懒加载单例：第一次用时才初始化并拉取市场列表）
_spot: Optional[ccxt.binance] = None
_futures: Optional[ccxt.binanceusdm] = None


def _get_spot() -> ccxt.binance:
    """返回现货交易所实例（懒加载）。"""
    global _spot
    if _spot is None:
        _spot = ccxt.binance({"enableRateLimit": True})  # 自动限速，避免被交易所封
        _spot.load_markets()
    return _spot


def _get_futures() -> ccxt.binanceusdm:
    """返回合约交易所实例（懒加载）。"""
    global _futures
    if _futures is None:
        _futures = ccxt.binanceusdm({"enableRateLimit": True})
        _futures.load_markets()
    return _futures


def _exchange_for(market: str):
    """根据 market 类型返回对应交易所实例。"""
    if market == "spot":
        return _get_spot()
    if market == "futures":
        return _get_futures()
    raise ValueError(f"market 只能是 {MARKET_TYPES}，收到: {market!r}")


def _iso(ms: int) -> str:
    """把毫秒时间戳转成 ISO 8601 字符串（带 UTC 时区）。"""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def resolve_symbol(exchange, symbol: str, market: str) -> str:
    """
    把用户输入的交易对转成 ccxt 统一格式，并校验它真实存在。

    支持的输入：
    - "BTC/USDT"          -> 现货 "BTC/USDT"，合约自动补成 "BTC/USDT:USDT"
    - "BTC/USDT:USDT"     -> 合约直接用
    - "BTCUSDT"（无斜杠） -> 自动反查成统一格式
    """
    symbol = symbol.strip().upper().replace(" ", "")

    if "/" not in symbol:
        # 原生格式（如 BTCUSDT）：遍历市场表反查统一符号
        for unified, m in exchange.markets.items():
            if m.get("id") == symbol:
                return unified
        raise ValueError(f"无法识别的交易对: {symbol!r}，请用 BASE/QUOTE 格式，例如 BTC/USDT")

    if market == "futures" and ":" not in symbol:
        symbol = symbol + ":USDT"  # U 本位合约，结算币固定是 USDT

    try:
        return exchange.market(symbol)["symbol"]  # 校验存在，返回规范符号
    except Exception as exc:
        raise ValueError(f"交易所没有这个交易对: {symbol!r}（{exc}）")


def normalized_symbol(market: str, symbol: str) -> str:
    """返回规范化后的统一符号（用于在结果里回显），例如 futures + BTC/USDT -> BTC/USDT:USDT。"""
    exchange = _exchange_for(market)
    return resolve_symbol(exchange, symbol, market)


def fetch_price(market: str, symbol: str) -> Dict:
    """查询最新成交价。现货和合约通用。"""
    exchange = _exchange_for(market)
    unified = resolve_symbol(exchange, symbol, market)
    ticker = exchange.fetch_ticker(unified)
    return {
        "market": market,
        "symbol": unified,
        "price": ticker["last"],
        "datetime": ticker["datetime"],
    }


def fetch_candles(market: str, symbol: str, interval: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """
    查询 K 线（含 Base Volume 和 Quote Volume）。

    用 Binance 原始 K 线接口，因为 ccxt 的 fetch_ohlcv 只有 6 列，不含 quote volume。
    返回按时间从旧到新排列的 K 线列表。
    """
    if interval not in INTERVALS:
        raise ValueError(f"interval 只能是 {INTERVALS}，收到: {interval!r}")

    limit = max(1, min(int(limit), MAX_LIMIT))
    exchange = _exchange_for(market)
    unified = resolve_symbol(exchange, symbol, market)
    native = exchange.market_id(unified)  # 统一符号 -> 原生符号（BTC/USDT -> BTCUSDT）

    if market == "spot":
        raw = exchange.publicGetKlines({"symbol": native, "interval": interval, "limit": limit})
    else:
        raw = exchange.fapiPublicGetKlines({"symbol": native, "interval": interval, "limit": limit})

    candles = []
    for row in raw:
        candles.append(
            {
                "time": _iso(int(row[0])),      # 开盘时间
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "baseVolume": float(row[5]),    # 基础币成交量
                "quoteVolume": float(row[7]),   # 计价币成交量
            }
        )
    return candles


def fetch_mark_price(symbol: str) -> Dict:
    """查询合约标记价格（Mark Price）与指数价格（Index Price）。"""
    exchange = _get_futures()
    unified = resolve_symbol(exchange, symbol, "futures")
    mp = exchange.fetch_mark_price(unified)
    return {
        "symbol": unified,
        "markPrice": mp.get("markPrice"),
        "indexPrice": mp.get("indexPrice"),
        "datetime": mp.get("datetime"),
    }


def fetch_funding_rate(symbol: str) -> Dict:
    """查询合约资金费率（Funding Rate）。"""
    exchange = _get_futures()
    unified = resolve_symbol(exchange, symbol, "futures")
    fr = exchange.fetch_funding_rate(unified)

    rate = fr.get("fundingRate")
    return {
        "symbol": unified,
        "fundingRate": rate,                                  # 小数形式，如 0.00005252
        "fundingRatePct": round(rate * 100, 6) if rate is not None else None,  # 百分比
        "nextFundingTime": fr.get("fundingDatetime"),         # 下一次资金费结算时间
        "markPrice": fr.get("markPrice"),
        "indexPrice": fr.get("indexPrice"),
    }


def fetch_open_interest(symbol: str) -> Dict:
    """
    查询合约持仓量（Open Interest），返回三种口径：

    - oi     ：按"张"（合约数量）计算
    - oiCcy  ：按"币"（基础资产，如 BTC）计算
    - oiUsd  ：按 USD 计算

    换算关系（对线性合约）：
        张   = 币 / contractSize
        USD  = 币 * 标记价格
    """
    exchange = _get_futures()
    unified = resolve_symbol(exchange, symbol, "futures")

    market_info = exchange.market(unified)
    contract_size = market_info.get("contractSize") or 1.0

    oi = exchange.fetch_open_interest(unified)
    amount = oi.get("openInterestAmount")  # 币数（USDT 本位合约的 openInterestAmount 即基础币数量）
    if amount is None:
        raise RuntimeError(f"未能获取 {unified} 的持仓量")

    mark_price = exchange.fetch_mark_price(unified).get("markPrice")

    oi_ccy = amount
    oi_contracts = amount / contract_size
    oi_usd = round(oi_ccy * mark_price, 4) if mark_price is not None else None

    return {
        "symbol": unified,
        "contractSize": contract_size,
        "oi": oi_contracts,       # 张
        "oiCcy": oi_ccy,          # 币
        "oiUsd": oi_usd,          # USD
        "markPrice": mark_price,
        "datetime": oi.get("datetime"),
    }
