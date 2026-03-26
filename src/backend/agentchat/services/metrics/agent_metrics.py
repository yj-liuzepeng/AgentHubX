"""
Agent 执行监控指标

监控 Agent 的执行次数、耗时、步骤数等
"""

from prometheus_client import Counter, Histogram, Gauge
import time
from functools import wraps
from typing import Callable, Any
import asyncio

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
    """
    Agent 执行监控装饰器
    
    用法:
        @track_agent_execution(agent_type="lingseek")
        async def execute_agent(query: str):
            return await agent.run(query)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = 'success'
            
            AGENT_ACTIVE_EXECUTIONS.labels(agent_type=agent_type).inc()
            
            try:
                result = await func(*args, **kwargs)
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
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
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
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def track_agent_step(agent_type: str):
    """
    Agent 步骤监控装饰器
    
    用于监控 Agent 内部每个步骤的执行
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            AGENT_STEPS_TOTAL.labels(agent_type=agent_type).inc()
            return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            AGENT_STEPS_TOTAL.labels(agent_type=agent_type).inc()
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
