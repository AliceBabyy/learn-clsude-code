#!/usr/bin/env python3
"""
s05_todo_write.py - 待办事项管理

模型通过 TodoManager 跟踪任务进度。连续三轮没有更新待办事项时，
Harness 会在工具结果之后追加一条提醒消息。

    +----------+      +-------+      +--------------+
    |   用户   | ---> |  LLM  | ---> | 工具         |
    |   提示   |      |       |      | + todo_write |
    +----------+      +---^---+      +------+-------+
                          |                 | 更新
                          |          +------v----------+
                          |          | TodoManager     |
                          |          | [ ] 待处理      |
                          |          | [>] 进行中      |
                          |          | [x] 已完成      |
                          |          +------+----------+
                          | 工具结果        |
                          +-----------------+

              rounds_since_todo >= 3 -> 追加 <reminder>
"""

import ast
import json
import os
import subprocess
from pathlib import Path

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
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

# s05 变化：系统提示中增加规划要求
SYSTEM = (
    f"你是位于 {WORKDIR} 的编程智能体。"
    "开始任何多步骤任务前，先使用 todo_write 规划步骤。"
    "执行过程中及时更新任务状态。"
)


# -- 来自 s02-s04 的工具实现 --

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


# -- s05 新增：由模型更新的结构化状态 --

class TodoManager:
    def __init__(self):
        self.items: list[dict] = []

    def update(self, todos: list | str) -> str:
        if isinstance(todos, str):
            try:
                todos = json.loads(todos)
            except json.JSONDecodeError:
                try:
                    todos = ast.literal_eval(todos)
                except (SyntaxError, ValueError) as e:
                    raise ValueError("todos 必须是列表或 JSON 数组字符串") from e

        if not isinstance(todos, list):
            raise ValueError("todos 必须是列表")
        if len(todos) > 20:
            raise ValueError("最多允许 20 个待办事项")

        validated = []
        in_progress_count = 0
        for index, todo in enumerate(todos):
            if not isinstance(todo, dict):
                raise ValueError(f"todos[{index}] 必须是对象")

            content = str(todo.get("content", "")).strip()
            status = str(todo.get("status", "pending")).lower()
            if not content:
                raise ValueError(f"todos[{index}] 缺少 content")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"todos[{index}] 的状态 '{status}' 无效")
            if status == "in_progress":
                in_progress_count += 1
            validated.append({"content": content, "status": status})

        if in_progress_count > 1:
            raise ValueError("同一时间只能有一个待办事项处于进行中")

        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "没有待办事项。"

        lines = []
        for todo in self.items:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }[todo["status"]]
            lines.append(f"{marker} {todo['content']}")

        done = sum(todo["status"] == "completed" for todo in self.items)
        lines.append(f"\n（已完成 {done}/{len(self.items)}）")
        return "\n".join(lines)


TODO = TodoManager()


def run_todo_write(todos: list | str) -> str:
    try:
        output = TODO.update(todos)
    except ValueError as e:
        return f"错误：{e}"
    print(f"\n\033[33m## 当前任务\033[0m\n{output}")
    return output

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
    # s05：新增工具
    {"type": "function", "name": "todo_write", "description": "创建并管理当前编程会话的任务列表。",
     "parameters": {"type": "object", "properties": {"todos": {"type": "array", "maxItems": 20, "items": {"type": "object", "properties": {"content": {"type": "string", "minLength": 1}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["content", "status"]}}}, "required": ["todos"]}},
]

TOOL_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_glob, "todo_write": run_todo_write,
}


# -- 来自 s04 的 Hook 系统 --

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
    """PreToolUse：将 s03 权限逻辑注册为 s04 Hook。"""
    if tool_name == "bash":
        command = arguments.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                print(f"\n\033[31m[已阻止] '{pattern}'\033[0m")
                return "权限拒绝：命令命中禁止列表"
        for keyword in DESTRUCTIVE:
            if keyword in command:
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

def context_inject_hook(query: str):
    """UserPromptSubmit：记录当前工作目录。"""
    print(f"\033[90m[HOOK] UserPromptSubmit：当前工作目录为 {WORKDIR}\033[0m")
    return None

def summary_hook(messages: list):
    """Stop：打印本次会话的工具调用次数。"""
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


# -- 带待办事项提醒计数器的智能体循环 --

def agent_loop(messages: list):
    rounds_since_todo = 0
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

        used_todo = False
        for tool_call in tool_calls:
            arguments = json.loads(tool_call.arguments)

            # 权限和其他 PreToolUse Hook 必须先于处理函数执行。
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

            if tool_call.name == "todo_write":
                used_todo = True

            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": str(output),
            })

        rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
        if rounds_since_todo >= 3:
            messages.append({
                "role": "user",
                "content": "<reminder>请更新待办事项。</reminder>",
            })
            rounds_since_todo = 0


if __name__ == "__main__":
    print("s05：待办事项管理 - 执行前先规划")
    print("输入问题后按回车发送，输入 q 或 exit 退出。\n")
    print(f"请求地址：{client.base_url}responses")

    history = []
    while True:
        try:
            query = input("\033[36ms05 >> \033[0m")
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
