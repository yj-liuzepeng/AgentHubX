import asyncio
import copy
import time
from loguru import logger
from typing import List, Dict, Any
from pydantic import BaseModel
from langgraph.types import Command
from langchain_core.tools import BaseTool
from langchain.agents.middleware import wrap_tool_call, after_model, ToolCallLimitMiddleware
from langgraph.prebuilt.tool_node import ToolCallRequest
from langchain.agents import AgentState, create_agent
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, AIMessageChunk

from agentchat.api.services.usage_stats import UsageStatsService
from agentchat.core.callbacks.usage_metadata import UsageMetadataCallbackHandler
from agentchat.core.models.manager import ModelManager
from agentchat.schema.usage_stats import UsageStatsAgentType
from agentchat.services.mars.mars_tools import MarsTool
from agentchat.services.mars.mars_tools.autobuild import construct_auto_build_prompt


class MarsConfig(BaseModel):
    # Mars 运行时配置，仅保留必要的用户上下文字段
    user_id: str

class MarsEnum:
    # Mars 内置能力枚举，用于业务侧识别任务类型
    AutoBuild_Agent = 1
    Retrieval_Knowledge = 2
    AI_News = 3
    Deep_Search = 4


class MarsAgent:

    def __init__(self, mars_config: MarsConfig):
        # 工具列表在初始化阶段动态构建
        self.mars_tools = None
        # 保存用户上下文，供工具调用注入 user_id
        self.mars_config = mars_config


    async def init_mars_agent(self):
        # 初始化工具、模型与中间件，并构建 ReAct 代理
        self.mars_tools = await self.setup_mars_tools()
        await self.setup_language_model()
        self.middlewares = await self.setup_middlewares()

        self.react_agent = self.setup_react_agent()

    async def setup_mars_tools(self) -> List[BaseTool]:
        # 组装工具列表，并为自动构建工具动态填充可选资源信息
        mars_tools = []
        for name in MarsTool:
            if name == "auto_build_agent":
                auto_build_prompt = await construct_auto_build_prompt(self.mars_config.user_id)
                mars_tool = copy.deepcopy(MarsTool[name])
                mars_tool.description = mars_tool.description.replace("{{{user_configs_placeholder}}}", auto_build_prompt)
                mars_tools.append(mars_tool)
            else:
                mars_tools.append(MarsTool[name])
        return mars_tools

    async def setup_language_model(self):
        # 普通对话模型
        self.conversation_model = ModelManager.get_conversation_model()

        # 支持Function Call模型
        self.tool_invocation_model = ModelManager.get_tool_invocation_model()

        # 推理模型
        self.reasoning_model = ModelManager.get_reasoning_model()

    def setup_react_agent(self):
        # 以对话模型 + 工具 + 中间件构建 ReAct Agent
        return create_agent(
            model=self.conversation_model,
            tools=self.mars_tools,
            middleware=self.middlewares,
        )

    async def setup_middlewares(self):
        # 限制单轮工具调用次数，避免无限调用
        tool_call_limiter = ToolCallLimitMiddleware(
            thread_limit=1
        )

        @after_model
        async def handler_after_model(
            state: AgentState,
            runtime,
        ) -> dict[str, Any] | None:
            # 若模型未触发工具调用，主动通知输出队列结束
            last_message = state["messages"][-1]
            if not last_message.tool_calls:
                await self.mars_output_queue.put(None)
            return None

        @wrap_tool_call
        async def handler_tool_call(
            request: ToolCallRequest,
            handler,
        ) -> ToolMessage | Command:
            # 注入用户ID，确保工具执行具备用户上下文
            request.tool_call["args"].update({"user_id": self.mars_config.user_id})
            tool_result = await handler(request)
            # 将工具返回封装为 ToolMessage 统一输出
            return ToolMessage(content=tool_result, tool_call_id=request.tool_call["id"])

        return [tool_call_limiter, handler_after_model, handler_tool_call]


    async def ainvoke_stream(self, messages: List[BaseMessage]):
        # 用于中断推理模型输出的事件
        self.reasoning_interrupt = asyncio.Event()
        # 用于存放Mars Agent输出的队列
        self.mars_output_queue = asyncio.Queue()

        # 标记是否发生工具调用，用于决定是否继续输出模型自然回复
        self.is_call_tool = False

        # 统计 token 用量的回调
        callback = UsageMetadataCallbackHandler()
        async def run_mars_agent():
            """
            运行Mars Agent，执行工具调用并将其输出放入队列。
            """
            async for token, chunk in self.react_agent.astream(
                input={"messages": messages},
                config={"callbacks": [callback]},
                stream_mode=["custom"]
            ):
                self.is_call_tool = True
                await self.mars_output_queue.put(chunk)

            # 发送结束信号，通知输出消费者退出
            await self.mars_output_queue.put(None)

        async def run_reasoning_model():
            """
            运行推理模型，流式输出思考过程，并随时响应中断事件。
            """
            try:
                response = await self.reasoning_model.astream(messages)
                async for chunk in response:
                    # 在每次输出前检查是否需要中断
                    if self.reasoning_interrupt.is_set():
                        break

                    delta = chunk.choices[0].delta
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                        # 推理内容流式输出
                        yield {
                            "type": "reasoning_chunk",
                            "time": time.time(),
                            "data": delta.reasoning_content
                        }

                    if hasattr(delta, "content") and delta.content:
                        # 若已触发工具调用，则停止自然回复
                        if self.is_call_tool: # 如果调用Mars工具的话 使用工具里面的信息进行回答
                            break
                        else:
                            # 未触发工具调用则直接输出模型内容
                            yield {
                                "type": "response_chunk",
                                "time": time.time(),
                                "data": delta.content
                            }
            except Exception as e:
                logger.error(f"推理模型流式输出错误: {e}")

        # --- 主执行流程 ---

        # 立即返回初始信息
        yield {
            "type": "response_chunk",
            "time": time.time(),
            "data": "#### 现在开始，我会边梳理思路边完成这项任务😊\n"
        }

        # 在后台启动Mars Agent任务
        mars_task = asyncio.create_task(run_mars_agent())

        # 首先，流式输出推理模型的思考过程，直到被中断
        async for reasoning_chunk in run_reasoning_model():
            yield reasoning_chunk

        # 推理过程结束后，开始处理并输出Mars Agent的结果
        while True:
            mars_chunk = await self.mars_output_queue.get()
            if mars_chunk is None:  # 收到结束信号
                break
            yield mars_chunk

        # 确保Mars Agent任务已彻底完成
        await mars_task

    async def _record_agent_token_usage(self, response: AIMessage | AIMessageChunk | BaseMessage, model):
        # 记录模型 token 用量，便于计量与统计
        if response.usage_metadata:
            await UsageStatsService.create_usage_stats(
                model=model,
                user_id=self.mars_config.user_id,
                agent=UsageStatsAgentType.mars_agent,
                input_tokens=response.usage_metadata.get("input_tokens"),
                output_tokens=response.usage_metadata.get("output_tokens")
            )

