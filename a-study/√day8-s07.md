### 第8天：s07 Skill Loading

今天只解决一个核心问题：

> Agent如何只常驻技能的名称和描述，并在任务真正需要时才把完整说明加载进上下文？

建议投入 **90分钟**。其中API迁移只是受控工程任务，不能掩盖“技能按需加载”这条主线。

### 今日定位

- 所属层：Harness的知识与能力按需加载层
- 解决的失败场景：把所有规范全文塞进system prompt，导致无关内容长期占用上下文和Token
- 接入位置：启动时扫描技能目录并组装catalog；运行中把`load_skill`作为普通工具接入Agent Loop
- 重要程度：增强，但它是Agent规模化管理知识的重要基础
- 今天停止位置：理解“发现”和“加载”两阶段，能追踪完整数据流并验证成功、失败场景；不深挖YAML解析器、Token精确计算和Skill自动执行

本地代码与前几天有一个协议差异：

> `s07_skill_loading/code.py`目前仍使用Anthropic Messages API。今天先识别原实现，再把它迁移到项目已采用的OpenAI Responses API；迁移后使用`function_call`、`function_call_output`和`call_id`。所有代码注释、日志、用户提示和错误信息统一中文化，但函数名、协议字段和工具名保持英文。

### 今日可见成果

今天结束时必须亲眼看到：

1. 启动后，system prompt只包含技能名称和描述，没有包含全部`SKILL.md`正文
2. 模型需要某项技能时调用`load_skill(name)`
3. 完整`SKILL.md`通过`function_call_output`进入消息历史，下一轮模型才能使用它
4. 请求不存在的技能时，Harness返回明确错误和可用技能列表
5. 新增一个最小测试技能后，它自动出现在catalog中，无需修改`TOOLS`或`TOOL_HANDLERS`

### 时间安排

#### 0～5分钟：先定位并预测

先不看实现，写下预测：

```text
启动时进入system prompt的内容：
调用load_skill后进入messages的内容：
新增一个技能是否需要修改Python注册表：
错误技能名应该由模型、工具还是Harness处理：
```

今天的所有权动作是：**先预测新增技能后的注册和加载行为，再运行验证。**

#### 5～15分钟：只读README的机制部分

阅读：

- `s07_skill_loading/README.zh.md`中的“问题”“解决方案”“工作原理”

重点区分：

```text
技能发现：名称 + 描述 → system prompt catalog
技能加载：完整SKILL.md → load_skill的function_call_output
```

暂时跳过：

- YAML语法的全部规则
- Skill应该如何写得完善
- Skill与MCP、插件系统的组合

#### 15～25分钟：追踪代码和数据流

打开`s07_skill_loading/code.py`，只按以下顺序追踪：

1. `SKILLS_DIR`
2. `SkillLoader.__init__()`和`scan()`
3. `parse_frontmatter()`如何得到`name`、`description`和正文
4. `catalog()`为什么只返回名称和描述
5. `build_system_prompt()`如何把catalog放入`SYSTEM`
6. `load()`如何按名称从`self.skills`查找全文
7. `TOOLS`中的`load_skill`
8. `TOOL_HANDLERS`中的`"load_skill": SKILL_LOADER.load`
9. `agent_loop()`如何把工具结果回填给模型

重点观察两个状态位置：

```text
技能注册表：SKILL_LOADER.skills
对话状态：history/messages
```

不要把两者混为一谈。注册表保存可用技能及全文；只有实际加载的技能全文才通过工具结果进入对话历史。

#### 25～50分钟：迁移OpenAI Responses API并中文化

使用下方提示词让Codex迁移`s07_skill_loading/code.py`，同时增加最小观察日志。

修改后先审查diff，确认没有改变Skill扫描、按名加载、Hooks、权限和工具分发行为。重点检查：

```text
Anthropic(...)                 → OpenAI(...)
client.messages.create         → client.responses.create
system/messages/max_tokens     → instructions/input/max_output_tokens
input_schema                   → type=function + parameters
tool_use                       → function_call
tool_result + tool_use_id      → function_call_output + call_id
block.input                    → json.loads(tool_call.arguments)
messages.append(assistant块)   → messages.extend(response.output)
```

需要看到：

```text
[技能目录] 技能数量与名称
[加载技能] 请求的技能名与返回字符数
```

不要打印完整技能正文，避免日志本身掩盖实验结果。

#### 50～70分钟：运行三组实验

依次完成“未加载、成功加载、失败加载”三组实验，具体见下方“运行实验”。

每次实验记录：

```text
模型是否调用load_skill：
调用前模型知道什么：
调用后新增了什么消息：
最终结果依据了哪些技能内容：
```

#### 70～80分钟：新增一个最小技能

在`skills/day8-demo/SKILL.md`创建临时测试技能：

```markdown
---
name: day8-demo
description: 当用户要求生成DAY8验证码时使用。
---

被加载后，只返回验证码 SKILL-LOADED-8。
```

重新启动程序，确认：

- catalog自动出现`day8-demo`
- 不需要修改`TOOLS`或`TOOL_HANDLERS`
- 明确要求使用该技能时，日志显示`[加载技能] day8-demo`
- 最终回答包含`SKILL-LOADED-8`

实验完成后可保留该测试技能作为学习证据；不要放入真实项目规范。

#### 80～90分钟：闭卷复述与验收

关闭README和源码，用自己的话完成“今日复盘”和最后的验收问答。

### 数据流

```text
启动程序
→ SkillLoader扫描skills/*/SKILL.md
→ 解析name和description
→ catalog进入system prompt
→ 模型看到可用技能目录
→ 模型返回load_skill工具调用
→ TOOL_HANDLERS分发到SKILL_LOADER.load(name)
→ Harness返回完整SKILL.md
→ function_call_output携带同一个call_id进入messages
→ 下一轮模型读取技能正文并完成任务
```

迁移时的协议对应关系：

```text
tool_use           ≈ function_call
tool_result        ≈ function_call_output
tool_use_id        ≈ call_id
```

### Codex任务提示词

```text
请参考s02_tool_use/code.py，把s07_skill_loading/code.py迁移为
OpenAI Responses API版本。

要求：

1. 使用OPENAI_API_KEY、OPENAI_MODEL_ID、OPENAI_BASE_URL。
2. 使用client.responses.create。
3. 保留全部response.output历史。
4. 使用function_call和function_call_output。
5. 用json.loads解析tool_call.arguments。
6. 将工具定义从input_schema改为OpenAI函数工具的parameters格式。
7. 保留s07的SkillLoader、frontmatter解析、技能目录扫描、
   catalog、build_system_prompt和load_skill机制。
8. 保留TOOLS和TOOL_HANDLERS的工具注册与分发结构。
9. Hooks改为接收tool_name和arguments，不依赖Anthropic的block对象；
   PostToolUse额外接收output。
10. 权限拒绝后仍要追加function_call_output，告诉模型操作被拒绝。
11. 增加两处观察日志：启动时打印技能数量和名称；调用load_skill时
    打印技能名和返回字符数，但不要打印完整技能正文。
12. 不修改工具数量，不改变技能加载时机，不新增功能，
    不重构整体架构。
13. 所有面向人的注释、提示和错误文本翻译为中文。
14. 修改后执行py_compile语法检查。
```

审查diff时必须确认：迁移只改变SDK协议适配和中文文本，没有把完整技能正文提前加入`SYSTEM`，也没有绕过`load_skill`直接读取文件。

### 运行实验

从项目根目录运行：

```powershell
python s07_skill_loading/code.py
```

#### 实验1：普通任务，不应加载无关技能

输入：

```text
告诉我当前有哪些技能，只列出名称，不要加载技能全文。
```

预期：

- 回答来自system prompt中的catalog
- 不出现`[加载技能]`日志
- 证明“知道技能存在”不等于“已经加载技能全文”

#### 实验2：加载已有技能

输入：

```text
请先加载code-review技能，再用三点概括它要求怎样审查代码。
```

预期：

- 模型调用`load_skill`，参数为`code-review`
- Harness返回完整`SKILL.md`
- 该结果使用原工具调用的`call_id`回填
- 下一轮模型依据完整内容回答

#### 实验3：不存在的技能

输入：

```text
请加载名为not-exists-day8的技能，并告诉我加载结果。
```

预期：

- 程序不崩溃
- `SkillLoader.load()`返回中文“未知技能”错误及可用技能名
- 错误同样作为普通`function_call_output`返回模型
- 模型不能假装已经获得该技能正文

#### 实验4：新增`day8-demo`技能

按时间安排创建测试技能，重启程序后输入：

```text
请使用day8-demo技能生成DAY8验证码。
```

预期：catalog自动发现、模型按名加载、最终输出`SKILL-LOADED-8`。

安全注意事项：

- 今天不需要调用`bash`、写入系统目录或访问工作区外文件
- 只允许新增`skills/day8-demo/SKILL.md`和两处观察日志
- 不要让测试提示要求模型修改其他项目文件
- `SYSTEM`在进程启动时构建，所以新增技能后必须重启程序才能刷新catalog

### 今日复盘

```text
Skill解决的核心问题：
启动时扫描的路径模式：
catalog中保存并展示什么：
完整SKILL.md何时进入模型上下文：
技能注册表保存在哪里：
load_skill如何找到对应handler：
未知技能名由哪里处理：
Skill与普通read_file工具的关键区别：
```

### 验收标准

- 能解释“技能发现”和“完整内容加载”是两个不同阶段
- 能指出`scan → catalog → SYSTEM`和`load_skill → load → function_call_output`两条代码链
- `s07`已使用OpenAI Responses API，且工具调用与结果通过同一个`call_id`关联
- 注释、提示和错误信息已经中文化，协议标识符没有被错误翻译
- 普通技能列表查询没有加载全文，指定技能任务出现了真实加载日志
- 未知技能实验返回错误但程序继续运行
- 新增`day8-demo`后无需修改Python注册代码即可被发现和加载

今日学习验收问答：

1. 为什么不把所有`SKILL.md`全文直接拼入system prompt？
2. 模型在调用`load_skill`之前，知道技能的哪些信息，不知道哪些信息？
3. `SKILL_LOADER.skills`和`messages`分别保存什么，它们的生命周期有什么不同？
4. 为什么新增一个技能通常不需要修改`TOOLS`和`TOOL_HANDLERS`？
5. `load_skill`返回正文后，为什么还必须经过`function_call_output`回填并再次调用模型？
6. 一次进程运行期间新增`SKILL.md`后，为什么默认不会立刻出现在catalog？

### 今天不要做

- 不修改OpenAI Responses API之外的SDK协议细节
- 不学习或实现Skill自动热重载
- 不设计复杂的Skill优先级、依赖和冲突处理
- 不研究YAML解析器的边界细节
- 不把Subagent、MCP或Context Compact混入今天的实验
- 不提前学习s08上下文压缩
- 不把“模型看到技能描述”误认为“模型已经执行或遵守了完整技能”
