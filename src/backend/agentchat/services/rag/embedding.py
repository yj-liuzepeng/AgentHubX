import tracemalloc
import sys
import gc
import asyncio
from typing import Union, List

from openai import AsyncOpenAI
from agentchat.settings import app_settings, initialize_app_settings

embedding_model = app_settings.multi_models.embedding.model_name
embedding_client = AsyncOpenAI(base_url=app_settings.multi_models.embedding.base_url,
                               api_key=app_settings.multi_models.embedding.api_key)


# 启动内存跟踪
tracemalloc.start()


async def get_embedding(query: Union[str, List[str]]):
    """获取文本嵌入向量，带有异常处理、重试机制和内存管理"""
    max_retries = 3
    retry_delay = 1  # 秒

    # 安全日志函数
    def safe_log(level, message):
        try:
            import loguru
            logger = loguru.logger
            if level == 'info':
                logger.info(message)
            elif level == 'error':
                logger.error(message)
            elif level == 'warning':
                logger.warning(message)
            elif level == 'debug':
                logger.debug(message)
        except:
            print(f"[{level.upper()}] {message}")

    safe_log(
        'info', f"Starting embedding generation for {len(query) if isinstance(query, list) else 1} items")

    try:
        for attempt in range(max_retries):
            try:
                # 内存检查
                current, peak = tracemalloc.get_traced_memory()
                safe_log(
                    'debug', f"Memory usage: {current / 1024 / 1024:.2f} MB, Peak: {peak / 1024 / 1024:.2f} MB")

                # 如果是字符串或长度小于等于5的列表，直接处理（减少并发压力）
                if isinstance(query, str) or (isinstance(query, list) and len(query) <= 5):
                    safe_log(
                        'debug', f"Processing small batch directly, size: {len(query) if isinstance(query, list) else 1}")
                    responses = await embedding_client.embeddings.create(
                        model=embedding_model,
                        input=query,
                        encoding_format="float")

                    if isinstance(query, str):
                        result = responses.data[0].embedding
                        safe_log(
                            'debug', f"Generated single embedding, length: {len(result)}")
                        return result
                    else:
                        result = [
                            response.embedding for response in responses.data]
                        safe_log(
                            'debug', f"Generated {len(result)} embeddings")
                        return result

                # 处理超过5条的情况 - 更保守的批处理
                safe_log(
                    'info', f"Processing large batch with {len(query)} items using conservative approach")
                semaphore = asyncio.Semaphore(2)  # 进一步减少并发数为2
                batch_size = 5  # 减少批次大小为5

                async def process_batch(batch, batch_index):
                    async with semaphore:
                        safe_log(
                            'debug', f"Processing batch {batch_index + 1} with {len(batch)} items")
                        for batch_attempt in range(max_retries):
                            try:
                                # 添加超时保护
                                import asyncio
                                responses = await asyncio.wait_for(
                                    embedding_client.embeddings.create(
                                        model=embedding_model,
                                        input=batch,
                                        encoding_format="float"),
                                    timeout=30.0  # 30秒超时
                                )
                                result = [
                                    response.embedding for response in responses.data]
                                safe_log(
                                    'debug', f"Batch {batch_index + 1} completed with {len(result)} embeddings")
                                return result
                            except asyncio.TimeoutError:
                                safe_log(
                                    'error', f"Batch {batch_index + 1} timeout on attempt {batch_attempt + 1}")
                                if batch_attempt < max_retries - 1:
                                    await asyncio.sleep(retry_delay * (batch_attempt + 1))
                                    continue
                                else:
                                    raise Exception(
                                        f"Batch {batch_index + 1} failed after {max_retries} timeout attempts")
                            except Exception as batch_e:
                                safe_log(
                                    'error', f"Batch {batch_index + 1} failed on attempt {batch_attempt + 1}: {batch_e}")
                                if batch_attempt < max_retries - 1:
                                    await asyncio.sleep(retry_delay * (batch_attempt + 1))
                                    continue
                                else:
                                    raise batch_e

                # 将查询分成更小的批次
                batches = [query[i:i + batch_size]
                           for i in range(0, len(query), batch_size)]
                safe_log(
                    'info', f"Split into {len(batches)} batches of max {batch_size} items each")

                # 顺序处理批次而不是并发，减少内存压力
                all_results = []
                for i, batch in enumerate(batches):
                    try:
                        batch_result = await process_batch(batch, i)
                        all_results.extend(batch_result)
                        safe_log(
                            'debug', f"Completed batch {i + 1}/{len(batches)}, total embeddings: {len(all_results)}")

                        # 定期清理内存
                        if i % 3 == 0:  # 每3个批次清理一次内存
                            gc.collect()
                            current, peak = tracemalloc.get_traced_memory()
                            safe_log(
                                'debug', f"Memory cleanup completed. Current: {current / 1024 / 1024:.2f} MB")

                    except Exception as e:
                        safe_log(
                            'error', f"Failed to process batch {i + 1}: {e}")
                        raise e

                safe_log(
                    'info', f"Successfully generated {len(all_results)} embeddings total")
                return all_results

            except Exception as e:
                safe_log(
                    'error', f"Embedding attempt {attempt + 1} failed: {e}")

                if attempt < max_retries - 1:
                    # 更长的重试延迟
                    await asyncio.sleep(retry_delay * (attempt + 1) * 2)
                    continue
                else:
                    # 最终失败时进行内存清理
                    gc.collect()
                    raise Exception(
                        f"Failed to get embedding after {max_retries} attempts: {e}")

    finally:
        # 函数结束时强制内存清理
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        safe_log(
            'debug', f"Final memory state: {current / 1024 / 1024:.2f} MB, Peak: {peak / 1024 / 1024:.2f} MB")
        # 注意：不要在finally块中return，否则会覆盖try/except中的返回值


if __name__ == "__main__":
    asyncio.run(initialize_app_settings("../../config.yaml"))

    asyncio.run(get_embedding(["大模型"]))
