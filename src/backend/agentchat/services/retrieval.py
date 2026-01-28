from agentchat.services.rag.es_client import client as es_client
from agentchat.services.rag.vector_db import milvus_client


class MixRetrival:

    @classmethod
    async def retrival_milvus_documents(cls, query, knowledges_id, search_field):
        """从Milvus检索文档"""
        print(
            f"[MILVUS_RETRIEVAL_START] Query: {query}, Knowledge IDs: {knowledges_id}, Search field: {search_field}")

        documents = []
        queries = query if isinstance(query, list) else [query]

        for query in queries:
            print(f"[MILVUS_RETRIEVAL_PROCESS] Processing query: {query}")
            for knowledge_id in knowledges_id:
                print(
                    f"[MILVUS_RETRIEVAL_PROCESS] Searching knowledge ID: {knowledge_id}")
                try:
                    if search_field == "summary":
                        print(f"[MILVUS_RETRIEVAL_PROCESS] Using summary search")
                        results = await milvus_client.search_summary(query, knowledge_id)
                    else:
                        print(f"[MILVUS_RETRIEVAL_PROCESS] Using content search")
                        results = await milvus_client.search(query, knowledge_id)

                    print(
                        f"[MILVUS_RETRIEVAL_PROCESS] Got {len(results)} results for knowledge ID {knowledge_id}")
                    documents += results
                except Exception as e:
                    print(
                        f"[MILVUS_RETRIEVAL_ERROR] Search failed for knowledge ID {knowledge_id}: {e}")
                    print(
                        f"[MILVUS_RETRIEVAL_ERROR] Exception details: {type(e).__name__}: {str(e)}")

        print(
            f"[MILVUS_RETRIEVAL_RESULT] Total documents retrieved: {len(documents)}")
        return documents

    @classmethod
    async def retrival_es_documents(cls, query, knowledges_id, search_field):
        """从Elasticsearch检索文档"""
        print(
            f"[ES_RETRIEVAL_START] Query: {query}, Knowledge IDs: {knowledges_id}, Search field: {search_field}")

        documents = []
        queries = query if isinstance(query, list) else [query]

        for query in queries:
            print(f"[ES_RETRIEVAL_PROCESS] Processing query: {query}")
            for knowledge_id in knowledges_id:
                print(
                    f"[ES_RETRIEVAL_PROCESS] Searching knowledge ID: {knowledge_id}")
                try:
                    if search_field == "summary":
                        print(f"[ES_RETRIEVAL_PROCESS] Using summary search")
                        results = await es_client.search_documents_summary(query, knowledge_id)
                    else:
                        print(f"[ES_RETRIEVAL_PROCESS] Using content search")
                        results = await es_client.search_documents(query, knowledge_id)

                    print(
                        f"[ES_RETRIEVAL_PROCESS] Got {len(results)} results for knowledge ID {knowledge_id}")
                    documents += results
                except Exception as e:
                    print(
                        f"[ES_RETRIEVAL_ERROR] Search failed for knowledge ID {knowledge_id}: {e}")
                    print(
                        f"[ES_RETRIEVAL_ERROR] Exception details: {type(e).__name__}: {str(e)}")

        print(
            f"[ES_RETRIEVAL_RESULT] Total documents retrieved: {len(documents)}")
        return documents

    @classmethod
    async def mix_retrival_documents(cls, query_list, knowledges_id, search_field):
        print(
            f"[MIX_RETRIEVAL_START] Query list: {query_list}, Knowledge IDs: {knowledges_id}, Search field: {search_field}")

        es_documents = []
        milvus_documents = []

        for query in query_list:
            print(f"[MIX_RETRIEVAL_PROCESS] Processing query: {query}")
            try:
                if app_settings.rag.enable_elasticsearch:
                    print(
                        f"[MIX_RETRIEVAL_PROCESS] Retrieving from Elasticsearch for query: {query}")
                    es_docs = await cls.retrival_es_documents(query, knowledges_id, search_field)
                    es_documents += es_docs
                    print(
                        f"[MIX_RETRIEVAL_PROCESS] Retrieved {len(es_docs)} documents from Elasticsearch")
                else:
                    print(
                        f"[MIX_RETRIEVAL_PROCESS] Elasticsearch disabled, skipping ES retrieval")
            except Exception as e:
                print(
                    f"[MIX_RETRIEVAL_ERROR] Elasticsearch retrieval failed for query '{query}': {e}")

            try:
                print(
                    f"[MIX_RETRIEVAL_PROCESS] Retrieving from Milvus for query: {query}")
                milvus_docs = await cls.retrival_milvus_documents(query, knowledges_id, search_field)
                milvus_documents += milvus_docs
                print(
                    f"[MIX_RETRIEVAL_PROCESS] Retrieved {len(milvus_docs)} documents from Milvus")
            except Exception as e:
                print(
                    f"[MIX_RETRIEVAL_ERROR] Milvus retrieval failed for query '{query}': {e}")

        print(
            f"[MIX_RETRIEVAL_RESULT] Total ES documents: {len(es_documents)}, Total Milvus documents: {len(milvus_documents)}")
        return es_documents, milvus_documents
