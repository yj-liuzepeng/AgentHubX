from agentchat.tools.send_email.action import send_email
from agentchat.tools.web_search.google_search.action import google_search
from agentchat.tools.web_search.tavily_search.action import tavily_search
from agentchat.tools.web_search.metaso_search.action import metaso_search
from agentchat.tools.arxiv.action import get_arxiv
from agentchat.tools.get_weather.action import get_weather
from agentchat.tools.delivery.action import get_delivery_info
from agentchat.tools.text2image.action import text_to_image
from agentchat.tools.convert_to_pdf.action import convert_to_pdf
from agentchat.tools.convert_to_docx.action import convert_to_docx
from agentchat.tools.image2text.action import image_to_text
from agentchat.tools.document_translation.action import document_translation


AgentTools = [
    send_email,
    tavily_search,
    metaso_search,
    get_weather,
    get_arxiv,
    get_delivery_info,
    text_to_image,
    image_to_text,
    convert_to_pdf,
    convert_to_docx,
    document_translation
]


AgentToolsWithName = {
    "send_email": send_email,
    "tavily_search": tavily_search,
    "web_search": metaso_search,
    "metaso_search": metaso_search,
    "get_arxiv": get_arxiv,
    "get_weather": get_weather,
    "get_delivery": get_delivery_info,
    "get_delivery_info": get_delivery_info,
    "text_to_image": text_to_image,
    "image_to_text": image_to_text,
    "convert_to_pdf": convert_to_pdf,
    "convert_to_docx": convert_to_docx,
    "document_translation": document_translation,
}

WorkSpacePlugins = AgentToolsWithName

LingSeekPlugins = AgentToolsWithName

WeChatTools = {
    "tavily_search": tavily_search,
    "get_arxiv": get_arxiv,
    "get_weather": get_weather,
    "text_to_image": text_to_image,
}
