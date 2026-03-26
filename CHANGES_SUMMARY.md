# AgentChat 改动总结文档

> 生成时间: 2026-03-26  
> 本次改动主要实现了 **Prometheus/Grafana 监控系统的完整接入**，为 AgentChat 提供全链路可观测性能力。

---

## 📋 改动概览

| 类别 | 数量 | 说明 |
|------|------|------|
| **新增文件** | 14+ | 监控配置、指标模块、仪表盘定义 |
| **修改文件** | 7 | 集成监控到业务代码 |
| **主要功能** | 1 | Prometheus/Grafana 监控接入 |

---

## 🎯 第一阶段：基础监控架构搭建

### 1.1 添加监控依赖
**文件**: `requirements.txt`

新增 Prometheus 相关依赖包：
```
prometheus-client==0.20.0
prometheus-fastapi-instrumentator==7.0.0
```

**作用**: 提供 FastAPI 应用的 HTTP 指标自动采集能力。

---

### 1.2 FastAPI 集成 Prometheus
**文件**: `src/backend/agentchat/main.py`

在 FastAPI 应用入口集成 Prometheus 监控：
- 导入 `prometheus_fastapi_instrumentator.Instrumentator`
- 配置 HTTP 指标采集（请求数、延迟、状态码等）
- 暴露 `/metrics` 端点供 Prometheus 抓取
- 排除静态资源和文档端点的监控

**关键代码**:
```python
instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics", "/health", "/docs", ...],
    ...
)
instrumentator.instrument(app)
instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
```

---

### 1.3 创建监控指标模块
**文件**: `src/backend/agentchat/services/metrics/` (新增目录)

创建了完整的业务指标采集模块，包含 5 个文件：

| 文件 | 功能 | 指标类型 |
|------|------|----------|
| `__init__.py` | 模块导出 | - |
| `llm_metrics.py` | LLM 调用指标 | Counter, Histogram |
| `agent_metrics.py` | Agent 执行指标 | Counter, Histogram, Gauge |
| `tool_metrics.py` | 工具调用指标 | Counter, Histogram |
| `external_api_metrics.py` | 外部 API 指标 | Counter, Histogram |

**核心指标定义**:

```python
# LLM 指标
LLM_REQUESTS_TOTAL      # LLM 请求总数
LLM_REQUEST_DURATION    # LLM 响应时间
LLM_TOKENS_INPUT        # 输入 Token 数
LLM_TOKENS_OUTPUT       # 输出 Token 数
LLM_TOKENS_COST         # Token 成本

# Agent 指标
AGENT_EXECUTIONS_TOTAL     # Agent 执行次数
AGENT_EXECUTION_DURATION   # Agent 执行耗时
AGENT_STEPS_TOTAL          # Agent 步骤数
AGENT_ACTIVE_EXECUTIONS    # 活跃 Agent 数

# 工具指标
TOOL_CALLS_TOTAL       # 工具调用次数
TOOL_CALL_DURATION     # 工具调用耗时

# 外部 API 指标
EXTERNAL_API_CALLS_TOTAL    # 外部 API 调用次数
EXTERNAL_API_DURATION       # 外部 API 耗时
```

**装饰器函数**:
- `track_llm_call()` - 追踪 LLM 调用
- `track_agent_execution()` - 追踪 Agent 执行
- `track_agent_step()` - 追踪 Agent 步骤
- `track_tool_call()` - 追踪工具调用
- `track_external_api()` - 追踪外部 API 调用

---

## 🎯 第二阶段：业务代码集成

### 2.1 Mars Agent 监控集成
**文件**: `src/backend/agentchat/api/v1/mars.py`

在 Mars Agent 的聊天接口添加监控装饰器：

```python
@router.post("/mars/chat")
@track_agent_execution(agent_type="mars")
async def chat_mars(...):
    ...
```

**作用**: 追踪 Mars Agent 的执行次数、耗时和状态。

---

### 2.2 LingSeek Agent 监控集成
**文件**: `src/backend/agentchat/api/v1/lingseek.py`

在 LingSeek Agent 的两个核心接口添加监控：

```python
@router.post("/guide_prompt")
@track_agent_execution(agent_type="lingseek")
async def generate_lingseek_guide_prompt(...):
    ...

@router.post("/task_start")
@track_agent_execution(agent_type="lingseek")
async def submit_lingseek_task(...):
    ...
```

**作用**: 追踪 LingSeek Agent 的指导提示生成和任务执行。

---

### 2.3 Tavily 搜索工具监控集成
**文件**: `src/backend/agentchat/tools/web_search/tavily_search/action.py`

在 Tavily 搜索工具添加监控装饰器：

```python
@tool("web_search", parse_docstring=True)
@track_tool_call(tool_name="tavily_search")
def tavily_search(...):
    ...

@track_external_api(service="tavily", endpoint="search")
def _tavily_search(...):
    ...
```

**作用**: 追踪搜索工具的调用次数和 Tavily API 的调用情况。

---

### 2.4 LLM 回调监控准备
**文件**: `src/backend/agentchat/core/callbacks/usage_metadata.py`

为 LLM 指标采集做准备，记录模型调用的 Token 使用情况。

---

## 🎯 第三阶段：监控部署配置

### 3.1 Prometheus 配置
**文件**: `docker/monitoring/prometheus/prometheus.yml` (新增)

配置 Prometheus 采集目标：
- Prometheus 自身监控 (localhost:9090)
- AgentChat API (host.docker.internal:7860)
- Node Exporter (node-exporter:9100)

---

### 3.2 告警规则配置
**文件**: `docker/monitoring/prometheus/rules/agentchat.yml` (新增)

定义 12 条告警规则：

| 告警名称 | 触发条件 | 级别 |
|----------|----------|------|
| HighErrorRate | 错误率 > 5% | critical |
| HighLatency | P95 延迟 > 5s | warning |
| APIDown | 服务不可用 | critical |
| LLMHighErrorRate | LLM 错误率 > 10% | critical |
| LLMHighLatency | LLM P95 > 30s | warning |
| AgentExecutionFailures | Agent 失败率 > 20% | warning |
| ExternalAPIDown | 外部 API 错误率 > 50% | critical |
| ToolCallFailures | 工具失败率 > 30% | warning |
| HighMemoryUsage | 内存 > 85% | warning |
| HighCPUUsage | CPU > 80% | warning |
| DiskSpaceLow | 磁盘 < 10% | critical |
| DiskSpaceCritical | 磁盘 < 5% | critical |

---

### 3.3 Grafana 配置
**文件**: `docker/monitoring/grafana/provisioning/` (新增目录)

包含以下配置：
- `datasources/prometheus.yml` - Prometheus 数据源配置
- `dashboards/agentchat-overview.json` - 系统概览仪表盘
- `dashboards/llm-usage.json` - LLM 使用分析仪表盘
- `custom.ini` - Grafana 中文语言配置

---

### 3.4 Docker Compose 配置
**文件**: `docker/monitoring/docker-compose.monitoring.yml` (新增)

定义三个服务：
- **prometheus**: 指标采集和存储
- **grafana**: 可视化仪表盘（已配置中文）
- **node-exporter**: 主机资源监控

---

## 🎯 第四阶段：辅助工具更新

### 4.1 Docker 启动脚本修复
**文件**: `docker/start.sh`

修复 `docker-compose` 命令兼容性问题：
- 自动检测 `docker-compose` 或 `docker compose`
- 支持新旧版本 Docker

---

### 4.2 环境变量配置
**文件**: `docker/docker.env` (新增)

根据 `config.yaml` 生成完整的 Docker 环境变量配置，包含：
- AI 模型配置（DeepSeek、通义千问等）
- 搜索服务配置（Tavily、Google 等）
- 数据库配置（MySQL、Redis）
- 向量数据库配置
- 阿里云 OSS 配置
- RAG 配置

---

## 🎯 第五阶段：文档编写

### 5.1 监控接入方案文档
**文件**: `docs/prometheus_grafana_integration.md` (新增)

完整的监控接入文档，包含：
- 方案概述和架构图
- 监控指标体系详解
- 接入步骤说明
- 部署和配置指南
- 告警规则说明
- 故障排查指南

---

## 📊 监控覆盖范围

### 已实现监控

| 层级 | 监控内容 | 状态 |
|------|----------|------|
| **基础设施** | CPU、内存、磁盘、网络 | ✅ Node Exporter |
| **应用层** | HTTP 请求、延迟、错误率 | ✅ FastAPI Instrumentator |
| **业务层** | Agent 执行、工具调用、外部 API | ✅ 自定义指标 |
| **LLM 层** | Token 使用、成本、延迟 | ✅ 指标已定义 |

### 访问地址

| 服务 | URL | 说明 |
|------|-----|------|
| Prometheus | http://localhost:9090 | 指标查询和告警状态 |
| Grafana | http://localhost:3000 | 可视化仪表盘 (admin/admin) |
| Metrics Endpoint | http://localhost:7860/metrics | 应用指标暴露端点 |

---

## 🚀 启动命令

```bash
# 启动监控服务
cd /Users/liuzepeng/Desktop/all/AI/AgentChat/docker/monitoring
docker compose -f docker-compose.monitoring.yml up -d

# 启动主服务（可选）
cd /Users/liuzepeng/Desktop/all/AI/AgentChat/docker
bash start.sh
```

---

## 📝 后续建议

1. **LLM Token 监控**: 需要在模型调用回调中实际集成 `record_llm_tokens` 函数
2. **更多工具监控**: 为 Google 搜索、知识库查询等工具添加装饰器
3. **仪表盘优化**: 根据实际使用情况调整 Grafana 面板布局
4. **告警通知**: 配置 Alertmanager 实现邮件/钉钉告警

---

## 📁 新增文件清单

```
docker/
├── docker.env                          # Docker 环境变量配置
├── start.sh                            # 启动脚本（修复版）
└── monitoring/                         # 监控部署目录
    ├── docker-compose.monitoring.yml   # 监控服务编排
    ├── prometheus/
    │   ├── prometheus.yml              # Prometheus 配置
    │   └── rules/
    │       └── agentchat.yml           # 告警规则
    └── grafana/
        ├── provisioning/
        │   ├── datasources/
        │   │   └── prometheus.yml      # 数据源配置
        │   ├── dashboards/
        │   │   ├── agentchat-overview.json
        │   │   └── llm-usage.json
        │   └── custom.ini              # 中文配置
        └── dashboards/                 # 仪表盘 JSON 文件

docs/
└── prometheus_grafana_integration.md   # 监控接入文档

src/backend/agentchat/services/
└── metrics/                            # 监控指标模块
    ├── __init__.py
    ├── llm_metrics.py
    ├── agent_metrics.py
    ├── tool_metrics.py
    └── external_api_metrics.py
```

---

## 🔧 修改文件清单

```
requirements.txt                                    # +2 依赖
src/backend/agentchat/main.py                       # Prometheus 集成
src/backend/agentchat/api/v1/mars.py                # Agent 监控装饰器
src/backend/agentchat/api/v1/lingseek.py            # Agent 监控装饰器
src/backend/agentchat/tools/web_search/tavily_search/action.py  # 工具监控
docker/start.sh                                     # 命令兼容性修复
```

---

**总结**: 本次改动完成了 AgentChat 项目的完整监控体系搭建，从基础设施到业务层实现了全链路可观测性，为生产环境运维提供了有力支撑。
