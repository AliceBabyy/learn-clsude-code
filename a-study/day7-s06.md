### 第7天：s06 Subagent

今天只解决一个核心问题：

> 父Agent如何把一个子任务交给独立上下文处理，并且只接收最终结论，而不接收子任务的全部过程？

建议投入 **75～90分钟**。

## 今日定位

- 所属层：Harness委派层
- 解决问题：复杂探索产生大量中间消息，污染父Agent上下文
- 接入位置：Subagent被包装成父Agent的`task`工具
- 重要程度：核心增强
- 今日学习边界：理解单层、同步、共享工作区的Subagent

先建立顶层认识：

```text
父Agent
→ 调用task工具
→ Harness创建新的messages
→ 子Agent独立循环并使用工具
→ 子Agent返回最终文本
→ 最终文本作为task工具结果回到父Agent
```

Subagent不是另一个模型的必要同义词。它可以使用同一个模型，关键区别是：

> 它拥有独立的消息上下文和明确的子任务边界。

## 本地代码的实际情况

本地`s06`目前：

- 仍使用Anthropic API
- 包含两个Agent Loop
- 父Agent拥有`task`工具
- 子Agent没有`task`工具
- 父子共享`WORKDIR`、基础工具和Hooks
- 子Agent最多运行30轮
- 没有保留`s05`的TodoWrite

最后一点需要注意：这个章节重点隔离展示Subagent，不是完整累计所有前置能力。今天不要擅自把TodoWrite合并进来，完整组装留到`s15`。

## 今日可见成果

今天结束时应当看到：

1. 父Agent调用`task`
2. 终端显示子Agent开始和结束
3. 子Agent独立调用文件工具
4. 父消息历史只收到子Agent最终总结
5. 子Agent中间工具调用不进入父消息历史
6. 子Agent创建的文件能被父Agent看到

## 0～10分钟：先画边界

阅读`s06_subagent/README.zh.md`的：

- 问题
- 解决方案
- 实际边界
- 工作原理

然后自己填写：

| 资源 | 是否隔离 |
|---|---|
| `messages` | 是 |
| System Prompt | 是 |
| 工具集合 | 部分隔离 |
| 文件系统 | 否 |
| 进程 | 否 |
| 权限Hooks | 否，共享 |
| 模型 | 默认相同 |

今天最重要的区分：

```text
上下文隔离 ≠ 进程隔离
上下文隔离 ≠ 权限隔离
上下文隔离 ≠ 文件系统隔离
```

## 10～25分钟：只追踪新增代码

不要从头逐行读`code.py`，只看：

```python
SUB_SYSTEM
SUB_TOOLS
SUB_HANDLERS
run_subagent()
TASK_TOOL
TOOLS
TOOL_HANDLERS
```

重点观察两套工具集合：

```python
SUB_TOOLS = list(BASE_TOOLS)
```

子Agent只有基础工具。

```python
TOOLS = [*BASE_TOOLS, TASK_TOOL]
```

父Agent额外拥有`task`工具。

因此委派深度被限制为一层：

```text
父Agent可以调用task
子Agent找不到task
→ 子Agent不能继续递归委派
```

## 25～35分钟：追踪两层循环

### 父循环

```text
用户任务
→ 父模型调用task
→ TOOL_HANDLERS["task"]
→ run_subagent(prompt)
```

### 子循环

```text
创建全新messages
→ 调用模型
→ 执行基础工具
→ 回填工具结果
→ 继续循环
→ 得到最终文本
```

### 结果返回

```text
子Agent最终文本
→ run_subagent返回值
→ 父Agent的function_call_output
→ 父模型继续处理
```

父Agent不会获得：

- 子Agent每一轮的完整消息
- 子Agent读取的所有文件内容
- 子Agent每次工具调用结果

它只获得压缩后的最终结论。

## 35～55分钟：迁移OpenAI版本

只迁移`s06`，不要处理`s05`。

交给Codex：

```text
请将s06_subagent/code.py迁移为OpenAI Responses API版本，
参考已迁移的s02_tool_use/code.py。

必须保留本章的核心结构：

1. 父Agent拥有task工具。
2. 子Agent只拥有BASE_TOOLS，不允许再次调用task。
3. run_subagent必须创建全新的局部messages列表。
4. 父子共享WORKDIR、基础工具和Hooks。
5. 子Agent只向父Agent返回最终文本。
6. 子Agent最多运行30轮。

OpenAI迁移要求：

1. 使用OPENAI_API_KEY、OPENAI_MODEL_ID、OPENAI_BASE_URL。
2. 父循环和子循环都使用client.responses.create。
3. 使用function_call和function_call_output。
4. 使用json.loads解析arguments。
5. 每个循环分别保存自己的全部response.output。
6. 使用response.output_text获取最终文本。
7. Hook改为接收tool_name和arguments，不依赖Anthropic block。
8. 工具被拒绝时仍返回function_call_output。
9. OpenAI工具定义使用type、name、description和parameters。
10. 所有面向人的注释、终端提示和错误信息使用中文。
11. 不加入TodoWrite，不实现并发，不重构为通用Agent类。
12. 修改后运行py_compile。
```

## 55～65分钟：审查关键边界

检查下面四件事。

### 子消息必须是局部变量

```python
def run_subagent(prompt: str) -> str:
    messages = [
        {"role": "user", "content": prompt}
    ]
```

不能把父Agent的`history`直接传进来。

### 子工具不能包含task

```python
SUB_TOOLS = list(BASE_TOOLS)
```

不能写成：

```python
SUB_TOOLS = TOOLS
```

否则可能无限递归委派。

### task只注册给父Agent

```python
TOOL_HANDLERS = {
    **BASE_HANDLERS,
    "task": run_subagent,
}
```

### 父Agent只接收最终结果

父历史中应该出现：

```text
function_call：task
function_call_output：子Agent最终总结
```

不应该追加子Agent完整的`messages`。

## 65～80分钟：运行三个实验

在临时目录中运行。

### 实验1：独立探索

```text
请使用task子Agent比较s01_agent_loop/code.py和
s02_tool_use/code.py，只向我返回最重要的三个区别。
```

观察：

- 父Agent调用`task`
- 子Agent读取两个文件
- 子Agent内部可能有多次工具调用
- 父Agent最终只拿到三个区别

### 实验2：证明文件系统共享

```text
让子Agent创建subagent_demo.txt，内容为hello from subagent，
然后由父Agent读取该文件并确认内容。
```

预期：

```text
子Agent写文件
→ 子Agent结束
→ 父Agent读取同一个文件
```

证明隔离的是上下文，不是工作目录。

### 实验3：观察委派边界

```text
让task子Agent完成任务，并要求它再委派给另一个子Agent。
```

观察子Agent无法找到`task`工具。

不要求模型一定明确报错，重点检查：

```text
SUB_TOOLS中确实没有task
```

## 所有权动作：可视化上下文隔离

让Codex临时加入调试日志：

```text
1. 父Agent调用task前打印父messages长度。
2. 子Agent每轮打印自己的messages长度。
3. 子Agent结束后打印最终文本长度。
4. task返回后再次打印父messages长度。
5. 不打印消息正文，不改变运行逻辑。
```

你需要亲眼看到：

```text
父messages：较短
子messages：独立增长
子Agent结束
父messages：只增加task调用及最终结果
```

## 数据流

```text
父messages
→ 父模型选择task
→ task(prompt)
→ 创建子messages=[prompt]
→ 子模型调用基础工具
→ 子messages独立增长
→ 子模型生成最终文本
→ task返回最终文本
→ 父function_call_output
→ 父messages继续增长
→ 父模型生成最终回答
```

## 今日复盘

```text
Subagent解决的问题：
隔离的核心资源：
没有隔离的资源：
父Agent如何启动子Agent：
子Agent为什么不能继续委派：
子Agent中间过程去了哪里：
父Agent最终收到什么：
为什么Subagent可以减少父上下文污染：
```

## 验收标准

- `s06`成功迁移到OpenAI Responses API
- 能解释父循环和子循环的关系
- 能证明父子`messages`不是同一个列表
- 能证明父子共享文件系统
- 能解释为什么子Agent没有`task`
- 父Agent只接收到子Agent的最终文本

## 今天不要做

- 不实现并行Subagent
- 不实现多个角色Agent
- 不学习Agent Team
- 不给子Agent复制父历史
- 不为父子配置不同模型
- 不加入TodoWrite
- 不实现进程或容器隔离
- 不抽象通用Agent基类
- 不讨论复杂任务调度

今天最重要的认知：

> Subagent的核心不是“多调用一次LLM”，而是用独立上下文处理一个边界清晰的子任务，再把压缩后的结果交回父Agent。