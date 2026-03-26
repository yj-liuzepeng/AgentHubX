"""
LLM 调用监控指标

监控 LLM API 的调用次数、延迟、Token 使用量和成本
"""

from prometheus_client import Counter, Histogram
import time
from functools import wraps
from typing import Callable, Any, Optional

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
    'gpt-4o': {'input': 0.005, 'output': 0.015},
    'gpt-4o-mini': {'input': 0.00015, 'output': 0.0006},
    'gpt-3.5-turbo': {'input': 0.0005, 'output': 0.0015},
    'qwen-max': {'input': 0.0035, 'output': 0.007},
    'qwen-plus': {'input': 0.0008, 'output': 0.002},
    'qwen-turbo': {'input': 0.0003, 'output': 0.0006},
    'claude-3-opus': {'input': 0.015, 'output': 0.075},
    'claude-3-sonnet': {'input': 0.003, 'output': 0.015},
    'claude-3-haiku': {'input': 0.00025, 'output': 0.00125},
}


def _extract_tokens(result: Any) -> tuple[int, int]:
    """从 LLM 响应中提取 Token 使用量"""
    input_tokens = 0
    output_tokens = 0
    
    # 处理 LangChain 响应格式
    if hasattr(result, 'usage_metadata'):
        metadata = result.usage_metadata
        input_tokens = metadata.get('input_tokens', 0)
        output_tokens = metadata.get('output_tokens', 0)
    elif hasattr(result, 'usage'):
        usage = result.usage
        if isinstance(usage, dict):
            input_tokens = usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
    
    # 处理 OpenAI 格式
    elif isinstance(result, dict):
        usage = result.get('usage', {})
        input_tokens = usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
    
    return input_tokens, output_tokens


def track_llm_call(model: str, provider: str = 'unknown'):
    """
    LLM 调用监控装饰器
    
    用法:
        @track_llm_call(model="gpt-4", provider="openai")
        async def call_llm(prompt: str):
            return await llm.ainvoke(prompt)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'
            
            try:
                result = await func(*args, **kwargs)
                
                # 提取 Token 使用量
                input_tokens, output_tokens = _extract_tokens(result)
                
                # 记录 Token 指标
                if input_tokens > 0:
                    LLM_TOKENS_INPUT.labels(model=model, provider=provider).inc(input_tokens)
                if output_tokens > 0:
                    LLM_TOKENS_OUTPUT.labels(model=model, provider=provider).inc(output_tokens)
                
                # 计算成本
                cost_config = TOKEN_COSTS.get(model, {'input': 0, 'output': 0})
                cost = (input_tokens * cost_config['input'] + 
                       output_tokens * cost_config['output']) / 1000
                if cost > 0:
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
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'
            
            try:
                result = func(*args, **kwargs)
                
                # 提取 Token 使用量
                input_tokens, output_tokens = _extract_tokens(result)
                
                # 记录 Token 指标
                if input_tokens > 0:
                    LLM_TOKENS_INPUT.labels(model=model, provider=provider).inc(input_tokens)
                if output_tokens > 0:
                    LLM_TOKENS_OUTPUT.labels(model=model, provider=provider).inc(output_tokens)
                
                # 计算成本
                cost_config = TOKEN_COSTS.get(model, {'input': 0, 'output': 0})
                cost = (input_tokens * cost_config['input'] + 
                       output_tokens * cost_config['output']) / 1000
                if cost > 0:
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
        
        # 根据函数类型返回对应的 wrapper
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def record_llm_tokens(model: str, provider: str, input_tokens: int, output_tokens: int):
    """
    手动记录 LLM Token 使用量
    
    用于无法使用装饰器的场景
    """
    LLM_TOKENS_INPUT.labels(model=model, provider=provider).inc(input_tokens)
    LLM_TOKENS_OUTPUT.labels(model=model, provider=provider).inc(output_tokens)
    
    # 计算成本
    cost_config = TOKEN_COSTS.get(model, {'input': 0, 'output': 0})
    cost = (input_tokens * cost_config['input'] + 
           output_tokens * cost_config['output']) / 1000
    LLM_TOKENS_COST.labels(model=model, provider=provider).inc(cost)
