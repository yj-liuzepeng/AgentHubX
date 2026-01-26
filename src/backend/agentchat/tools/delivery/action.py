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
    logger.info(f"=== 快递查询工具开始执行 ===")
    logger.info(f"快递单号: {delivery_number}")

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
        logger.info(f"API URL: {url}")
        logger.info(f"查询参数: {query_params}")

        # 设置请求头
        headers = {
            'Authorization': 'APPCODE ' + app_settings.tools.delivery.get('api_key'),
            'Content-Type': 'application/json;charset=UTF-8',
            'Accept': 'application/json'
        }
        logger.info(f"请求头包含认证信息: APPCODE [隐藏]")

        logger.info(f"准备发送请求到快递API...")

        # 发送GET请求
        response = http.request(
            'GET',
            url,
            fields=query_params,  # 查询参数
            headers=headers
        )

        logger.info(f"API响应状态码: {response.status}")
        logger.info(f"API响应头: {dict(response.headers)}")

        # 检查响应状态
        if response.status != 200:
            error_content = response.data.decode('utf-8')
            logger.error(f"API响应错误 - 状态码: {response.status}")
            logger.error(f"错误响应内容: {error_content}")
            return f"快递查询服务暂时不可用，错误码: {response.status}"

        # 解析响应数据
        logger.info("开始解析API响应数据...")
        content = response.data.decode('utf-8')
        logger.info(f"原始响应内容长度: {len(content)} 字符")

        result_data = json.loads(content)
        logger.info(f"解析后的数据结构: {list(result_data.keys())}")
        logger.debug(f"API响应数据: {result_data}")

        # 检查业务状态码
        response_code = result_data.get('code')
        logger.info(f"业务状态码: {response_code}")

        if response_code != 200:
            error_msg = result_data.get('msg', '未知错误')
            logger.error(f"快递查询业务错误 - 单号: {delivery_number}")
            logger.error(f"错误信息: {error_msg}")
            return f"查询失败: {error_msg}，请检查快递单号是否正确"

        # 提取快递信息
        data = result_data.get('data', {})
        logger.info(
            f"提取到的数据对象: {type(data)} - 键: {list(data.keys()) if isinstance(data, dict) else '非字典类型'}")

        if not data:
            logger.warning(f"快递数据为空 - 单号: {delivery_number}")
            return "未查询到该快递的物流信息，请确认单号是否正确或稍后再试"

        # 获取快递公司名称 - 适配新的字段名
        company = data.get('logisticsCompanyName',
                           data.get('typename', '未知快递'))
        logger.info(f"快递公司名称: {company}")

        # 获取物流状态信息
        logistics_status = data.get('logisticsStatusDesc', '')
        last_message = data.get('theLastMessage', '')
        last_time = data.get('theLastTime', '')
        cp_code = data.get('cpCode', '')
        cp_mobile = data.get('cpMobile', '')

        logger.info(f"物流状态描述: {logistics_status}")
        logger.info(f"最后消息: {last_message}")
        logger.info(f"最后时间: {last_time}")
        logger.info(f"快递公司代码: {cp_code}")
        logger.info(f"客服电话: {cp_mobile}")

        # 获取物流轨迹 - 适配新的字段名
        track_list = data.get('logisticsTraceDetailList', data.get('list', []))
        logger.info(f"物流轨迹列表长度: {len(track_list) if track_list else 0}")

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
                logger.info(f"=== 快递查询工具执行完成 ===")
                return final_result
            else:
                logger.info(f"=== 快递查询工具执行完成 - 无物流信息 ===")
                return f"【{company}】快递单号 {delivery_number} 暂无物流更新信息"

        # 格式化物流信息
        logger.info("开始格式化物流轨迹信息...")
        formatted_tracks = []
        for i, track in enumerate(track_list):
            # 适配新的时间字段格式
            time_str = track.get('timeDesc', track.get('time', ''))
            status_str = track.get('desc', track.get('status', ''))

            logger.debug(f"轨迹 {i+1}: 时间={time_str}, 状态={status_str}")

            if time_str and status_str:
                formatted_tracks.append(f"• {time_str}: {status_str}")

        logger.info(f"成功格式化 {len(formatted_tracks)} 条轨迹记录")

        # 按时间倒序排列（最新的在前）
        formatted_tracks.reverse()
        logger.info("轨迹记录已按时间倒序排列")

        # 如果没有成功格式化的轨迹，尝试使用其他可用信息
        if not formatted_tracks:
            logger.warning("没有成功格式化的轨迹，使用备用信息")
            last_message = data.get('theLastMessage', '')
            logistics_status = data.get(
                'logisticsStatusDesc', data.get('logisticsStatus', ''))

            if last_message:
                formatted_tracks.append(f"• 最新动态: {last_message}")
                logger.info("使用最后消息作为轨迹")
            elif logistics_status:
                formatted_tracks.append(f"• 当前状态: {logistics_status}")
                logger.info("使用物流状态作为轨迹")
            else:
                formatted_tracks.append("• 暂无详细物流轨迹信息")
                logger.info("无可用信息，显示默认提示")

        # 构建状态摘要信息
        status_summary = []
        if logistics_status:
            status_summary.append(f"📊 当前状态: {logistics_status}")
            logger.info(f"添加状态摘要: {logistics_status}")
        if last_message and last_time:
            status_summary.append(f"🕐 最新更新: {last_time}")
            status_summary.append(f"📍 {last_message}")
            logger.info(f"添加最新更新: {last_time} - {last_message}")
        elif last_message:
            status_summary.append(f"📍 最新动态: {last_message}")
            logger.info(f"添加最新动态: {last_message}")
        if cp_mobile:
            status_summary.append(f"📞 客服热线: {cp_mobile}")
            logger.info(f"添加客服热线: {cp_mobile}")

        # 合并状态摘要和详细轨迹
        if status_summary:
            status_info = "\n".join(status_summary)
            if formatted_tracks:
                track_info = f"{status_info}\n\n📍 详细轨迹:\n" + \
                    "\n".join(formatted_tracks)
                logger.info("合并状态摘要和详细轨迹")
            else:
                track_info = status_info
                logger.info("仅使用状态摘要")
        else:
            track_info = "\n".join(
                formatted_tracks) if formatted_tracks else "暂无物流轨迹信息"
            logger.info("仅使用格式化的轨迹信息")

        final_result = DELIVERY_PROMPT.format(
            company, delivery_number, track_info)

        logger.info(f"最终格式化结果长度: {len(final_result)} 字符")
        logger.info(f"=== 快递查询工具执行成功完成 ===")
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
