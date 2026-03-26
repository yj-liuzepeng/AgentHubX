# AgentChat Prometheus/Grafana 监控接入方案

## 1. 方案概述

### 1.1 背景

AgentChat 是一个基于 FastAPI 的智能体对话系统，包含 LingSeek Agent（深度研究）和 Mars Agent（全能助手）两种核心 Agent。系统依赖多种外部服务（LLM API、搜索引擎、向量数据库等），需要全面的可观测性方案来保障服务稳定性。

### 1.2 目标

- 实现系统全链路监控（基础设施 → 应用 → 业务）
- 建立 LLM 调用成本和使用量的可观测性
- 监控 Agent 执行性能和成功率
- 提供实时告警能力

### 1.3 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AgentChat 监控架构                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────┐ │
│  │   FastAPI   │    │   Redis     │    │   Milvus    │    │  MySQL   │ │
│  │  Application│    │             │    │             │    │          │ │
│  │  (业务指标)  │    │  (缓存指标)  │    │ (向量数据库) │    │ (SQL指标)│ │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └────┬─────┘ │
│         │                  │                  │                │       │
│         └──────────────────┴──────────────────┴────────────────┘       │
│                                    │                                   │
│                                    ▼                                   │
│                         ┌─────────────────┐                            │
│                         │   Prometheus    │                            │
│                         │    (TSDB)       │                            │
│                         │  时序数据存储    │                            │
│                         └────────┬────────┘                            │
│                                  │                                     │
│                                  ▼                                     │
│                         ┌─────────────────┐                            │
│                         │     Grafana     │                            │
│                         │   (可视化)       │                            │
│                         │  仪表盘/告警    │                            │
│                         └─────────────────┘                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 监控指标体系

### 2.1 基础设施层（Infrastructure）

| 指标类别 | 具体指标         | 采集方式      | 用途         |
| -------- | ---------------- | ------------- | ------------ |
| **CPU**  | 使用率、负载     | Node Exporter | 资源瓶颈预警 |
| **内存** | 使用率、可用内存 | Node Exporter | OOM 预警     |
| **磁盘** | 使用率、I/O 延迟 | Node Exporter | 存储空间预警 |
| **网络** | 带宽、连接数     | Node Exporter | 网络异常检测 |

### 2.2 应用层（Application）

#### 2.2.1 FastAPI HTTP 指标

| 指标名称                        | 类型      | 标签                     | 说明              |
| ------------------------------- | --------- | ------------------------ | ----------------- |
| `http_requests_total`           | Counter   | method, endpoint, status | HTTP 请求总数     |
| `http_request_duration_seconds` | Histogram | method, endpoint         | HTTP 请求耗时分布 |
| `http_request_size_bytes`       | Histogram | method, endpoint         | 请求体大小        |
| `http_response_size_bytes`      | Histogram | method, endpoint         | 响应体大小        |
| `http_active_requests`          | Gauge     | method, endpoint         | 活跃请求数        |

#### 2.2.2 自定义业务指标

| 指标名称                           | 类型      | 标签                      | 说明               |
| ---------------------------------- | --------- | ------------------------- | ------------------ |
| `llm_requests_total`               | Counter   | model, provider, status   | LLM 调用总数       |
| `llm_request_duration_seconds`     | Histogram | model, provider           | LLM 响应时间       |
| `llm_tokens_input_total`           | Counter   | model, provider           | 输入 Token 数      |
| `llm_tokens_output_total`          | Counter   | model, provider           | 输出 Token 数      |
| `llm_tokens_cost_total`            | Counter   | model, provider           | Token 成本（估算） |
| `agent_executions_total`           | Counter   | agent_type, status        | Agent 执行次数     |
| `agent_execution_duration_seconds` | Histogram | agent_type                | Agent 执行耗时     |
| `agent_steps_total`                | Counter   | agent_type                | Agent 步骤数       |
| `tool_calls_total`                 | Counter   | tool_name, status         | 工具调用次数       |
| `tool_call_duration_seconds`       | Histogram | tool_name                 | 工具调用耗时       |
| `rag_queries_total`                | Counter   | collection, status        | RAG 查询次数       |
| `rag_query_duration_seconds`       | Histogram | collection                | RAG 查询耗时       |
| `external_api_calls_total`         | Counter   | service, endpoint, status | 外部 API 调用      |
| `external_api_duration_seconds`    | Histogram | service, endpoint         | 外部 API 耗时      |

### 2.3 业务层（Business）

| 指标名称                       | 类型    | 标签          | 说明       |
| ------------------------------ | ------- | ------------- | ---------- |
| `conversations_total`          | Counter | -             | 对话总数   |
| `messages_total`               | Counter | message_type  | 消息总数   |
| `active_conversations`         | Gauge   | -             | 活跃对话数 |
| `knowledge_base_queries_total` | Counter | kb_id, status | 知识库查询 |

---

## 3. 技术选型

### 3.1 核心组件

| 组件               | 版本   | 用途           | 部署方式 |
| ------------------ | ------ | -------------- | -------- |
| **Prometheus**     | v2.50+ | 时序数据库     | Docker   |
| **Grafana**        | v10.3+ | 可视化平台     | Docker   |
| **Node Exporter**  | v1.7+  | 主机指标采集   | Docker   |
| **Redis Exporter** | v1.58+ | Redis 指标采集 | Docker   |
| **MySQL Exporter** | v0.15+ | MySQL 指标采集 | Docker   |

### 3.2 Python 依赖

```
prometheus-client==0.20.0
prometheus-fastapi-instrumentator==7.0.0
```

---

## 4. 接入方案详解

### 4.1 后端代码集成

#### 4.1.1 基础集成（FastAPI 自动指标）

```python
# src/backend/agentchat/main.py

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="AgentChat API")

# 自动采集 HTTP 指标
instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics", "/health", "/docs", "/openapi.json"],
    env_var_name="ENABLE_METRICS",
    inprogress_name="http_requests_inprogress",
    inprogress_labels=True,
)
instrumentator.instrument(app).expose(app, endpoint="/metrics")
```

#### 4.1.2 LLM 调用指标采集

```python
# src/backend/agentchat/services/metrics/llm_metrics.py

from prometheus_client import Counter, Histogram, Gauge
import time
from functools import wraps
from typing import Callable, Any

# LLM 指标定义
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

LLM_TOKENS_COST = Counter(
    'llm_tokens_cost_total',
    'Estimated cost of LLM tokens in USD',
    ['model', 'provider']
)

# Token 成本配置（USD per 1K tokens）
TOKEN_COSTS = {
    'gpt-4': {'input': 0.03, 'output': 0.06},
    'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
    'gpt-3.5-turbo': {'input': 0.0005, 'output': 0.0015},
    'qwen-max': {'input': 0.0035, 'output': 0.007},
    'qwen-plus': {'input': 0.0008, 'output': 0.002},
}


def track_llm_call(model: str, provider: str):
    """LLM 调用监控装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'

            try:
                result = func(*args, **kwargs)

                # 提取 Token 使用量（从 result 或 kwargs）
                input_tokens = getattr(result, 'usage', {}).get('prompt_tokens', 0)
                output_tokens = getattr(result, 'usage', {}).get('completion_tokens', 0)

                # 记录 Token 指标
                LLM_TOKENS_INPUT.labels(model=model, provider=provider).inc(input_tokens)
                LLM_TOKENS_OUTPUT.labels(model=model, provider=provider).inc(output_tokens)

                # 计算成本
                cost_config = TOKEN_COSTS.get(model, {'input': 0, 'output': 0})
                cost = (input_tokens * cost_config['input'] +
                       output_tokens * cost_config['output']) / 1000
                LLM_TOKENS_COST.labels(model=model, provider=provider).inc(cost)

                return result

            except Exception as e:
                status = 'error'
                raise
            finally:
                # 记录请求数和延迟
                LLM_REQUESTS_TOTAL.labels(
                    model=model,
                    provider=provider,
                    status=status
                ).inc()
                LLM_REQUEST_DURATION.labels(
                    model=model,
                    provider=provider
                ).observe(time.time() - start_time)

        return wrapper
    return decorator
```

#### 4.1.3 Agent 执行指标采集

```python
# src/backend/agentchat/services/metrics/agent_metrics.py

from prometheus_client import Counter, Histogram, Gauge
import time
from functools import wraps
from typing import Callable, Any

AGENT_EXECUTIONS_TOTAL = Counter(
    'agent_executions_total',
    'Total agent executions',
    ['agent_type', 'status']
)

AGENT_EXECUTION_DURATION = Histogram(
    'agent_execution_duration_seconds',
    'Agent execution duration',
    ['agent_type'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

AGENT_STEPS_TOTAL = Counter(
    'agent_steps_total',
    'Total agent steps executed',
    ['agent_type']
)

AGENT_ACTIVE_EXECUTIONS = Gauge(
    'agent_active_executions',
    'Number of active agent executions',
    ['agent_type']
)


def track_agent_execution(agent_type: str):
    """Agent 执行监控装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'

            AGENT_ACTIVE_EXECUTIONS.labels(agent_type=agent_type).inc()

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                raise
            finally:
                AGENT_EXECUTIONS_TOTAL.labels(
                    agent_type=agent_type,
                    status=status
                ).inc()
                AGENT_EXECUTION_DURATION.labels(
                    agent_type=agent_type
                ).observe(time.time() - start_time)
                AGENT_ACTIVE_EXECUTIONS.labels(agent_type=agent_type).dec()

        return wrapper
    return decorator


def track_agent_step(agent_type: str):
    """Agent 步骤监控装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            AGENT_STEPS_TOTAL.labels(agent_type=agent_type).inc()
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

#### 4.1.4 工具调用指标采集

```python
# src/backend/agentchat/services/metrics/tool_metrics.py

from prometheus_client import Counter, Histogram
import time
from functools import wraps
from typing import Callable, Any

TOOL_CALLS_TOTAL = Counter(
    'tool_calls_total',
    'Total tool calls',
    ['tool_name', 'status']
)

TOOL_CALL_DURATION = Histogram(
    'tool_call_duration_seconds',
    'Tool call duration',
    ['tool_name'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)


def track_tool_call(tool_name: str):
    """工具调用监控装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                raise
            finally:
                TOOL_CALLS_TOTAL.labels(
                    tool_name=tool_name,
                    status=status
                ).inc()
                TOOL_CALL_DURATION.labels(
                    tool_name=tool_name
                ).observe(time.time() - start_time)

        return wrapper
    return decorator
```

#### 4.1.5 外部 API 调用指标

```python
# src/backend/agentchat/services/metrics/external_api_metrics.py

from prometheus_client import Counter, Histogram
import time
from functools import wraps
from typing import Callable, Any

EXTERNAL_API_CALLS_TOTAL = Counter(
    'external_api_calls_total',
    'Total external API calls',
    ['service', 'endpoint', 'status']
)

EXTERNAL_API_DURATION = Histogram(
    'external_api_duration_seconds',
    'External API call duration',
    ['service', 'endpoint'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)


def track_external_api(service: str, endpoint: str = 'default'):
    """外部 API 调用监控装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'

            try:
                result = func(*args, **kwargs)
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

        return wrapper
    return decorator
```

### 4.2 中间件集成

```python
# src/backend/agentchat/middleware/metrics_middleware.py

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram
import time

# API 调用指标
API_CALLS_TOTAL = Counter(
    'api_calls_total',
    'Total API calls',
    ['path', 'method', 'status_code']
)

API_CALL_DURATION = Histogram(
    'api_call_duration_seconds',
    'API call duration',
    ['path', 'method'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """自定义指标中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time
        path = request.url.path
        method = request.method
        status_code = response.status_code

        # 记录指标
        API_CALLS_TOTAL.labels(
            path=path,
            method=method,
            status_code=status_code
        ).inc()

        API_CALL_DURATION.labels(
            path=path,
            method=method
        ).observe(duration)

        return response
```

### 4.3 Docker Compose 部署配置

```yaml
# docker/monitoring/docker-compose.monitoring.yml

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
      - "--storage.tsdb.retention.time=15d"
      - "--web.console.libraries=/etc/prometheus/console_libraries"
      - "--web.console.templates=/etc/prometheus/consoles"
      - "--web.enable-lifecycle"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
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
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_SERVER_ROOT_URL=http://localhost:3000
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    ports:
      - "3000:3000"
    networks:
      - monitoring
    depends_on:
      - prometheus

  # Node Exporter（主机指标）
  node-exporter:
    image: prom/node-exporter:v1.7.0
    container_name: node-exporter
    restart: unless-stopped
    command:
      - "--path.rootfs=/host"
    volumes:
      - /:/host:ro,rslave
    ports:
      - "9100:9100"
    networks:
      - monitoring

  # Redis Exporter
  redis-exporter:
    image: oliver006/redis_exporter:v1.58.0
    container_name: redis-exporter
    restart: unless-stopped
    environment:
      - REDIS_ADDR=redis:6379
    ports:
      - "9121:9121"
    networks:
      - monitoring
      - agentchat

  # MySQL Exporter
  mysql-exporter:
    image: prom/mysqld-exporter:v0.15.1
    container_name: mysql-exporter
    restart: unless-stopped
    environment:
      - DATA_SOURCE_NAME=exporter:exporter_password@(mysql:3306)/
    ports:
      - "9104:9104"
    networks:
      - monitoring
      - agentchat

volumes:
  prometheus_data:
  grafana_data:

networks:
  monitoring:
    driver: bridge
  agentchat:
    external: true
```

### 4.4 Prometheus 配置

```yaml
# docker/monitoring/prometheus/prometheus.yml

global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: agentchat
    replica: "{{.ExternalURL}}"

alerting:
  alertmanagers:
    - static_configs:
        - targets: []

rule_files:
  - "rules/*.yml"

scrape_configs:
  # Prometheus 自身监控
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]

  # FastAPI 应用监控
  - job_name: "agentchat-api"
    static_configs:
      - targets: ["host.docker.internal:7860"]
    metrics_path: "/metrics"
    scrape_interval: 10s

  # Node Exporter（主机监控）
  - job_name: "node-exporter"
    static_configs:
      - targets: ["node-exporter:9100"]

  # Redis Exporter
  - job_name: "redis"
    static_configs:
      - targets: ["redis-exporter:9121"]

  # MySQL Exporter
  - job_name: "mysql"
    static_configs:
      - targets: ["mysql-exporter:9104"]
```

### 4.5 告警规则配置

```yaml
# docker/monitoring/prometheus/rules/agentchat.yml

groups:
  - name: agentchat-alerts
    rules:
      # API 高错误率告警
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(http_requests_total[5m]))
          ) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is above 5% for the last 5 minutes"

      # API 高延迟告警
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, 
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          ) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency detected"
          description: "95th percentile latency is above 5 seconds"

      # LLM 调用失败告警
      - alert: LLMHighErrorRate
        expr: |
          (
            sum(rate(llm_requests_total{status="error"}[10m]))
            /
            sum(rate(llm_requests_total[10m]))
          ) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High LLM error rate"
          description: "LLM API error rate is above 10%"

      # Agent 执行失败告警
      - alert: AgentExecutionFailures
        expr: |
          (
            sum(rate(agent_executions_total{status="error"}[10m]))
            /
            sum(rate(agent_executions_total[10m]))
          ) > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High agent execution failure rate"
          description: "Agent execution failure rate is above 20%"

      # 外部 API 不可用告警
      - alert: ExternalAPIDown
        expr: |
          (
            sum(rate(external_api_calls_total{status="error"}[5m]))
            /
            sum(rate(external_api_calls_total[5m]))
          ) > 0.5
        for: 3m
        labels:
          severity: critical
        annotations:
          summary: "External API experiencing high error rate"
          description: "External API error rate is above 50%"

      # 主机资源告警
      - alert: HighMemoryUsage
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Memory usage is above 85%"

      - alert: HighCPUUsage
        expr: 100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage"
          description: "CPU usage is above 80%"

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space"
          description: "Disk space is below 10%"
```

---

## 5. Grafana 仪表盘设计

### 5.1 仪表盘列表

| 仪表盘名称             | 用途           | 数据源     |
| ---------------------- | -------------- | ---------- |
| **AgentChat Overview** | 系统整体概览   | Prometheus |
| **FastAPI Metrics**    | API 性能详情   | Prometheus |
| **LLM Usage & Cost**   | LLM 调用和成本 | Prometheus |
| **Agent Performance**  | Agent 执行分析 | Prometheus |
| **Infrastructure**     | 基础设施监控   | Prometheus |
| **External Services**  | 外部服务健康度 | Prometheus |

### 5.2 关键面板设计

#### 5.2.1 AgentChat Overview 仪表盘

```json
{
  "dashboard": {
    "title": "AgentChat Overview",
    "panels": [
      {
        "title": "Total Requests (24h)",
        "type": "stat",
        "targets": [
          {
            "expr": "sum(increase(http_requests_total[24h]))"
          }
        ]
      },
      {
        "title": "Error Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "sum(rate(http_requests_total{status=~\"5..\"}[5m])) / sum(rate(http_requests_total[5m]))"
          }
        ],
        "fieldConfig": {
          "thresholds": {
            "steps": [
              { "color": "green", "value": 0 },
              { "color": "yellow", "value": 0.01 },
              { "color": "red", "value": 0.05 }
            ]
          }
        }
      },
      {
        "title": "P95 Latency",
        "type": "stat",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))"
          }
        ]
      },
      {
        "title": "LLM Cost (24h)",
        "type": "stat",
        "targets": [
          {
            "expr": "sum(increase(llm_tokens_cost_total[24h]))"
          }
        ],
        "unit": "currencyUSD"
      },
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "sum(rate(http_requests_total[5m])) by (endpoint)",
            "legendFormat": "{{endpoint}}"
          }
        ]
      },
      {
        "title": "Latency Distribution",
        "type": "heatmap",
        "targets": [
          {
            "expr": "sum(rate(http_request_duration_seconds_bucket[5m])) by (le)"
          }
        ]
      }
    ]
  }
}
```

#### 5.2.2 LLM Usage & Cost 仪表盘

```json
{
  "dashboard": {
    "title": "LLM Usage & Cost",
    "panels": [
      {
        "title": "Token Usage by Model",
        "type": "piechart",
        "targets": [
          {
            "expr": "sum by (model) (llm_tokens_input_total + llm_tokens_output_total)"
          }
        ]
      },
      {
        "title": "Cost by Model (24h)",
        "type": "barchart",
        "targets": [
          {
            "expr": "sum by (model) (increase(llm_tokens_cost_total[24h]))"
          }
        ]
      },
      {
        "title": "LLM Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "sum(rate(llm_requests_total[5m])) by (model)",
            "legendFormat": "{{model}}"
          }
        ]
      },
      {
        "title": "LLM Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, sum(rate(llm_request_duration_seconds_bucket[5m])) by (model, le))",
            "legendFormat": "P95 {{model}}"
          }
        ]
      }
    ]
  }
}
```

---

## 6. 实施计划

### 6.1 阶段划分

| 阶段        | 内容         | 预计工时 | 优先级 |
| ----------- | ------------ | -------- | ------ |
| **Phase 1** | 基础监控搭建 | 4h       | P0     |
| **Phase 2** | 业务指标集成 | 6h       | P0     |
| **Phase 3** | 仪表盘配置   | 4h       | P1     |
| **Phase 4** | 告警配置     | 2h       | P1     |
| **Phase 5** | 文档和培训   | 2h       | P2     |

### 6.2 Phase 1: 基础监控搭建

1. **安装依赖**

   ```bash
   pip install prometheus-client prometheus-fastapi-instrumentator
   ```

2. **FastAPI 集成**
   - 修改 `main.py` 添加自动指标采集
   - 验证 `/metrics` 端点可访问

3. **部署 Prometheus + Grafana**

   ```bash
   cd docker/monitoring
   docker-compose -f docker-compose.monitoring.yml up -d
   ```

4. **验证**
   - 访问 http://localhost:9090 (Prometheus)
   - 访问 http://localhost:3000 (Grafana)
   - 确认 Targets 状态为 UP

### 6.3 Phase 2: 业务指标集成

1. **创建指标模块**
   - `services/metrics/llm_metrics.py`
   - `services/metrics/agent_metrics.py`
   - `services/metrics/tool_metrics.py`
   - `services/metrics/external_api_metrics.py`

2. **集成到业务代码**
   - 在 LLM 调用处添加 `@track_llm_call` 装饰器
   - 在 Agent 执行处添加 `@track_agent_execution` 装饰器
   - 在工具调用处添加 `@track_tool_call` 装饰器

3. **验证指标**
   - 执行一些对话操作
   - 检查 `/metrics` 端点输出
   - 在 Prometheus 中查询指标

### 6.4 Phase 3: 仪表盘配置

1. **配置数据源**
   - 在 Grafana 中添加 Prometheus 数据源

2. **导入仪表盘**
   - 导入 Node Exporter Full 仪表盘
   - 创建自定义 AgentChat 仪表盘

3. **配置面板**
   - 按照 5.2 节设计配置面板

### 6.5 Phase 4: 告警配置

1. **配置告警规则**
   - 创建 `prometheus/rules/agentchat.yml`
   - 配置告警通知渠道（邮件/钉钉/Slack）

2. **测试告警**
   - 模拟错误场景
   - 验证告警触发和通知

---

## 7. 成本估算

### 7.1 资源需求

| 组件          | CPU       | 内存     | 存储      | 说明         |
| ------------- | --------- | -------- | --------- | ------------ |
| Prometheus    | 0.5 核    | 2GB      | 50GB      | 15天数据保留 |
| Grafana       | 0.25 核   | 512MB    | 1GB       | 配置和仪表盘 |
| Node Exporter | 0.1 核    | 128MB    | -         | 主机指标     |
| **总计**      | **~1 核** | **~3GB** | **~51GB** | -            |

### 7.2 存储增长估算

- Prometheus 存储增长：~10GB/月（假设每秒 1000 个样本）
- 建议配置：100GB 存储，保留 30 天数据

---

## 8. 运维指南

### 8.1 日常检查清单

- [ ] Prometheus Targets 页面所有状态为 UP
- [ ] Grafana 仪表盘数据正常刷新
- [ ] 磁盘空间使用率 < 80%
- [ ] 告警通道正常

### 8.2 常见问题排查

| 问题                | 排查步骤             | 解决方案                           |
| ------------------- | -------------------- | ---------------------------------- |
| 指标未采集          | 检查 `/metrics` 端点 | 确认中间件已注册                   |
| Prometheus 无法连接 | 检查网络配置         | 确认 `host.docker.internal` 可访问 |
| 告警未触发          | 检查告警规则语法     | 使用 Prometheus 表达式验证         |
| 仪表盘无数据        | 检查数据源配置       | 确认 Prometheus URL 正确           |

### 8.3 扩展建议

1. **日志聚合**: 接入 Loki 实现日志监控
2. **链路追踪**: 接入 Jaeger 实现分布式追踪
3. **自定义 Exporter**: 为 Milvus 开发专用 Exporter

---

## 9. 附录

### 9.1 参考文档

- [Prometheus 官方文档](https://prometheus.io/docs/)
- [Grafana 官方文档](https://grafana.com/docs/)
- [FastAPI Prometheus 集成](https://github.com/trallnag/prometheus-fastapi-instrumentator)

### 9.2 术语表

| 术语      | 说明                 |
| --------- | -------------------- |
| Counter   | 只增不减的计数器     |
| Gauge     | 可增可减的仪表盘     |
| Histogram | 直方图，用于统计分布 |
| Target    | Prometheus 采集目标  |
| Job       | 一组 Targets 的集合  |

---

**文档版本**: v1.0  
**最后更新**: 2026-03-25  
**作者**: AgentChat Team
