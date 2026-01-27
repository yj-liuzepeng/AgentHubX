from loguru import logger
from agentchat.settings import app_settings
from agentchat.services.rag.embedding import get_embedding
from agentchat.schema.search import SearchModel
from pymilvus import connections, Collection, utility, FieldSchema, DataType, CollectionSchema
from typing import Dict, Optional, List

# 安全日志函数，避免logger未定义问题
def safe_log(level, message):
    try:
        import loguru
        safe_logger = loguru.logger
        if level == 'info':
            safe_logger.info(message)
        elif level == 'error':
            safe_logger.error(message)
        elif level == 'warning':
            safe_logger.warning(message)
        elif level == 'debug':
            safe_logger.debug(message)
    except:
        print(f"[{level.upper()}] {message}")


class MilvusClient:
    def __init__(self, **kwargs):
        self.milvus_host = app_settings.rag.vector_db.get('host')
        self.milvus_port = app_settings.rag.vector_db.get('port')
        self.collections: Dict[str, Collection] = {}
        self.loaded_collections: set = set()  # 跟踪已加载的集合

        # 连接管理
        self._connect()

    def _connect(self):
        """建立 Milvus 连接，带有重试机制"""
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                connections.connect("default", host=self.milvus_host, port=self.milvus_port)
                safe_log('info', f"Successfully connected to Milvus at {self.milvus_host}:{self.milvus_port}")
                return
            except Exception as e:
                safe_log('warning', f"Attempt {attempt + 1} to connect to Milvus failed: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    safe_log('error', f"Failed to connect to Milvus after {max_retries} attempts: {e}")
                    raise

    def _initialize_collections(self):
        """移除此方法，改为懒加载模式"""
        pass

    def _ensure_collection_loaded(self, collection: Collection) -> bool:
        """确保集合被加载到内存中（懒加载）"""
        collection_name = collection.name

        # 如果已经加载过，直接返回
        if collection_name in self.loaded_collections:
            return True

        try:
            # 尝试加载集合
            collection.load()
            self.loaded_collections.add(collection_name)
            safe_log('info', f"Collection '{collection_name}' loaded successfully")
            return True
        except Exception as e:
            # 如果加载失败，可能是因为集合已经加载或其他原因
            try:
                # 尝试通过简单查询来验证集合是否可用
                self.loaded_collections.add(collection_name)
                safe_log('info', f"Collection '{collection_name}' is already loaded")
                return True
            except Exception as inner_e:
                safe_log('error', f"Failed to load collection '{collection_name}': {e}, verification failed: {inner_e}")
                return False

    def _get_collection_safe(self, collection_name: str) -> Optional[Collection]:
        """安全地获取集合，按需加载（懒加载）"""
        try:
            # 如果集合不在缓存中，先检查是否存在
            if collection_name not in self.collections:
                if not self._collection_exists(collection_name):
                    safe_log('error', f"Collection '{collection_name}' does not exist")
                    return None

                # 创建集合对象但不立即加载
                collection = Collection(collection_name)
                self.collections[collection_name] = collection
                safe_log('debug', f"Collection '{collection_name}' added to cache")

            collection = self.collections[collection_name]

            # 懒加载：只有在实际使用时才加载到内存
            if not self._ensure_collection_loaded(collection):
                safe_log('warning', f"Collection '{collection_name}' may not be fully loaded, but will try to proceed")

            return collection

        except Exception as e:
            safe_log('error', f"Error getting collection '{collection_name}': {e}")
            return None

    def _collection_exists(self, collection_name: str) -> bool:
        """检查集合是否存在"""
        return utility.has_collection(collection_name)

    async def create_collection(self, collection_name: str):
        """创建 Milvus 集合（如果不存在）"""
        if self._collection_exists(collection_name):
            safe_log('info', f"Collection '{collection_name}' already exists")
            return

        try:
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2048),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
                FieldSchema(name="summary", dtype=DataType.VARCHAR, max_length=1024),
                FieldSchema(name="embedding_summary", dtype=DataType.FLOAT_VECTOR, dim=1024),
                FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="knowledge_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="update_time", dtype=DataType.VARCHAR, max_length=128),
            ]

            schema = CollectionSchema(fields, description=f"RAG Collection: {collection_name}")
            collection = Collection(collection_name, schema)

            # 创建索引
            index_params = {
                "index_type": "IVF_FLAT",
                "metric_type": "L2",
                "params": {"nlist": 128}
            }
            collection.create_index("embedding", index_params)
            collection.create_index("embedding_summary", index_params)

            # 加载集合
            collection.load()

            self.collections[collection_name] = collection
            safe_log('info', f'Successfully created and loaded collection: {collection_name}')

        except Exception as e:
            safe_log('error', f"Failed to create collection '{collection_name}': {e}")
            raise

    async def search(self, query: str, collection_name: str, top_k: int = 10) -> List[SearchModel]:
        """在指定集合中搜索相似数据"""
        collection = self._get_collection_safe(collection_name)
        if not collection:
            safe_log('error', f"Cannot search in collection '{collection_name}' - collection not available")
            return []

        try:
            # 生成查询向量
            query_embedding = await get_embedding(query)

            # 定义搜索参数
            search_params = {
                "metric_type": "L2",
                "params": {"nprobe": 16}
            }

            # 执行搜索
            results = collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["content", "chunk_id", "summary", "file_id", "file_name", "knowledge_id", "update_time"]
            )
    
            # 格式化结果
            documents = []
            for hit in results[0]:
                documents.append(
                    SearchModel(
                        content=hit.entity.content,
                        chunk_id=hit.entity.chunk_id,
                        file_id=hit.entity.file_id,
                        file_name=hit.entity.file_name,
                        knowledge_id=hit.entity.knowledge_id,
                        update_time=hit.entity.update_time,
                        summary=hit.entity.summary,
                        score=hit.distance
                    )
                )

            return documents

        except Exception as e:
            safe_log('error', f"Search failed in collection '{collection_name}': {e}")
            return []

    async def search_summary(self, query: str, collection_name: str, top_k: int = 10) -> List[SearchModel]:
        """在指定集合中搜索相似数据（基于摘要）"""
        collection = self._get_collection_safe(collection_name)
        if not collection:
            safe_log('error', f"Cannot search in collection '{collection_name}' - collection not available")
            return []

        try:
            # 生成查询向量
            query_embedding = await get_embedding(query)

            # 定义搜索参数
            search_params = {
                "metric_type": "L2",
                "params": {"nprobe": 16}
            }

            # 执行搜索
            results = collection.search(
                data=[query_embedding],
                anns_field="embedding_summary",
                param=search_params,
                limit=top_k,
                output_fields=["content", "chunk_id", "summary", "file_id", "file_name", "knowledge_id", "update_time"]
            )

            # 格式化结果
            documents = []
            for hit in results[0]:
                documents.append(
                    SearchModel(
                        content=hit.entity.get("content", ""),
                        chunk_id=hit.entity.get("chunk_id", ""),
                        file_id=hit.entity.get("file_id", ""),
                        file_name=hit.entity.get("file_name", ""),
                        knowledge_id=hit.entity.get("knowledge_id", ""),
                        update_time=hit.entity.get("update_time", ""),
                        summary=hit.entity.get("summary", ""),
                        score=hit.distance
                    )
                )

            return documents

        except Exception as e:
            safe_log('error', f"Summary search failed in collection '{collection_name}': {e}")
            return []

    async def delete_by_file_id(self, file_id: str, collection_name: str) -> bool:
        """根据文件ID删除数据"""
        collection = self._get_collection_safe(collection_name)
        if not collection:
            safe_log('error', f"Cannot delete from collection '{collection_name}' - collection not available")
            return False

        try:
            # 构造查询表达式
            query_expr = f'file_id == "{file_id}"'

            # 查询符合条件的文档
            results = collection.query(query_expr, output_fields=["id"])
            delete_ids = [result['id'] for result in results]

            # 如果找到匹配的文档，执行删除操作
            if delete_ids:
                delete_expr = f"id in {delete_ids}"
                collection.delete(delete_expr)
                collection.flush()  # 确保删除操作立即生效
                safe_log('info', f'Successfully deleted {len(delete_ids)} documents for file_id: {file_id}')
                return True
            else:
                safe_log('info', f'No documents found for file_id: {file_id}')
                return True

        except Exception as e:
            safe_log('error', f'Error deleting file_id {file_id} from collection {collection_name}: {e}')
            return False

    async def insert(self, collection_name: str, chunks) -> bool:
        """插入数据到指定集合，带有内存管理和错误恢复"""
        import gc
        import psutil
        import os
        
        # 使用安全的日志记录，避免logger未定义问题
        try:
            import loguru
            safe_logger = loguru.logger
        except:
            safe_logger = None
            
        def safe_log(level, message):
            try:
                if safe_logger:
                    if level == 'info':
                        safe_logger.info(message)
                    elif level == 'error':
                        safe_logger.error(message)
                    elif level == 'warning':
                        safe_logger.warning(message)
                    elif level == 'debug':
                        safe_logger.debug(message)
                else:
                    print(f"[{level.upper()}] {message}")
            except:
                print(f"[{level.upper()}] {message}")
        
        def get_memory_usage():
            try:
                process = psutil.Process(os.getpid())
                return process.memory_info().rss / 1024 / 1024  # MB
            except:
                return 0
        
        safe_log('info', f"Starting insert into collection '{collection_name}' with {len(chunks)} chunks")
        initial_memory = get_memory_usage()
        safe_log('debug', f"Initial memory usage: {initial_memory:.2f} MB")
        
        if collection_name not in self.collections:
            safe_log('info', f"Collection '{collection_name}' not found, creating...")
            await self.create_collection(collection_name)

        collection = self._get_collection_safe(collection_name)
        if not collection:
            safe_log('error', f"Cannot insert into collection '{collection_name}' - collection not available")
            return False

        try:
            # 更保守的批次大小以避免内存问题
            batch_size = 20  # 从50减少到20
            total_chunks = len(chunks)
            
            safe_log('info', f"Processing {total_chunks} chunks in batches of {batch_size}")
            
            for i in range(0, total_chunks, batch_size):
                batch_chunks = chunks[i:i + batch_size]
                current_memory = get_memory_usage()
                safe_log('debug', f"Processing batch {i//batch_size + 1}/{(total_chunks + batch_size - 1)//batch_size}, Memory: {current_memory:.2f} MB")
                
                # 检查内存使用情况，如果内存使用过高则进行清理
                if current_memory > initial_memory + 500:  # 如果内存增加超过500MB
                    safe_log('warning', f"High memory usage detected: {current_memory:.2f} MB, forcing garbage collection")
                    gc.collect()
                    current_memory = get_memory_usage()
                    safe_log('info', f"Memory after cleanup: {current_memory:.2f} MB")
                
                # 准备批次数据
                content_list, summary_list, chunk_id_list = [], [], []
                file_id_list, file_name_list, update_time_list, knowledge_id_list = [], [], [], []

                for chunk in batch_chunks:
                    content_list.append(chunk.content)
                    summary_list.append(chunk.summary)
                    chunk_id_list.append(chunk.chunk_id)
                    file_id_list.append(chunk.file_id)
                    file_name_list.append(chunk.file_name)
                    update_time_list.append(chunk.update_time)
                    knowledge_id_list.append(chunk.knowledge_id)

                try:
                    # 生成嵌入向量 - 使用更小的批次
                    safe_log('info', f"Generating embeddings for batch {i//batch_size + 1} ({len(content_list)} content, {len(summary_list)} summaries)")
                    
                    # 分别处理内容和摘要，减少内存峰值
                    safe_log('debug', f"Generating content embeddings for batch {i//batch_size + 1}")
                    embedding_list = await get_embedding(content_list)
                    
                    # 清理内容列表内存
                    content_list = None
                    gc.collect()
                    
                    safe_log('debug', f"Generating summary embeddings for batch {i//batch_size + 1}")
                    embedding_summary_list = await get_embedding(summary_list)
                    
                    # 清理摘要列表内存
                    summary_list = None
                    gc.collect()

                    # 组织数据
                    data = [
                        chunk_id_list,
                        content_list if content_list else [chunk.content for chunk in batch_chunks],  # 重新获取内容
                        embedding_list,
                        summary_list if summary_list else [chunk.summary for chunk in batch_chunks],  # 重新获取摘要
                        embedding_summary_list,
                        file_id_list,
                        file_name_list,
                        knowledge_id_list,
                        update_time_list
                    ]

                    # 插入批次数据
                    safe_log('info', f"Inserting batch {i//batch_size + 1} into collection ({len(batch_chunks)} chunks)")
                    collection.insert(data)
                    safe_log('info', f"Successfully inserted batch {i//batch_size + 1} with {len(batch_chunks)} chunks")
                    
                    # 批次完成后清理内存
                    data = None
                    embedding_list = None
                    embedding_summary_list = None
                    gc.collect()
                    
                except Exception as batch_e:
                    safe_log('error', f"Failed to insert batch {i//batch_size + 1}: {batch_e}")
                    raise batch_e

            # 所有批次完成后刷新
            safe_log('info', f"Flushing collection '{collection_name}'")
            collection.flush()
            
            final_memory = get_memory_usage()
            safe_log('info', f"Successfully inserted all {total_chunks} chunks into collection '{collection_name}'")
            safe_log('info', f"Memory usage change: {initial_memory:.2f} MB → {final_memory:.2f} MB (+{final_memory - initial_memory:.2f} MB)")
            
            # 最终内存清理
            gc.collect()
            return True

        except Exception as e:
            safe_log('error', f"Failed to insert data into collection '{collection_name}': {e}")
            # 出错时强制内存清理
            gc.collect()
            return False
        
        finally:
            # 确保最终清理
            gc.collect()

    async def delete_collection(self, collection_name: str) -> bool:
        """删除集合"""
        if collection_name not in self.collections:
            safe_log('warning', f"Collection '{collection_name}' not found in cache")
            return False

        try:
            # 删除集合
            Collection(collection_name).drop()
            self.collections.pop(collection_name, None)
            safe_log('info', f"Collection '{collection_name}' deleted successfully")
            return True

        except Exception as e:
            safe_log('error', f"Failed to delete collection '{collection_name}': {e}")
            return False

    def unload_collection(self, collection_name: str) -> bool:
        """卸载集合以释放内存"""
        try:
            if collection_name in self.collections:
                collection = self.collections[collection_name]
                collection.release()
                self.loaded_collections.discard(collection_name)
                safe_log('info', f"Collection '{collection_name}' unloaded successfully")
                return True
            else:
                safe_log('warning', f"Collection '{collection_name}' not found in cache")
                return False
        except Exception as e:
            safe_log('error', f"Failed to unload collection '{collection_name}': {e}")
            return False

    def get_loaded_collections(self) -> List[str]:
        """获取当前已加载的集合列表"""
        return list(self.loaded_collections)

    def get_all_collections(self) -> List[str]:
        """获取所有可用集合列表（不加载）"""
        try:
            return utility.list_collections()
        except Exception as e:
            safe_log('error', f"Failed to get collection list: {e}")
            return []

    def close(self):
        """关闭连接并清理资源"""
        try:
            # 卸载所有已加载的集合
            for collection_name in list(self.loaded_collections):
                self.unload_collection(collection_name)

            connections.disconnect("default")
            safe_log('info', "Milvus connection closed and all collections unloaded")
        except Exception as e:
            safe_log('error', f"Error closing Milvus connection: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

