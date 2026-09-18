"""
演示：MCP 客户端如何调用我们自己的 server.py。

这里展示了 MCP 的另一半 ——「客户端」。
平时这个角色由 Claude Desktop / Cursor 等 AI 应用扮演；这里我们手写一个客户端，
通过 stdio 启动 server.py，然后像大模型一样调用里面的工具。

运行：
    .venv/bin/python demo_client.py
"""

import asyncio
import json

from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def main():
    # 1) 指定要启动的服务端：用 python 运行 server.py
    params = StdioServerParameters(
        command=".venv/bin/python",
        args=["server.py"],
        cwd=".",  # 相对当前目录
    )

    # 2) 建立连接（Client 会启动 server.py 子进程，通过标准输入输出通信）
    async with Client(params) as client:
        # 3) 看看服务端提供了哪些工具
        tools = await client.list_tools()
        print("=== 服务端提供的工具 ===")
        for t in tools.tools:
            print("  -", t.name)

        # 4) 像大模型一样调用工具
        async def call(name, args):
            result = await client.call_tool(name, args)
            return result.structured_content, result.is_error

        print("\n=== 调用 get_price（现货 BTC）===")
        data, err = await call("get_price", {"market_type": "spot", "symbol": "BTC/USDT"})
        print(json.dumps(data, ensure_ascii=False, indent=2))

        print("\n=== 调用 get_open_interest（合约 BTC 持仓量）===")
        data, err = await call("get_open_interest", {"symbol": "BTC/USDT"})
        print(json.dumps(data, ensure_ascii=False, indent=2))

        print("\n=== 调用 get_macd（合约 BTC，1h）===")
        data, err = await call("get_macd", {"market_type": "futures", "symbol": "BTC/USDT", "interval": "1h"})
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
