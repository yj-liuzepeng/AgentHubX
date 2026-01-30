import os
import json
from typing import Optional, Any
from langchain.tools import tool

from agentchat.settings import app_settings


def _refresh_metaso_client(api_key: str) -> None:
    import httpx
    from metaso_sdk import client as client_module
    import importlib

    current_key = getattr(client_module, "api_key", None)
    if current_key == api_key and getattr(client_module, "client", None) is not None:
        return

    existing_client = getattr(client_module, "client", None)
    if existing_client is not None:
        try:
            existing_client.close()
        except Exception:
            pass

    client = httpx.Client(
        base_url="https://metaso.cn/api/open",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    client_module.api_key = api_key
    client_module.client = client
    search_module = importlib.import_module("metaso_sdk.search")
    search_module.client = client


def _get_metaso_api_key() -> Optional[str]:
    tool_config = getattr(app_settings.tools, "metaso", {})
    if isinstance(tool_config, dict):
        api_key = tool_config.get("api_key")
    else:
        api_key = getattr(tool_config, "api_key", None)
    env_key = os.environ.get("METASO_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    if api_key and str(api_key).strip():
        os.environ["METASO_API_KEY"] = str(api_key).strip()
        return os.environ.get("METASO_API_KEY")
    return None


def _normalize_response(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ["text", "answer", "content", "data"]:
            if key in value and isinstance(value[key], str):
                return value[key]
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        parts = [_normalize_response(item) for item in value]
        return "\n\n".join([part for part in parts if part])
    return str(value)


@tool("metaso_search", parse_docstring=True)
def metaso_search(query: str, session_id: Optional[str] = None, stream: Optional[bool] = False,
                  max_chars: Optional[int] = None):
    """
    使用 MetaSo 搜索引擎进行联网搜索

    Args:
        query: 用户想要搜索的问题
        session_id: 追问时的会话ID，可为空
        stream: 是否开启流式返回
        max_chars: 最大返回字符数，避免输出过长

    Returns:
        将联网搜索到的信息返回给用户
    """
    api_key = _get_metaso_api_key()
    if not api_key:
        raise ValueError("METASO_API_KEY 未配置，请在配置文件 tools.metaso.api_key 中设置")

    _refresh_metaso_client(api_key)
    from metaso_sdk import Query
    import importlib
    search_module = importlib.import_module("metaso_sdk.search")

    query_payload = {"question": query}
    if session_id:
        query_payload["sessionId"] = session_id

    if stream:
        chunks = []
        for chunk in search_module.search(Query(**query_payload), stream=True):
            if isinstance(chunk, dict):
                if chunk.get("type") == "append-text" and chunk.get("text"):
                    chunks.append(chunk.get("text"))
                elif chunk.get("text"):
                    chunks.append(chunk.get("text"))
            elif isinstance(chunk, str):
                chunks.append(chunk)
        result = "".join(chunks)
    else:
        result = _normalize_response(search_module.search(Query(**query_payload)))

    if max_chars is not None and isinstance(result, str):
        return result[:max_chars]
    return result
