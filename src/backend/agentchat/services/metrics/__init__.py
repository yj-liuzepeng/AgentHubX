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
