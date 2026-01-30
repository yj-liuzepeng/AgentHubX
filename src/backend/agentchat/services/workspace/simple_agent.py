import copy
import asyncio
from loguru import logger
from typing import List, Dict, Any
from pydantic import BaseModel
from langgraph.types import Command
from langgraph.prebuilt.tool_node import ToolCallRequest
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, AIMessageChunk

from agentchat.core.callbacks import usage_metadata_callback
from agentchat.tools import WorkSpacePlugins
from agentchat.schema.usage_stats import UsageStatsAgentType
from agentchat.schema.workspace import WorkSpaceAgents
from agentchat.api.services.tool import ToolService
from agentchat.services.mcp.manager import MCPManager
from agentchat.prompts.chat import GenerateTitlePrompt
from agentchat.utils.convert import convert_mcp_config
from agentchat.core.models.manager import ModelManager
from agentchat.prompts.chat import DEFAULT_CALL_PROMPT
from agentchat.api.services.mcp_user_config import MCPUserConfigService
from agentchat.api.services.usage_stats import UsageStatsService
from agentchat.api.services.workspace_session import WorkSpaceSessionService
from agentchat.api.services.usage_stats import UsageStatsService
from agentchat.api.services.workspace_session import WorkSpaceSessionService
from agentchat.database.models.workspace_session import WorkSpaceSessionCreate, WorkSpaceSessionContext


class MCPConfig(BaseModel):
    url: str
    type: str = "sse"
    tools: List[str] = []
    server_name: str
    mcp_server_id: str


class WorkSpaceSimpleAgent:
    """

    Sub-agent that can invoke **both user-provided plugin functions and MCP tools**.  It analyses the
    current conversation, decides which tool(s) should be run, performs the calls asynchronously and
    pushes progress/result events back to the main :class:`mars_agent.agent.MarsAgent`.

    Responsibilities
    ---------------
    1. Select appropriate plugin or MCP tool according to conversation context.
    2. Execute the tool in an asynchronous, non-blocking way.
    3. Report every progress, success or error through the shared ``EventManager``.
    4. **Does not generate any LLM response** – that task belongs to the main agent.

    Usage
    -----
    ``SimpleAgent`` instances are automatically created by.
    End-users rarely need to touch this class directly.
    """

    def __init__(self,
                 model_config,
                 user_id: str,
                 session_id: str,
                 plugins: List[str] = [],
                 mcp_configs: List[MCPConfig] = []):

        # Simple-agent only needs tool calling model, not conversation model
        self.model = ModelManager.get_user_model(**model_config)
        self.plugin_tools = []
        self.mcp_tools = []
        self.mcp_configs = mcp_configs
        self.tools = []
        self.mcp_manager = MCPManager(convert_mcp_config(
            [mcp_config.model_dump() for mcp_config in mcp_configs]))
        self.plugins = plugins
        self.session_id = session_id

        self.user_id = user_id

        # Find user config by server name
        self.server_dict: dict[str, Any] = {}

        # Initialize state management
        self._initialized = False

    async def init_simple_agent(self):
        """Initialize sub-agent - with resource management"""
        try:
            logger.info("=== SimpleAgent 初始化开始 ===")
            if self._initialized:
                logger.info("Simple Agent already initialized")
                return

            logger.info(f"插件列表: {self.plugins}")
            logger.info(f"MCP配置数量: {len(self.mcp_configs)}")

            logger.info("开始设置MCP工具...")
            await self.setup_mcp_tools()

            logger.info("开始设置插件工具...")
            await self.setup_plugin_tools()

            logger.info("开始设置中间件...")
            self.middlewares = await self.setup_middlewares()

            self.tools = self.plugin_tools + self.mcp_tools
            logger.info(
                f"工具初始化完成 - 插件工具: {len(self.plugin_tools)}, MCP工具: {len(self.mcp_tools)}, 总计: {len(self.tools)}")

            self._initialized = True
            self.react_agent = self.setup_react_agent()

            logger.info("Simple Agent initialized successfully")
            logger.info("=== SimpleAgent 初始化完成 ===")
        except Exception as err:
            logger.error(f"Failed to initialize Simple Agent: {err}")
            raise

    def setup_react_agent(self):
        return create_agent(
            model=self.model,
            tools=self.tools,
            middleware=self.middlewares,
            system_prompt=DEFAULT_CALL_PROMPT
        )

    async def setup_middlewares(self):
        @wrap_tool_call
        async def handler_call_mcp_tool(
            request: ToolCallRequest,
            handler
        ) -> ToolMessage | Command:
            logger.info(f"处理工具调用: {request.tool_call['name']}")
            logger.info(f"工具参数: {request.tool_call['args']}")

            try:
                if self.is_mcp_tool(request.tool_call["name"]):
                    # 针对鉴权的MCP Server需要用户的单独配置，例如飞书、邮箱
                    logger.info(f"检测到MCP工具调用: {request.tool_call['name']}")
                    mcp_config = await MCPUserConfigService.get_mcp_user_config(self.user_id, self.get_mcp_id_by_tool(request.tool_call["name"]))
                    request.tool_call["args"].update(mcp_config)
                    logger.info(f"更新MCP工具参数: {request.tool_call['args']}")
                    tool_result = await handler(request)
                    logger.info(f"MCP工具执行成功: {request.tool_call['name']}")
                else:
                    logger.info(f"处理插件工具调用: {request.tool_call['name']}")
                    tool_result = await handler(request)
                    logger.info(f"插件工具执行成功: {request.tool_call['name']}")

                logger.info(f"工具返回结果长度: {len(str(tool_result))} 字符")
                return tool_result

            except Exception as e:
                logger.error(f"工具执行失败: {request.tool_call['name']} - 错误: {e}")
                # 返回工具执行失败的友好提示
                error_content = f"工具 {request.tool_call['name']} 执行失败: {str(e)}"
                return ToolMessage(
                    content=error_content,
                    name=request.tool_call["name"],
                    tool_call_id=request.tool_call.get("id")
                )

        return [handler_call_mcp_tool]

    async def setup_mcp_tools(self):
        """Initialize MCP tools - with error handling"""
        if not self.mcp_configs:
            self.mcp_tools = []
            logger.info("没有MCP配置，跳过MCP工具初始化")
            return

        try:
            logger.info(f"开始连接MCP服务器，配置数量: {len(self.mcp_configs)}")
            # Establish connection with MCP Server
            self.mcp_tools = await self.mcp_manager.get_mcp_tools()
            logger.info(f"成功获取 {len(self.mcp_tools)} 个MCP工具")

            mcp_servers_info = await self.mcp_manager.show_mcp_tools()
            self.server_dict = {server_name: [tool["name"] for tool in tools_info] for server_name, tools_info in
                                mcp_servers_info.items()}

            logger.info(f"MCP服务器详情: {list(self.server_dict.keys())}")
            logger.info(
                f"Loaded {len(self.mcp_tools)} MCP tools from MCP servers")

        except Exception as err:
            logger.error(f"Failed to initialize MCP tools: {err}")
            self.mcp_tools = []

    async def setup_plugin_tools(self):
        """Initialize plugin tools - with error handling"""
        try:
            logger.info(f"开始初始化插件工具，插件ID列表: {self.plugins}")
            tools_name = await ToolService.get_tool_name_by_id(self.plugins)
            logger.info(f"获取到的工具名称: {tools_name}")

            for name in tools_name:
                if name in WorkSpacePlugins:
                    tool_func = WorkSpacePlugins[name]
                    self.plugin_tools.append(tool_func)
                    logger.info(
                        f"成功加载插件工具: {name} - {tool_func.__doc__[:50]}...")
                else:
                    logger.warning(f"工具 {name} 在WorkSpacePlugins中未找到")

            logger.info(f"Loaded {len(self.plugin_tools)} plugin tools")
            logger.info(
                f"已加载的插件工具: {[tool.name for tool in self.plugin_tools]}")

        except Exception as err:
            logger.error(f"Failed to initialize plugin tools: {err}")
            self.plugin_tools = []

    async def ainvoke(self, messages: List[BaseMessage]):
        """Sub-agent tool execution - only return tool execution results, no model reply"""
        if not self._initialized:
            await self.init_simple_agent()

        try:
            react_agent_task = None
            if self.tools and len(self.tools) != 0:
                react_agent_task = asyncio.create_task(
                    self.react_agent.ainvoke({"messages": messages}))

            # Wait for tool execution to complete
            if react_agent_task:
                results = await react_agent_task
                # Remove messages that didn't hit tools
                messages = results["messages"][:-1]

                messages = [msg for msg in messages if
                            isinstance(msg, ToolMessage) or (isinstance(msg, AIMessage) and msg.tool_calls)]

                return messages
            else:
                return []

        except Exception as err:
            return []

    async def _generate_title(self, query):
        session = await WorkSpaceSessionService.get_workspace_session_from_id(self.session_id, self.user_id)
        if session:
            return session.get("title")
        title_prompt = GenerateTitlePrompt.format(query=query)
        response = await self.model.ainvoke(title_prompt, config={"callbacks": [usage_metadata_callback]})
        return response.content

    async def _add_workspace_session(self, title, contexts: WorkSpaceSessionContext):
        session = await WorkSpaceSessionService.get_workspace_session_from_id(self.session_id, self.user_id)
        if session:
            await WorkSpaceSessionService.update_workspace_session_contexts(
                session_id=self.session_id,
                session_context=contexts.model_dump()
            )
        else:
            await WorkSpaceSessionService.create_workspace_session(
                WorkSpaceSessionCreate(
                    title=title,
                    user_id=self.user_id,
                    session_id=self.session_id,
                    contexts=[contexts.model_dump()],
                    agent=WorkSpaceAgents.SimpleAgent.value))

    async def astream(self, messages: List[BaseMessage]):
        if not self._initialized:
            logger.info("SimpleAgent未初始化，开始初始化...")
            await self.init_simple_agent()
        else:
            logger.info("SimpleAgent已初始化，跳过初始化步骤")

        user_messages = copy.deepcopy(messages)
        final_answer = ""

        logger.info(f"=== SimpleAgent 开始处理流式请求 ===")
        logger.info(f"用户消息数量: {len(messages)}")
        logger.info(f"最后一条用户消息: {messages[-1].content[:100]}...")

        generate_title_task = asyncio.create_task(
            self._generate_title(user_messages[-1].content))
        try:
            react_agent_task = None
            if self.tools and len(self.tools) != 0:
                logger.info(f"检测到 {len(self.tools)} 个可用工具，开始ReAct代理处理")
                logger.info(f"可用工具列表: {[tool.name for tool in self.tools]}")
                react_agent_task = asyncio.create_task(self.react_agent.ainvoke(
                    input={"messages": messages}, config={"callbacks": [usage_metadata_callback]}))
            else:
                logger.info("没有可用工具，跳过工具调用阶段")

            # Wait for tool execution to complete
            if react_agent_task:
                logger.info("等待工具执行完成...")
                results = await react_agent_task
                logger.info(f"工具执行完成，结果包含 {len(results['messages'])} 条消息")

                # Remove messages that didn't hit tools
                messages = results["messages"][:-1]
                logger.info(f"过滤后剩余 {len(messages)} 条工具相关消息")

                messages = [msg for msg in messages if
                            isinstance(msg, ToolMessage) or (isinstance(msg, AIMessage) and msg.tool_calls)]
                logger.info(f"最终工具消息数量: {len(messages)}")

                # 打印工具调用详情
                for msg in messages:
                    if isinstance(msg, ToolMessage):
                        logger.info(
                            f"工具执行结果: {msg.name} - 内容长度: {len(msg.content)}")

                        # 检查是否是图片生成工具，如果是则直接返回结果
                        if msg.name == "text_to_image" and "![" in msg.content and "](" in msg.content:
                            logger.info(
                                f"检测到图片生成工具返回，直接显示图片: {msg.content[:50]}...")
                            yield {
                                "event": "task_result",
                                "data": {
                                    "message": msg.content
                                }
                            }
                            return  # 直接返回，不再让模型重新生成

                        # 更通用的图片检测：如果工具返回包含Markdown图片语法，直接显示
                        elif "![" in msg.content and "](" in msg.content and "http" in msg.content:
                            logger.info(
                                f"检测到工具返回包含图片链接，直接显示: {msg.content[:50]}...")
                            yield {
                                "event": "task_result",
                                "data": {
                                    "message": msg.content
                                }
                            }
                            return  # 直接返回，不再让模型重新生成

                    elif isinstance(msg, AIMessage) and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            logger.info(
                                f"工具调用: {tool_call['name']} - 参数: {tool_call['args']}")
        except Exception as err:
            logger.error(f"工具执行阶段出错: {err}")
            # 检查是否是内容审查错误
            error_str = str(err)
            if "DataInspectionFailed" in error_str or "inappropriate content" in error_str:
                logger.error("检测到内容审查错误，可能是提示词或输入内容触发审查")
                logger.info("尝试使用简化提示词重新处理...")

                # 创建简化版本的提示词
                simple_messages = [
                    HumanMessage(content=user_messages[-1].content)
                ]

                logger.info("使用简化消息重新生成响应...")
                try:
                    simple_final_answer = ""
                    async for chunk in self.model.astream(input=simple_messages, config={"callbacks": [usage_metadata_callback]}):
                        simple_final_answer += chunk.content
                        yield {
                            "event": "task_result",
                            "data": {
                                "message": chunk.content
                            }
                        }

                    # 保存简化版本的会话
                    await self._add_workspace_session(
                        title="简化对话",
                        contexts=WorkSpaceSessionContext(
                            query=user_messages[-1].content,
                            answer=simple_final_answer
                        ))
                    logger.info("简化版本响应生成完成")
                    return

                except Exception as simple_err:
                    logger.error(f"简化版本也失败: {simple_err}")
                    # 返回友好的错误消息
                    error_message = "抱歉，当前请求无法处理。请尝试简化您的问题或联系技术支持。"
                    yield {
                        "event": "task_result",
                        "data": {
                            "message": error_message
                        }
                    }
                    return

            # 对于其他错误，返回通用错误消息
            logger.error(f"其他类型的错误: {err}")
            error_message = "抱歉，处理您的请求时出现了错误。请稍后重试。"
            yield {
                "event": "task_result",
                "data": {
                    "message": error_message
                }
            }
            return

        messages = user_messages + messages
        logger.info(f"合并用户消息和工具消息，总计: {len(messages)} 条消息")

        logger.info("开始生成最终响应...")
        chunk_count = 0
        async for chunk in self.model.astream(input=messages, config={"callbacks": [usage_metadata_callback]}):
            chunk_count += 1
            final_answer += chunk.content
            yield {
                "event": "task_result",
                "data": {
                    "message": chunk.content
                }
            }
        logger.info(
            f"流式响应完成，共生成 {chunk_count} 个chunk，总长度: {len(final_answer)} 字符")

        await generate_title_task
        title = generate_title_task.result() if generate_title_task.done() else None
        logger.info(f"生成会话标题: {title}")

        logger.info("开始保存会话上下文...")
        await self._add_workspace_session(
            title=title,
            contexts=WorkSpaceSessionContext(
                query=user_messages[-1].content,
                answer=final_answer
            ))
        logger.info("会话上下文保存完成")
        logger.info("=== SimpleAgent 流式请求处理完成 ===")

    async def _record_agent_token_usage(self, response: AIMessage | AIMessageChunk | BaseMessage, model):
        if response.usage_metadata:
            await UsageStatsService.create_usage_stats(
                model=model,
                user_id=self.user_id,
                agent=UsageStatsAgentType.simple_agent,
                input_tokens=response.usage_metadata.get("input_tokens"),
                output_tokens=response.usage_metadata.get("output_tokens")
            )

    def is_mcp_tool(self, tool_name: str):
        """Determine if it's an MCP tool and return the corresponding tool instance"""
        mcp_names = [tool.name for tool in self.mcp_tools]
        plugin_names = [tool.name for tool in self.plugin_tools]

        if tool_name in mcp_names:
            return True
        elif tool_name in plugin_names:
            return False
        else:
            raise ValueError(
                f"Tool '{tool_name}' not found in either MCP or plugin tools.")

    def get_mcp_id_by_tool(self, tool_name):
        for server_name, tools in self.server_dict.items():
            if tool_name in tools:
                for config in self.mcp_configs:
                    if server_name == config.server_name:
                        return config.mcp_server_id
        return None
