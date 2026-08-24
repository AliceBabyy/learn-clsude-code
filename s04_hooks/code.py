#!/usr/bin/env python3
"""
s04_hooks.py - 钩子

Hook 会在智能体循环的固定位置执行回调：

      用户提示
         |
         v
    UserPromptSubmit
         |
         v
    +----------+      +-------+      +------------+      +-------+
    |   消息   | ---> |  LLM  | ---> | PreToolUse | ---> | 工具  |
    +----------+      +---+---+      | permission |      +---+---+
         ^                | 停止     | 权限、日志 |          |
         |                v          +------------+          v
         |            Stop Hook                         PostToolUse
         |                                               |
         +----------------- 工具结果 --------------------+
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

SYSTEM = f"你是位于 {WORKDIR} 的编程智能体。使用工具解决任务。直接行动，不要只解释。"


# -- 来自 s02-s03 的工具实现 --

def run_bash(command: str) -> str:
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "（没有输出）"
    except subprocess.TimeoutExpired:
        return "错误：执行超时（120 秒）"

def run_read(path: str, limit: int | None = None) -> str:
    try:
        file_path = (WORKDIR / path).resolve()
        lines = file_path.read_text().splitlines()
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
    import glob as g
    try:
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "（没有匹配项）"
    except Exception as e:
        return f"错误：{e}"

TOOLS = [
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

TOOL_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_glob,
}


# -- s04 新增：Hook 系统（s03 权限逻辑现在通过 Hook 实现）--

HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}

def register_hook(event: str, callback):
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:  # Hook 返回结果表示阻止本次工具调用。
            return result
    return None


# s03 权限检查逻辑，现在封装为 Hook
DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]

def permission_hook(tool_name: str, arguments: dict):
    """PreToolUse：将 s03 check_permission() 权限逻辑移到这里。"""
    if tool_name == "bash":
        for pattern in DENY_LIST:
            if pattern in arguments.get("command", ""):
                print(f"\n\033[31m[已阻止] '{pattern}'\033[0m")
                return "权限拒绝：命令命中禁止列表"
        for kw in DESTRUCTIVE:
            if kw in arguments.get("command", ""):
                print(f"\n\033[33m[权限确认] 可能具有破坏性的命令\033[0m")
                print(f"   工具：{tool_name}({arguments})")
                choice = input("   是否允许？[y/N] ").strip().lower()
                if choice not in ("y", "yes"):
                    return "权限拒绝：用户未授权"
    if tool_name in ("read_file", "write_file", "edit_file"):
        path = arguments.get("path", "")
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            print(f"\n\033[33m[权限确认] 正在访问工作区外部\033[0m")
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

# UserPromptSubmit Hook：用户输入到达 LLM 前记录当前工作目录
def context_inject_hook(query: str):
    print(f"\033[90m[HOOK] UserPromptSubmit：当前工作目录为 {WORKDIR}\033[0m")
    return None

# Stop Hook：循环即将结束时打印摘要
def summary_hook(messages: list):
    tool_count = sum(
        1 for item in messages
        if (item.get("type") if isinstance(item, dict) else getattr(item, "type", None))
        == "function_call"
    )
    print(f"\033[90m[HOOK] Stop：本次会话调用了 {tool_count} 次工具\033[0m")
    return None

register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)


# -- 智能体循环：结构与 s03 相同，但不再写死权限检查 --
# s03：if not check_permission(tool_name, arguments): ...
# s04：if trigger_hooks("PreToolUse", tool_name, arguments): ...

def agent_loop(messages: list):
    while True:
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM,
            input=messages,
            tools=TOOLS,
            max_output_tokens=8000,
        )
        # 保留全部输出项，包括消息、推理项和函数调用，供下一轮完整回传。
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

            # s04 变化：用 Hook 替代写死的 check_permission()。
            # PreToolUse 必须先于处理函数执行。
            blocked = trigger_hooks("PreToolUse", tool_call.name, arguments)
            if blocked:
                messages.append({
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": str(blocked),
                })
                continue

            handler = TOOL_HANDLERS.get(tool_call.name)
            try:
                output = handler(**arguments) if handler else f"错误：未知工具 {tool_call.name}"
            except Exception as e:
                output = f"错误：{e}"

            trigger_hooks("PostToolUse", tool_call.name, arguments, output)

            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": str(output),
            })


if __name__ == "__main__":
    print("s04：Hook - 通过钩子扩展逻辑，保持循环简洁")
    print("输入问题后按回车发送，输入 q 或 exit 退出。\n")
    print(f"请求地址：{client.base_url}responses")

    history = []
    while True:
        try:
            query = input("\033[36ms04 >> \033[0m")
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
