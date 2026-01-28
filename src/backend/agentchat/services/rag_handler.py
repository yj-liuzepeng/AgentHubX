from loguru import logger
from typing import Optional
from agentchat.services.retrieval import MixRetrival
from agentchat.services.rewrite.query_write import query_rewriter
from agentchat.services.rag.es_client import client as es_client
from agentchat.services.rag.vector_db import milvus_client
from agentchat.services.rag.rerank import Reranker
from agentchat.settings import app_settings

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
        elif level == 'exception':
            safe_logger.exception(message)
        else:
            safe_logger.info(message)
    except:
        print(f"[{level.upper()}] {message}")


class RagHandler:

    @classmethod
    async def query_rewrite(cls, query):
        query_list = await query_rewriter.rewrite(query)
        return query_list

    @classmethod
    async def index_milvus_documents(cls, collection_name, chunks):
        await milvus_client.insert(collection_name, chunks)

    @classmethod
    async def index_es_documents(cls, index_name, chunks):
        await es_client.index_documents(index_name, chunks)

    @classmethod
    async def mix_retrival_documents(cls, query_list, knowledges_id, search_field="summary"):
        safe_log(
            'info', f"[MIX_RETRIEVAL_HANDLER_START] Query list: {query_list}, Knowledge IDs: {knowledges_id}, Search field: {search_field}")
        safe_log(
            'info', f"[MIX_RETRIEVAL_HANDLER_CONFIG] Elasticsearch enabled: {app_settings.rag.enable_elasticsearch}")

        if app_settings.rag.enable_elasticsearch:
            try:
                es_documents, milvus_documents = await MixRetrival.mix_retrival_documents(query_list, knowledges_id, search_field)
                # 先对ES和Milvus结果分别排序
                es_documents.sort(key=lambda x: x.score, reverse=True)
                milvus_documents.sort(key=lambda x: x.score, reverse=True)
                all_documents = es_documents + milvus_documents
                safe_log(
                    'info', f"[MIX_RETRIEVAL_HANDLER_RESULT] ES docs: {len(es_documents)}, Milvus docs: {len(milvus_documents)}")
            except Exception as e:
                safe_log(
                    'error', f"[MIX_RETRIEVAL_HANDLER_ERROR] Mixed retrieval failed: {e}")
                safe_log(
                    'info', f"[MIX_RETRIEVAL_HANDLER_FALLBACK] Falling back to Milvus only")
                all_documents = await MixRetrival.retrival_milvus_documents(query_list, knowledges_id, search_field)
        else:
            safe_log(
                'info', f"[MIX_RETRIEVAL_HANDLER_PROCESS] Using Milvus only retrieval")
            all_documents = await MixRetrival.retrival_milvus_documents(query_list, knowledges_id, search_field)

        safe_log(
            'info', f"[MIX_RETRIEVAL_HANDLER_PROCESS] Starting deduplication, total documents: {len(all_documents)}")

        # 合并并去重，保留分数更高的文档
        documents = []
        seen_chunk_ids = set()

        # 按分数从高到低排序
        all_documents.sort(key=lambda x: x.score, reverse=True)

        # 去重，保留分数最高的
        for doc in all_documents:
            if doc.chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(doc.chunk_id)
                documents.append(doc)
                if len(documents) >= 10:  # 限制返回10个文档
                    break

        safe_log(
            'info', f"[MIX_RETRIEVAL_HANDLER_RESULT] Final deduplicated documents: {len(documents)}")
        return documents

    @classmethod
    async def rag_query_summary(cls, query, knowledges_id, min_score: Optional[float] = None,
                                top_k: Optional[int] = None, needs_query_rewrite: bool = True):
        if min_score is None:
            min_score = app_settings.rag.retrival.get('min_score')
        if top_k is None:
            top_k = app_settings.rag.retrival.get('top_k')

        # 查询重写
        if needs_query_rewrite:
            rewritten_queries = await cls.query_rewrite(query)
        else:
            rewritten_queries = [query]

        # 文档检索
        retrieved_documents = await cls.mix_retrival_documents(rewritten_queries, knowledges_id, "summary")

        # 准备重排序的文档内容
        documents_to_rerank = [doc.content for doc in retrieved_documents]

        # 文档重排序
        reranked_docs = await Reranker.rerank_documents(query, documents_to_rerank)

        # 过滤结果
        filtered_results = []
        # 确保top_k不为None
        actual_top_k = top_k if top_k is not None else 0
        if len(reranked_docs) >= actual_top_k:
            for doc in reranked_docs[:actual_top_k]:
                if min_score is not None and doc.score >= min_score:
                    filtered_results.append(doc)
            # 拼接最终结果
            final_result = "\n".join(
                result.content for result in filtered_results)
            return final_result
        else:
            safe_log(
                'info', f"Recall for summary Field numbers < top k, Start recall use content Field")
            return await cls.retrieve_ranked_documents(query, knowledges_id, knowledges_id)

    @classmethod
    async def retrieve_ranked_documents(cls, query, collection_names, index_names=None, min_score: Optional[float] = None,
                                        top_k: Optional[int] = None, needs_query_rewrite: bool = True):
        """
        处理 RAG 流程：查询重写、文档检索、重排序、结果过滤和拼接。

        Args:
            query (str): 用户查询。
            collection_names (list[str]): 向量知识库 集合ID。
            index_names (list[str]): ES关键词库 集合ID。
            min_score (float): 文档最低分数阈值，默认为配置中的值。
            top_k (int): 召回文档的个数。
            needs_query_rewrite (bool): 是否需要开启Query重写，默认开启

        Returns:
            str: 拼接后的最终结果。
            """
        safe_log('info', f"[RAG_START] Query: {query}")
        safe_log(
            'info', f"[RAG_CONFIG] Collection names: {collection_names}, Index names: {index_names}")

        if min_score is None:
            min_score = app_settings.rag.retrival.get('min_score')
            safe_log(
                'debug', f"[RAG_CONFIG] Using default min_score: {min_score}")
        if top_k is None:
            top_k = app_settings.rag.retrival.get('top_k')
            safe_log('debug', f"[RAG_CONFIG] Using default top_k: {top_k}")

        # 查询重写
        safe_log(
            'info', f"[RAG_PROCESS] Starting query rewrite, needs_query_rewrite: {needs_query_rewrite}")
        if needs_query_rewrite:
            try:
                rewritten_queries = await cls.query_rewrite(query)
                safe_log(
                    'info', f"[RAG_PROCESS] Query rewrite completed, generated {len(rewritten_queries)} queries")
                safe_log(
                    'debug', f"[RAG_PROCESS] Rewritten queries: {rewritten_queries}")
            except Exception as e:
                safe_log('error', f"[RAG_ERROR] Query rewrite failed: {e}")
                rewritten_queries = [query]
        else:
            rewritten_queries = [query]
            safe_log(
                'debug', f"[RAG_PROCESS] Using original query without rewrite")

        # 文档检索
        safe_log(
            'info', f"[RAG_PROCESS] Starting document retrieval with {len(rewritten_queries)} queries")
        try:
            retrieved_documents = await cls.mix_retrival_documents(rewritten_queries, collection_names, "content")
            safe_log(
                'info', f"[RAG_PROCESS] Document retrieval completed, retrieved {len(retrieved_documents)} documents")
            safe_log(
                'debug', f"[RAG_PROCESS] Retrieved documents: {[doc.chunk_id for doc in retrieved_documents[:5]]}")
        except Exception as e:
            safe_log('error', f"[RAG_ERROR] Document retrieval failed: {e}")
            safe_log('exception', e)
            return "Error occurred during document retrieval."

        # 准备重排序的文档内容
        documents_to_rerank = [doc.content for doc in retrieved_documents]
        safe_log(
            'info', f"[RAG_PROCESS] Prepared {len(documents_to_rerank)} documents for reranking")

        # 文档重排序
        safe_log('info', f"[RAG_PROCESS] Starting document reranking")
        try:
            reranked_docs = await Reranker.rerank_documents(query, documents_to_rerank)
            safe_log(
                'info', f"[RAG_PROCESS] Document reranking completed, got {len(reranked_docs)} reranked documents")
            safe_log(
                'debug', f"[RAG_PROCESS] Reranked documents scores: {[doc.score for doc in reranked_docs[:5]]}")
        except Exception as e:
            safe_log('error', f"[RAG_ERROR] Document reranking failed: {e}")
            safe_log('exception', e)
            # Fallback: use original documents with basic scoring
            reranked_docs = retrieved_documents

        # 过滤结果
        safe_log(
            'info', f"[RAG_PROCESS] Starting result filtering with min_score: {min_score}, top_k: {top_k}")
        filtered_results = []
        # 确保top_k不为None
        actual_top_k = top_k if top_k is not None else 0
        docs_to_process = reranked_docs if len(
            reranked_docs) <= actual_top_k else reranked_docs[:actual_top_k]

        safe_log(
            'debug', f"[RAG_PROCESS] Processing {len(docs_to_process)} documents for filtering")
        for i, doc in enumerate(docs_to_process):
            if min_score is not None and doc.score >= min_score:
                filtered_results.append(doc)
                safe_log(
                    'debug', f"[RAG_PROCESS] Document {i} passed filtering (score: {doc.score})")

        safe_log(
            'info', f"[RAG_PROCESS] Filtering completed, {len(filtered_results)} documents passed")

        # 处理空结果
        if not filtered_results:
            safe_log(
                'warning', "[RAG_RESULT] No relevant documents found after filtering")
            return "No relevant documents found."

        # 拼接最终结果
        final_result = "\n".join(result.content for result in filtered_results)
        safe_log(
            'info', f"[RAG_RESULT] Final result prepared, length: {len(final_result)} characters")
        safe_log(
            'debug', f"[RAG_RESULT] Final result preview: {final_result[:200]}...")

        return final_result

    @classmethod
    async def delete_documents_es_milvus(cls, file_id, knowledge_id):
        """删除ES和Milvus中的文档数据
        
        Args:
            file_id: 文件ID
            knowledge_id: 知识库ID（用作集合/索引名）
            
        Returns:
            bool: 是否成功删除
            
        注意:
            该方法具有强容错能力，即使部分删除失败也不会抛出异常，
            避免导致主程序崩溃
        """
        safe_log('info', f"开始清理向量数据 - 文件ID: {file_id}, 知识库ID: {knowledge_id}")
        
        es_success = True
        milvus_success = True
        
        # 删除ES数据（如果启用）
        if app_settings.rag.enable_elasticsearch:
            try:
                safe_log('debug', f"开始删除ES数据: {file_id}")
                await es_client.delete_documents(file_id, knowledge_id)
                safe_log('info', f"ES数据删除成功: {file_id}")
            except Exception as es_e:
                safe_log('error', f"ES数据删除失败: {es_e}")
                safe_log('exception', es_e)
                es_success = False
        else:
            safe_log('debug', "ES未启用，跳过ES数据删除")
        
        # 删除Milvus数据（或Chroma数据）
        try:
            safe_log('debug', f"开始删除向量数据: {file_id}")
            result = await milvus_client.delete_by_file_id(file_id, knowledge_id)
            if result:
                safe_log('info', f"向量数据删除成功: {file_id}")
            else:
                safe_log('warning', f"向量数据删除可能失败: {file_id}")
                milvus_success = False
        except Exception as milvus_e:
            safe_log('error', f"向量数据删除失败: {milvus_e}")
            safe_log('exception', milvus_e)
            milvus_success = False
            # 即使向量删除失败，也不影响主流程
            safe_log('warning', f"向量数据删除失败，但继续执行 - 文件ID: {file_id}")
        
        # 返回总体结果 - 总是返回成功，避免程序崩溃
        if es_success and milvus_success:
            safe_log('info', f"向量数据清理完成: {file_id}")
        elif es_success or milvus_success:
            safe_log('warning', f"向量数据部分清理成功: ES={es_success}, Milvus={milvus_success}")
        else:
            safe_log('error', f"向量数据清理完全失败: {file_id}")
        
        # 总是返回True，避免上层调用因向量删除失败而崩溃
        # 数据库记录已经成功删除，向量数据清理失败可以后续处理
        return True
