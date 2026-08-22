#!/usr/bin/env python3
"""
s03_permission.py - 权限系统

在工具执行前依次经过三道权限检查：

    第一道：硬拒绝列表（rm -rf /、sudo 等）
    第二道：规则匹配（访问工作区外？破坏性命令？）
    第三道：用户批准（暂停并等待确认）

基于 s02（多工具）。用法：

    python s03_permission/code.py
    依赖：pip install openai python-dotenv，并在 .env 中配置 OpenAI 环境变量
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

SYSTEM = f"你是位于 {WORKDIR} 的编程智能体。所有破坏性操作都需要用户批准。"


# -- 来自 s02：工具实现 --

def run_bash(command: str) -> str:
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
    import glob as g
    try:
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "（没有匹配项）"
    except Exception as e:
        return f"错误：{e}"


# -- 来自 s02（保持不变）：工具定义和分发 --

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


# -- s03 新增：三道权限管线 --

# 第一道：硬拒绝列表，始终禁止
DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/sda"]


def check_deny_list(command: str) -> str | None:
    for pattern in DENY_LIST:
        if pattern in command:
            return f"已拦截：'{pattern}' 位于拒绝列表中"
    return None


# 第二道：规则匹配，根据上下文检查
PERMISSION_RULES = [
    {"tools": ["read_file", "write_file", "edit_file"],
     "check": lambda args: not (WORKDIR / args.get("path", "")).resolve().is_relative_to(WORKDIR),
     "message": "访问工作区外的文件"},
    {"tools": ["bash"],
     "check": lambda args: any(kw in args.get("command", "") for kw in ["rm ", "> /etc/", "chmod 777"]),
     "message": "可能具有破坏性的命令"},
]


def check_rules(tool_name: str, args: dict) -> str | None:
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    return None


# 第三道：用户批准，规则匹配后等待确认
def ask_user(tool_name: str, args: dict, reason: str) -> str:
    print(f"\n\033[33m[权限] {reason}\033[0m")
    print(f"   工具：{tool_name}({args})")
    choice = input("   是否允许？[y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


# 权限管线：依次串联三道检查
def check_permission(tool_name: str, arguments: dict) -> bool:
    if tool_name == "bash":
        reason = check_deny_list(arguments.get("command", ""))
        if reason:
            print(f"\n\033[31m[已拦截] {reason}\033[0m")
            return False
    reason = check_rules(tool_name, arguments)
    if reason:
        decision = ask_user(tool_name, arguments, reason)
        if decision == "deny":
            return False
    return True


# -- 智能体循环：与 s02 相同，并插入 check_permission() --

def agent_loop(messages: list):
    while True:
        response = client.responses.create(
            model=MODEL, instructions=SYSTEM, input=messages,
            tools=TOOLS, max_output_tokens=8000,
        )
        # 保留全部输出项，包括消息、推理项和函数调用，供下一轮完整回传。
        messages.extend(response.output)

        tool_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        if not tool_calls:
            return response.output_text

        for tool_call in tool_calls:
            print(f"\033[36m> {tool_call.name}\033[0m")
            arguments = json.loads(tool_call.arguments)

            # s03 变更：执行工具前先经过权限管线
            if not check_permission(tool_call.name, arguments):
                messages.append({
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": "权限被拒绝，操作未执行。",
                })
                continue

            handler = TOOL_HANDLERS.get(tool_call.name)
            output = handler(**arguments) if handler else f"错误：未知工具 {tool_call.name}"
            print(str(output)[:200])
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": output,
            })


if __name__ == "__main__":
    print("s03：权限系统")
    print("输入问题后按回车发送，输入 q 或 exit 退出。\n")
    print(f"请求地址：{client.base_url}responses")

    history = []
    while True:
        try:
            query = input("\033[36ms03 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        final_text = agent_loop(history)
        if final_text:
            print(final_text)
        print()
