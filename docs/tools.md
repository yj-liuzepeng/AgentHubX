# 后端工具文档 (Backend Tools Documentation)

本文档详细介绍了 `src/backend/agentchat/tools/` 目录下各个工具的功能和实现细节。

## 1. Arxiv 论文搜索 (arxiv)
*   **功能**: 在 Arxiv 上搜索并获取相关论文信息。
*   **实现细节**:
    *   使用 `langchain_community.utilities.ArxivAPIWrapper` 封装了 Arxiv API 的调用。
    *   通过 `_get_arxiv` 函数执行搜索。
*   **输入**: `query` (搜索关键词)。
*   **输出**: 相关论文的摘要和元数据字符串。

## 2. PDF 转 DOCX (convert_to_docx)
*   **功能**: 将用户上传的 PDF 文件转换为 DOCX 格式。
*   **实现细节**:
    *   **下载**: 从阿里云 OSS 下载用户上传的 PDF 文件到本地临时目录。
    *   **转换**: 使用 `pdf2docx.Converter` 库进行格式转换。
        *   配置了布局参数：`detect_vertical_text=True` (识别垂直文本), `char_margin=1.0`, `line_overlap=0.5`。
    *   **上传**: 将生成的 DOCX 文件上传回阿里云 OSS。
    *   **返回**: 生成一个有效期为 1 小时的临时下载链接。
*   **输入**: `file_url` (PDF 文件的 OSS 链接)。
*   **输出**: 包含下载链接的提示信息。

## 3. 格式转 PDF (convert_to_pdf)
*   **功能**: 将 DOCX 等多种格式文件转换为 PDF。
*   **实现细节**:
    *   **支持格式**: docx, doc, odt, rtf, txt, html, xls, xlsx, ppt, pptx 等。
    *   **转换**: 调用系统安装的 `libreoffice` 命令 (`--headless --convert-to pdf`) 进行转换。使用 `subprocess` 执行命令。
    *   **流程**: 下载文件 -> LibreOffice 转换 -> 上传 PDF 到 OSS -> 生成下载链接。
*   **输入**: `file_url` (源文件链接)。
*   **输出**: 包含 PDF 下载链接的提示信息。

## 4. 网页爬虫 (crawl_web)
*   **功能**: 爬取指定网页的内容并转换为 Markdown 格式。
*   **实现细节**:
    *   使用 `crawl4ai.AsyncWebCrawler` 进行异步网页抓取。
    *   `crawl_action` 函数中执行 `crawler.arun()` 并返回 `result.markdown`。
*   **输入**: `web_url` (目标网页地址)。
*   **输出**: 网页内容的 Markdown 文本。

## 5. 快递查询 (delivery)
*   **功能**: 查询快递物流轨迹。
*   **实现细节**:
    *   调用第三方 API: `https://kzexpress.market.alicloudapi.com/api-mall/api/express/query`。
    *   使用 `urllib3` 连接池发送 HTTP GET 请求。
    *   需要配置 `app_settings.tools.delivery.api_key`。
*   **输入**: `delivery_number` (快递单号)。
*   **输出**: 快递物流详情字符串或错误信息。

## 6. 文档翻译 (document_translation)
*   **功能**: 批量翻译文档（PDF, DOCX, DOC, TXT, PPT），支持保持原格式。
*   **实现细节**:
    *   **多组件架构**:
        *   `parsers.py`: 解析不同格式文档（PDFParser, DOCXParser 等）。
        *   `translators.py`: `TranslationEngine` 负责调用翻译服务（如 LLM）。
        *   `generators.py`: `DocumentGenerator` 重新生成翻译后的文档。
    *   **流程**: 下载 -> 解析内容 -> 翻译 -> 生成新文档 -> 上传 OSS。
    *   支持多种语言（中文, 英语, 日语, 韩语等）。
*   **输入**: `file_urls` (文件链接列表), `target_language` (目标语言), `source_language` (源语言)。
*   **输出**: 翻译结果及下载链接。

## 7. 天气查询 (get_weather)
*   **功能**: 查询指定城市的天气预报。
*   **实现细节**:
    *   发送 HTTP GET 请求到配置的天气 API 端点。
    *   解析 JSON 响应，提取白天/夜间温度、天气现象等信息。
    *   使用预定义的 Prompt 模板格式化输出。
*   **输入**: `city` (城市名称)。
*   **输出**: 格式化的天气预报信息。

## 8. 图片转文字 (image2text)
*   **功能**: 描述图片内容（Image Captioning / VQA）。
*   **实现细节**:
    *   读取本地图片文件并编码为 Base64。
    *   调用 `ModelManager.get_qwen_vl_model()` (Qwen-VL 多模态模型)。
    *   发送包含图片数据和提示词("图中描绘的是什么景象?")的请求。
*   **输入**: `image_path` (本地图片路径)。
*   **输出**: 图片内容的文本描述。

## 9. 简历优化 (resume_optimizer)
*   **功能**: 优化简历文档（DOCX/PDF）的内容，使其更专业。
*   **实现细节**:
    *   **DOCX 处理**: 使用 `python-docx` 遍历段落和表格。保留原始格式（字体、加粗、大小等），仅替换文本内容。
    *   **PDF 处理**: 使用 `PyMuPDF (fitz)` 提取文本块，优化后在新建 PDF 页面上按原位置重绘文本。
    *   **AI 优化**: 调用 OpenAI GPT-3.5-turbo 模型，Prompt 为 "请优化以下简历内容..."。
*   **输入**: `input_path` (输入文件路径), `output_path` (输出路径)。
*   **输出**: (工具内部保存文件，返回操作完成信息)。

## 10. 邮件发送 (send_email)
*   **功能**: 发送电子邮件。
*   **实现细节**:
    *   使用 Python 内置 `smtplib` 库。
    *   默认使用 SSL 连接 (`smtp.qq.com`, 端口 465)。
    *   构建 MIME Multipart 邮件对象。
*   **输入**: `sender` (发件人), `receiver` (收件人), `email_message` (内容), `password` (授权码)。
*   **输出**: 发送结果状态字符串。

## 11. 文生图 (text2image)
*   **功能**: 根据文本提示词生成图片。
*   **实现细节**:
    *   调用阿里云 DashScope `ImageSynthesis` API。
    *   生成图片后，将其下载并上传到阿里云 OSS 存储。
    *   返回 Markdown 格式的图片链接 `![prompt](url)` 以便在聊天界面直接显示。
*   **输入**: `user_prompt` (图片描述)。
*   **输出**: Markdown 图片链接。

## 12. 联网搜索 (web_search)
包含三种不同的搜索实现，根据配置选择使用。

### Google Search
*   **实现**: 使用 `langchain_community.utilities.SerpAPIWrapper`。
*   **依赖**: SerpAPI Key。

### MetaSo Search
*   **实现**: 使用 `metaso_sdk` 调用 MetaSo 聚合搜索 API。
*   **特性**: 支持流式返回 (`stream=True`)，支持会话上下文 (`session_id`)。
*   **输入**: `query`, `session_id`。

### Tavily Search
*   **实现**: 使用 `tavily.TavilyClient`。
*   **特性**: 专为 AI Agent 优化的搜索结果。
*   **参数**: 支持 `topic` (general/news/finance), `time_range`, `max_results`。
*   **输出**: 拼接了 URL 和内容的字符串。
