#!/usr/bin/env python3
"""
s01_agent_loop.py - 智能体循环

AI 编程智能体最核心的模式如下：

    while True:
        response = LLM(messages, tools)
        if response 中没有工具调用:
            break
        执行工具
        追加工具结果

    +----------+      +-------+      +---------+
    |   用户   | ---> |  LLM  | ---> |  工具   |
    |   提示   |      |       |      |  执行   |
    +----------+      +---+---+      +----+----+
                          ^               |
                          |    工具结果   |
                          +---------------+
                           （继续循环）

这就是核心循环：把工具执行结果返回给模型，直到模型决定停止。
后续章节会在这个循环周围逐步增加权限策略、钩子和生命周期控制。

运行方式：
    pip install openai python-dotenv
    OPENAI_API_KEY=... python s01_agent_loop/code.py
"""

import json
import os
import subprocess

try:
    import readline
    # 修复 macOS libedit 环境下 UTF-8 字符退格异常（Issue #143）
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass
from openai import OpenAI
from dotenv import load_dotenv

# 从项目根目录的 .env 文件加载环境变量；同名变量以 .env 中的值为准
load_dotenv(override=True)

# OpenAI SDK 自动读取 OPENAI_API_KEY；兼容代理时可设置 OPENAI_BASE_URL
client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL") or None)
MODEL = os.getenv("OPENAI_MODEL_ID")
if not MODEL:
    raise RuntimeError("缺少 OPENAI_MODEL_ID，请在项目根目录的 .env 中配置模型名称")

SYSTEM = f"你是位于win系统的 {os.getcwd()} 的编程智能体。使用 Bash 解决任务。直接行动，不要只解释。"

# -- 工具定义：目前只有 Bash --
TOOLS = [{
    "type": "function",
    "name": "bash",
    "description": "执行一条 Shell 命令。",
    "parameters": {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
        "additionalProperties": False,
    },
    "strict": True,
}]


# -- 工具执行 --
def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "错误：危险命令已被拦截"
    try:
        r = subprocess.run(command, shell=True, cwd=os.getcwd(),
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "（没有输出）"
    except subprocess.TimeoutExpired:
        return "错误：执行超时（120 秒）"
    except (FileNotFoundError, OSError) as e:
        return f"错误：{e}"


# -- 核心模式：持续调用模型和工具，直到模型决定停止 --
def agent_loop(messages: list):
    while True:
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM,
            input=messages,
            tools=TOOLS,
            max_output_tokens=8000,
        )

        # OpenAI Responses 可能包含消息、推理项和函数调用。
        # 保存所有输出项，确保下一次请求拥有完整的历史记录。
        messages.extend(response.output)

        # 如果模型没有调用工具，本轮任务结束
        tool_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        if not tool_calls:
            return response.output_text

        # 依次执行工具调用，并把结果追加到消息历史
        for tool_call in tool_calls:
            arguments = json.loads(tool_call.arguments)
            command = arguments["command"]
            print(f"\033[33m$ {command}\033[0m")
            output = run_bash(command)
            print(output[:200])
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": output,
            })


# -- 程序入口 --
if __name__ == "__main__":
    print("s01：智能体循环")
    print("输入问题后按回车发送，输入 q 或 exit 退出。\n")
    print(f"请求地址：{client.base_url}responses")
    history = []
    while True:
        try:
            query = input("\033[36ms01 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        final_text = agent_loop(history)
        if final_text:
            print(final_text)
        print()

