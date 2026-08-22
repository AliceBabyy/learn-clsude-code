### 第6天：Hooks + TodoWrite

今天把`s04`和`s05`放在一起，但只围绕一个核心问题：

> 如何在不持续污染Agent Loop的情况下，增加日志、权限、收尾和任务计划等能力？

建议投入 **90分钟**。如果今天只有60分钟，完成Hooks部分即可，把TodoWrite顺延半天。

## 今日定位

### Hooks

- 所属层：Harness扩展机制
- 解决问题：权限、日志、监控等逻辑不断塞进Agent Loop
- 接入位置：输入提交、工具执行前后、循环停止前
- 重要程度：核心工程能力

### TodoWrite

- 所属层：规划和显式状态
- 解决问题：长任务执行中丢失目标、遗漏步骤
- 接入位置：作为普通工具注册，由模型主动更新
- 重要程度：重要增强

今天需要先纠正一个认识：

> `todo_write`不是规划算法，也不会自动完成任务。它只是Harness提供给模型的一块外部任务状态板。

## 今日可见成果

今天结束时应当看到：

1. 工具执行前出现Hook日志
2. 权限检查从硬编码函数变成`PreToolUse Hook`
3. 工具完成后触发`PostToolUse`
4. Agent停止前触发`Stop Hook`
5. Agent为复杂任务创建Todo列表并更新状态
6. 增加Hooks和Todo后，Agent Loop的核心结构仍然稳定

## 0～10分钟：先画扩展位置

先不看代码，画出：

```text
用户输入
→ UserPromptSubmit Hook
→ 调用模型
→ function_call
→ PreToolUse Hook
→ 工具执行
→ PostToolUse Hook
→ 回填结果
→ 再次调用模型
→ Stop Hook
→ 结束或继续
```

Hooks本身不等于日志或权限。它只是提供固定扩展点：

```text
Hook = 什么时候调用
Callback = 到时具体做什么
```

## 10～25分钟：阅读s04核心代码

阅读：

- `s04_hooks/README.zh.md`
- `s04_hooks/code.py`

只追踪：

```python
HOOKS
register_hook()
trigger_hooks()
permission_hook()
log_hook()
large_output_hook()
summary_hook()
```

以及四个触发位置：

```text
UserPromptSubmit
PreToolUse
PostToolUse
Stop
```

重点理解注册表：

```python
HOOKS = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": [],
}
```

它的数据结构本质是：

```text
事件名称 → 一组回调函数
```

### 注意Hook顺序

本地代码先注册：

```python
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
```

而`trigger_hooks()`遇到非`None`结果就立即返回。

因此，如果`permission_hook`拒绝操作，后面的`log_hook`可能不会运行。这说明：

> Hook注册顺序会影响行为，Hook系统并不天然保证所有回调都执行。

今天知道这个风险即可，不重构。

## 25～35分钟：阅读s05新增部分

不要从头阅读`s05/code.py`，只找：

```python
class TodoManager
run_todo_write()
TOOLS中的todo_write
TOOL_HANDLERS中的todo_write
rounds_since_todo
used_todo
reminder
```

梳理两个不同机制：

### Todo工具

```text
模型调用todo_write
→ TodoManager校验列表
→ 保存到内存
→ 返回当前任务状态
```

### Reminder机制

```text
连续三轮没有使用todo_write
→ Harness追加提醒
→ 模型看到提醒
→ 可能重新更新Todo
```

Todo状态不在`messages`里维护，而在：

```python
TODO = TodoManager()
```

工具返回的渲染结果会进入消息历史，但真正的当前Todo列表由`TODO.items`保存。

## 35～55分钟：迁移并整合OpenAI版本

`s04`和`s05`目前仍是Anthropic版本。今天不要迁移两个文件，只迁移最终包含二者的`s05`。

交给Codex：

```text
请把s05_todo_write/code.py迁移为OpenAI Responses API版本，
参考已经迁移好的s02_tool_use/code.py。

目标是保留s04 Hooks和s05 TodoWrite两套机制。

要求：

1. 使用OpenAI SDK、client.responses.create和项目现有三个
   OPENAI环境变量。
2. 使用function_call和function_call_output。
3. 使用json.loads解析tool_call.arguments。
4. 将全部response.output追加到messages。
5. 保留UserPromptSubmit、PreToolUse、PostToolUse、Stop四类Hook。
6. Hook不要依赖Anthropic block对象，改为接收tool_name和arguments；
   PostToolUse额外接收output。
7. 权限Hook必须在handler执行前运行。
8. 被Hook阻止时仍追加function_call_output，把拒绝原因返回模型。
9. 保留TodoManager、todo_write工具和rounds_since_todo提醒机制。
10. OpenAI版reminder使用普通user消息追加，不使用Anthropic text block。
11. 不新增工具，不重构TodoManager，不引入Hook类。
12. 所有面向人的注释、提示和错误信息使用中文。
13. 修改后运行py_compile。
```

## 55～65分钟：审查Diff

确认修改没有破坏以下主线：

```python
response = client.responses.create(...)
messages.extend(response.output)

tool_calls = [
    item for item in response.output
    if item.type == "function_call"
]

arguments = json.loads(tool_call.arguments)

blocked = trigger_hooks(
    "PreToolUse",
    tool_call.name,
    arguments,
)

if not blocked:
    output = handler(**arguments)
    trigger_hooks(
        "PostToolUse",
        tool_call.name,
        arguments,
        output,
    )

messages.append({
    "type": "function_call_output",
    "call_id": tool_call.call_id,
    "output": output,
})
```

重点检查：

- Hook位于工具执行前后正确的位置
- 被拒绝后没有执行handler
- Todo仍通过`TOOL_HANDLERS`分发
- Agent Loop没有直接调用`permission_hook`
- `call_id`正确回填

## 65～80分钟：运行实验

在临时目录运行`s05`。

### 实验1：观察完整Hook生命周期

```text
读取README.md的前10行，然后总结。
```

观察：

```text
UserPromptSubmit
→ PreToolUse
→ read_file
→ PostToolUse
→ Stop
```

注意：`large_output_hook`即使没有打印警告，也可能已经执行，只是输出不足10万字符。

### 实验2：观察计划状态

```text
请先使用todo_write制定计划，然后完成：
1. 创建plan_demo.txt
2. 写入hello plan
3. 读取并确认内容
每完成一步都更新Todo状态。
```

预期看到Todo状态变化：

```text
[>] 创建文件
[ ] 写入内容
[ ] 验证内容

[x] 创建文件
[>] 写入内容
[ ] 验证内容
```

模型不一定每次都严格更新，这是实验要观察的问题，不要为此反复调提示词。

### 实验3：观察权限Hook

```text
请调用bash执行sudo echo hello。
```

预期：

```text
PreToolUse
→ permission_hook返回拒绝原因
→ handler不执行
→ 拒绝结果返回模型
```

## 80～85分钟：增加一个最小Hook

今天的所有权动作：自行定义需求，让Codex添加一个计时Hook。

要求：

```text
增加一个PostToolUse Hook，打印：
- 工具名称
- 工具输出字符数

只增加一个回调和一次register_hook，
不要修改agent_loop和trigger_hooks。
```

预期效果：

```text
[HOOK] read_file输出1234个字符
```

这个实验用于证明：

> 增加横切能力时，只注册新的Hook，不需要修改Agent Loop。

## 85～90分钟：闭卷复述

```text
Hook解决的问题：
Hook注册表保存什么：
PreToolUse位于哪里：
PostToolUse位于哪里：
Hook为什么会影响控制流：
Hook注册顺序有什么风险：
Todo状态保存在哪里：
Todo为什么只是工具而不是规划算法：
Reminder由模型还是Harness触发：
```

## 验收标准

- 能画出四类Hook在循环中的位置
- 能解释`register_hook`和`trigger_hooks`
- 成功观察工具执行前后Hook
- Agent成功创建并至少更新一次Todo
- 新增一个Hook且没有修改Agent Loop
- 能区分Todo状态、消息历史和模型内部判断


今天最重要的两点：

> Hooks解决的是“在哪里扩展而不污染核心循环”。

> TodoWrite解决的是“把任务计划变成模型和Harness都能观察、更新的显式状态”。