"""
外部 API 调用监控指标

监控 Tavily、搜索引擎等外部服务的调用情况
"""

from prometheus_client import Counter, Histogram
import time
from functools import wraps
from typing import Callable, Any
import asyncio

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
    """
    外部 API 调用监控装饰器
    
    用法:
        @track_external_api(service="tavily", endpoint="search")
        async def tavily_search(query: str):
            return await tavily_client.search(query)
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
                EXTERNAL_API_CALLS_TOTAL.labels(
                    service=service,
                    endpoint=endpoint,
                    status=status
                ).inc()
                EXTERNAL_API_DURATION.labels(
                    service=service,
                    endpoint=endpoint
                ).observe(time.time() - start_time)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
