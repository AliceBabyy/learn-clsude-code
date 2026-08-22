```text
s2课程任务
试试这些 prompt：

1. `Read the file README.md and tell me what this project is about`
2. `Create a file called test.py that prints "hello", then read it back`
3. `Find all Python files in this directory`
4. `Read both README.md and requirements.txt, then create a summary file`

观察重点：模型什么时候只调一个工具，什么时候一次调多个？多个工具调用的顺序和结果是否正确？
```

第三天进入 `s02 Tool Use`。今天只解决一个核心问题：

> Agent有多个工具时，模型如何选择工具，Harness又如何找到并执行正确的Python函数？


## 今日成果

完成后你应该能解释：

```text
工具定义TOOLS
→ 告诉模型有哪些能力、需要什么参数

模型返回function_call
→ 选择工具并生成参数

TOOL_HANDLERS
→ 根据工具名找到Python函数

handler(**arguments)
→ 执行函数并返回结果
```

## 0～10分钟：确定s02的定位

先读`s02_tool_use/README.zh.md`，重点看：

- 只有bash一个工具的问题
- 全局视角：工具分发
- 从1个工具到5个工具
- 工具分发
- 相对s01的变更

暂时跳过细节代码。

用一句话记住s02：

> s01解决“如何循环”，s02解决“如何扩展和分发能力”。

## 10～20分钟：把s02切换到OpenAI

本地`s02/code.py`仍然使用Anthropic API。让Codex参考已经改好的`s01`，完成协议替换。

可以直接给Codex这个要求：

```text
参考s01_agent_loop/code.py，把s02_tool_use/code.py从Anthropic改成
OpenAI Responses API。

要求：
1. 保留s02的五个工具和TOOL_HANDLERS分发结构。
2. 使用OPENAI_API_KEY、OPENAI_MODEL_ID和OPENAI_BASE_URL。
3. 使用function_call和function_call_output回填结果。
4. 保留完整response.output历史。
5. 所有面向人的注释、提示和错误信息改成中文。
6. 不重构其他逻辑。
7. 修改后执行语法检查。
```

不要让Codex重新设计整个文件。你需要检查`s01`中的以下结构是否被正确迁移：

- `client.responses.create`
- `instructions`
- `input=messages`
- `messages.extend(response.output)`
- `item.type == "function_call"`
- `function_call_output`
- `call_id`

## 20～35分钟：理解工具的三层结构

以`read_file`为例追踪。

### 第一层：工具定义

```python
{
    "type": "function",
    "name": "read_file",
    "description": "读取文件内容",
    "parameters": {
        ...
    }
}
```

作用：告诉模型工具叫什么、能做什么、参数是什么。

这不是工具实现，只是一份能力说明书。

### 第二层：工具实现

```python
def run_read(path: str, limit: int | None = None) -> str:
    ...
```

作用：真正读取文件。模型不会执行这段代码，是Harness执行。

### 第三层：工具注册

```python
TOOL_HANDLERS = {
    "read_file": run_read,
}
```

作用：把模型知道的工具名称映射到Python函数。

完整链路：

```text
模型选择read_file
→ 返回name="read_file"和arguments
→ TOOL_HANDLERS["read_file"]
→ 得到run_read函数
→ run_read(**arguments)
```

## 35～50分钟：运行并观察工具选择

在临时练习目录运行，不要对重要项目测试。

依次尝试：

```text
找出当前目录下所有Python文件。
```

观察是否调用`glob`。

```text
创建hello.py，内容为print("hello")，然后读取它。
```

观察是否调用`write_file`和`read_file`。

```text
把hello.py中的hello改成hello agent，然后读取确认。
```

观察是否调用`edit_file`和`read_file`。

记录：

```text
任务：
模型选择的工具：
模型生成的参数：
最终执行的Python函数：
工具返回结果：
```

重点不是模型是否每次都按你预期选工具，而是你能否追踪它最终选择了什么。

## 50～60分钟：理解safe_path

`s02`新增了：

```python
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(...)
    return path
```

亲自验证：

```text
读取../某个文件
```

预期文件工具拒绝访问工作目录外的路径。

你需要理解：

- `resolve()`消除`..`等路径跳转
- `is_relative_to(WORKDIR)`检查最终路径是否仍在工作区
- 保护的是`read_file/write_file/edit_file`
- `bash`仍然可能绕过该限制
- 完整权限控制要到`s03`

## 今日复盘

```text
s02解决的问题：
工具定义的作用：
工具实现的作用：
TOOL_HANDLERS的作用：
模型负责选择什么：
Harness负责执行什么：
safe_path保护了什么：
safe_path没有保护什么：
```

## 今日验收

今天完成以下内容即可：

- 将`s02`切换为OpenAI Responses API
- 能追踪一个工具从定义到执行的全过程
- 实际观察至少三种工具被调用
- 验证路径越界会被文件工具拒绝
- 理解Agent Loop本身没有因为工具数量增加而改变

今天最重要的认知是：

> 增加Agent能力，不应该不断修改Agent Loop；应该新增工具定义、工具实现和注册映射。