"""
工具函数模块
提供各种实用工具函数
"""

import os
import re
import time
import mimetypes
from typing import Dict, List, Optional, Any
from pathlib import Path
from loguru import logger

class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self, total_steps: int = 100):
        self.total_steps = total_steps
        self.current_step = 0
        self.start_time = time.time()
        self.messages = []
        
    def update(self, message: str, steps: int = 1):
        """更新进度"""
        self.current_step += steps
        self.messages.append({
            'time': time.time(),
            'message': message,
            'progress': min(100, (self.current_step / self.total_steps) * 100)
        })
        logger.info(f"[{self.get_progress_percentage():.1f}%] {message}")
    
    def get_progress_percentage(self) -> float:
        """获取进度百分比"""
        return min(100, (self.current_step / self.total_steps) * 100)
    
    def get_elapsed_time(self) -> float:
        """获取已用时间"""
        return time.time() - self.start_time
    
    def get_estimated_time_remaining(self) -> float:
        """获取预计剩余时间"""
        if self.current_step == 0:
            return 0
        
        elapsed = self.get_elapsed_time()
        rate = self.current_step / elapsed
        remaining_steps = self.total_steps - self.current_step
        
        return remaining_steps / rate if rate > 0 else 0
    
    def get_summary(self) -> Dict[str, Any]:
        """获取进度摘要"""
        return {
            'progress_percentage': self.get_progress_percentage(),
            'elapsed_time': self.get_elapsed_time(),
            'estimated_time_remaining': self.get_estimated_time_remaining(),
            'current_step': self.current_step,
            'total_steps': self.total_steps,
            'latest_message': self.messages[-1]['message'] if self.messages else '',
            'total_messages': len(self.messages)
        }

def validate_file_size(file_path: str, max_size_mb: int = 50) -> bool:
    """
    验证文件大小
    
    Args:
        file_path: 文件路径
        max_size_mb: 最大文件大小（MB）
    
    Returns:
        文件是否在大小限制内
    """
    try:
        if not os.path.exists(file_path):
            return False
        
        file_size = os.path.getsize(file_path)
        max_size_bytes = max_size_mb * 1024 * 1024
        
        return file_size <= max_size_bytes
        
    except Exception as e:
        logger.error(f"验证文件大小失败: {str(e)}")
        return False

def get_file_extension(file_path: str) -> str:
    """
    获取文件扩展名
    
    Args:
        file_path: 文件路径
    
    Returns:
        文件扩展名（包含点号）
    """
    return Path(file_path).suffix.lower()

def get_file_mime_type(file_path: str) -> str:
    """
    获取文件的MIME类型
    
    Args:
        file_path: 文件路径
    
    Returns:
        MIME类型
    """
    try:
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or 'application/octet-stream'
    except Exception as e:
        logger.error(f"获取MIME类型失败: {str(e)}")
        return 'application/octet-stream'

def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除不合法字符
    
    Args:
        filename: 原始文件名
    
    Returns:
        清理后的文件名
    """
    # 移除或替换不合法字符
    invalid_chars = r'[<>:"/\\|?*]'
    filename = re.sub(invalid_chars, '_', filename)
    
    # 移除控制字符
    filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
    
    # 限制长度
    max_length = 255
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    
    return filename.strip()

def create_temp_directory(prefix: str = "doc_translation_") -> str:
    """
    创建临时目录
    
    Args:
        prefix: 目录名前缀
    
    Returns:
        临时目录路径
    """
    try:
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        logger.info(f"创建临时目录: {temp_dir}")
        return temp_dir
        
    except Exception as e:
        logger.error(f"创建临时目录失败: {str(e)}")
        raise

def cleanup_temp_files(file_paths: List[str]) -> bool:
    """
    清理临时文件
    
    Args:
        file_paths: 要清理的文件路径列表
    
    Returns:
        是否全部清理成功
    """
    success_count = 0
    
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                success_count += 1
                logger.debug(f"清理文件成功: {file_path}")
        except Exception as e:
            logger.warning(f"清理文件失败 {file_path}: {str(e)}")
    
    return success_count == len(file_paths)

def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小
    
    Args:
        size_bytes: 文件大小（字节）
    
    Returns:
        格式化的大小字符串
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def estimate_translation_time(text_length: int, complexity: str = 'normal') -> float:
    """
    估算翻译所需时间
    
    Args:
        text_length: 文本长度（字符数）
        complexity: 复杂度（simple, normal, complex）
    
    Returns:
        预计时间（秒）
    """
    # 基础时间（每1000字符）
    base_time_per_1000_chars = {
        'simple': 2.0,    # 简单文本
        'normal': 3.0,    # 普通文本
        'complex': 5.0    # 复杂文本（专业术语多）
    }
    
    base_time = base_time_per_1000_chars.get(complexity, 3.0)
    
    # 计算总时间
    estimated_time = (text_length / 1000.0) * base_time
    
    # 添加网络延迟
    network_delay = 1.0
    
    # 添加处理开销
    processing_overhead = 2.0
    
    total_time = estimated_time + network_delay + processing_overhead
    
    return max(1.0, total_time)  # 最少1秒

def split_text_for_translation(text: str, max_chunk_size: int = 5000) -> List[str]:
    """
    将长文本分割成适合翻译的块
    
    Args:
        text: 原始文本
        max_chunk_size: 最大块大小（字符数）
    
    Returns:
        文本块列表
    """
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # 按句子分割
    sentences = re.split(r'[.!?。！？]\s*', text)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # 添加标点符号
        if sentence:
            sentence += ". "
        
        # 检查当前块大小
        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence
        else:
            # 保存当前块
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            # 开始新块
            if len(sentence) <= max_chunk_size:
                current_chunk = sentence
            else:
                # 如果单个句子就超过限制，按标点分割
                sub_sentences = re.split(r'[,;，；]\s*', sentence)
                sub_chunk = ""
                for sub_sentence in sub_sentences:
                    if len(sub_chunk) + len(sub_sentence) <= max_chunk_size:
                        sub_chunk += sub_sentence + ", "
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk.strip())
                        sub_chunk = sub_sentence + ", "
                
                if sub_chunk:
                    chunks.append(sub_chunk.strip())
                current_chunk = ""
    
    # 添加最后一个块
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def create_progress_tracker(total_steps: int = 100) -> ProgressTracker:
    """
    创建进度跟踪器
    
    Args:
        total_steps: 总步骤数
    
    Returns:
        ProgressTracker实例
    """
    return ProgressTracker(total_steps)

def validate_language_code(language_code: str, supported_languages: Dict[str, str]) -> bool:
    """
    验证语言代码是否有效
    
    Args:
        language_code: 语言代码
        supported_languages: 支持的语言字典
    
    Returns:
        语言代码是否有效
    """
    return language_code in supported_languages

def get_language_name(language_code: str, supported_languages: Dict[str, str]) -> str:
    """
    获取语言名称
    
    Args:
        language_code: 语言代码
        supported_languages: 支持的语言字典
    
    Returns:
        语言名称
    """
    return supported_languages.get(language_code, language_code)

def format_translation_result(
    processed_files: List[Dict],
    failed_files: List[str],
    total_time: float
) -> str:
    """
    格式化翻译结果信息
    
    Args:
        processed_files: 成功处理的文件列表
        failed_files: 失败的文件列表
        total_time: 总耗时
    
    Returns:
        格式化后的结果字符串
    """
    result_parts = []
    
    # 成功处理的文件
    if processed_files:
        result_parts.append("✅ 翻译完成！")
        result_parts.append("")
        
        for file_info in processed_files:
            result_parts.append(f"📄 {file_info['original_name']}")
            result_parts.append(f"   目标语言: {file_info['target_language']}")
            result_parts.append(f"   下载链接: {file_info['translated_url']}")
            result_parts.append("")
    
    # 失败的文件
    if failed_files:
        result_parts.append("❌ 以下文件处理失败：")
        for failure in failed_files:
            result_parts.append(f"  • {failure}")
        result_parts.append("")
    
    # 统计信息
    result_parts.append("📊 统计信息：")
    result_parts.append(f"   总文件数: {len(processed_files) + len(failed_files)}")
    result_parts.append(f"   成功: {len(processed_files)}")
    result_parts.append(f"   失败: {len(failed_files)}")
    result_parts.append(f"   总耗时: {total_time:.1f}秒")
    
    return "\n".join(result_parts)

import tempfile