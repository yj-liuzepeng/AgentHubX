from agentchat.database import SystemUser
from agentchat.database.models.user import AdminUser
from agentchat.database.dao.tool import ToolDao
from typing import List, Union
from agentchat.schema.schemas import resp_200, resp_500
from loguru import logger


class ToolService:

    @classmethod
    async def create_tool(cls, user_id: str, zh_name: str, en_name: str, description: str, logo_url: str):
        try:
            await ToolDao.create_tool(user_id=user_id, zh_name=zh_name, logo_url=logo_url,
                                      en_name=en_name, description=description)
        except Exception as err:
            raise ValueError(f'Create Tool Appear Error: {err}')

    @classmethod
    async def delete_tool(cls, tool_id: str):
        try:
            await ToolDao.delete_tool_by_id(tool_id=tool_id)
        except Exception as err:
            raise ValueError(f'Delete Tool Appear Error: {err}')

    @classmethod
    async def verify_user_permission(cls, tool_id, user_id):
        logger.info(
            f"权限验证 - tool_id: {tool_id}, user_id: {user_id}, AdminUser: {AdminUser}")
        logger.info(
            f"user_id类型: {type(user_id)}, AdminUser类型: {type(AdminUser)}")

        # 获取工具的所有者ID
        tool_user_id = await cls._get_user_by_tool_id(tool_id)
        logger.info(f"工具所有者ID: {tool_user_id}, 类型: {type(tool_user_id)}")

        # 检查是否是管理员或工具所有者
        if str(user_id) == str(AdminUser) or str(user_id) == str(tool_user_id):
            logger.info("权限验证通过")
            pass
        else:
            logger.error(f"权限验证失败 - 当前用户: {user_id}, 工具所有者: {tool_user_id}")
            logger.error(
                f"字符串比较结果 - user_id==AdminUser: {str(user_id) == str(AdminUser)}, user_id==tool_user_id: {str(user_id) == str(tool_user_id)}")
            raise ValueError("没有权限访问")

    @classmethod
    async def update_tool(cls, tool_id: str, zh_name: str,
                          en_name: str, description: str, logo_url: str):
        try:
            await ToolDao.update_tool_by_id(tool_id=tool_id, zh_name=zh_name, logo_url=logo_url,
                                            en_name=en_name, description=description)
        except Exception as err:
            raise ValueError(f'Update Tool Appear Error: {err}')

    @classmethod
    async def get_personal_tool_by_user(cls, user_id: str):
        try:
            personal_results = await ToolDao.get_tool_by_user_id(user_id=user_id)
            return [res.to_dict() for res in personal_results]
        except Exception as err:
            raise ValueError(f'Get Tool By User Id Appear Error: {err}')

    @classmethod
    async def get_visible_tool_by_user(cls, user_id: str):
        try:
            personal_results = await ToolDao.get_tool_by_user_id(user_id=user_id)
            system_results = await ToolDao.get_tool_by_user_id(user_id=SystemUser)
            return [res.to_dict() for res in personal_results + system_results]
        except Exception as err:
            raise ValueError(f'Get All Tool By User Appear Error: {err}')

    @classmethod
    async def get_all_tools(cls):
        try:
            tools = await ToolDao.get_all_tools()
            return [tool.to_dict() for tool in tools]
        except Exception as err:
            raise ValueError(f'Get All Tools Appear Error: {err}')

    @classmethod
    async def get_tool_name_by_id(cls, tool_id: Union[List[str], str]):
        try:
            if isinstance(tool_id, str):
                tools = await ToolDao.get_tool_name_by_id(tool_id=[tool_id])
            else:
                tools = await ToolDao.get_tool_name_by_id(tool_id=tool_id)
            result = []
            for tool in tools:
                result.append(tool.en_name)
            return result
        except Exception as err:
            raise ValueError(f'Get Tool name by Id appear Err: {err}')

    @classmethod
    async def _get_user_by_tool_id(cls, tool_id: str):
        try:
            tool = await ToolDao.get_tool_by_id(tool_id=tool_id)
            return tool.user_id  # 修复：返回user_id而不是tool_id
        except Exception as err:
            raise ValueError(f'Get user by tool Id appear Error: {err}')

    @classmethod
    async def get_tools_data(cls):
        try:
            tools = await ToolDao.get_all_tools()
            return [tool.to_dict() for tool in tools]
        except Exception as err:
            raise ValueError(f'Get tools data appear Error: {err}')

    @classmethod
    async def get_id_by_tool_name(cls, tool_name: str, user_id: str):
        try:
            tool = await ToolDao.get_id_by_tool_name(tool_name, user_id)
            return tool.tool_id
        except Exception as err:
            raise ValueError(f'Get Id by tool name appear Error: {err}')

    @classmethod
    async def get_tool_ids_from_name(cls, tool_names: List[str], user_id):
        try:
            tools = await ToolDao.get_tool_ids_from_name(tool_names, user_id)
            # 加上系统自带的
            tools.extend(await ToolDao.get_tool_ids_from_name(tool_names, SystemUser))
            return [tool.tool_id for tool in tools]
        except Exception as err:
            raise ValueError(f'Get Tool ID tool name appear Error: {err}')

    @classmethod
    async def convert_zh_name_from_en_name(cls, en_name: str):
        try:
            tool = await ToolDao.get_zh_name_from_en_name(en_name)
            if tool:
                return tool.zh_name
            return None
        except Exception as err:
            raise ValueError(f"Convert Zh name Error:{err}")
