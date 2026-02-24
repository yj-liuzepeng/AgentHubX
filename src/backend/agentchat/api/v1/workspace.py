import json
from loguru import logger
from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from starlette.responses import StreamingResponse

from agentchat.api.services.llm import LLMService
from agentchat.api.services.mcp_server import MCPService
from agentchat.api.services.tool import ToolService
from agentchat.api.services.workspace_session import WorkSpaceSessionService
from agentchat.prompts.chat import SYSTEM_PROMPT
from agentchat.schema.schemas import resp_200
from agentchat.schema.usage_stats import UsageStatsAgentType
from agentchat.schema.workspace import WorkSpaceSimpleTask
from agentchat.api.services.user import UserPayload, get_login_user
from agentchat.services.workspace.simple_agent import WorkSpaceSimpleAgent, MCPConfig
from agentchat.services.model_selector import ModelSelector
from agentchat.utils.contexts import set_user_id_context, set_agent_name_context
from agentchat.utils.convert import convert_mcp_config

router = APIRouter(prefix="/workspace", tags=["WorkSpace"])


@router.get("/plugins", summary="获取工作台的可用插件")
async def get_workspace_plugins(login_user: UserPayload = Depends(get_login_user)):
    results = await ToolService.get_visible_tool_by_user(login_user.user_id)
    return resp_200(data=results)


@router.get("/session", summary="获取工作台所有会话列表")
async def get_workspace_sessions(login_user: UserPayload = Depends(get_login_user)):
    results = await WorkSpaceSessionService.get_workspace_sessions(login_user.user_id)
    return resp_200(data=results)


@router.post("/session", summary="创建工作台会话")
async def create_workspace_session(*,
                                   title: str = "",
                                   contexts: dict = {},
                                   login_user: UserPayload = Depends(get_login_user)):
    pass


@router.post("/session/{session_id}", summary="进入工作台会话")
async def workspace_session_info(session_id: str,
                                 login_user: UserPayload = Depends(get_login_user)):
    try:
        result = await WorkSpaceSessionService.get_workspace_session_from_id(session_id, login_user.user_id)
        return resp_200(data=result)
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))


@router.delete("/session", summary="删除工作台的会话")
async def create_workspace_session(session_id: str,
                                   login_user: UserPayload = Depends(get_login_user)):
    try:
        await WorkSpaceSessionService.delete_workspace_session([session_id], login_user.user_id)
        return resp_200()
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))


@router.post("/simple/chat", summary="工作台日常对话")
async def workspace_simple_chat(simple_task: WorkSpaceSimpleTask,
                                login_user: UserPayload = Depends(get_login_user)):
    # 设置全局变量统计调用
    set_user_id_context(login_user.user_id)
    set_agent_name_context(UsageStatsAgentType.simple_agent)

    logger.info(f"=== WORKSPACE API 入口开始 ===")
    logger.info(f"用户ID: {login_user.user_id}")
    logger.info(f"会话ID: {simple_task.session_id}")
    logger.info(f"用户查询: {simple_task.query}")
    logger.info(f"选择的插件: {simple_task.plugins}")
    logger.info(f"MCP服务器: {simple_task.mcp_servers}")
    logger.info(f"模型ID: {simple_task.model_id}")

    if simple_task.model_id == "auto":
        logger.info("=== 启动自动模型选择流程 ===")
        try:
            # 获取用户可见的所有模型
            visible_llms_data = await LLMService.get_visible_llm(login_user.user_id)
            # 提取 LLM 类型的模型列表
            available_models = visible_llms_data.get("LLM", [])
            logger.info(f"获取到用户可见LLM模型数量: {len(available_models)}")
            
            # 使用 ModelSelector 选择模型
            selected_id = ModelSelector.select_model(simple_task.query, available_models)
            
            if selected_id:
                simple_task.model_id = selected_id
                logger.info(f"=== 自动选择完成，最终使用模型ID: {simple_task.model_id} ===")
            else:
                logger.error("自动模式未能选择有效模型，可能没有可用模型")
        except Exception as e:
            logger.error(f"自动模型选择过程出错: {e}")

    model_config = await LLMService.get_llm_by_id(simple_task.model_id)
    logger.info(f"获取模型配置: {model_config['model']}")

    servers_config = []
    for mcp_id in simple_task.mcp_servers:
        mcp_server = await MCPService.get_mcp_server_from_id(mcp_id)
        servers_config.append(
            MCPConfig(**mcp_server)
        )
    logger.info(f"MCP服务器配置数量: {len(servers_config)}")

    logger.info("开始创建SimpleAgent实例...")
    simple_agent = WorkSpaceSimpleAgent(
        model_config={
            "model": model_config["model"],
            "base_url": model_config["base_url"],
            "api_key": model_config["api_key"],
            "user_id": login_user.user_id,
        },
        user_id=login_user.user_id,
        session_id=simple_task.session_id,
        plugins=simple_task.plugins,
        mcp_configs=servers_config
    )
    logger.info("SimpleAgent实例创建完成")

    workspace_session = await WorkSpaceSessionService.get_workspace_session_from_id(simple_task.session_id, login_user.user_id)
    history_messages = []
    if workspace_session:
        contexts = workspace_session.get("contexts", [])
        history_messages = [
            f"query: {message.get("query")}, answer: {message.get("answer")}\n" for message in contexts]
        logger.info(f"获取历史会话: 包含 {len(history_messages)} 条历史记录")
    else:
        logger.info("未找到历史会话，创建新会话")

    async def general_generate():
        # 使用包含工具信息的系统消息
        system_message = SYSTEM_PROMPT.format(history=str(history_messages))
        logger.info(f"=== 开始生成响应 ===")
        logger.info(f"用户输入内容: {simple_task.query}")
        logger.info(f"历史上下文数量: {len(history_messages)}")
        logger.info(f"系统提示词: {system_message[:200]}...")  # 只打印前200字符避免日志过长

        try:
            async for chunk in simple_agent.astream([SystemMessage(content=system_message), HumanMessage(content=simple_task.query)]):
                # logger.debug(f"收到chunk: {chunk}")
                # chunk 已经是 dict: {"event": "task_result", "data": {"message": "..."}}
                # 需要 JSON 序列化后作为 SSE 的 data 字段
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            logger.info("=== 响应生成完成 ===")
        except Exception as e:
            logger.error(f"生成响应时出错: {e}")
            error_chunk = {
                "event": "error",
                "data": {
                    "message": "抱歉，处理您的请求时出现了错误。请稍后重试。"
                }
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"

    logger.info("=== WORKSPACE API 入口处理完成，返回StreamingResponse ===")
    return StreamingResponse(
        general_generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
