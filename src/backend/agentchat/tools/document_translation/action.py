import os
import tempfile
import zipfile
from typing import List, Dict, Optional
from pathlib import Path
import json
from datetime import datetime
from loguru import logger

from langchain.tools import tool

from agentchat.services.aliyun_oss import aliyun_oss
from agentchat.utils.file_utils import get_object_name_from_aliyun_url, get_save_tempfile
from agentchat.utils.helpers import get_now_beijing_time
from agentchat.settings import app_settings

# 文件解析器
from .parsers import PDFParser, DOCXParser, DOCParser, TXTParser, PPTParser
# 翻译引擎
from .translators import TranslationEngine
# 文件生成器
from .generators import DocumentGenerator
# 工具函数
from .utils import validate_file_size, get_file_extension, create_progress_tracker

SUPPORTED_FORMATS = ['.pdf', '.docx', '.doc', '.txt', '.ppt', '.pptx']
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
SUPPORTED_LANGUAGES = {
    'zh': '中文',
    'en': 'English',
    'ja': '日本語',
    'ko': '한국어',
    'fr': 'Français',
    'de': 'Deutsch',
    'es': 'Español',
    'ru': 'Русский'
}

@tool(parse_docstring=True)
def document_translation(
    file_urls: List[str],
    target_language: str = 'zh',
    source_language: str = 'auto',
    preserve_formatting: bool = True
) -> str:
    """
    文档翻译工具，支持PDF、DOCX、DOC、TXT、PPT格式文件的批量翻译。
    
    当用户消息中包含"上传的文件链接："或提供了文件URL，并表达了翻译意图时，必须调用此工具。
    请从用户输入中提取文件URL作为 file_urls 参数。

    Args:
        file_urls: 文件URL列表，支持多个文件同时上传。请务必从用户输入中提取"上传的文件链接："后的URL。
        target_language: 目标语言代码，默认为中文(zh)。支持：zh, en, ja, ko, fr, de, es, ru
        source_language: 源语言代码，默认为自动检测(auto)
        preserve_formatting: 是否保持原始格式，默认为True

    Returns:
        str: 翻译结果信息，包含下载链接和操作状态
    """
    return _document_translation(file_urls, target_language, source_language, preserve_formatting)

def _document_translation(
    file_urls: List[str],
    target_language: str,
    source_language: str,
    preserve_formatting: bool
) -> str:
    """执行文档翻译的核心函数"""
    
    # 验证输入参数
    if not file_urls:
        return "错误：未提供文件链接，请上传文件后再试。"
    
    if target_language not in SUPPORTED_LANGUAGES:
        return f"错误：不支持的目标语言 '{target_language}'。支持的语言：{', '.join(SUPPORTED_LANGUAGES.keys())}"
    
    try:
        # 初始化组件
        progress_tracker = create_progress_tracker()
        
        # 获取文档翻译配置
        translation_config = getattr(app_settings.tools, 'document_translation', {})
        translation_engine = TranslationEngine(config=translation_config)
        
        doc_generator = DocumentGenerator()
        
        # 文件处理结果
        processed_files = []
        failed_files = []
        
        # 处理每个文件
        for idx, file_url in enumerate(file_urls):
            try:
                # 更新进度
                progress_tracker.update(f"正在处理第 {idx + 1}/{len(file_urls)} 个文件...")
                
                # 下载和验证文件
                file_info = download_and_validate_file(file_url)
                if not file_info:
                    failed_files.append(f"文件 {file_url}: 下载或验证失败")
                    continue
                
                # 解析文件
                progress_tracker.update(f"正在解析 {file_info['filename']}...")
                parsed_content = parse_document(file_info)
                if not parsed_content:
                    failed_files.append(f"文件 {file_info['filename']}: 解析失败")
                    continue
                
                # 翻译内容
                progress_tracker.update(f"正在翻译 {file_info['filename']}...")
                translated_content = translate_content(
                    parsed_content, 
                    source_language, 
                    target_language,
                    translation_engine
                )
                
                # 生成翻译文档
                progress_tracker.update(f"正在生成翻译文档 {file_info['filename']}...")
                output_file = generate_translated_document(
                    file_info,
                    translated_content,
                    target_language,
                    preserve_formatting,
                    doc_generator
                )
                
                # 上传翻译后的文件
                progress_tracker.update(f"正在上传翻译文档 {file_info['filename']}...")
                download_url = upload_translated_file(output_file, file_info)
                
                processed_files.append({
                    'original_name': file_info['filename'],
                    'translated_url': download_url,
                    'target_language': SUPPORTED_LANGUAGES[target_language]
                })
                
                # 清理临时文件
                cleanup_temp_files(file_info)
                
            except Exception as e:
                logger.error(f"处理文件 {file_url} 时出错: {str(e)}")
                failed_files.append(f"文件 {file_url}: {str(e)}")
                continue
        
        # 生成结果信息
        return generate_result_message(processed_files, failed_files, progress_tracker)
        
    except Exception as e:
        logger.error(f"文档翻译过程出错: {str(e)}")
        return f"文档翻译失败：{str(e)}"

def download_and_validate_file(file_url: str) -> Optional[Dict]:
    """下载并验证文件"""
    try:
        # 从阿里云下载文件
        object_name = get_object_name_from_aliyun_url(file_url)
        file_name = file_url.split("/")[-1]
        file_path = get_save_tempfile(file_name)
        
        # 下载文件
        aliyun_oss.download_file(object_name, file_path)
        
        # 验证文件是否存在
        if not os.path.isfile(file_path):
            return None
        
        # 验证文件大小
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            os.remove(file_path)
            return None
        
        # 验证文件格式
        file_ext = get_file_extension(file_path)
        if file_ext.lower() not in SUPPORTED_FORMATS:
            os.remove(file_path)
            return None
        
        return {
            'url': file_url,
            'filename': file_name,
            'filepath': file_path,
            'extension': file_ext.lower(),
            'size': file_size
        }
        
    except Exception as e:
        logger.error(f"文件下载验证失败: {str(e)}")
        return None

def parse_document(file_info: Dict) -> Optional[Dict]:
    """解析文档内容"""
    try:
        file_path = file_info['filepath']
        file_ext = file_info['extension']
        
        # 根据文件类型选择解析器
        if file_ext == '.pdf':
            parser = PDFParser()
        elif file_ext == '.docx':
            parser = DOCXParser()
        elif file_ext == '.doc':
            parser = DOCParser()
        elif file_ext == '.txt':
            parser = TXTParser()
        elif file_ext in ['.ppt', '.pptx']:
            parser = PPTParser()
        else:
            return None
        
        return parser.parse(file_path)
        
    except Exception as e:
        logger.error(f"文档解析失败: {str(e)}")
        return None

def translate_content(
    content: Dict, 
    source_lang: str, 
    target_lang: str, 
    translator: TranslationEngine
) -> Dict:
    """翻译文档内容"""
    try:
        translated_content = content.copy()
        has_structural_translation = False
        
        # 1. 翻译结构化内容
        
        # 翻译 pages (PDF)
        if 'pages' in content and content['pages']:
            translated_pages = []
            for page in content['pages']:
                new_page = page.copy()
                if 'text' in page and page['text']:
                    new_page['text'] = translator.translate(
                        page['text'],
                        source_language=source_lang,
                        target_language=target_lang
                    )
                translated_pages.append(new_page)
            translated_content['pages'] = translated_pages
            has_structural_translation = True
            
            # 从翻译后的页面重构全文文本
            translated_content['text'] = '\n\n'.join([p.get('text', '') for p in translated_pages])

        # 翻译 paragraphs (DOCX/DOC)
        if 'paragraphs' in content and content['paragraphs']:
            translated_paragraphs = []
            full_text_parts = []
            
            for para in content['paragraphs']:
                new_para = para.copy()
                
                # 翻译段落文本
                if 'text' in para and para['text']:
                    new_para['text'] = translator.translate(
                        para['text'],
                        source_language=source_lang,
                        target_language=target_lang
                    )
                
                # 翻译 runs (用于保留样式)
                if 'runs' in para and para['runs']:
                    new_runs = []
                    for run in para['runs']:
                        new_run = run.copy()
                        if 'text' in run and run['text']:
                            new_run['text'] = translator.translate(
                                run['text'],
                                source_language=source_lang,
                                target_language=target_lang
                            )
                        new_runs.append(new_run)
                    new_para['runs'] = new_runs
                    
                    # 如果有 runs，段落文本应该是 runs 的组合
                    # 但为了简单，我们优先信任 runs 的翻译结果组合（如果有）
                    # 或者保持 new_para['text'] 的独立翻译结果
                
                translated_paragraphs.append(new_para)
                if new_para.get('text'):
                    full_text_parts.append(new_para['text'])
            
            translated_content['paragraphs'] = translated_paragraphs
            has_structural_translation = True
            
            # 更新全文文本 (如果没有 pages 更新过)
            if 'pages' not in content:
                translated_content['text'] = '\n\n'.join(full_text_parts)

        # 翻译 tables (DOCX)
        if 'tables' in content and content['tables']:
            translated_tables = []
            for table in content['tables']:
                new_table = []
                for row in table:
                    new_row = []
                    for cell_text in row:
                        if cell_text and isinstance(cell_text, str) and cell_text.strip():
                            new_cell_text = translator.translate(
                                cell_text,
                                source_language=source_lang,
                                target_language=target_lang
                            )
                            new_row.append(new_cell_text)
                        else:
                            new_row.append(cell_text)
                    new_table.append(new_row)
                translated_tables.append(new_table)
            translated_content['tables'] = translated_tables
            # 表格通常不计入 content['text'] 的主要部分，或者解析器已处理
        
        # 2. 如果没有结构化内容，翻译全文文本 (如 TXT)
        if not has_structural_translation:
            text_content = content.get('text', '')
            if text_content:
                translated_text = translator.translate(
                    text_content,
                    source_language=source_lang,
                    target_language=target_lang
                )
                translated_content['text'] = translated_text
        
        translated_content['translated_language'] = target_lang
        
        return translated_content
        
    except Exception as e:
        logger.error(f"翻译失败: {str(e)}")
        raise e

def generate_translated_document(
    file_info: Dict,
    translated_content: Dict,
    target_language: str,
    preserve_formatting: bool,
    generator: DocumentGenerator
) -> str:
    """生成翻译后的文档"""
    try:
        original_path = file_info['filepath']
        file_ext = file_info['extension']
        
        # 生成输出文件路径
        output_dir = tempfile.mkdtemp()
        base_name = os.path.splitext(file_info['filename'])[0]
        output_filename = f"{base_name}_translated_{target_language}{file_ext}"
        output_path = os.path.join(output_dir, output_filename)
        
        # 生成文档
        generator.generate(
            translated_content,
            output_path,
            original_path,
            preserve_formatting
        )
        
        return output_path
        
    except Exception as e:
        logger.error(f"文档生成失败: {str(e)}")
        raise e

def upload_translated_file(output_file: str, file_info: Dict) -> str:
    """上传翻译后的文件"""
    try:
        # 生成阿里云对象名称
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output_filename = os.path.basename(output_file)
        oss_object_name = f"document_translation/{timestamp}_{output_filename}"
        
        # 上传到阿里云
        aliyun_oss.upload_local_file(oss_object_name, output_file)
        
        # 生成签名URL
        download_url = aliyun_oss.sign_url_for_get(oss_object_name)
        
        return download_url
        
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise e

def cleanup_temp_files(file_info: Dict):
    """清理临时文件"""
    try:
        if os.path.exists(file_info['filepath']):
            os.remove(file_info['filepath'])
    except Exception as e:
        logger.warning(f"清理临时文件失败: {str(e)}")

def generate_result_message(
    processed_files: List[Dict], 
    failed_files: List[str], 
    progress_tracker
) -> str:
    """生成结果信息"""
    
    if not processed_files and not failed_files:
        return "没有文件被处理，请检查文件格式和大小限制。"
    
    result_parts = []
    
    # 成功处理的文件
    if processed_files:
        result_parts.append("✅ 翻译完成！")
        result_parts.append("")
        
        for file_info in processed_files:
            result_parts.append(
                f"📄 {file_info['original_name']} -> {file_info['target_language']}"
            )
            result_parts.append(f"[点击下载翻译文件]({file_info['translated_url']})")
            result_parts.append("")
    
    # 失败的文件
    if failed_files:
        result_parts.append("❌ 以下文件处理失败：")
        for failure in failed_files:
            result_parts.append(f"  • {failure}")
        result_parts.append("")
    
    # 添加时间限制提示
    now_time = get_now_beijing_time(delta=1)
    result_parts.append(f"⏰ 请在 {now_time} 前下载文件，超过时间链接将失效")
    
    return "\n".join(result_parts)