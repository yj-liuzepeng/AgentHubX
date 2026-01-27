import os
import asyncio
from loguru import logger

from agentchat.settings import app_settings
from agentchat.core.models.manager import ModelManager
from agentchat.schema.chunk import ChunkModel
from agentchat.services.rag.doc_parser.docx import docx_parser
from agentchat.services.rag.doc_parser.pdf import pdf_parser
from agentchat.services.rag.doc_parser.text import text_parser
from agentchat.services.rag.doc_parser.markdown import markdown_parser


class DocParser:

    @classmethod
    async def parse_doc_into_chunks(cls, file_id, file_path, knowledge_id, max_concurrent_tasks=3):
        """解析文档为chunks，带有异常处理"""
        try:
            file_suffix = file_path.split('.')[-1]
            chunks = []
            
            if file_suffix == 'md':
                chunks = await markdown_parser.parse_into_chunks(file_id, file_path, knowledge_id)
            elif file_suffix == 'txt':
                chunks = await text_parser.parse_into_chunks(file_id, file_path, knowledge_id)
            elif file_suffix == 'docx':
                chunks = await docx_parser.parse_into_chunks(file_id, file_path, knowledge_id)
            elif file_suffix == 'pdf':
                chunks = await pdf_parser.parse_into_chunks(file_id, file_path, knowledge_id)
            else:
                logger.warning(f"Unsupported file type: {file_suffix} for file {file_path}")
                return []

            # 当开启chunk总结时才有该步骤
            if app_settings.rag.enable_summary and chunks:
                # 创建信号量，限制最大并发任务数
                semaphore = asyncio.Semaphore(max_concurrent_tasks)

                # 分批处理，避免内存问题
                batch_size = 20
                all_chunks = []
                
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i:i + batch_size]
                    tasks = [asyncio.create_task(cls.generate_summary(chunk, semaphore)) for chunk in batch]
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # 处理异常结果
                    for j, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            logger.error(f"Failed to generate summary for chunk {j} in batch {i//batch_size + 1}: {result}")
                            # 使用原始内容作为摘要
                            batch[j].summary = batch[j].content[:200]  # 截取前200字符作为摘要
                        else:
                            batch[j] = result
                    
                    all_chunks.extend(batch)
                
                chunks = all_chunks

            logger.info(f"Successfully parsed {len(chunks)} chunks from file {file_path}")
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to parse document {file_path}: {e}")
            raise

    @classmethod
    async def generate_summary(cls, chunk: ChunkModel, semaphore):
        async_client = ModelManager.get_conversation_model()

        async with semaphore:
            prompt = f"""
                你是一个专业的摘要生成助手，请根据以下要求为文本生成一段摘要：
                ## 需要总结的文本：
                {chunk.content}
                ## 要求：
                1. 摘要字数控制在 100 字左右。
                2. 摘要中仅包含文字和字母，不得出现链接或其他特殊符号。
                3. 只输出摘要部分，不准输出 `以下是文本的摘要` 等字段
            """
            response = await async_client.ainvoke(prompt)
            chunk.summary = response.content

            return chunk

doc_parser = DocParser()