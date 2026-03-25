# AgentChat 智能体架构详解

本文档深入解析 AgentChat 项目中两种核心智能体（Agent）的架构设计与实现机制：**LingSeek Agent（灵寻）** 与 **Mars Agent**。

## 1. LingSeek Agent (灵寻)

**LingSeek Agent** 采用了改进的 **Plan-and-Execute（规划-执行）** 模式，专为解决复杂任务、深度调研和长流程工作而设计。其核心理念是“先思考方法论，再拆解步骤，最后逐步执行”。

### 1.1 核心架构组件

*   **Guide Prompt Generator (指南生成器)**:
    *   利用隐式 **Chain-of-Thought (CoT)** 技术，基于用户需求生成一份结构化的“指导手册”（Markdown 格式）。
    *   **机制**: 模型在内部进行思维链推导，但只向用户展示最终生成的指南，确保交互的专业性。
    *   **代码位置**: [agent.py](../src/backend/agentchat/services/lingseek/agent.py#L42-L65)

*   **Task Decomposer (任务拆解器)**:
    *   将自然语言的“指导手册”转化为结构化的 JSON 任务列表 (`LingSeekTaskStep`)。
    *   **自修复机制**: 内置 `FixJsonPrompt`，当模型生成的 JSON 格式错误时，自动触发修复流程，提高稳定性。
    *   **代码位置**: [agent.py](../src/backend/agentchat/services/lingseek/agent.py#L67-L82)

*   **Graph Executor (图执行器)**:
    *   将线性或并行的任务列表构建为执行图 (`tasks_graph`)。
    *   **上下文流转**: 每个步骤执行时，会将前序依赖步骤的输出作为上下文 (`step_context`) 注入到当前步骤的 Prompt 中，实现复杂逻辑的串联。
    *   **代码位置**: [agent.py](../src/backend/agentchat/services/lingseek/agent.py#L148-L200)

### 1.2 工作流 (Workflow)

1.  **用户输入**: 接收用户发起的复杂查询。
2.  **生成指南**: 调用 `_generate_guide_prompt` 生成解决问题的标准操作手册。
3.  **拆解任务**: 调用 `_generate_tasks` 将手册拆解为具体的执行步骤（如搜索、阅读、总结、撰写）。
4.  **逐步执行**:
    *   遍历任务图。
    *   为每个步骤动态绑定工具（支持本地插件和 MCP 工具）。
    *   执行工具并获取结果。
    *   实时推送步骤状态（Step Update）。
5.  **最终汇总**: 根据所有步骤的执行结果，生成最终的回答或交付物。

---

## 2. Mars Agent (Mars)

**Mars Agent** 采用了增强型的 **ReAct (Reasoning + Acting)** 模式，集成了 **RAG (检索增强生成)** 和 **MCP (模型上下文协议)**。它是系统的全能助手，负责处理日常问答、意图识别、Agent 自动构建以及系统资源管理。

### 2.1 核心架构组件

*   **Memory System (记忆系统)**:
    *   基于 RAG 技术，在对话开始前检索与用户输入相关的历史记忆。
    *   **注入机制**: 检索到的记忆片段被格式化后注入到 `Mars_System_Prompt` 中，使 Agent 具备“长期记忆”能力。
    *   **代码位置**: [mars.py](../src/backend/agentchat/api/v1/mars.py#L48-L62)

*   **Dynamic Tooling (动态工具构建)**:
    *   **Dynamic Docstring**: 使用装饰器 `@dynamic_docstring`，在运行时实时拉取用户可用的模型、工具、知识库列表，动态更新工具的文档字符串。
    *   **AutoBuild**: 允许 Agent 根据当前系统的资源状态，智能地构建和配置新的 Agent。
    *   **代码位置**: [autobuild.py](../src/backend/agentchat/services/mars/mars_tools/autobuild.py#L31-L49)

*   **Streaming Graph (流式图)**:
    *   在 `deep_search` 等工具中，封装了 `StreamingGraph`。
    *   支持向前端实时推送细粒度的执行状态（如 🚀 Start, ✅ Complete, ❌ Error），实现可视化的深度搜索过程。
    *   **代码位置**: [deepsearch.py](../src/backend/agentchat/services/mars/mars_tools/deepsearch.py#L22-L40)

### 2.2 工作流 (Workflow)

1.  **初始化**: 加载用户配置、工具集和中间件。
2.  **记忆检索**: 根据用户输入检索向量数据库中的相关记忆。
3.  **ReAct 循环**:
    *   **思考 (Reasoning)**: 模型分析用户意图和当前上下文。
    *   **行动 (Acting)**: 决定是否调用工具（如 `auto_build_agent`, `query_knowledge`, `deep_search`）。
    *   **观察 (Observation)**: 获取工具执行结果。
4.  **流式反馈**: 将推理过程和工具结果实时流式传输给用户。
5.  **记忆存储**: 对话结束后，异步更新用户的记忆库。

---

## 3. 架构对比总结

| 特性 | LingSeek Agent (灵寻) | Mars Agent (Mars) |
| :--- | :--- | :--- |
| **核心模式** | **Plan-and-Execute (规划-执行)** | **ReAct (推理-行动) + RAG** |
| **主要定位** | 深度研究专家、复杂任务执行者 | 全能助手、系统元能力入口 |
| **思考方式** | 先整体规划，后分步执行 | 边思考边执行，动态调整 |
| **交互形态** | 指南生成 -> 任务列表 -> 进度展示 | 自然语言对话 -> 流式响应 |
| **记忆能力** | 侧重于任务内的上下文流转 (`step_context`) | 侧重于跨会话的长期记忆 (`Memory System`) |
| **适用场景** | 行业调研、报告撰写、长流程任务 | 快速问答、Agent 创建、天气/新闻查询 |
| **关键技术** | Implicit CoT, JSON Self-Correction, Task Graph | Dynamic Docstring, RAG Memory, Streaming Graph |

## 4. 代码引用

*   **LingSeek Agent**:
    *   主逻辑: [agent.py](../src/backend/agentchat/services/lingseek/agent.py)
    *   Prompts: [lingseek.py](../src/backend/agentchat/prompts/lingseek.py)
    *   Schema: [lingseek.py](../src/backend/agentchat/schema/lingseek.py)

*   **Mars Agent**:
    *   主逻辑: [mars_agent.py](../src/backend/agentchat/services/mars/mars_agent.py)
    *   API 入口: [mars.py](../src/backend/agentchat/api/v1/mars.py)
    *   自动构建工具: [autobuild.py](../src/backend/agentchat/services/mars/mars_tools/autobuild.py)
