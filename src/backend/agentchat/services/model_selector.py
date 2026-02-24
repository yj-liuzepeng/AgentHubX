
import re
from typing import List, Dict, Any, Optional
from loguru import logger

class ModelSelector:
    """
    自动模型选择器
    根据用户输入和可用模型列表，自动选择最合适的模型。
    """

    # 预定义的模型能力关键词映射（越靠前优先级越高）
    
    # 强推理/复杂任务模型
    POWERFUL_MODELS = [
        "gpt-4", "claude-3-opus", "gemini-1.5-pro", "deepseek-v3", "deepseek-chat", "gpt-4-turbo"
    ]
    
    # 快速/低成本模型
    FAST_MODELS = [
        "gpt-3.5", "gpt-4o-mini", "claude-3-haiku", "gemini-1.5-flash", "llama-3", "qwen", "glm-4"
    ]
    
    # 编程专用模型
    CODING_MODELS = [
        "deepseek-coder", "codellama", "gpt-4", "claude-3-opus", "gpt-4-turbo"
    ]

    @classmethod
    def select_model(cls, query: str, available_models: List[Dict[str, Any]]) -> str:
        """
        根据查询内容和可用模型选择最佳模型ID。
        
        Args:
            query: 用户输入的查询文本
            available_models: 可用的模型列表，每个模型包含 'model', 'llm_id' 等字段
            
        Returns:
            str: 选中的模型ID。如果无法选择，返回列表中的第一个模型ID。
        """
        if not available_models:
            logger.warning("没有可用的模型供选择")
            return ""

        # 1. 分析查询意图
        intent = cls._analyze_intent(query)
        logger.info(f"自动模式 - 用户查询摘要: {query[:100]}..." if len(query) > 100 else f"自动模式 - 用户查询: {query}")
        logger.info(f"自动模式 - 查询意图分析结果: {intent}")

        # 记录可用模型摘要
        available_model_names = [m.get('model', 'Unknown') for m in available_models]
        logger.info(f"自动模式 - 当前可用模型列表 ({len(available_models)}个): {available_model_names}")

        # 2. 根据意图筛选最佳模型
        selected_model = cls._find_best_match(intent, available_models)
        
        if selected_model:
            logger.info(f"自动模式 - 匹配成功! 选中模型: {selected_model['model']} (ID: {selected_model['llm_id']})")
            return selected_model['llm_id']
        
        # 3. 兜底策略：如果没有匹配到特定意图的模型，使用第一个可用模型
        fallback = available_models[0]
        logger.warning(f"自动模式 - 未匹配到特定意图({intent})的推荐模型，触发兜底策略")
        logger.warning(f"自动模式 - 兜底选中模型: {fallback['model']} (ID: {fallback['llm_id']})")
        return fallback['llm_id']

    @classmethod
    def _analyze_intent(cls, query: str) -> str:
        """简单分析用户查询意图"""
        if not query:
            return "simple"
            
        query_lower = query.lower()
        
        # 编程相关关键词
        code_keywords = [
            "code", "python", "java", "javascript", "function", "class", 
            "def ", "import ", "bug", "error", "exception", "代码", "报错", 
            "函数", "类", "接口", "api", "sql", "database", "编程", "写一个"
        ]
        
        # 复杂推理/长文本关键词
        complex_keywords = [
            "analyze", "analysis", "summary", "summarize", "compare", "difference",
            "explain", "reason", "plan", "design", "architecture", 
            "分析", "总结", "比较", "区别", "解释", "推理", "规划", "设计", "架构",
            "复杂的", "详细", "深入", "原理"
        ]

        if any(k in query_lower for k in code_keywords):
            return "coding"
            
        # 如果长度超过一定限制(300字符)，也认为是复杂任务
        if len(query) > 300 or any(k in query_lower for k in complex_keywords):
            return "complex"
            
        return "simple"

    @classmethod
    def _find_best_match(cls, intent: str, available_models: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """根据意图查找最佳匹配模型"""
        
        # 定义意图对应的优先级列表
        priority_lists = []
        if intent == "coding":
            priority_lists = [cls.CODING_MODELS, cls.POWERFUL_MODELS, cls.FAST_MODELS]
        elif intent == "complex":
            priority_lists = [cls.POWERFUL_MODELS, cls.FAST_MODELS]
        else: # simple
            priority_lists = [cls.FAST_MODELS, cls.POWERFUL_MODELS]
            
        # 按优先级尝试匹配
        for target_names in priority_lists:
            # 在当前优先级列表中寻找匹配的模型
            for target in target_names:
                for model in available_models:
                    # 忽略大小写匹配，只要模型名称包含目标关键词即可
                    if target.lower() in model['model'].lower():
                        return model
                        
        # 如果都没有匹配到，返回None，交给兜底逻辑处理
        return None
