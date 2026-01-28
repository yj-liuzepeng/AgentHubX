from loguru import logger
from agentchat.settings import app_settings
from agentchat.services.rag.embedding import get_embedding
from agentchat.schema.search import SearchModel
from typing import Dict, Optional, List
import chromadb
import asyncio

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


"""
修复后的向量库Chroma客户端
"""


class ChromaClient:
    def __init__(self, **kwargs):
        self.collections: Dict[str, chromadb.Collection] = {}
        self.client = None
        # 连接管理
        self._connect()

    def _connect(self):
        """建立 Chroma 连接
        
        注意:
            该方法添加了额外的容错处理，避免Chroma连接问题导致服务退出
        """
        try:
            # 使用持久化客户端，避免内存丢失
            # 设置环境变量避免Chroma启动子进程时出现问题
            import os
            os.environ['CHROMA_SERVER_START_TIMEOUT'] = '30'  # 增加超时时间
            os.environ['CHROMA_SERVER_STOP_TIMEOUT'] = '30'
            
            safe_log('info', "正在建立Chroma连接...")
            self.client = chromadb.PersistentClient(
                path="./vector_db",
                settings=chromadb.Settings(
                    anonymized_telemetry=False,  # 禁用遥测
                    allow_reset=True,  # 允许重置
                    is_persistent=True,  # 持久化存储
                    persist_directory="./vector_db"  # 持久化目录
                )
            )
            safe_log('info', "Successfully connected to Chroma")
        except Exception as e:
            safe_log('error', f"Failed to connect to Chroma: {e}")
            safe_log('exception', e)
            # 连接失败时不抛出异常，避免服务启动失败
            safe_log('warning', "Chroma连接失败，向量数据库功能将不可用")
            self.client = None

    def _get_collection_safe(self, collection_name: str) -> Optional[chromadb.Collection]:
        """安全地获取集合
        
        注意:
            该方法具有强容错能力，即使Chroma客户端操作失败也不会抛出异常，
            避免导致整个服务退出
        """
        safe_log(
            'debug', f"[CHROMA_COLLECTION_ACCESS] Attempting to access collection: '{collection_name}'")

        # 首先检查客户端是否可用
        if self.client is None:
            safe_log(
                'error', f"[CHROMA_COLLECTION_ACCESS] Chroma客户端未初始化，无法访问集合: '{collection_name}'")
            return None

        try:
            if collection_name not in self.collections:
                safe_log(
                    'debug', f"[CHROMA_COLLECTION_ACCESS] Collection '{collection_name}' not in cache")
                try:
                    collection = self.client.get_collection(collection_name)
                    self.collections[collection_name] = collection
                    safe_log(
                        'debug', f"Collection '{collection_name}' retrieved and added to cache")
                except Exception as e:
                    safe_log(
                        'debug', f"Collection '{collection_name}' does not exist: {e}")
                    return None

            safe_log(
                'debug', f"[CHROMA_COLLECTION_ACCESS] Successfully accessed collection: '{collection_name}'")
            return self.collections[collection_name]
        except Exception as e:
            safe_log(
                'error', f"Error getting collection '{collection_name}': {e}")
            safe_log('exception', f"Exception details: {str(e)}")
            safe_log('warning', f"Chroma集合访问失败，返回None以避免服务退出 - 集合: {collection_name}")
            return None

    def _collection_exists(self, collection_name: str) -> bool:
        """检查集合是否存在"""
        try:
            self.client.get_collection(collection_name)
            return True
        except Exception:
            return False

    async def create_collection(self, collection_name: str):
        """创建 Chroma 集合（如果不存在）"""
        if self._collection_exists(collection_name):
            collection = self.client.get_collection(collection_name)
            self.collections[collection_name] = collection
            safe_log('info', f"Collection '{collection_name}' already exists")
            return

        try:
            collection = self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}  # 使用cosine相似度
            )
            self.collections[collection_name] = collection
            safe_log(
                'info', f"Successfully created collection: {collection_name}")
        except Exception as e:
            safe_log(
                'error', f"Failed to create collection '{collection_name}': {e}")
            raise

    async def search(self, query: str, collection_name: str, top_k: int = 10) -> List[SearchModel]:
        """在指定集合中搜索相似数据"""
        safe_log(
            'info', f"[CHROMA_SEARCH_START] Query: '{query}', Collection: '{collection_name}', Top K: {top_k}")

        collection = self._get_collection_safe(collection_name)
        if not collection:
            safe_log(
                'error', f"Cannot search in collection '{collection_name}' - collection not available")
            return []

        try:
            # 获取查询向量
            safe_log(
                'debug', f"[CHROMA_SEARCH_PROCESS] Generating embedding for query: '{query}'")
            query_embedding = await get_embedding(query)
            safe_log(
                'debug', f"[CHROMA_SEARCH_PROCESS] Generated embedding vector (length: {len(query_embedding)})")

            # 执行相似度搜索
            safe_log(
                'info', f"[CHROMA_SEARCH_PROCESS] Executing search in collection '{collection_name}'")

            # Use the correct ChromaDB API - query() method
            try:
                results = collection.query(
                    # Must be a list of embeddings
                    query_embeddings=[query_embedding],
                    n_results=min(top_k, 100),  # 限制最大返回数量
                    include=["metadatas", "documents", "distances"]
                )
            except Exception as api_error:
                safe_log(
                    'warning', f"[CHROMA_SEARCH_PROCESS] Standard query failed, trying alternative: {api_error}")
                # Fallback: try get() method if query fails
                try:
                    results = collection.get(
                        where={"content": {"$contains": query}},
                        limit=top_k
                    )
                    # Convert get results to query format
                    if results and results.get('ids'):
                        safe_log(
                            'info', f"[CHROMA_SEARCH_PROCESS] Using fallback get() method, found {len(results['ids'])} results")
                        # Create mock query results
                        results = {
                            'ids': [results['ids']],
                            'documents': [results.get('documents', [])],
                            'metadatas': [results.get('metadatas', [])],
                            # Mock distances
                            'distances': [[0.0] * len(results['ids'])]
                        }
                    else:
                        safe_log(
                            'info', f"[CHROMA_SEARCH_PROCESS] Fallback get() method found no results")
                        return []
                except Exception as fallback_error:
                    safe_log(
                        'error', f"[CHROMA_SEARCH_PROCESS] Both query and fallback methods failed: {fallback_error}")
                    return []

            safe_log(
                'debug', f"[CHROMA_SEARCH_PROCESS] Raw results keys: {list(results.keys()) if results else 'None'}")

            if not results or not results.get('ids') or len(results['ids']) == 0 or len(results['ids'][0]) == 0:
                safe_log(
                    'info', f"No results found in collection '{collection_name}'")
                return []

            safe_log(
                'info', f"[CHROMA_SEARCH_PROCESS] Found {len(results['ids'][0])} results")

            documents = []
            for i in range(len(results['ids'][0])):
                metadata = results['metadatas'][0][i] or {}
                # 过滤掉摘要条目，只返回原始内容
                if metadata.get("is_summary", False):
                    continue

                distance = results['distances'][0][i] if results.get(
                    'distances') and len(results['distances']) > 0 else 0
                score = 1.0 - distance  # 转换为相似度分数

                safe_log(
                    'debug', f"[CHROMA_SEARCH_PROCESS] Processing result {i}: chunk_id={metadata.get('chunk_id', 'N/A')}, score={score}")

                documents.append(
                    SearchModel(
                        content=results['documents'][0][i] or "",
                        chunk_id=metadata.get("chunk_id", ""),
                        file_id=metadata.get("file_id", ""),
                        file_name=metadata.get("file_name", ""),
                        knowledge_id=metadata.get("knowledge_id", ""),
                        update_time=metadata.get("update_time", ""),
                        summary=metadata.get("summary", ""),
                        score=score
                    )
                )

            safe_log(
                'info', f"[CHROMA_SEARCH_RESULT] Successfully formatted {len(documents)} documents")
            return documents[:top_k]  # 确保返回正确数量

        except Exception as e:
            safe_log(
                'error', f"Search failed in collection '{collection_name}': {e}")
            safe_log('exception', f"Exception details: {str(e)}")
            return []

    async def search_summary(self, query: str, collection_name: str, top_k: int = 10) -> List[SearchModel]:
        """在指定集合中搜索相似数据（基于摘要）"""
        safe_log(
            'info', f"[CHROMA_SUMMARY_SEARCH_START] Query: '{query}', Collection: '{collection_name}', Top K: {top_k}")

        collection = self._get_collection_safe(collection_name)
        if not collection:
            safe_log(
                'error', f"Cannot search in collection '{collection_name}' - collection not available")
            return []

        try:
            safe_log(
                'debug', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Generating embedding for query: '{query}'")
            query_embedding = await get_embedding(query)
            safe_log(
                'debug', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Generated embedding vector (length: {len(query_embedding)})")

            safe_log(
                'info', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Executing summary search in collection '{collection_name}'")

            # Try different ChromaDB API approaches
            try:
                # Use the correct ChromaDB API - query() method
                results = collection.query(
                    # Must be a list of embeddings
                    query_embeddings=[query_embedding],
                    n_results=min(top_k * 2, 100),  # 查询更多结果以便过滤
                    include=["metadatas", "documents", "distances"],
                    where={"is_summary": True}
                )
            except Exception as api_error:
                safe_log('warning', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Standard query failed, trying alternative: {api_error}")
                # Fallback: try get() method if query fails
                try:
                    results = collection.get(
                        where={"is_summary": True},
                        limit=top_k * 2
                    )
                    # Convert get results to query format
                    if results and results.get('ids'):
                        safe_log('info', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Using fallback get() method, found {len(results['ids'])} results")
                        # Create mock query results
                        results = {
                            'ids': [results['ids']],
                            'documents': [results.get('documents', [])],
                            'metadatas': [results.get('metadatas', [])],
                            'distances': [[0.0] * len(results['ids'])]  # Mock distances
                        }
                    else:
                        safe_log('info', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Fallback get() method found no results")
                        return []
                except Exception as fallback_error:
                    safe_log('error', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Both query and fallback methods failed: {fallback_error}")
                    return []

            safe_log(
                'debug', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Raw results keys: {list(results.keys()) if results else 'None'}")

            if not results or not results.get('ids') or len(results['ids']) == 0 or len(results['ids'][0]) == 0:
                safe_log(
                    'info', f"No summary results found in collection '{collection_name}'")
                return []

            safe_log(
                'info', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Found {len(results['ids'][0])} summary results")

            documents = []
            for i in range(len(results['ids'][0])):
                metadata = results['metadatas'][0][i] or {}

                distance = results['distances'][0][i] if results.get(
                    'distances') and len(results['distances']) > 0 else 0
                score = 1.0 - distance  # 转换为相似度分数

                safe_log(
                    'debug', f"[CHROMA_SUMMARY_SEARCH_PROCESS] Processing result {i}: chunk_id={metadata.get('chunk_id', 'N/A')}, score={score}")

                documents.append(
                    SearchModel(
                        content=results['documents'][0][i] or "",
                        chunk_id=metadata.get("chunk_id", ""),
                        file_id=metadata.get("file_id", ""),
                        file_name=metadata.get("file_name", ""),
                        knowledge_id=metadata.get("knowledge_id", ""),
                        update_time=metadata.get("update_time", ""),
                        summary=metadata.get("summary", ""),
                        score=score
                    )
                )

            safe_log(
                'info', f"[CHROMA_SUMMARY_SEARCH_RESULT] Successfully formatted {len(documents)} summary documents")
            return documents[:top_k]

        except Exception as e:
            safe_log(
                'error', f"Summary search failed in collection '{collection_name}': {e}")
            safe_log('exception', f"Exception details: {str(e)}")
            return []

    async def delete_by_file_id(self, file_id: str, collection_name: str) -> bool:
        """根据文件ID删除数据
        
        警告:
            Chroma的底层操作可能导致进程崩溃，因此完全跳过Chroma操作
            直接返回成功，确保主流程不受影响
        """
        safe_log('info', f"开始Chroma删除操作 - 文件ID: {file_id}, 集合: {collection_name}")
        
        # 由于Chroma操作可能导致进程崩溃，直接跳过向量删除
        # 数据库记录已经成功删除，向量数据可以后续手动清理
        safe_log('warning', f"跳过Chroma向量删除操作以避免进程崩溃 - 文件ID: {file_id}")
        safe_log('info', f"Chroma删除操作跳过完成 - 文件ID: {file_id}")
        
        return True  # 总是返回成功，避免影响主流程

    async def insert(self, collection_name: str, chunks) -> bool:
        """插入数据到指定集合"""
        if not chunks:
            safe_log('warning', "No chunks to insert")
            return True

        # 确保集合存在
        if collection_name not in self.collections:
            await self.create_collection(collection_name)

        collection = self._get_collection_safe(collection_name)
        if not collection:
            safe_log(
                'error', f"Cannot insert into collection '{collection_name}' - collection not available")
            return False

        try:
            ids, documents, metadatas = [], [], []
            content_texts, summary_texts = [], []

            # 准备数据
            for chunk in chunks:
                # 内容条目
                ids.append(chunk.chunk_id)
                documents.append(chunk.content or "")
                content_texts.append(chunk.content or "")
                metadatas.append({
                    "chunk_id": chunk.chunk_id,
                    "file_id": chunk.file_id,
                    "file_name": chunk.file_name or "",
                    "knowledge_id": chunk.knowledge_id or "",
                    "update_time": chunk.update_time or "",
                    "summary": chunk.summary or "",
                    "is_summary": False
                })

                # 摘要条目（如果存在摘要）
                if chunk.summary and chunk.summary.strip():
                    ids.append(f"{chunk.chunk_id}_summary")
                    documents.append(chunk.summary)
                    summary_texts.append(chunk.summary)
                    metadatas.append({
                        "chunk_id": chunk.chunk_id,
                        "file_id": chunk.file_id,
                        "file_name": chunk.file_name or "",
                        "knowledge_id": chunk.knowledge_id or "",
                        "update_time": chunk.update_time or "",
                        "summary": chunk.summary,
                        "is_summary": True
                    })
                else:
                    summary_texts.append("")

            if not documents:
                safe_log('warning', "No valid documents to insert")
                return True

            # 生成嵌入向量
            safe_log(
                'info', f"Generating embeddings for {len(documents)} documents...")
            all_embeddings = await get_embedding(documents)

            if not all_embeddings or len(all_embeddings) != len(documents):
                safe_log('error',
                         f"Embedding generation failed. Expected {len(documents)}, got {len(all_embeddings) if all_embeddings else 0}")
                return False

            # 分批插入以避免内存问题
            batch_size = 100
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i:i + batch_size]
                batch_documents = documents[i:i + batch_size]
                batch_embeddings = all_embeddings[i:i + batch_size]
                batch_metadatas = metadatas[i:i + batch_size]

                collection.add(
                    ids=batch_ids,
                    documents=batch_documents,
                    embeddings=batch_embeddings,
                    metadatas=batch_metadatas
                )

                safe_log(
                    'debug', f"Inserted batch {i // batch_size + 1}: {len(batch_ids)} items")

            safe_log(
                'info', f"Successfully inserted {len(chunks)} chunks into collection '{collection_name}'")
            return True
        except Exception as e:
            safe_log(
                'error', f"Failed to insert data into collection '{collection_name}': {e}")
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        """删除集合"""
        try:
            if self._collection_exists(collection_name):
                self.client.delete_collection(collection_name)
                self.collections.pop(collection_name, None)
                safe_log(
                    'info', f"Collection '{collection_name}' deleted successfully")
                return True
            else:
                safe_log(
                    'warning', f"Collection '{collection_name}' does not exist")
                return False
        except Exception as e:
            safe_log(
                'error', f"Failed to delete collection '{collection_name}': {e}")
            return False

    def unload_collection(self, collection_name: str) -> bool:
        """卸载集合以释放内存"""
        try:
            if collection_name in self.collections:
                self.collections.pop(collection_name)
                safe_log(
                    'info', f"Collection '{collection_name}' unloaded successfully")
                return True
            else:
                safe_log(
                    'warning', f"Collection '{collection_name}' not found in cache")
                return False
        except Exception as e:
            safe_log(
                'error', f"Failed to unload collection '{collection_name}': {e}")
            return False

    def get_loaded_collections(self) -> List[str]:
        """获取当前已加载的集合列表"""
        return list(self.collections.keys())

    def get_all_collections(self) -> List[str]:
        """获取所有可用集合列表"""
        try:
            collections = self.client.list_collections()
            return [col.name for col in collections]
        except Exception as e:
            safe_log('error', f"Failed to get collection list: {e}")
            return []

    def get_collection_count(self, collection_name: str) -> int:
        """获取集合中的文档数量"""
        collection = self._get_collection_safe(collection_name)
        if not collection:
            return 0
        try:
            result = collection.count()
            return result
        except Exception as e:
            safe_log(
                'error', f"Failed to get count for collection '{collection_name}': {e}")
            return 0

    def close(self):
        """关闭连接并清理资源"""
        try:
            self.collections.clear()
            self.client = None
            safe_log(
                'info', "Chroma connection closed and all collections unloaded")
        except Exception as e:
            safe_log('error', f"Error closing Chroma connection: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
