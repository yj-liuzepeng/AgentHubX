import urllib3
import json
from typing import Dict, Any, Optional
from langchain.tools import tool
from agentchat.settings import app_settings
from agentchat.prompts.tool import DELIVERY_PROMPT
from loguru import logger

# 创建连接池管理器
http = urllib3.PoolManager(
    num_pools=10,  # 连接池数量
    maxsize=100,   # 每个连接池的最大连接数
    timeout=urllib3.Timeout(connect=5.0, read=30.0)  # 连接超时和读取超时
)


@tool(parse_docstring=True)
def get_delivery_info(delivery_number: str):
    """
    根据用户提供的快递号码查询快递物流信息。

    Args:
        delivery_number (str): 用户提供的快递号码。

    Returns:
        str: 查询到的快递信息。
    """
    return _get_delivery(delivery_number)


def _get_delivery(delivery_number: str):
    """用来查询用户的快递物流信息"""
    try:
        # 构建查询参数 - 使用阿里云API标准格式
        host = 'https://kzexpress.market.alicloudapi.com'
        path = '/api-mall/api/express/query'

        # 构建查询字符串
        query_params = {
            'expressNo': delivery_number,
            'mobile': 'mobile'  # 可选参数，手机号后4位
        }

        # 构建完整URL
        url = host + path

        # 设置请求头
        headers = {
            'Authorization': 'APPCODE ' + app_settings.tools.delivery.get('api_key'),
            'Content-Type': 'application/json;charset=UTF-8',
            'Accept': 'application/json'
        }

        logger.info(f"查询快递信息 - 单号: {delivery_number}")

        # 发送GET请求
        response = http.request(
            'GET',
            url,
            fields=query_params,  # 查询参数
            headers=headers
        )

        # 检查响应状态
        if response.status != 200:
            logger.error(
                f"API响应错误 - 状态码: {response.status}, 内容: {response.data.decode('utf-8')}")
            return f"快递查询服务暂时不可用，错误码: {response.status}"

        # 解析响应数据
        content = response.data.decode('utf-8')
        result_data = json.loads(content)

        logger.debug(f"API响应数据: {result_data}")

        # 检查业务状态码
        if result_data.get('code') != 200:
            error_msg = result_data.get('msg', '未知错误')
            logger.warning(
                f"快递查询业务错误 - 单号: {delivery_number}, 错误: {error_msg}")
            return f"查询失败: {error_msg}，请检查快递单号是否正确"

        # 提取快递信息
        data = result_data.get('data', {})
        if not data:
            logger.warning(f"快递数据为空 - 单号: {delivery_number}")
            return "未查询到该快递的物流信息，请确认单号是否正确或稍后再试"

        # 获取快递公司名称 - 适配新的字段名
        company = data.get('logisticsCompanyName',
                           data.get('typename', '未知快递'))

        # 获取物流状态信息
        logistics_status = data.get('logisticsStatusDesc', '')
        last_message = data.get('theLastMessage', '')
        last_time = data.get('theLastTime', '')
        cp_code = data.get('cpCode', '')
        cp_mobile = data.get('cpMobile', '')

        # 获取物流轨迹 - 适配新的字段名
        track_list = data.get('logisticsTraceDetailList', data.get('list', []))

        # 更详细的调试信息
        logger.debug(f"快递公司: {company} (代码: {cp_code})")
        logger.debug(f"物流状态: {logistics_status}")
        logger.debug(f"最后更新: {last_time} - {last_message}")
        logger.debug(f"客服电话: {cp_mobile}")
        logger.debug(f"轨迹列表长度: {len(track_list) if track_list else 0}")
        logger.debug(f"轨迹数据: {track_list}")

        if not track_list:
            # 检查是否有其他状态信息可用
            last_message = data.get('theLastMessage', '')
            logistics_status = data.get(
                'logisticsStatusDesc', data.get('logisticsStatus', ''))

            if last_message or logistics_status:
                # 如果有最后一条信息或状态，也显示给用户
                status_info = f"当前状态: {logistics_status}" if logistics_status else ""
                last_info = f"最新动态: {last_message}" if last_message else ""

                fallback_info = []
                if status_info:
                    fallback_info.append(status_info)
                if last_info:
                    fallback_info.append(last_info)

                track_info = "\n".join(
                    fallback_info) if fallback_info else "暂无详细物流轨迹信息"
                final_result = DELIVERY_PROMPT.format(
                    company, delivery_number, track_info)
                logger.info(
                    f"快递查询成功(使用备用信息) - 单号: {delivery_number}, 快递公司: {company}")
                return final_result
            else:
                return f"【{company}】快递单号 {delivery_number} 暂无物流更新信息"

        # 格式化物流信息
        formatted_tracks = []
        for i, track in enumerate(track_list):
            # 适配新的时间字段格式
            time_str = track.get('timeDesc', track.get('time', ''))
            status_str = track.get('desc', track.get('status', ''))

            logger.debug(f"轨迹 {i+1}: 时间={time_str}, 状态={status_str}")

            if time_str and status_str:
                formatted_tracks.append(f"• {time_str}: {status_str}")

        # 按时间倒序排列（最新的在前）
        formatted_tracks.reverse()

        # 如果没有成功格式化的轨迹，尝试使用其他可用信息
        if not formatted_tracks:
            last_message = data.get('theLastMessage', '')
            logistics_status = data.get(
                'logisticsStatusDesc', data.get('logisticsStatus', ''))

            if last_message:
                formatted_tracks.append(f"• 最新动态: {last_message}")
            elif logistics_status:
                formatted_tracks.append(f"• 当前状态: {logistics_status}")
            else:
                formatted_tracks.append("• 暂无详细物流轨迹信息")

        # 构建状态摘要信息
        status_summary = []
        if logistics_status:
            status_summary.append(f"📊 当前状态: {logistics_status}")
        if last_message and last_time:
            status_summary.append(f"🕐 最新更新: {last_time}")
            status_summary.append(f"📍 {last_message}")
        elif last_message:
            status_summary.append(f"📍 最新动态: {last_message}")
        if cp_mobile:
            status_summary.append(f"📞 客服热线: {cp_mobile}")

        # 合并状态摘要和详细轨迹
        if status_summary:
            status_info = "\n".join(status_summary)
            if formatted_tracks:
                track_info = f"{status_info}\n\n📍 详细轨迹:\n" + \
                    "\n".join(formatted_tracks)
            else:
                track_info = status_info
        else:
            track_info = "\n".join(
                formatted_tracks) if formatted_tracks else "暂无物流轨迹信息"

        final_result = DELIVERY_PROMPT.format(
            company, delivery_number, track_info)

        logger.info(
            f"快递查询成功 - 单号: {delivery_number}, 快递公司: {company}, 轨迹数: {len(formatted_tracks)}")
        return final_result

    except urllib3.exceptions.MaxRetryError as e:
        logger.error(f"网络连接失败 - 单号: {delivery_number}, 错误: {str(e)}")
        return "网络连接失败，请检查网络连接后重试"

    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误 - 单号: {delivery_number}, 错误: {str(e)}")
        return "服务器响应格式错误，请联系技术支持"

    except Exception as err:
        logger.error(
            f"快递查询异常 - 单号: {delivery_number}, 错误类型: {type(err).__name__}, 错误: {str(err)}")
        return "查询快递信息时发生未知错误，请稍后重试或联系客服"
