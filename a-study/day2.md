第二天仍然不进入 `s02`。今天要把昨天“能运行”的 `s01` 变成“能看清内部数据流”。

> 今日目标：观察每一轮 `history` 和 `response.output` 如何变化，真正理解 Agent Loop 为什么能连续行动。

用时约 60 分钟。

## 0～10 分钟：闭卷回忆

不要看代码，先画出：

```text
用户输入
→ history
→ Responses API
→ response.output
→ function_call
→ 本地执行bash
→ function_call_output
→ history
→ 再次调用模型
→ 最终文本
```

然后回答：

1. 模型是否亲自执行了命令？
2. `function_call`是谁生成的？
3. `function_call_output`是谁生成的？
4. 为什么二者必须使用同一个`call_id`？
5. 模型不再返回`function_call`时会发生什么？

不会的先标记，今天通过运行结果解决。

## 10～25 分钟：认识三种核心数据

打开 `s01_agent_loop/code.py`，只追踪：

### 用户消息

```python
{"role": "user", "content": query}
```

它是任务的起点。

### 模型工具调用

模型可能在`response.output`中返回：

```text
type = function_call
name = bash
arguments = {"command": "..."}
call_id = ...
```

模型只是在提出调用请求，没有执行命令。

### 工具调用结果

Harness执行命令后追加：

```python
{
    "type": "function_call_output",
    "call_id": tool_call.call_id,
    "output": output,
}
```

`call_id`将结果与原来的工具请求对应起来。

## 25～45 分钟：让循环可视化

让 Codex帮你增加临时调试输出，但你要明确提出需求：

```text
给agent_loop增加轮次计数。
每次请求模型前，打印当前轮次和history长度。
模型返回后，打印response.output中每个item的type。
不要改变Agent Loop的行为。
```

你需要审查修改，确认日志分别位于：

- 模型调用之前
- 模型响应之后
- 工具执行前后

然后运行这个任务：

```text
查看当前目录，创建一个day2.txt写入当前目录的文件数量，
然后读取day2.txt并告诉我结果。
```

注意观察模型是否一次调用多个工具，还是经过多轮逐步调用。

预期会看到类似：

```text
第1轮：history长度=1
返回：function_call
执行：查看目录

第2轮：history长度=3
返回：function_call
执行：写入文件

第3轮：history长度=5
返回：function_call
执行：读取文件

第4轮：
返回：message
循环结束
```

实际轮数可能不同，由模型决定。

## 45～55 分钟：增加循环上限

当前代码存在一个问题：如果模型一直调用工具，`while True`可能无限持续。

让 Codex增加：

```python
MAX_ROUNDS = 10
```

达到上限时：

- 停止循环
- 返回明确的中文提示
- 不再调用模型或工具

你需要理解：

> 模型决定正常停止，Harness负责强制安全停止。

这是后面权限、预算和目标循环的基础。

## 55～60 分钟：今日复盘

只写下面内容：

```text
history中会出现哪些类型的数据：
response.output可能包含什么：
call_id的作用：
一轮循环的边界：
正常停止条件：
强制停止条件：
今天亲眼观察到的轮数：
仍然不懂的问题：
```

## 今日验收

完成以下四项就结束：

- 能画出工具调用和结果回填链路
- 看到了真实`response.output`中的类型
- 增加了轮次和历史长度日志
- 增加了最大循环次数

今天不学：

- `s02`
- 多工具注册
- JSON Schema细节
- 权限规则
- 上下文压缩
- SDK的所有响应类型

今天的可见成果是：你能够像观察程序调用栈一样，看到 Agent每一轮发生了什么，并且Harness已经不会无限循环。