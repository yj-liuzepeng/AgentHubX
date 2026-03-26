# AgentChat Prometheus 监控接入详细报告

> 本文档详细说明 AgentChat 项目中如何接入 Prometheus 监控，包括监控注册、指标定义、业务集成等完整流程。

---

## 📑 目录

1. [架构概述](#1-架构概述)
2. [监控指标模块](#2-监控指标模块)
3. [FastAPI 集成](#3-fastapi-集成)
4. [业务代码集成](#4-业务代码集成)
5. [部署配置](#5-部署配置)
6. [使用示例](#6-使用示例)

---

## 1. 架构概述

### 1.1 监控分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        监控采集层                                │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   HTTP 指标   │  │   业务指标    │  │   系统指标    │          │
│  │  (自动采集)   │  │  (手动埋点)   │  │  (Node Exp)  │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                  │
│         └─────────────────┴─────────────────┘                  │
│                           │                                    │
│                           ▼                                    │
│                  ┌─────────────────┐                          │
│                  │   Prometheus    │                          │
│                  │    (TSDB)       │                          │
│                  │  时序数据存储    │                          │
│                  └────────┬────────┘                          │
│                           │                                    │
│                           ▼                                    │
│                  ┌─────────────────┐                          │
│                  │     Grafana     │                          │
│                  │    (可视化)      │                          │
│                  └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 监控覆盖范围

| 层级         | 监控对象                       | 采集方式               | 指标类型                  |
| ------------ | ------------------------------ | ---------------------- | ------------------------- |
| **基础设施** | CPU、内存、磁盘、网络          | Node Exporter          | Gauge                     |
| **应用层**   | HTTP 请求、延迟、错误率        | FastAPI Instrumentator | Counter, Histogram        |
| **业务层**   | Agent 执行、工具调用、外部 API | 自定义装饰器           | Counter, Histogram, Gauge |
| **LLM 层**   | Token 使用、成本、延迟         | 回调/装饰器            | Counter, Histogram        |

---

## 2. 监控指标模块

### 2.1 模块结构

```
src/backend/agentchat/services/metrics/
├── __init__.py              # 模块导出
├── llm_metrics.py           # LLM 调用指标
├── agent_metrics.py         # Agent 执行指标
├── tool_metrics.py          # 工具调用指标
└── external_api_metrics.py  # 外部 API 指标
```

### 2.2 指标定义详解

#### 2.2.1 Agent 执行指标 (`agent_metrics.py`)

```python
from prometheus_client import Counter, Histogram, Gauge

# 1. Counter - 只增不减的计数器
AGENT_EXECUTIONS_TOTAL = Counter(
    'agent_executions_total',           # 指标名称（必须唯一）
    'Total agent executions',            # 指标描述
    ['agent_type', 'status']             # 标签维度
)
# 用途：统计 Agent 执行总次数，按类型和状态分类

# 2. Histogram - 直方图，用于统计分布
AGENT_EXECUTION_DURATION = Histogram(
    'agent_execution_duration_seconds',  # 指标名称
    'Agent execution duration',          # 指标描述
    ['agent_type'],                      # 标签维度
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]  # 桶分布
)
# 用途：统计 Agent 执行耗时分布，支持 P50/P95/P99 计算

# 3. Gauge - 可增可减的仪表盘
AGENT_ACTIVE_EXECUTIONS = Gauge(
    'agent_active_executions',           # 指标名称
    'Number of active agent executions', # 指标描述
    ['agent_type']                       # 标签维度
)
# 用途：实时监控正在执行的 Agent 数量
```

**核心装饰器实现**:

```python
def track_agent_execution(agent_type: str):
    """
    Agent 执行监控装饰器

    功能：
    1. 记录执行次数（成功/失败）
    2. 记录执行耗时
    3. 记录并发执行数

    参数：
        agent_type: Agent 类型标识，如 "mars", "lingseek"
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'

            # 增加活跃执行数
            AGENT_ACTIVE_EXECUTIONS.labels(agent_type=agent_type).inc()

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'  # 记录失败状态
                raise
            finally:
                # 记录执行次数
                AGENT_EXECUTIONS_TOTAL.labels(
                    agent_type=agent_type,
                    status=status
                ).inc()
                # 记录执行耗时
                AGENT_EXECUTION_DURATION.labels(
                    agent_type=agent_type
                ).observe(time.time() - start_time)
                # 减少活跃执行数
                AGENT_ACTIVE_EXECUTIONS.labels(agent_type=agent_type).dec()

        return async_wrapper
    return decorator
```

#### 2.2.2 工具调用指标 (`tool_metrics.py`)

```python
TOOL_CALLS_TOTAL = Counter(
    'tool_calls_total',
    'Total tool calls',
    ['tool_name', 'status']  # 按工具名称和状态分类
)

TOOL_CALL_DURATION = Histogram(
    'tool_call_duration_seconds',
    'Tool call duration',
    ['tool_name'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)


def track_tool_call(tool_name: str):
    """
    工具调用监控装饰器

    示例：追踪 Tavily 搜索工具的调用情况
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                raise
            finally:
                # 记录工具调用次数和耗时
                TOOL_CALLS_TOTAL.labels(
                    tool_name=tool_name,
                    status=status
                ).inc()
                TOOL_CALL_DURATION.labels(
                    tool_name=tool_name
                ).observe(time.time() - start_time)

        return async_wrapper
    return decorator
```

#### 2.2.3 LLM 调用指标 (`llm_metrics.py`)

```python
# 请求指标
LLM_REQUESTS_TOTAL = Counter(
    'llm_requests_total',
    'Total LLM API requests',
    ['model', 'provider', 'status']
)

LLM_REQUEST_DURATION = Histogram(
    'llm_request_duration_seconds',
    'LLM API request duration',
    ['model', 'provider'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Token 使用指标
LLM_TOKENS_INPUT = Counter(
    'llm_tokens_input_total',
    'Total input tokens used',
    ['model', 'provider']
)

LLM_TOKENS_OUTPUT = Counter(
    'llm_tokens_output_total',
    'Total output tokens used',
    ['model', 'provider']
)

# 成本指标
LLM_TOKENS_COST = Counter(
    'llm_tokens_cost_total',
    'Estimated cost of LLM tokens in USD',
    ['model', 'provider']
)

# Token 成本配置（USD per 1K tokens）
TOKEN_COSTS = {
    'gpt-4': {'input': 0.03, 'output': 0.06},
    'gpt-4o': {'input': 0.005, 'output': 0.015},
    'qwen-plus': {'input': 0.0008, 'output': 0.002},
    # ... 其他模型
}
```

**Token 提取逻辑**:

```python
def _extract_tokens(result: Any) -> tuple[int, int]:
    """
    从 LLM 响应中提取 Token 使用量
    支持多种响应格式：LangChain、OpenAI、字典
    """
    input_tokens = 0
    output_tokens = 0

    # LangChain 格式
    if hasattr(result, 'usage_metadata'):
        metadata = result.usage_metadata
        input_tokens = metadata.get('input_tokens', 0)
        output_tokens = metadata.get('output_tokens', 0)

    # OpenAI 格式
    elif hasattr(result, 'usage'):
        usage = result.usage
        input_tokens = usage.get('prompt_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0)

    # 字典格式
    elif isinstance(result, dict):
        usage = result.get('usage', {})
        input_tokens = usage.get('prompt_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0)

    return input_tokens, output_tokens
```

#### 2.2.4 外部 API 指标 (`external_api_metrics.py`)

```python
EXTERNAL_API_CALLS_TOTAL = Counter(
    'external_api_calls_total',
    'Total external API calls',
    ['service', 'endpoint', 'status']
)

EXTERNAL_API_DURATION = Histogram(
    'external_api_duration_seconds',
    'External API call duration',
    ['service', 'endpoint'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)


def track_external_api(service: str, endpoint: str = 'default'):
    """
    外部 API 调用监控装饰器

    用于追踪第三方服务调用，如 Tavily、Google Search 等
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                raise
            finally:
                EXTERNAL_API_CALLS_TOTAL.labels(
                    service=service,
                    endpoint=endpoint,
                    status=status
                ).inc()
                EXTERNAL_API_DURATION.labels(
                    service=service,
                    endpoint=endpoint
                ).observe(time.time() - start_time)

        return async_wrapper
    return decorator
```

---

## 3. FastAPI 集成

### 3.1 集成方式

**文件**: `src/backend/agentchat/main.py`

```python
from prometheus_fastapi_instrumentator import Instrumentator

def create_app():
    app = FastAPI(title="AgentChat", version="v2.2.0")

    # 1. 创建 Instrumentator 实例
    instrumentator = Instrumentator(
        # 不按状态码分组（保留详细状态码）
        should_group_status_codes=False,

        # 忽略未模板化的处理器
        should_ignore_untemplated=True,

        # 不根据环境变量调整行为
        should_respect_env_var=False,

        # 追踪进行中的请求数
        should_instrument_requests_inprogress=True,

        # 排除的端点（不监控这些路径）
        excluded_handlers=[
            "/metrics",      # 监控端点本身
            "/health",       # 健康检查
            "/docs",         # API 文档
            "/openapi.json", # OpenAPI 规范
            "/static/*"      # 静态资源
        ],

        # 进行中请求数的指标名称
        inprogress_name="http_requests_inprogress",

        # 为进行中请求添加标签
        inprogress_labels=True,
    )

    # 2. 将 Instrumentator 应用到 FastAPI 应用
    instrumentator.instrument(app)

    @app.on_event("startup")
    async def startup_event():
        await init_config()
        await register_router(app)

        # 3. 暴露 /metrics 端点
        instrumentator.expose(
            app,
            endpoint="/metrics",           # 指标暴露路径
            include_in_schema=False        # 不在 API 文档中显示
        )

    return app
```

### 3.2 自动采集的 HTTP 指标

FastAPI Instrumentator 自动采集以下指标：

| 指标名称                        | 类型      | 说明                                             |
| ------------------------------- | --------- | ------------------------------------------------ |
| `http_requests_total`           | Counter   | HTTP 请求总数（按 method、handler、status 分类） |
| `http_request_duration_seconds` | Histogram | HTTP 请求处理时间分布                            |
| `http_request_size_bytes`       | Histogram | HTTP 请求体大小                                  |
| `http_response_size_bytes`      | Histogram | HTTP 响应体大小                                  |
| `http_requests_inprogress`      | Gauge     | 当前正在处理的请求数                             |

---

## 4. 业务代码集成

### 4.1 Agent 监控集成

**文件**: `src/backend/agentchat/api/v1/lingseek.py`

```python
from agentchat.services.metrics import track_agent_execution

router = APIRouter(prefix="/workspace/lingseek", tags=["LingSeek"])

@router.post("/guide_prompt", summary="生成灵寻的指导提示")
@track_agent_execution(agent_type="lingseek")  # <-- 添加监控装饰器
async def generate_lingseek_guide_prompt(
    *,
    lingseek_info: LingSeekGuidePrompt,
    login_user: UserPayload = Depends(get_login_user)
):
    """
    该接口的每次调用都会被监控：
    - 记录执行次数（lingseek 类型）
    - 记录执行耗时
    - 记录成功/失败状态
    """
    set_user_id_context(login_user.user_id)
    set_agent_name_context(UsageStatsAgentType.lingseek_agent)

    lingseek_agent = LingSeekAgent(login_user.user_id)

    async def general_generate():
        async for chunk in lingseek_agent.generate_guide_prompt(lingseek_info):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(general_generate(), media_type="text/event-stream")
```

**文件**: `src/backend/agentchat/api/v1/mars.py`

```python
from agentchat.services.metrics import track_agent_execution

@router.post("/mars/chat")
@track_agent_execution(agent_type="mars")  # <-- Mars Agent 监控
async def chat_mars(
    user_input: str = Body(..., description="用户输入", embed=True),
    login_user: UserPayload = Depends(get_login_user)
):
    """
    Mars Agent 对话接口监控
    """
    # ... 业务逻辑
```

### 4.2 工具监控集成

**文件**: `src/backend/agentchat/tools/web_search/tavily_search/action.py`

```python
from agentchat.services.metrics import track_tool_call, track_external_api

@tool("web_search", parse_docstring=True)
@track_tool_call(tool_name="tavily_search")  # <-- 工具调用监控
def tavily_search(
    query: str,
    topic: Optional[str],
    max_results: Optional[int],
    time_range: Optional[Literal["day", "week", "month", "year"]]
):
    """
    根据用户的问题以及查询参数进行联网搜索
    """
    return _tavily_search(query, topic, max_results, time_range)

@track_external_api(service="tavily", endpoint="search")  # <-- 外部 API 监控
def _tavily_search(query, topic, max_results, time_range):
    """
    使用 Tavily 搜索工具给用户进行搜索
    该函数的实际调用会被监控：
    - 记录 Tavily API 调用次数
    - 记录 API 响应时间
    - 记录成功/失败状态
    """
    response = tavily_client.search(
        query=query,
        country="china",
        topic=topic,
        time_range=time_range,
        max_results=max_results
    )
    return "\n\n".join([f'网址:{result["url"]}, 内容: {result["content"]}'
                       for result in response["results"]])
```

### 4.3 监控指标导出

**文件**: `src/backend/agentchat/services/metrics/__init__.py`

```python
"""
AgentChat 监控指标模块

提供 LLM、Agent、工具调用等业务指标的采集能力
"""

from .llm_metrics import (
    LLM_REQUESTS_TOTAL,
    LLM_REQUEST_DURATION,
    LLM_TOKENS_INPUT,
    LLM_TOKENS_OUTPUT,
    LLM_TOKENS_COST,
    track_llm_call,
    record_llm_tokens,
)

from .agent_metrics import (
    AGENT_EXECUTIONS_TOTAL,
    AGENT_EXECUTION_DURATION,
    AGENT_STEPS_TOTAL,
    AGENT_ACTIVE_EXECUTIONS,
    track_agent_execution,
    track_agent_step,
)

from .tool_metrics import (
    TOOL_CALLS_TOTAL,
    TOOL_CALL_DURATION,
    track_tool_call,
)

from .external_api_metrics import (
    EXTERNAL_API_CALLS_TOTAL,
    EXTERNAL_API_DURATION,
    track_external_api,
)

__all__ = [
    # LLM 指标
    'LLM_REQUESTS_TOTAL',
    'LLM_REQUEST_DURATION',
    'LLM_TOKENS_INPUT',
    'LLM_TOKENS_OUTPUT',
    'LLM_TOKENS_COST',
    'track_llm_call',
    'record_llm_tokens',
    # Agent 指标
    'AGENT_EXECUTIONS_TOTAL',
    'AGENT_EXECUTION_DURATION',
    'AGENT_STEPS_TOTAL',
    'AGENT_ACTIVE_EXECUTIONS',
    'track_agent_execution',
    'track_agent_step',
    # 工具指标
    'TOOL_CALLS_TOTAL',
    'TOOL_CALL_DURATION',
    'track_tool_call',
    # 外部 API 指标
    'EXTERNAL_API_CALLS_TOTAL',
    'EXTERNAL_API_DURATION',
    'track_external_api',
]
```

---

## 5. 部署配置

### 5.1 Prometheus 配置

**文件**: `docker/monitoring/prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s # 默认采集间隔
  evaluation_interval: 15s # 告警规则评估间隔

# 告警管理器配置
alerting:
  alertmanagers:
    - static_configs:
        - targets: [] # 暂时未配置 Alertmanager

# 告警规则文件
rule_files:
  - "rules/*.yml"

# 采集目标配置
scrape_configs:
  # 1. Prometheus 自身监控
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]

  # 2. FastAPI 应用监控
  - job_name: "agentchat-api"
    static_configs:
      - targets: ["host.docker.internal:7860"] # 访问宿主机上的应用
    metrics_path: "/metrics"
    scrape_interval: 10s

  # 3. Node Exporter（主机监控）
  - job_name: "node-exporter"
    static_configs:
      - targets: ["node-exporter:9100"]
```

### 5.2 Docker Compose 配置

**文件**: `docker/monitoring/docker-compose.monitoring.yml`

```yaml
version: "3.8"

services:
  # Prometheus 服务
  prometheus:
    image: prom/prometheus:v2.50.0
    container_name: prometheus
    restart: unless-stopped
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--storage.tsdb.retention.time=15d" # 数据保留15天
      - "--web.enable-lifecycle" # 支持配置热重载
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prometheus/rules:/etc/prometheus/rules:ro
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - monitoring

  # Grafana 服务
  grafana:
    image: grafana/grafana:10.3.1
    container_name: grafana
    restart: unless-stopped
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_DEFAULT_LANGUAGE=zh-Hans # 中文界面
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    ports:
      - "3000:3000"
    networks:
      - monitoring

  # Node Exporter（主机资源监控）
  node-exporter:
    image: prom/node-exporter:v1.7.0
    container_name: node-exporter
    restart: unless-stopped
    volumes:
      - /:/host:ro # 只读挂载宿主机根目录
    ports:
      - "9100:9100"
    networks:
      - monitoring
    pid: host # 共享宿主机进程命名空间

volumes:
  prometheus_data:
  grafana_data:

networks:
  monitoring:
    driver: bridge
```

---

## 6. 使用示例

### 6.1 启动监控服务

```bash
# 进入监控目录
cd /Users/liuzepeng/Desktop/all/AI/AgentChat/docker/monitoring

# 启动 Prometheus + Grafana
docker compose -f docker-compose.monitoring.yml up -d

# 查看状态
docker compose -f docker-compose.monitoring.yml ps
```

### 6.2 访问监控界面

| 服务       | URL                           | 说明               |
| ---------- | ----------------------------- | ------------------ |
| Prometheus | http://localhost:9090         | 指标查询和告警状态 |
| Grafana    | http://localhost:3000         | 可视化仪表盘       |
| 指标端点   | http://localhost:7860/metrics | 应用原始指标       |

### 6.3 查询指标示例

**PromQL 查询示例**:

```promql
# 1. 查询 Mars Agent 执行总次数
agent_executions_total{agent_type="mars"}

# 2. 查询 LingSeek Agent 成功率
rate(agent_executions_total{agent_type="lingseek",status="success"}[5m])
/
rate(agent_executions_total{agent_type="lingseek"}[5m])

# 3. 查询 Tavily 搜索平均耗时
rate(tool_call_duration_seconds_sum{tool_name="tavily_search"}[5m])
/
rate(tool_call_duration_seconds_count{tool_name="tavily_search"}[5m])

# 4. 查询 HTTP 请求 P95 延迟
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)

# 5. 查询 LLM Token 总消耗
topk(10, sum by (model) (llm_tokens_input_total + llm_tokens_output_total))
```

### 6.4 添加新的监控

**为新的 Agent 添加监控**:

```python
from agentchat.services.metrics import track_agent_execution

@router.post("/my_agent/chat")
@track_agent_execution(agent_type="my_agent")  # 指定 Agent 类型
async def my_agent_chat(...):
    # 业务逻辑
    pass
```

**为新的工具添加监控**:

```python
from agentchat.services.metrics import track_tool_call, track_external_api

@track_tool_call(tool_name="my_tool")
@track_external_api(service="third_party_api", endpoint="search")
def my_tool_function(...):
    # 工具逻辑
    pass
```

---

## 📊 监控指标汇总

| 指标名称                           | 类型      | 标签                      | 用途           |
| ---------------------------------- | --------- | ------------------------- | -------------- |
| `agent_executions_total`           | Counter   | agent_type, status        | Agent 执行次数 |
| `agent_execution_duration_seconds` | Histogram | agent_type                | Agent 执行耗时 |
| `agent_active_executions`          | Gauge     | agent_type                | 活跃 Agent 数  |
| `tool_calls_total`                 | Counter   | tool_name, status         | 工具调用次数   |
| `tool_call_duration_seconds`       | Histogram | tool_name                 | 工具调用耗时   |
| `llm_requests_total`               | Counter   | model, provider, status   | LLM 请求数     |
| `llm_tokens_input_total`           | Counter   | model, provider           | 输入 Token 数  |
| `llm_tokens_output_total`          | Counter   | model, provider           | 输出 Token 数  |
| `llm_tokens_cost_total`            | Counter   | model, provider           | Token 成本     |
| `external_api_calls_total`         | Counter   | service, endpoint, status | 外部 API 调用  |
| `http_requests_total`              | Counter   | method, handler, status   | HTTP 请求数    |
| `http_request_duration_seconds`    | Histogram | method, handler           | HTTP 请求耗时  |

---

**文档结束**
