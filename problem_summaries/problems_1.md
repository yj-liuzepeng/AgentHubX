# Problem Summaries (Vol. 1)

## Problem 1
**Time:** 2026-02-27 14:05:00

### Description
在工作台“日常模式”中选择 MCP 后，多模型对“知识库检索”调用不一致：部分模型仅 list_collections 后停止或不触发工具调用，导致 RAG 结果未进入最终回答；开启强制 RAG 兜底后又出现 tool 消息顺序协议报错，整体表现为“同一问题检索不稳定、模型答案未参考 RAG”。

### Cause
问题由两部分叠加导致：1) 工具调用由模型决策，部分模型在 list_collections 为空或工具规划不稳定时直接生成回答，未调用 query_knowledge_hub；2) 兜底检索初版直接插入 ToolMessage 未配套 tool_calls，触发 OpenAI 兼容接口校验失败。

### Solution
完整修复流程：1) 后端增加“强制 RAG 兜底”能力，当模型未触发工具调用时自动执行 list_collections 与 query_knowledge_hub；2) 增加“知识库检索”前端开关透传 force_rag，保证用户显式选择后必走 RAG；3) 兜底流程补充 AIMessage(tool_calls) 并与 ToolMessage 关联，满足协议顺序要求；4) 最终回答阶段注入“严格依据工具结果”提示，降低模型忽略 RAG 的概率。

---

## Problem 2
**Time:** 2026-02-27 14:28:00

### Description
在工作台调用 MCP 的 query_knowledge_hub 时，工具返回“未找到相关文档，请先运行 ingest.py 摄取数据”，但使用其他工具接入同一 MCP 能正常检索，导致本系统检索结果持续为空。

### Cause
MCP 用户配置中的空值被无条件合并进工具调用参数，覆盖了模型生成的有效参数（例如 collection），使实际查询落到空集合或错误集合，从而返回“未找到相关文档”。

### Solution
合并 MCP 配置与工具参数时过滤空值，仅覆盖非空配置，保留模型生成的 query/collection/top_k；同时在 handler_call_mcp_tool 与 _build_mcp_args 使用统一合并逻辑，避免参数被空值污染。

---
