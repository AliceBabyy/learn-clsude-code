第四天不学新章节，专门实践`s02`：

> 独立设计并接入第六个工具，验证扩展工具时Agent Loop不需要修改。

今天推荐实现`file_stats`工具：读取指定文本文件，返回行数、单词数和字符数。难度适中，能复用`safe_path`，效果也容易验证。

## 0～10分钟：先设计，不写代码

先写清楚工具契约：

```text
工具名称：file_stats
用途：统计文本文件的行数、单词数和字符数
输入：path，字符串，必填
输出：包含path、lines、words、characters
失败：文件不存在、路径越界、无法读取时返回错误
```

验收标准：

```text
给定一个内容已知的文本文件
→ Agent选择file_stats
→ 参数包含正确路径
→ 结果中的统计数字正确
→ Agent用自然语言回答用户
```

## 10～25分钟：让Codex实现

给Codex一个边界明确的要求：

```text
在s02_tool_use/code.py中增加file_stats工具。

要求：
1. 新增run_file_stats(path: str)函数。
2. 必须通过safe_path限制文件路径。
3. 返回JSON字符串，包含path、lines、words、characters。
4. 在TOOLS中增加OpenAI function工具定义。
5. 在TOOL_HANDLERS中注册file_stats。
6. 不修改agent_loop。
7. 不修改现有五个工具。
8. 所有面向人的注释和错误信息使用中文。
9. 完成后执行语法检查。
```

注意：不要直接接受结果，先看diff。

## 25～35分钟：审查改动

确认Codex只修改了三个位置：

```text
1. 工具实现：run_file_stats
2. 工具说明：TOOLS
3. 工具注册：TOOL_HANDLERS
```

重点检查：

- 工具名是否三处一致：`file_stats`
- 参数名是否都是`path`
- JSON Schema是否声明`path`必填
- 是否设置`additionalProperties: False`
- 是否经过`safe_path`
- 返回值是否为字符串
- `agent_loop`是否完全没改

完整链路应该是：

```text
TOOLS中的file_stats
→ 模型生成function_call
→ TOOL_HANDLERS["file_stats"]
→ run_file_stats(**arguments)
→ function_call_output
→ 模型生成最终回答
```

## 35～50分钟：运行验证

在临时目录创建文件：

```text
agent_day4.txt
```

内容：

```text
hello agent
tool calling works
```

然后向Agent提问：

```text
请使用file_stats工具统计agent_day4.txt，不要使用bash。
```

观察：

- `response.output`中是否出现`function_call`
- `name`是否为`file_stats`
- `arguments`是否包含正确的`path`
- Harness是否找到`run_file_stats`
- 最终统计是否正确

再测试失败场景：

```text
统计一个不存在的文件missing.txt
```

```text
统计工作目录外的../test.txt
```

预期：返回明确错误，程序不崩溃。

## 50～55分钟：测试工具描述的重要性

先把工具描述故意改模糊：

```text
"处理文件"
```

询问：

```text
agent_day4.txt有多少行？
```

观察模型是否可能选择`read_file`或`bash`。

再改成明确描述：

```text
统计文本文件的行数、单词数和字符数。当用户询问文件大小或文本统计信息时使用。
```

重新提问，观察选择是否更稳定。

需要理解：

> Tool Calling不是程序按照工具名关键词匹配；模型根据工具名称、描述和参数Schema判断是否使用。

## 55～60分钟：闭卷复述

填写：

```text
我新增的工具：
它解决的问题：
工具定义在哪里：
工具实现在哪里：
工具注册在哪里：
模型如何知道它存在：
Harness如何找到实现：
失败如何返回模型：
为什么Agent Loop不用修改：
```

## 今日验收

完成以下内容即可：

- 新增`file_stats`
- 成功调用一次
- 验证不存在文件和路径越界
- 比较模糊与准确工具描述的效果
- 确认Agent Loop没有修改

今天不要做：

- 不进入`s03`
- 不抽象工具基类
- 不自动生成Schema
- 不新增多个工具
- 不做并行调用
- 不追求完整测试框架

今天最重要的收获应当是：

> Agent的能力边界由工具集合决定。扩展能力时增加“契约、实现、注册”，而不是改动核心循环。