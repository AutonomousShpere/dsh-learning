# Binance 现货/合约技术指标 MCP

一个用 **Python + ccxt** 写的 MCP（Model Context Protocol）服务，查询 **Binance** 现货与 U 本位合约（USDT-M 永续）的价格、K 线和常用技术指标。

- 数据源：[ccxt](https://ccxt.com/)（统一封装 100+ 交易所 API）
- MCP 框架：官方 [mcp Python SDK v2](https://github.com/modelcontextprotocol/python-sdk)

---

## 一、提供的工具（8 个）

| 工具 | 市场 | 说明 |
|------|------|------|
| `get_price` | 现货 + 合约 | 最新成交价 |
| `get_candles` | 现货 + 合约 | K 线：开高低收、Base Volume、Quote Volume |
| `get_rsi` | 现货 + 合约 | 相对强弱指标（Wilder 平滑） |
| `get_ema` | 现货 + 合约 | 指数移动平均 |
| `get_macd` | 现货 + 合约 | MACD 线 / 信号线 / 柱状图 |
| `get_funding_rate` | 合约 | 资金费率（含下一次结算时间、标记价、指数价） |
| `get_open_interest` | 合约 | 持仓量：`oi`（张）/ `oiCcy`（币）/ `oiUsd`（USD） |
| `get_mark_price` | 合约 | 标记价格 Mark Price 与指数价格 Index Price |

---

## 二、目录结构

```
crypto-mcp/
├── server.py         # MCP 服务入口：定义 8 个工具并启动
├── market.py         # 数据层：用 ccxt 查 Binance 现货/合约
├── indicators.py     # 指标计算：RSI / EMA / MACD（纯 Python）
├── requirements.txt  # 依赖清单
└── .venv/            # 虚拟环境
```

依赖关系：`server.py` → `market.py`（取数）+ `indicators.py`（算指标）

---

## 三、安装

```bash
cd crypto-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

依赖只有三个：`ccxt`、`mcp`、`pydantic`。

---

## 四、测试

### 方式 1：直接跑单元测试

```bash
.venv/bin/python -c "import indicators; print(indicators.ema([1,2,3,4,5], 3))"
```

### 方式 2：用 MCP Inspector 图形界面调试（推荐）

```bash
.venv/bin/mcp dev server.py
```

会自动打开一个网页，你可以在里面手动调用每个工具、看到返回结果。

### 方式 3：命令行直接跑服务

```bash
.venv/bin/python server.py        # 默认 stdio 模式
```

---

## 五、接入客户端（Claude Desktop / Cursor 等）

在客户端的 MCP 配置里加一段（把路径换成你自己的绝对路径）：

```json
{
  "mcpServers": {
    "binance-indicators": {
      "command": "/绝对路径/crypto-mcp/.venv/bin/python",
      "args": ["server.py"],
      "cwd": "/绝对路径/crypto-mcp"
    }
  }
}
```

- Claude Desktop：`~/Library/Application Support/Claude/claude_desktop_config.json`
- Cursor：项目根目录 `.cursor/mcp.json`

配置后重启客户端，就能让大模型调用这些工具了。

---

## 六、参数说明

**通用参数**

- `market_type`：`spot`（现货）或 `futures`（合约）
- `symbol`：交易对，支持三种写法，效果等价：
  - `BTC/USDT`
  - `BTC/USDT:USDT`（合约）
  - `BTCUSDT`（原生格式，自动识别）
- `interval`：`1m` / `5m` / `15m` / `1h` / `4h` / `1d`
- `limit`：取多少根 K 线（最大 1500）

**指标参数**

- `get_rsi` → `period`（默认 14）
- `get_ema` → `period`（默认 20）
- `get_macd` → `fast`（12）/ `slow`（26）/ `signal`（9）

---

## 七、几个关键知识点

1. **指标公式**（在 `indicators.py` 里，纯手写不依赖 pandas）：
   - EMA：`EMA_t = price_t × k + EMA_{t-1} × (1-k)`，`k = 2/(period+1)`
   - RSI：`RSI = 100 - 100/(1+RS)`，`RS = 平均涨幅/平均跌幅`（Wilder 平滑）
   - MACD：`MACD线 = EMA(fast) - EMA(slow)`，`信号线 = EMA(signal) of MACD线`，`柱状图 = MACD线 - 信号线`

2. **持仓量三种口径**（`get_open_interest`）：
   - `oi`（张）= `oiCcy / contractSize`
   - `oiCcy`（币）= Binance 返回的 `openInterest`（U 本位合约里它就是基础币数量，如 BTC）
   - `oiUsd`（USD）= `oiCcy × 标记价格`
   - 注意：U 本位合约的 `contractSize` 通常是 `1.0`，所以「张」和「币」数值相等；换成币本位合约（contractSize ≠ 1）后两者才会不同。

3. **K 线含两个成交量**：ccxt 的 `fetch_ohlcv` 只有 6 列（不含 quote volume），所以这里直接调 Binance 原始 K 线接口，拿到 `Base Volume` 和 `Quote Volume` 两列。

4. **合约用 `ccxt.binanceusdm()`**：对应 Binance U 本位（USDT 结算）永续合约。现货用 `ccxt.binance()`。

---

## 八、常见问题

- **连接超时 / 网络错误**：Binance 在某些地区可能被限制访问，需要网络能直连 `api.binance.com`。
- **请求太频繁被限流**：代码里已开启 `enableRateLimit=True`，ccxt 会自动限速。
- **找不到交易对**：确认符号拼写正确，用 `BASE/QUOTE` 格式最稳妥（如 `ETH/USDT`）。
