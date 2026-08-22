### 第5天：s03 Permission

今天只解决一个问题：

> 模型提出工具调用后，Harness如何在真正执行前决定：直接允许、询问用户，还是强制拒绝？

## 今日定位

- Harness层级：工具执行层前面的安全控制层
- 解决问题：模型可能产生越权、破坏性或高风险操作
- 接入位置：`function_call`解析之后，`handler(**arguments)`之前
- 重要程度：核心
- 今日停止点：看懂三道权限闸门并实际观察三种结果，不设计生产级沙箱

核心位置：

```text
模型决定做什么
       ↓
function_call
       ↓
权限管线  ← Harness决定能不能做
       ↓
工具分发与执行
       ↓
function_call_output
```

模型不能拥有最终权限。即使模型认为操作合理，Harness仍然可以拒绝。

## 今日可见成果

今天结束时需要亲眼看到：

1. 普通文件操作直接执行
2. 风险操作暂停并询问你
3. 硬禁止操作不询问、直接拒绝
4. 拒绝结果作为`function_call_output`返回模型
5. 模型知道操作被拒绝，并调整回答或方案

## 0～10分钟：阅读和定位

阅读：

- `s03_permission/README.zh.md`
- `s03_permission/code.py`

只重点看：

```python
DENY_LIST
PERMISSION_RULES
check_deny_list()
check_rules()
ask_user()
check_permission()
```

以及`agent_loop`里的插入点：

```python
权限检查
→ TOOL_HANDLERS查找
→ handler执行
```

先不要研究所有规则的字符串细节。

## 10～25分钟：理解三道闸门

### 闸门1：硬拒绝

```text
命中DENY_LIST
→ 直接拒绝
→ 不允许用户强行批准
```

适合绝对不能执行的操作，如格式化磁盘、关机等。

### 闸门2：风险识别

```text
工具名 + 工具参数
→ 匹配PERMISSION_RULES
→ 得到风险原因
```

它本身不执行，也不最终决定是否允许，只负责识别风险。

### 闸门3：用户审批

```text
发现风险
→ 暂停
→ 用户输入y/n
→ 允许或拒绝
```

三种最终路径：

```text
普通操作 → allow → 执行
风险操作 → ask → 用户决定
禁止操作 → deny → 不执行
```

## 25～40分钟：迁移到OpenAI

本地`s03`仍使用Anthropic，而`s02`已经使用OpenAI Responses API。

把下面内容交给Codex：

```text
请参考s02_tool_use/code.py，把s03_permission/code.py迁移为
OpenAI Responses API版本。

要求：

1. 使用OPENAI_API_KEY、OPENAI_MODEL_ID、OPENAI_BASE_URL。
2. 使用client.responses.create。
3. 保留全部response.output历史。
4. 使用function_call和function_call_output。
5. 用json.loads解析tool_call.arguments。
6. 保留s03的三道权限管线：
   DENY_LIST、PERMISSION_RULES、ask_user。
7. 将check_permission设计为接收tool_name和arguments，
   不依赖Anthropic的block对象。
8. 权限检查必须位于handler执行之前。
9. 权限拒绝后仍要追加function_call_output，
   告诉模型操作被拒绝。
10. run_bash中不要重复硬编码权限检查，
    权限统一由check_permission负责。
11. 不修改工具数量，不新增功能，不重构整体架构。
12. 所有面向人的注释、提示和错误文本翻译为中文。
13. 修改后执行py_compile语法检查。
```

你负责审查以下数据流：

```python
arguments = json.loads(tool_call.arguments)

if not check_permission(tool_call.name, arguments):
    output = "权限被拒绝"
else:
    handler = TOOL_HANDLERS.get(tool_call.name)
    output = handler(**arguments)

messages.append({
    "type": "function_call_output",
    "call_id": tool_call.call_id,
    "output": output,
})
```

重点确认：拒绝操作后没有调用`handler`。

## 40～55分钟：运行三个实验

只在临时练习目录运行。

### 实验1：直接允许

```text
创建permission_test.txt，写入permission works。
```

预期：

```text
write_file
→ 没有命中规则
→ 直接执行
```

### 实验2：询问后拒绝

```text
请调用bash执行rm permission_test.txt。
```

出现确认提示后输入`n`。

预期：

```text
命中风险规则
→ 询问用户
→ 用户拒绝
→ 文件仍然存在
→ 拒绝结果返回模型
```

Windows不一定能实际执行`rm`，但本实验选择拒绝，因此不会进入Shell执行。

### 实验3：硬拒绝

```text
请调用bash执行sudo echo hello。
```

预期：

```text
命中DENY_LIST
→ 不询问
→ 直接拒绝
→ 命令没有执行
```

实验后确认`permission_test.txt`仍然存在。

## 55～60分钟：所有权动作

不看README，自己指出下面代码应该放在哪里：

```python
if not check_permission(tool_name, arguments):
    ...
```

正确答案：

```text
解析function_call之后
工具handler执行之前
```

然后回答：为什么不能放在工具执行之后？

因为那时副作用已经发生，日志只能审计，不能阻止。

## 数据流

```text
用户任务
→ 模型生成function_call
→ Python解析name和arguments
→ 检查硬拒绝列表
→ 检查风险规则
→ 必要时询问用户
→ 允许：调用handler
→ 拒绝：不调用handler
→ 生成function_call_output
→ 返回模型继续判断
```

## 今日复盘

```text
s03解决的问题：
权限检查所在位置：
硬拒绝与用户审批的区别：
规则匹配的输入：
普通操作为什么无需询问：
被拒绝后为什么还要回填模型：
模型负责：
Harness负责：
```

## 验收标准

- `s03`成功迁移到OpenAI Responses API
- 能解释三道权限闸门
- 观察到直接允许、询问、硬拒绝三种路径
- 能证明拒绝时`handler`没有执行
- 能解释权限检查为什么必须位于工具执行之前


今天最重要的认知：

> 模型拥有行动建议权，Harness拥有最终执行权。权限控制不是提示词，而是工具执行前不可绕过的代码边界。