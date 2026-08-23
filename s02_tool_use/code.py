#!/usr/bin/env python3
"""
s02_tool_use.py - 工具使用

s01 的智能体循环保持不变。本课新增四个工具和一个分发表：

    +----------+      +-------+      +--------------------------+
    |   用户   | ---> |  LLM  | ---> | 工具分发                  |
    |   提示   |      |       |      | bash       -> run_bash   |
    +----------+      +---+---+      | read_file  -> run_read   |
                          ^          | write_file -> run_write  |
                          |          | edit_file  -> run_edit   |
                          +----------+ glob       -> run_glob   |
                          工具结果   +--------------------------+

  + 新增 run_read / run_write / run_edit / run_glob
  + 使用 TOOL_HANDLERS 替代写死的 run_bash 调用
  + 使用 safe_path 将文件工具限制在工作区内

核心要点：循环保持不变，只扩展工具注册和分发。
"""

import json
import os
import subprocess
from pathlib import Path

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

# 获取当前运行程序所在期目录
WORKDIR = Path.cwd()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or None,
)
MODEL = os.getenv("OPENAI_MODEL_ID")
if not MODEL:
    raise RuntimeError("缺少 OPENAI_MODEL_ID，请在项目根目录的 .env 中配置模型名称")

SYSTEM = f"你是位于 {WORKDIR} 的编程智能体。使用工具解决任务。直接行动，不要只解释。"


# -- 来自 s01（保持不变）--
def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "错误：危险命令已被拦截"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "（没有输出）"
    except subprocess.TimeoutExpired:
        return "错误：执行超时（120 秒）"
    except (FileNotFoundError, OSError) as e:
        return f"错误：{e}"


# -- s02 新增：四个工具 --
# 安全路径检查
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"路径超出工作区：{p}")
    return path

# 读取文件内容
def run_read(path: str, limit: int | None = None) -> str:
    try:
        # 读取文件内容；lines是一个列表，内容元素是文件的每一行
        # .read_text()是path的对象方法，作用是读取整个文件内容并且返回字符串
        # .splitlines()是字符串方法，把字符串按照回车拆成列表
        lines = safe_path(path).read_text().splitlines()

        # 如果指定了行数限制且文件行数超过限制，则截断并添加省略提示
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"...（还有 {len(lines) - limit} 行）"]
        # "\n".join()是用换行符吧所有列表元素连成一个字符串，最终返回一个字符串
        return "\n".join(lines)
    except Exception as e:
        return f"错误：{e}"

# 读取文件内容
def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"已向 {path} 写入 {len(content)} 字节"
    except Exception as e:
        return f"错误：{e}"

# 写入文件内容
def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text()
        if old_text not in text:
            return f"错误：在 {path} 中未找到指定文本"
        file_path.write_text(text.replace(old_text, new_text, 1))
        return f"已编辑 {path}"
    except Exception as e:
        return f"错误：{e}"

# 文件编辑
def run_glob(pattern: str) -> str:
    import glob as g
    try:
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "（没有匹配项）"
    except Exception as e:
        return f"错误：{e}"


# -- s02 新增：工具定义（s01 有一个工具，s02 有五个）--
# 本质是一个字典列表，每个字典定义一个工具
TOOLS = [
    {"type": "function", "name": "bash", "description": "执行一条 Shell 命令。",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"type": "function", "name": "read_file", "description": "读取文件内容。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}},"required": ["path"]}},
    {"type": "function", "name": "write_file", "description": "将内容写入文件。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"type": "function", "name": "edit_file", "description": "精确替换文件中首次出现的指定文本。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"type": "function", "name": "glob", "description": "查找与 glob 模式匹配的文件。",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]

# 工具注册
# -- s02 新增：分发表（替代 s01 中写死的 run_bash 调用）--
# 本质是一个字典，key-value对应着工具名称-函数名称
TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}


# -- 智能体循环保持与 s01 相同的结构，仅改变分发方式 --
# s01: output = run_bash(block.input["command"])
# s02: output = TOOL_HANDLERS[block.name](**block.input)
def agent_loop(messages: list):
    loop_times = 0
    while True:
        loop_times += 1
        print(f"\033[35m> 循环次数：{loop_times}\033[0m")
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM,
            input=messages,
            tools=TOOLS,
            max_output_tokens=8000,
        )
        # 保留全部输出项，包括消息、推理项和函数调用，供下一轮完整回传。
        messages.extend(response.output)

        # 判断是否调用工具
        # 列表推导式，过滤出所有需要调用工具的项
        tool_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        if not tool_calls:
            return response.output_text
        print(f'\033需要调用工具数量为：{len(tool_calls)}\033[0m')

        # 按照收集的tool_calls，调用相应的工具，并把调用工具返回结果追加到messages
        for tool_call in tool_calls:
            print(f"\033[33m> 调用工具name：{tool_call.name}\033[0m")
            print(f'\033[33m> 对应的函数名称为：{TOOL_HANDLERS.get(tool_call.name)}\033[0m')
            handler = TOOL_HANDLERS.get(tool_call.name)
            arguments = json.loads(tool_call.arguments)
            output = handler(**arguments) if handler else f"错误：未知工具 {tool_call.name}"
            print(str(output)[:200])
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": output,
            })


if __name__ == "__main__":
    print("s02：工具使用 - 在 s01 基础上新增四个工具")
    print("输入问题后按回车发送，输入 q 或 exit 退出。\n")
    print(f"请求地址：{client.base_url}responses")

    history = []
    while True:
        try:
            query = input("\033[36ms02 >> \033[0m")
        except (EOFError,  KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        final_text = agent_loop(history)
        if final_text:
            print(final_text)
        print()
