"""
工具调用监控指标

监控各类工具（搜索、数据库查询等）的调用情况
"""

from prometheus_client import Counter, Histogram
import time
from functools import wraps
from typing import Callable, Any
import asyncio

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
    """
    工具调用监控装饰器

    用法:
        @track_tool_call(tool_name="tavily_search")
        async def search(query: str):
            return await tavily.search(query)
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
                TOOL_CALLS_TOTAL.labels(
                    tool_name=tool_name,
                    status=status
                ).inc()
                TOOL_CALL_DURATION.labels(
                    tool_name=tool_name
                ).observe(time.time() - start_time)

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
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

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
