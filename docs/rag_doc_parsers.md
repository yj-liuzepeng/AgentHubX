# RAG 系统文档解析方案分析

本文档基于 `src/backend/agentchat/services/rag/doc_parser/` 目录下的代码实现，对 RAG 系统中不同类型文件的解析方案进行深入分析与总结。

## 1. 总体架构

当前 RAG 系统的文档解析采用**"Markdown 为核心"**的策略。大多数富文本文档（PDF, Word, PPT）最终都会被转换为 Markdown 格式，然后利用 Markdown 的结构化特性（标题、层级）进行切片。

支持的文件类型包括：
- **结构化文档**: Markdown (`.md`)
- **富文本文档**: PDF (`.pdf`), Word (`.docx`), PowerPoint (`.pptx`)
- **表格文档**: Excel (`.xlsx`)
- **纯文本**: Text (`.txt`)

## 2. 解析方案详解

### 2.1 Markdown 解析 (`markdown.py`)
Markdown 解析器是整个系统的核心组件，被 PDF、Word 和 PPT 解析器复用。

*   **核心类**: `MarkdownParser`
*   **解析逻辑**:
    1.  **标题识别**: 使用正则 `^(#{1,5})\s+(.+)$` 识别 1-5 级标题。
    2.  **层级保持**: 解析过程中维护当前的标题路径（例如 `一级标题 > 二级标题`），确保切片后的文本块包含上下文信息。
    3.  **智能切分**:
        *   **按标题切分**: 优先在标题处进行切分。
        *   **长度控制**: 严格控制切片大小在 `min_chunk_size` 和 `max_chunk_size` 之间。
        *   **完整性保护**: 
            *   **链接/图片保护**: 检测 `[text](url)` 和 `![alt](url)` 语法，确保不会在链接中间强行截断。
            *   **句子边界**: 在必须强行切分长段落时，优先寻找句号、感叹号、换行符等自然停顿点。
    4.  **元数据**: 每个 Chunk 包含 `file_id`, `knowledge_id`, `chunk_id`, `update_time` 等元数据。

### 2.2 PDF 解析 (`pdf.py`)
PDF 解析采用了"先转 Markdown，再切分"的策略，并重点处理了图片资源。

*   **核心类**: `PDFParser`
*   **依赖库**: `pymupdf4llm` (基于 PyMuPDF), `aliyun_oss`
*   **解析流程**:
    1.  **格式转换**: 使用 `pymupdf4llm.to_markdown` 将 PDF 转换为 Markdown 格式。
    2.  **图片提取**: 在转换过程中提取 PDF 中的图片保存到本地临时目录。
    3.  **资源上云**:
        *   将提取的图片批量上传至阿里云 OSS。
        *   获取图片的访问 URL。
    4.  **链接重写**: 使用 `markdown_rewriter` 将 Markdown 中的本地图片路径替换为 OSS 的 URL。
    5.  **最终切分**: 调用 `MarkdownParser.parse_into_chunks` 对处理后的 Markdown 进行切片。

### 2.3 Office 文档解析 (Word/PPT)
Word (`docx.py`) 和 PPT (`pptx.py`) 采用预处理策略，将其归一化为 PDF 处理流程。

*   **核心类**: `DocxParser`, `PPTXParser`
*   **依赖工具**: LibreOffice (通过 `subprocess` 调用)
*   **解析流程**:
    1.  **格式转换**: 调用 `convert_to_pdf` 工具函数，利用 LibreOffice 的命令行工具 (`soffice --headless --convert-to pdf`) 将 `.docx` 或 `.pptx` 转换为 `.pdf`。
    2.  **复用流程**: 将生成的 PDF 文件交给 `PDFParser` 处理（即：PDF -> Markdown -> OSS Upload -> Chunks）。

### 2.4 Excel 解析 (`excel.py`)
Excel 解析侧重于数据内容的提取，而非格式保留。

*   **核心函数**: `excel_loader`
*   **依赖库**: `pandas`, `langchain_community.document_loaders.CSVLoader`
*   **解析流程**:
    1.  **格式转换**: 使用 `pandas.read_excel` 读取 Excel 文件。
    2.  **转 CSV**: 将 DataFrame 保存为 CSV 格式（中间格式）。
    3.  **加载切分**: 使用 LangChain 的 `CSVLoader` 加载 CSV 内容并进行切分。
    4.  **清理**: 删除临时的 CSV 文件。

### 2.5 纯文本解析 (`text.py`)
针对无结构的纯文本文件。

*   **核心类**: `TextParser`
*   **解析逻辑**:
    1.  **按行读取**: 逐行读取文本内容。
    2.  **累积切分**: 
        *   累积行内容直到达到 `chunk_size` 限制。
        *   当达到限制时生成一个 Chunk。
    3.  **重叠处理**: 生成新 Chunk 时，保留上一个 Chunk 结尾的 `overlap_size` 长度的内容作为开头，保证上下文连续性。

## 3. 方案总结表

| 文件类型 | 核心处理类 | 关键技术/库 | 解析策略 | 产物特点 |
| :--- | :--- | :--- | :--- | :--- |
| **Markdown** | `MarkdownParser` | Regex, Custom Logic | 标题层级感知切分 | 保留标题路径，链接/图片完整 |
| **PDF** | `PDFParser` | `pymupdf4llm`, Aliyun OSS | PDF -> Markdown (带图片) | 图文并茂，图片存储在云端 |
| **Word** | `DocxParser` | LibreOffice | Docx -> PDF -> Markdown | 同 PDF |
| **PPT** | `PPTXParser` | LibreOffice | PPTx -> PDF -> Markdown | 同 PDF |
| **Excel** | `excel_loader` | Pandas, LangChain | Xlsx -> CSV -> Loader | 表格行数据，适合结构化查询 |
| **Text** | `TextParser` | Python String | 滑动窗口 (Chunk + Overlap) | 简单文本块，带重叠窗口 |

## 4. 优势分析

1.  **统一性**: 通过将 PDF、Word、PPT 统一转换为 Markdown，极大地简化了下游的切片逻辑（Chunking Logic），只需要维护一套高质量的 Markdown 切片算法即可。
2.  **多模态支持**: PDF 解析流程中集成了图片提取和 OSS 上传，使得 RAG 系统能够处理和展示文档中的图表信息，而非仅仅是纯文本。
3.  **结构保留**: Markdown 解析器能够保留文档的标题层级结构，这对于大模型理解文档上下文非常有帮助。
