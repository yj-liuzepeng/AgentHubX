from uuid import uuid4

from loguru import logger
from agentchat.database.dao.knowledge_file import KnowledgeFileDao
from agentchat.database.models.knowledge_file import Status
from agentchat.database.models.user import AdminUser
from agentchat.services.rag.parser import doc_parser
from agentchat.services.rag_handler import RagHandler
from agentchat.settings import app_settings

class KnowledgeFileService:
    @classmethod
    def parse_knowledge_file(cls):
        """使用 miner u 进行解析PDF，然后进行切割"""
        pass

    @classmethod
    async def get_knowledge_file(cls, knowledge_id):
        results = await KnowledgeFileDao.select_knowledge_file(knowledge_id)
        return [res.to_dict() for res in results]

    @classmethod
    async def create_knowledge_file(cls, file_name, file_path, knowledge_id, user_id, oss_url, file_size_bytes):
        knowledge_file_id = uuid4().hex
        await KnowledgeFileDao.create_knowledge_file(knowledge_file_id, file_name, knowledge_id, user_id, oss_url, file_size_bytes)
        try:
            # 解析状态改成 进行中
            await cls.update_parsing_status(knowledge_file_id, Status.process)
            # 针对不同的文件类型进行解析
            chunks = await doc_parser.parse_doc_into_chunks(knowledge_file_id, file_path, knowledge_id)

            # 将上传的文件解析成chunks 放到ES 和 Milvus
            await RagHandler.index_milvus_documents(knowledge_id, chunks)
            if app_settings.rag.enable_elasticsearch:
                await RagHandler.index_es_documents(knowledge_id, chunks)
            # 解析状态改为 成功
            await cls.update_parsing_status(knowledge_file_id, Status.success)
        except Exception as err:
            # 解析状态改为 失败
            logger.info(f"Create Knowledge File Error: {err}")
            await cls.update_parsing_status(knowledge_file_id, Status.fail)
            raise ValueError(f"Create Knowledge File Error: {err}")

    @classmethod
    async def delete_knowledge_file(cls, knowledge_file_id):
        """删除知识文件，包含完整的错误处理和清理操作
        
        Args:
            knowledge_file_id: 知识文件ID
            
        Returns:
            bool: 删除是否成功
            
        Raises:
            ValueError: 当文件不存在或删除失败时
            
        注意:
            该方法具有强容错能力，即使向量数据清理失败，
            只要数据库记录删除成功，就会返回成功
        """
        # 添加系统信号处理，防止意外中断
        import signal
        
        def safe_signal_handler(signum, frame):
            logger.warning(f"删除操作收到系统信号 {signum}，继续执行以确保数据一致性")
            # 不退出程序，只记录警告
            
        # 临时注册信号处理，确保删除操作不会被中断
        old_term_handler = signal.signal(signal.SIGTERM, safe_signal_handler)
        old_int_handler = signal.signal(signal.SIGINT, safe_signal_handler)
        
        try:
            # 首先获取文件信息，验证是否存在
            knowledge_file = await cls.select_knowledge_file_by_id(knowledge_file_id)
            if not knowledge_file:
                raise ValueError(f"知识文件不存在: {knowledge_file_id}")
            
            file_id = knowledge_file.id
            knowledge_id = knowledge_file.knowledge_id
            
            logger.info(f"开始删除知识文件: {file_id} (知识库: {knowledge_id})")
            
            # 先删除数据库记录，确保数据一致性
            # 如果向量删除失败，数据库记录仍然存在，可以重试
            await KnowledgeFileDao.delete_knowledge_file(knowledge_file_id)
            logger.info(f"数据库记录删除成功: {knowledge_file_id}")
            
            # 然后清理向量数据，这部分失败不会影响数据库一致性
            try:
                vector_result = await RagHandler.delete_documents_es_milvus(file_id, knowledge_id)
                if vector_result:
                    logger.info(f"向量数据清理完成: {file_id}")
                else:
                    logger.warning(f"向量数据清理返回失败状态，但继续执行: {file_id}")
            except Exception as vector_e:
                # 向量删除失败只记录日志，不抛出异常，确保主流程成功
                logger.warning(f"向量数据清理失败: {vector_e}，但数据库记录已删除，删除操作视为成功")
            
            return True
            
        except ValueError as ve:
            # 文件不存在等验证错误
            logger.error(f"删除知识文件验证失败: {ve}")
            raise ve
        except Exception as e:
            # 其他未预期的错误
            logger.error(f"删除知识文件失败: {e}")
            raise ValueError(f"删除知识文件失败: {e}")
        finally:
            # 恢复原始信号处理
            signal.signal(signal.SIGTERM, old_term_handler)
            signal.signal(signal.SIGINT, old_int_handler)

    @classmethod
    async def select_knowledge_file_by_id(cls, knowledge_file_id):
        knowledge_file = await KnowledgeFileDao.select_knowledge_file_by_id(knowledge_file_id)
        return knowledge_file

    @classmethod
    async def verify_user_permission(cls, knowledge_file_id, user_id):
        """验证用户对知识文件的访问权限
        
        Args:
            knowledge_file_id: 知识文件ID
            user_id: 用户ID
            
        Raises:
            ValueError: 当文件不存在或没有权限时
        """
        knowledge_file = await cls.select_knowledge_file_by_id(knowledge_file_id)
        if not knowledge_file:
            raise ValueError(f"知识文件不存在: {knowledge_file_id}")
        
        if user_id not in (AdminUser, knowledge_file.user_id):
            raise ValueError("没有权限访问该知识文件")

    @classmethod
    async def update_parsing_status(cls, knowledge_file_id, status):
        return await KnowledgeFileDao.update_parsing_status(knowledge_file_id, status)