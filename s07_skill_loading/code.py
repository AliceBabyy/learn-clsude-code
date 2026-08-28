#!/usr/bin/env python3
"""
s07_skill_loading.py - 技能加载

系统提示词包含技能名称和描述的目录。
只有当模型调用 load_skill 时，才会加载完整的 SKILL.md。

    skills/                    启动
    +------------------+       +------------------+
    | code-review/     | ----> | SkillLoader      |
    |   SKILL.md       |       | 名称 + 摘要      |
    | pdf/             |       +--------+---------+
    |   SKILL.md       |                |
    +------------------+                v
                                 系统提示词目录

    LLM -- load_skill(name) --> 完整 SKILL.md
     ^                              |
     +---------- 工具结果 ----------+
"""

import json
import os
import subprocess
from pathlib import Path

import yaml

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

WORKDIR = Path.cwd() #返回当前运行程序所在的工作目录路径
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or None,
)
MODEL = os.getenv("OPENAI_MODEL_ID")
if not MODEL:
    raise RuntimeError("缺少 OPENAI_MODEL_ID，请在项目根目录的 .env 中配置模型名称")

# / 是你做了运算符重载，作用是连接路径；这一句表示SKILLS_DIR保存了当前目录下的skills文件夹
SKILLS_DIR = WORKDIR / "skills" #技能目录
# -- 正文 --
# ------------------------------------------------------------------------------
# -- skils 技能目录 --

class SkillLoader:
    # 初始化参数：
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills: dict[str, dict[str, str]] = {}
        self.scan()

    # --- 方法1 ：作用是处理单个 SKILLS.md文档，把一个skills文档的yaml和文本分开并分别处理干净，分别作为一个完整的字符串return
    # 接收参数text：来源于scan的调用，传入content，内容是skills.md文档的内容，字符串
    @staticmethod # 静态方法：可以直接通过类名调用；静态方法不可访问类的self属性
    # 该函数核心作用是把 SKLLS.md 文档的 yaml 内容和正文内容分开
    def parse_frontmatter(text: str) -> tuple[dict, str]:
        # line: 列表；内容是SKILLS.md文档，每行为一个列表元素
        lines = text.splitlines(keepends=True) # .splitlines为字符串方法，将字符串按照换行符拆成一个列表
        if not lines or lines[0].rstrip("\r\n") != "---":
            return {}, text

        # next() 是跟迭代器适配方法，可以从迭代器中迭代逐个取值
        # closing_index 记录的是SKILLS.md文档中第二个 --- 出现的行数，以定位yaml内容
        closing_index = next(
            # enumerate 用于遍历列表的同时把索引取出来，返回一个元组(索引，值)；索引从0开始
            # 这个列表生成式：最终返回一个
            (index for index, line in enumerate(lines[1:], start=1) if line.rstrip("\r\n") == "---"),
            None,
        )
        if closing_index is None:
            return {}, text

        frontmatter = "".join(lines[1:closing_index])
        body = "".join(lines[closing_index + 1:]).strip()
        try:
            metadata = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}

        # 返回内容为：yaml，正文内容
        # metadata 为字典，内容是yaml；body是正文内容，是一整个字符串
        return metadata, body

    # --- 方法2 ：遍历、处理所有skills文档，完成给self.skills的赋值
    # self.skills赋值后是字典，存有skills文档的名称、简介、正文
    def scan(self):
        self.skills.clear()
        if not self.skills_dir.exists():
            return

        # 该循环核心作用：遍历所有 SKILLS.md 文件，将所有skill的名称name、简介description、全文content处理干净后，都弄成一个完整的字符串作为value，后存进 self.skills 字典
        # 所以scan方法不返回任何东西，核心作用是可以调用其属性skills
        # resolve是Path的方法，作用是把相对路径转化为绝对路径，同时去掉多余部分
        skills_root = self.skills_dir.resolve()
        # .glob是Path的对象方法；在这里作用是找到skills_dir路径下所有直接子目录的内容，找有名字是SKILL.md的文件，返回一个生成器
        for manifest in sorted(self.skills_dir.glob("*/SKILL.md")):
            # 遍历skills_dir目录下所有SKILL.md文档
            if (not manifest.is_file() #.is_file()是Path方法，用于判断该文件是否是一个普通文件
                    or not manifest.resolve().is_relative_to(skills_root)):
                continue
            content = manifest.read_text(encoding="utf-8") # read_text()是Path方法，用于读取整个文件内容，返回一个字符串
            # 调用parse_frontmatter方法，把skills文档yaml配置参数和正文内容分开获取
            metadata, body = self.parse_frontmatter(content) # metadata 为字典，内容为yaml；body为字符串，内容是skills正文
            raw_name = metadata.get("name") # skills文档的name
            name = raw_name.strip() if isinstance(raw_name, str) else "" #如果raw_name是字符串，就去首尾空格；如果不是，就赋为空
            name = name or manifest.parent.name # .parent为Path的属性，用于取当前路径的父目录；.name 是Path的属性，用于取路径最后一部分名字
            raw_description = metadata.get("description")
            description = (raw_description.strip()
                           if isinstance(raw_description, str) else "")
            description = description or body.split("\n", 1)[0]
            description = " ".join(str(description).lstrip("# ").split())
            self.skills[name] = {
                "name": name,
                "description": description,
                "content": content,
            }
        # self.skills被赋值后最后可能呈现这个样子：
        # {
        #     name1: {name:skill1, description: description1, content: content1},
        #     name2: {name: skill2, description: description2, content: content2},
        #     name3: {name: skill3, description: description3, content: content3},
        #     ... ...
        # }

    # --- 方法3 ：生成skills技能目录
    def catalog(self) -> str:
        if not self.skills:
            return "（未发现技能）"
        return "\n".join(
            f"- {skill['name']}: {skill['description']}" for skill in self.skills.values()
        )
    # 输出类似这样：
    # - code - review: 执行完整的代码审查
    # - pdf: 处理PDF文件


    # --- 方法4 ：按skill名字加载完整技能
    # 接收参数，要找的技能名字 name；返回内容，该 skill 的 content
    def load(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill:
            return skill["content"]
        available = ", ".join(self.skills) or "无"
        return f"错误：未知技能“{name}”。可用技能：{available}"

# 初始化一个 SKILL_LOADER 类的对象
SKILL_LOADER = SkillLoader(SKILLS_DIR)

# ------------------------------------------------------------------------------
# 提示词

def build_system_prompt() -> str:
    return (
        f"你是位于 {WORKDIR} 的编程智能体。使用工具解决任务。"
        "直接行动，不要只解释。\n\n"
        f"可用技能：\n{SKILL_LOADER.catalog()}\n\n"
        "当某个技能适用时，使用 load_skill 读取完整说明。"
    )


SYSTEM = build_system_prompt()

# ------------------------------------------------------------------------------
# -- 工具 --

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
        lines = (WORKDIR / path).resolve().read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"...（还有 {len(lines) - limit} 行）"]
        return "\n".join(lines)
    except Exception as e:
        return f"错误：{e}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = (WORKDIR / path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"已向 {path} 写入 {len(content)} 字节"
    except Exception as e:
        return f"错误：{e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = (WORKDIR / path).resolve()
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"错误：在 {path} 中未找到指定文本"
        file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
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
    {"type": "function", "name": "load_skill", "description": "按技能名称加载完整的 SKILL.md 内容。",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
]

TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
    "load_skill": SKILL_LOADER.load, # 将skill注册为工具
}

# ------------------------------------------------------------------------------
# -- 钩子 --

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
    """PreToolUse：拦截禁止的操作，并询问是否允许有风险的操作。"""
    if tool_name == "bash":
        command = arguments.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                print(f"\n\033[31m[已拦截]“{pattern}”\033[0m")
                return "权限被拒绝：命令命中禁止列表"
        for keyword in DESTRUCTIVE:
            if keyword in command:
                print("\n\033[33m[权限] 检测到可能具有破坏性的命令\033[0m")
                print(f"   工具：{tool_name}({arguments})")
                choice = input("   是否允许？[y/N] ").strip().lower()
                if choice not in ("y", "yes"):
                    return "权限被拒绝：用户未允许该操作"

    if tool_name in ("read_file", "write_file", "edit_file"):
        path = arguments.get("path", "")
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            print("\n\033[33m[权限] 请求访问工作区之外的路径\033[0m")
            print(f"   工具：{tool_name}({arguments})")
            choice = input("   是否允许？[y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限被拒绝：用户未允许该操作"
    return None


def log_hook(tool_name: str, arguments: dict):
    """PreToolUse：记录每次工具调用。"""
    args_preview = str(list(arguments.values())[:2])[:60]
    print(f"\033[90m[钩子] {tool_name}({args_preview})\033[0m")
    return None


def large_output_hook(tool_name: str, arguments: dict, output):
    """PostToolUse：在工具输出过大时发出警告。"""
    if len(str(output)) > 100000:
        print(f"\033[33m[钩子] {tool_name} 输出过大：{len(str(output))} 个字符\033[0m")
    return None


def context_inject_hook(query: str):
    """UserPromptSubmit：记录当前工作目录。"""
    print(f"\033[90m[钩子] 用户提交提示：当前工作目录为 {WORKDIR}\033[0m")
    return None


def summary_hook(messages: list):
    """Stop：打印当前消息列表中的工具结果数量。"""
    tool_count = sum(
        1
        for item in messages
        if isinstance(item, dict)
        and item.get("type") == "function_call_output"
    )
    print(f"\033[90m[钩子] 停止：本次会话使用了 {tool_count} 次工具调用\033[0m")
    return None


register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)

# ------------------------------------------------------------------------------

# skill也是被定义并注册为工具，共同跟工具使用execute_tool方法调用
def execute_tool(tool_name: str, arguments: dict) -> str:
    blocked = trigger_hooks("PreToolUse", tool_name, arguments)
    if blocked:
        return str(blocked)

    handler = TOOL_HANDLERS.get(tool_name)
    try:
        output = handler(**arguments) if handler else f"错误：未知工具 {tool_name}"
    except Exception as e:
        output = f"错误：{e}"

    if tool_name == "load_skill":
        print(f"已加载技能“{arguments.get('name', '')}”，返回 {len(str(output))} 个字符")
    trigger_hooks("PostToolUse", tool_name, arguments, output)
    return str(output)

# ------------------------------------------------------------------------------

def agent_loop(messages: list):
    while True:
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM,
            input=messages,
            tools=TOOLS,
            max_output_tokens=8000,
        )
        # 保留消息、推理项和函数调用等全部输出，供下一轮完整回传。
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
            output = execute_tool(tool_call.name, arguments)
            # 权限拒绝也作为函数调用结果回填，使模型能够继续处理。
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": output,
            })


if __name__ == "__main__":
    print("s07：技能加载 - 先提供目录，按需加载完整内容")
    print("输入问题后按回车发送，输入 q 或 exit 退出。\n")
    skill_names = ", ".join(SKILL_LOADER.skills) or "无"
    print(f"已发现 {len(SKILL_LOADER.skills)} 个技能：{skill_names}")
    print(f"请求地址：{client.base_url}responses")

    history = []
    while True:
        try:
            query = input("\033[36ms07 >> \033[0m")
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
