# 知识库文件上传处理流程

本文档详细描述了 `AgentHubX` 项目中知识库文件上传的全生命周期处理流程，从用户在前端选择文件开始，经过后端中转上传至云存储（OSS），最后进行异步解析和向量化存储。

## 1. 流程概述

整个文件上传处理流程主要分为三个阶段：
1.  **文件上传阶段 (Phase 1)**：用户上传原始文件到后端，后端将文件转存至阿里云 OSS 的 `pdf/`（或其他格式）目录，并返回文件 URL。
2.  **创建记录阶段 (Phase 2)**：前端收到 URL 后，请求创建知识库文件记录，后端启动后台处理任务。
3.  **异步处理阶段 (Phase 3)**：后台任务负责下载原始文件，解析文件内容（对于 PDF，此时会生成图片和 Markdown 并**再次上传到 OSS** 的 `png/` 和 `md/` 目录），最后生成向量并入库。

## 2. 详细处理流程图 (ASCII)

```ascii
+-------------------+       +---------------------------+       +-----------------------+       +-----------------------+
|   Client (User)   |       |   API Server (FastAPI)    |       |      Aliyun OSS       |       |   Background Worker   |
+-------------------+       +---------------------------+       +-----------------------+       +-----------------------+
          |                               |                               |                                 |
          | [Phase 1: Upload Original]    |                               |                                 |
          |                               |                               |                                 |
          | 1. POST /api/v1/upload        |                               |                                 |
          | (File Content)                |                               |                                 |
          |------------------------------>|                               |                                 |
          |                               | 2. Upload Original File       |                                 |
          | (aliyun_oss.upload_file)      |                               |                                 |
          |                               |------------------------------>|                                 |
          |                               | (Save to: pdf/xxx.pdf)        |                                 |
          |                               |                               |                                 |
          | 4. Return File URL            |                               |                                 |
          | (sign_url)                    |<------------------------------|                                 |
          |<------------------------------|                               |                                 |
          |                               |                               |                                 |
          |                               |                               |                                 |
          | [Phase 2: Create Record]      |                               |                                 |
          |                               |                               |                                 |
          | 5. POST /knowledge_file/create|                               |                                 |
          | (knowledge_id, file_url)      |                               |                                 |
          |------------------------------>|                               |                                 |
          |                               | 6. Download Original from OSS |                                 |
          | (aliyun_oss.download_file)    |                               |                                 |
          |                               |------------------------------>|                                 |
          |                               |                               |                                 |
          |                               | 7. Launch Async Task          |                                 |
          | (safe_process_task)           |                               |                                 |
          |                               |---------------------------------------------------------------->|
          |                               |                                                                 |
          | 9. Return Response            |                                                                 |
          | (knowledge_file_id)           |                                                                 |
          |<------------------------------|                                                                 |
          |                                                                                                 |
          |                                                                                                 |
          | [Phase 3: Async Processing & Intermediate Upload]                                               |
          |                                                                                                 |
          |                                                                        [Async Task Start]       |
          |                                                                                                 |
          |                                                                        10. Parse Document       |
          |                                                                        (doc_parser.parse)       |
          |                                                                        - Extract text/images    |
          |                                                                        - Convert to Markdown    |
          |                                                                                                 |
          |                                                                        11. Upload Images        |
          |                                                                        (upload_folder_to_oss)   |
          |                                                                        -----------------------> |
          |                                                                        (Save to: png/xxx.png)   |
          |                                                                                                 |
          |                                                                        12. Upload Markdown      |
          |                                                                        (upload_file_to_oss)     |
          |                                                                        -----------------------> |
          |                                                                        (Save to: md/xxx.md)     |
          |                                                                                                 |
          |                                                                        13. Vectorization        |
          |                                                                        (RagHandler.index)       |
          |                                                                        - Generate Embeddings    |
          |                                                                        - Insert into Milvus     |
          |                                                                                                 |
          |                                                                        14. Update Status        |
          |                                                                        (Status: success/fail)   |
          |                                                                        ------------------------>|
```

## 3. 详细步骤解析

### 3.1 文件上传阶段 (Phase 1)

**核心动作**：用户将**原始文件**上传到 OSS。

1.  **上传接口**: 前端调用 `/api/v1/upload`。
2.  **存储原始文件**: 后端接收文件流，直接调用 `aliyun_oss.upload_file` 将其上传到 OSS。
    *   如果是 PDF 文件，它会被存储在 `pdf/` 目录下（例如 `2024-02-24/pdf/manual.pdf`）。
    *   **注意**: 此时 OSS 上只有这一个原始文件，还没有生成的图片或 Markdown 文件。

### 3.2 记录创建与任务启动 (Phase 2)

**核心动作**：创建数据库记录，并准备开始异步处理。

1.  **创建记录**: 前端调用 `/knowledge_file/create`。
2.  **下载原始文件**: 后端为了进行解析，必须先将刚才上传到 OSS 的文件下载回本地临时目录（`tempfile.mkdtemp()`）。
3.  **启动异步任务**: 任务启动后立即返回响应，后续逻辑在后台执行。

### 3.3 异步处理与中间文件上传 (Phase 3)

**核心动作**：解析原始文件，**生成并上传中间文件**，最后向量化。

**这一步解释了为什么 OSS 上会出现 `png/` 和 `md/` 目录：**

1.  **解析 PDF (`PDFParser.convert_markdown`)**:
    *   **位置**: `src/backend/agentchat/services/rag/doc_parser/pdf.py`
    *   后台任务使用 `pymupdf4llm` 工具读取本地的 PDF 文件。
    *   **提取图片**: 将 PDF 中的图片提取出来，保存在本地临时 `images` 文件夹中。
    *   **转换 Markdown**: 将 PDF 文本内容转换为 Markdown 格式。
2.  **上传中间图片**:
    *   代码显式调用 `self.upload_folder_to_oss(images_dir)`。
    *   这会将所有提取出来的图片上传到 OSS 的 `png/` 目录（例如 `2024-02-24/png/image_001.png`）。
3.  **上传中间 Markdown**:
    *   代码显式调用 `self.upload_file_to_oss(markdown_output_path)`。
    *   这会将生成的 Markdown 文件上传到 OSS 的 `md/` 目录（例如 `2024-02-24/md/manual.md`）。
4.  **向量化**:
    *   最后，系统使用这个生成的 Markdown 内容进行切分（Chunking）和向量化（Embedding），存入 Milvus。

## 4. 总结：文件在 OSS 上的生成时序

| 时间点 | 动作 | OSS 上的文件变化 | 说明 |
| :--- | :--- | :--- | :--- |
| **Phase 1** | 用户上传 | `pdf/manual.pdf` | 原始文件被存储。 |
| **Phase 2** | 任务启动 | (无变化) | 仅下载文件到本地处理。 |
| **Phase 3** | PDF 解析中 | `png/img1.png`, `png/img2.png` | 解析器提取图片并**主动上传**。 |
| **Phase 3** | PDF 解析后 | `md/manual.md` | 解析器生成 Markdown 并**主动上传**。 |

因此，最终在 OSS 上看到 `pdf/`, `png/`, `md/` 三个目录下的文件，是因为系统在不同阶段分别进行了上传操作，而不仅仅是一次上传的结果。

## 5. 存储与检索层 (Milvus) 详解

本项目的核心向量存储采用 **Milvus**，它负责存储文档切片（Chunks）及其向量表示，并支持高效的相似度检索。

### 5.1 架构与初始化

*   **实例化模式**: 系统采用单例/工厂模式管理 Milvus 客户端。在 `src/backend/agentchat/services/rag/vector_db/__init__.py` 中，根据 `config.yaml` 配置 (`rag.vector_db.mode`) 决定实例化 `MilvusClient`、`ChromaClient` 或 `MilvusLiteClient`。
*   **连接管理**: `MilvusClient` 实现了连接重试机制（默认 3 次重试），确保在网络波动时的稳定性。
*   **懒加载 (Lazy Loading)**: 为了优化启动速度和资源占用，集合（Collection）仅在首次被访问时加载到内存（`load()`），而非服务启动时全部加载。

### 5.2 数据模型 (Schema)

Milvus 中的集合（Collection）结构是固定的，包含以下核心字段：

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | INT64 | 主键，自动生成。 |
| `chunk_id` | VARCHAR | 业务主键，唯一标识一个切片。 |
| `content` | VARCHAR | **原始文本内容**，检索后直接返回给 LLM。 |
| `embedding` | FLOAT_VECTOR | **内容向量** (1024维)，用于语义搜索。 |
| `summary` | VARCHAR | 文本摘要（可选）。 |
| `embedding_summary` | FLOAT_VECTOR | **摘要向量** (1024维)，用于基于摘要的搜索。 |
| `file_id` | VARCHAR | 关联的文件 ID。 |
| `knowledge_id` | VARCHAR | 关联的知识库 ID。 |

### 5.3 向量化与写入流程

写入过程在 `MilvusClient.insert` 方法中完成，具有以下特点：

1.  **批处理 (Batching)**: 为了防止内存溢出，大文件切片被分为小批次（默认 20 个 Chunk 一组）进行处理。
2.  **即时向量化 (On-the-fly Embedding)**:
    *   系统接收纯文本 Chunks。
    *   在 `insert` 方法内部，调用 `agentchat.services.rag.embedding.get_embedding` 生成向量。
    *   **关键点**: 向量化是在写入数据库的最后一步进行的，而不是在解析阶段。
3.  **内存管理**: 每次批处理后，系统会主动检查内存使用情况（`psutil`），并在内存占用过高（>500MB 增量）时强制执行垃圾回收（`gc.collect()`）。

### 5.4 混合检索策略 (Hybrid Retrieval)

虽然 Milvus 是核心，但系统支持与 Elasticsearch (ES) 配合进行混合检索：

*   **Milvus**: 负责语义检索（Semantic Search），通过向量相似度找到含义相近的片段。
*   **Elasticsearch (可选)**: 负责关键词检索（Keyword Search），弥补向量检索在精确匹配上的不足。
*   **结果合并**: `RagHandler` 会获取两者的结果，进行加权排序和去重，最终返回给大模型。
