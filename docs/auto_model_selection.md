# 自动模型选择功能 (Auto Model Mode)

## 1. 功能概述

**自动模型选择 (Auto Model Mode)** 是 AgentHubX 提供的一项智能辅助功能。旨在通过算法自动分析用户输入的内容，从当前可用的模型列表中，智能选择最匹配的模型来生成回答。

此功能的主要优势：
*   **降低使用门槛**：用户无需了解每个模型的优劣，系统自动决策。
*   **优化成本与效果**：对于简单问题使用轻量模型，对于复杂/编程问题使用强力模型，实现效果与成本的平衡。
*   **提升响应速度**：针对简单对话优先选择低延迟模型。

---

## 2. 核心流程

当用户在前端模型列表中选择 **"Auto Mode (自动选择)"** 时，系统会执行以下流程：

1.  **请求拦截**：后端接口 `/simple/chat` 识别到请求的 `model_id` 为 `"auto"`。
2.  **获取可用模型**：系统获取当前用户有权限使用的所有 LLM 模型列表。
3.  **意图分析**：`ModelSelector` 组件分析用户的 Query 内容，判断其任务类型（编程、复杂推理、简单对话）。
4.  **智能匹配**：根据任务类型，在可用模型中按照预设的优先级策略进行匹配。
5.  **模型替换**：将 `model_id` 替换为选中的真实模型 ID，继续后续的对话流程。
6.  **日志记录**：全程记录决策过程，便于追踪和优化。

---

## 3. 技术实现细节

### 3.1 意图识别策略 (`ModelSelector._analyze_intent`)

系统目前支持三种意图分类：

| 意图类型 (Intent) | 判定规则 | 典型场景 |
| :--- | :--- | :--- |
| **CODING (编程)** | 输入包含编程关键词 (如 `python`, `function`, `api`, `代码`, `报错` 等) | 代码生成、Bug 修复、SQL 编写 |
| **COMPLEX (复杂)** | 输入长度 > 300 字符，或包含深度思考关键词 (如 `analyze`, `design`, `架构`, `原理` 等) | 深度分析、长文本总结、架构设计 |
| **SIMPLE (简单)** | 不满足上述两种情况 | 日常闲聊、简单问答、翻译 |

### 3.2 模型分级与匹配策略 (`ModelSelector._find_best_match`)

系统预定义了三类模型池，并根据意图设定了不同的查找优先级：

**预定义模型池** (可在 `src/backend/agentchat/services/model_selector.py` 中扩展):
*   `POWERFUL_MODELS`: GPT-4, Claude-3-Opus, DeepSeek-V3 等
*   `FAST_MODELS`: GPT-3.5, Haiku, Gemini-Flash 等
*   `CODING_MODELS`: DeepSeek-Coder, CodeLlama 等

**匹配优先级**:

*   **CODING 意图**: `CODING_MODELS` > `POWERFUL_MODELS` > `FAST_MODELS`
*   **COMPLEX 意图**: `POWERFUL_MODELS` > `FAST_MODELS`
*   **SIMPLE 意图**: `FAST_MODELS` > `POWERFUL_MODELS`

### 3.3 兜底机制

如果根据策略未能在可用模型列表中找到匹配的模型（例如用户只配置了一个未在预定义列表中的小众模型），系统会触发**兜底策略**：
*   直接选择可用模型列表中的**第一个模型**。
*   同时输出 Warning 级别日志，提示未匹配到推荐模型。

---

## 4. 关键代码说明

### 后端服务 (`src/backend`)

*   **`agentchat/services/model_selector.py`**: 核心逻辑类。包含 `select_model` (主入口), `_analyze_intent` (意图分析), `_find_best_match` (模型匹配)。
*   **`agentchat/api/v1/workspace.py`**: API 接口层。在 `workspace_simple_chat` 函数中，检测 `model_id == "auto"` 并调用 `ModelSelector`。

### 前端页面 (`src/frontend`)

*   **`src/pages/workspace/defaultPage/defaultPage.vue`**: 在模型下拉列表初始化时，手动插入 `Auto Mode` 选项并设为默认。

---

## 5. 日志与调试

为了方便排查自动选择的逻辑，系统输出了详细的日志 (Loguru INFO 级别)：

```text
=== 启动自动模型选择流程 ===
获取到用户可见LLM模型数量: 5
自动模式 - 用户查询: Write a python function to...
自动模式 - 查询意图分析结果: coding
自动模式 - 当前可用模型列表 (5个): ['gpt-4', 'deepseek-coder', ...]
自动模式 - 匹配成功! 选中模型: deepseek-coder (ID: dscoder)
=== 自动选择完成，最终使用模型ID: dscoder ===
```

可以通过查看控制台日志，确认每次请求的意图判定结果和最终选择的模型。

---

## 6. 扩展指南

如果集成了新的模型，希望被自动模式识别：

1.  打开 `src/backend/agentchat/services/model_selector.py`。
2.  根据模型能力，将其名称关键词添加到对应的列表常量中：
    *   如果是强力模型，加入 `POWERFUL_MODELS`。
    *   如果是编程模型，加入 `CODING_MODELS`。
    *   如果是快速/轻量模型，加入 `FAST_MODELS`。
3.  重启后端服务即可生效。
