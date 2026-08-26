#!/usr/bin/env python3
"""
s06_subagent.py - 子智能体

task 工具使用全新的消息列表运行第二个智能体循环。父子循环共享
工作目录，但只有子智能体的最终文本会返回父对话。

    父智能体                        子智能体
    +------------------+            +------------------+
    | messages=[...]   |            | messages=[prompt]|
    |                  |   task     |                  |
    | 工具: task       | ---------> | 独立智能体循环   |
    |                  |            | 仅基础工具       |
    | 工具结果         | <--------- | 最终文本         |
    +------------------+            +------------------+

子智能体没有 task 工具，因此不能再次委派。
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

WORKDIR = Path.cwd()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or None,
)
MODEL = os.getenv("OPENAI_MODEL_ID")
if not MODEL:
    raise RuntimeError("缺少 OPENAI_MODEL_ID，请在项目根目录的 .env 中配置模型名称")

# -----------------------------------------------------------------------
# --提示词--

SYSTEM = (
    f"你是位于 {WORKDIR} 的编程智能体。"
    "使用 task 工具处理聚焦的探索任务或边界清晰的独立子任务。"
)
SUB_SYSTEM = (
    f"你是位于 {WORKDIR} 的编程智能体。"
    "完成给定任务，然后返回简洁的最终答案。"
)

# -------------------------------------------------------------------------
# -- 基础工具 --

def run_bash(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, cwd=WORKDIR,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        return output[:50000] if output else "（没有输出）"
    except subprocess.TimeoutExpired:
        return "错误：执行超时（120 秒）"


def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = (WORKDIR / path).resolve().read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"...（还有 {len(lines) - limit} 行）"]
        return "\n".join(lines)
    except Exception as e:
        return f"错误：{e}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = (WORKDIR / path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"已向 {path} 写入 {len(content)} 字节"
    except Exception as e:
        return f"错误：{e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = (WORKDIR / path).resolve()
        text = file_path.read_text()
        if old_text not in text:
            return f"错误：在 {path} 中未找到指定文本"
        file_path.write_text(text.replace(old_text, new_text, 1))
        return f"已编辑 {path}"
    except Exception as e:
        return f"错误：{e}"


def run_glob(pattern: str) -> str:
    import glob
    try:
        matches = []
        for match in glob.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                matches.append(match)
        return "\n".join(matches) if matches else "（没有匹配项）"
    except Exception as e:
        return f"错误：{e}"


BASE_TOOLS = [
    {"type": "function", "name": "bash", "description": "执行一条 Shell 命令。",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"type": "function", "name": "read_file", "description": "读取文件内容。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"type": "function", "name": "write_file", "description": "将内容写入文件。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"type": "function", "name": "edit_file", "description": "精确替换文件中首次出现的指定文本。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"type": "function", "name": "glob", "description": "查找与 glob 模式匹配的文件。",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]

BASE_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}

# ------------------------------------------------------------------------------
# -- Hook系统 --

HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}


def register_hook(event: str, callback):
    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None


DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]


def permission_hook(tool_name: str, arguments: dict):
    """PreToolUse：阻止禁止操作，并对风险操作请求确认。"""
    if tool_name == "bash":
        command = arguments.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                print(f"\n\033[31m[已阻止] '{pattern}'\033[0m")
                return "权限拒绝：命令命中禁止列表"
        for keyword in DESTRUCTIVE:
            if keyword in command:
                print("\n\033[33m[权限确认] 可能具有破坏性的命令\033[0m")
                print(f"   工具：{tool_name}({arguments})")
                choice = input("   是否允许？[y/N] ").strip().lower()
                if choice not in ("y", "yes"):
                    return "权限拒绝：用户未授权"

    if tool_name in ("read_file", "write_file", "edit_file"):
        path = arguments.get("path", "")
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            print("\n\033[33m[权限确认] 正在访问工作区外部\033[0m")
            print(f"   工具：{tool_name}({arguments})")
            choice = input("   是否允许？[y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限拒绝：用户未授权"
    return None


def log_hook(tool_name: str, arguments: dict):
    """PreToolUse：记录每次工具调用。"""
    args_preview = str(list(arguments.values())[:2])[:60]
    print(f"\033[90m[HOOK] {tool_name}({args_preview})\033[0m")
    return None


def large_output_hook(tool_name: str, arguments: dict, output):
    """PostToolUse：工具输出过大时发出警告。"""
    if len(str(output)) > 100000:
        print(f"\033[33m[HOOK] {tool_name} 输出过大：{len(str(output))} 个字符\033[0m")
    return None


def context_inject_hook(query: str):
    """UserPromptSubmit：记录当前工作目录。"""
    print(f"\033[90m[HOOK] UserPromptSubmit：当前工作目录为 {WORKDIR}\033[0m")
    return None


def summary_hook(messages: list):
    """Stop：打印当前消息列表中的工具调用次数。"""
    tool_count = sum(
        1 for item in messages
        if (item.get("type") if isinstance(item, dict) else getattr(item, "type", None))
        == "function_call"
    )
    print(f"\033[90m[HOOK] Stop：本次上下文调用了 {tool_count} 次工具\033[0m")
    return None


register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)

# --------------------------------------------------------------------------------

# 所有已注册的工具通过execute_tool调用
# 接收参数：工具名称，工具参数，工具注册表
def execute_tool(tool_name: str, arguments: dict, handlers: dict) -> str:
    blocked = trigger_hooks("PreToolUse", tool_name, arguments)
    if blocked:
        return str(blocked)

    # 根据工具名字取注册表中找相应的处理函数，并调用处理函数
    handler = handlers.get(tool_name)
    try:
        # handler 就是工具函数的名字了，**arguments是将参数解包后当做参数传给工具函数
        output = handler(**arguments) if handler else f"错误：未知工具 {tool_name}"
    except Exception as e:
        output = f"错误：{e}"

    trigger_hooks("PostToolUse", tool_name, arguments, output)
    # 返回结果为工具调用输出
    return str(output)

# ----------------------------------------------------------------------------------
# -- s06新增：使用全新消息列表的嵌套智能体循环 --

SUB_TOOLS = list(BASE_TOOLS)
SUB_HANDLERS = dict(BASE_HANDLERS)

# -- 子智能体 --
# 一般来讲，这里接收参数 prompt 其实就是要调用工具对应的参数arguments
def run_subagent(prompt: str) -> str:
    print("\n\033[35m[子智能体已启动]\033[0m")
    messages = [{"role": "user", "content": prompt}]

    # 主循环，最多循环30轮
    for _ in range(30):
        response = client.responses.create(
            model=MODEL,
            instructions=SUB_SYSTEM,
            input=messages,
            tools=SUB_TOOLS,
            max_output_tokens=8000,
        )
        messages.extend(response.output)

        tool_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        if not tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            print("\033[35m[子智能体已完成]\033[0m")
            return response.output_text or "（没有总结）"

        for tool_call in tool_calls:
            arguments = json.loads(tool_call.arguments)
            output = execute_tool(tool_call.name, arguments, SUB_HANDLERS)
            print(f"  \033[90m[子] {tool_call.name}: {output[:100]}\033[0m")
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": output,
            })

    print("\033[35m[子智能体已停止]\033[0m")
    return "子智能体运行30轮后仍未生成最终答案，已停止。"


TASK_TOOL = {
    "type": "function",
    "name": "task",
    "description": "使用全新的对话上下文运行子智能体，并返回其最终文本。",
    "parameters": {
        "type": "object",
        "properties": {"prompt": {"type": "string", "minLength": 1}},
        "required": ["prompt"],
    },
}

# 定义工具（所有定义好的工具都是放在一个列表里）
# 把BASE_TOOLS解包，跟TASK_TOOL拼成一个新列表，命名为TOOLS
TOOLS = [*BASE_TOOLS, TASK_TOOL]

# 注册工具
# **是字典解包。这是把 BASE_HANDLERS 解包后跟字典 "task": run_subagent 拼一起，命名为TOOL_HANDLERS
TOOL_HANDLERS = {**BASE_HANDLERS, "task": run_subagent}

# --------------------------------------------------------------------------
# -- 父智能体循环 --

def agent_loop(messages: list):
    while True:
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM,
            input=messages,
            tools=TOOLS,
            max_output_tokens=8000,
        )
        messages.extend(response.output)

        tool_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        if not tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            return response.output_text

        for tool_call in tool_calls:
            arguments = json.loads(tool_call.arguments)
            # 已注册的工具通过execute_tool调用
            output = execute_tool(tool_call.name, arguments, TOOL_HANDLERS)
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": output,
            })


if __name__ == "__main__":
    print("s06：子智能体 - 使用独立消息上下文，只返回最终文本")
    print("输入问题后按回车发送，输入 q 或 exit 退出。\n")
    print(f"请求地址：{client.base_url}responses")

    history = []
    while True:
        try:
            query = input("\033[36ms06 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        trigger_hooks("UserPromptSubmit", query)
        history.append({"role": "user", "content": query})
        final_text = agent_loop(history)
        if final_text:
            print(final_text)
        print()
