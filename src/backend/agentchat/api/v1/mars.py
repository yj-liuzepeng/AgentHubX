from typing import List

from fastapi import FastAPI, APIRouter, Body, Depends
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from starlette.responses import StreamingResponse

from agentchat.api.services.user import UserPayload, get_login_user
from agentchat.prompts.mars import Mars_System_Prompt
from agentchat.schema.usage_stats import UsageStatsAgentType
from agentchat.services.mars.mars_agent import MarsAgent, MarsConfig
from agentchat.services.mars.mars_tools.autobuild import construct_auto_build_prompt
from agentchat.services.memory.client import memory_client
from agentchat.utils.contexts import set_user_id_context, set_agent_name_context

router = APIRouter(tags=["Mars"])

class MarsExampleEnum:
    """Mars 示例场景枚举定义"""
    Autobuild_Agent = 1  # 自动构建智能体
    Deep_Search = 2      # 深度搜索
    AI_News = 3          # AI 日报
    Query_Knowledge = 4  # 知识库问答

@router.post("/mars/chat")
async def chat_mars(user_input: str = Body(..., description="用户输入", embed=True),
                    login_user: UserPayload = Depends(get_login_user)):
    """
    Mars 智能体对话接口
    
    处理用户与 Mars 智能体的交互流程：
    1. 初始化上下文和 Agent 环境
    2. 检索用户相关的记忆信息 (RAG)
    3. 调用 Mars Agent 执行推理与工具调用
    4. 流式返回结果 (SSE) 并异步保存对话记忆
    """
    
    # 1. 设置全局上下文变量，用于日志追踪和用量统计
    set_user_id_context(login_user.user_id)
    set_agent_name_context(UsageStatsAgentType.mars_agent)

    # 2. 初始化 Mars Agent 实例与配置
    mars_config = MarsConfig(user_id=login_user.user_id)
    mars_agent = MarsAgent(mars_config)

    # 异步初始化：加载必要的工具、模型和中间件
    await mars_agent.init_mars_agent()

    # 3. 记忆检索 (RAG)：根据用户输入从向量数据库中查找相关历史记忆
    memory_messages = await memory_client.search(query=user_input, user_id=login_user.user_id)
    # 格式化记忆内容，准备注入到 System Prompt 中
    memory_content = str([f"- {msg.get('memory', '')} \n" for msg in memory_messages.get('results', [])])

    # 4. 构建消息列表：包含带有记忆增强的系统提示词和用户输入
    messages: List[BaseMessage] = [
        SystemMessage(content=Mars_System_Prompt.format(memory_content=memory_content)),
        HumanMessage(content=user_input)
    ]

    async def general_generate():
        """
        生成器函数：处理流式响应并管理记忆存储
        """
        final_response = ""
        # 调用 Mars Agent 的流式接口，获取推理过程(Reasoning)和结果(Response)
        async for chunk in mars_agent.ainvoke_stream(messages):
            # 将 chunk 数据封装为 SSE (Server-Sent Events) 格式发送给前端
            yield f"data: {chunk}\n\n"
            
            # 累积最终回复内容，用于后续存储记忆
            # 注意：这里只收集类型为 'response_chunk' 的文本内容
            if chunk.get("type") == "response_chunk":
                final_response += chunk.get("data", "")

        # 5. 对话结束后的收尾：将本次用户输入和助手回复存入记忆库
        await memory_client.add(
            user_id=login_user.user_id, 
            messages=[
                {"role": "user", "content": user_input}, 
                {"role": "assistant", "content": final_response}
            ]
        )

    # 返回流式响应，MIME 类型设置为 text/event-stream
    return StreamingResponse(general_generate(), media_type="text/event-stream")

@router.post("/mars/example")
async def chat_mars_example(example_id: int = Body(..., description="例子ID", embed=True),
                            login_user: UserPayload = Depends(get_login_user)):
    """
    Mars 示例场景演示接口
    
    根据预设的 example_id 触发特定的演示任务（如自动构建、深度搜索等）。
    与普通聊天接口的区别：
    1. 使用预设的用户输入 Prompt
    2. 不检索历史记忆 (memory_content 为空)
    3. 不保存本次对话到记忆库
    """
    
    # 1. 设置全局上下文
    set_user_id_context(login_user.user_id)
    set_agent_name_context(UsageStatsAgentType.mars_agent)

    # 2. 初始化 Mars Agent
    mars_config = MarsConfig(user_id=login_user.user_id)
    mars_agent = MarsAgent(mars_config)

    await mars_agent.init_mars_agent()

    # 3. 根据 example_id 匹配预设的演示 Prompt
    user_input = ""
    if example_id == MarsExampleEnum.Autobuild_Agent:
        user_input = "帮我生成一个智能体，它可以给我预报每天的天气情况并且可以帮我生成图片，名称跟描述的话请你给他起一个吧，智能体名称字数要处于2-10字之间"
    elif example_id == MarsExampleEnum.AI_News:
        user_input = "请帮我生成一份今天的AI日报，然后总结之后提供给我一个AI日报的图片，不需要详细内容"
    elif example_id == MarsExampleEnum.Query_Knowledge:
        user_input = "请你帮我查询我所有的知识库，然后告诉我知识库中都是什么信息，最好还有图表展示什么的。"
    elif example_id == MarsExampleEnum.Deep_Search:
        user_input = "使用深度搜索查泰山游玩攻略"

    # 4. 构建消息列表（示例模式下 memory_content 传入空字符串）
    messages: List[BaseMessage] = [
        SystemMessage(content=Mars_System_Prompt.format(memory_content="")),
        HumanMessage(content=user_input)
    ]

    async def general_generate():
        """
        生成器函数：仅负责流式输出，不记录记忆
        """
        async for chunk in mars_agent.ainvoke_stream(messages):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(general_generate(), media_type="text/event-stream")
