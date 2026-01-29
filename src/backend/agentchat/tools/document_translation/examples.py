"""
文档翻译工具使用示例
"""

from agentchat.tools.document_translation.action import document_translation

def example_single_file():
    """单个文件翻译示例"""
    print("=== 单个文件翻译示例 ===")
    
    # 单个PDF文件翻译
    result = document_translation(
        file_urls=["https://example.com/document.pdf"],
        target_language="zh",
        source_language="en",
        preserve_formatting=True
    )
    print(result)
    print()

def example_batch_files():
    """批量文件翻译示例"""
    print("=== 批量文件翻译示例 ===")
    
    # 多个不同类型文件翻译
    result = document_translation(
        file_urls=[
            "https://example.com/report.pdf",
            "https://example.com/document.docx",
            "https://example.com/presentation.pptx"
        ],
        target_language="zh",
        source_language="auto",  # 自动检测源语言
        preserve_formatting=True
    )
    print(result)
    print()

def example_different_languages():
    """不同语言翻译示例"""
    print("=== 不同语言翻译示例 ===")
    
    # 中文翻译成英文
    result = document_translation(
        file_urls=["https://example.com/中文文档.pdf"],
        target_language="en",
        source_language="zh"
    )
    print(result)
    print()
    
    # 英文翻译成日文
    result = document_translation(
        file_urls=["https://example.com/english-document.pdf"],
        target_language="ja",
        source_language="en"
    )
    print(result)
    print()

def example_format_preservation():
    """格式保持示例"""
    print("=== 格式保持示例 ===")
    
    # 保持原始格式
    result_with_format = document_translation(
        file_urls=["https://example.com/formatted-document.docx"],
        target_language="zh",
        preserve_formatting=True
    )
    print("保持格式:")
    print(result_with_format)
    print()
    
    # 不保持格式（纯文本）
    result_plain_text = document_translation(
        file_urls=["https://example.com/formatted-document.docx"],
        target_language="zh",
        preserve_formatting=False
    )
    print("纯文本:")
    print(result_plain_text)
    print()

def example_error_handling():
    """错误处理示例"""
    print("=== 错误处理示例 ===")
    
    try:
        # 不支持的文件格式
        result = document_translation(
            file_urls=["https://example.com/unsupported.xyz"],
            target_language="zh"
        )
        print(result)
        
        # 无效的语言代码
        result = document_translation(
            file_urls=["https://example.com/document.pdf"],
            target_language="invalid_lang"
        )
        print(result)
        
        # 空文件列表
        result = document_translation(
            file_urls=[],
            target_language="zh"
        )
        print(result)
        
    except Exception as e:
        print(f"错误: {str(e)}")

def example_advanced_usage():
    """高级用法示例"""
    print("=== 高级用法示例 ===")
    
    # 使用不同的翻译引擎配置
    from agentchat.tools.document_translation.translators import TranslationEngine
    
    # 配置多个翻译API
    config = {
        'google_api_key': 'your-google-api-key',
        'baidu_app_id': 'your-baidu-app-id',
        'baidu_app_key': 'your-baidu-app-key',
        'youdao_app_id': 'your-youdao-app-id',
        'youdao_app_secret': 'your-youdao-app-secret'
    }
    
    translation_engine = TranslationEngine(config)
    
    # 使用进度跟踪
    from agentchat.tools.document_translation.utils import create_progress_tracker
    
    progress = create_progress_tracker(total_steps=100)
    progress.update("开始文档翻译...", steps=10)
    
    # 执行翻译
    result = document_translation(
        file_urls=["https://example.com/large-document.pdf"],
        target_language="zh",
        source_language="en"
    )
    
    progress.update("翻译完成", steps=90)
    print(result)
    print()

def example_file_format_support():
    """支持的文件格式示例"""
    print("=== 支持的文件格式示例 ===")
    
    # PDF文件
    result = document_translation(
        file_urls=["https://example.com/document.pdf"],
        target_language="zh"
    )
    print("PDF翻译:", result)
    
    # DOCX文件
    result = document_translation(
        file_urls=["https://example.com/document.docx"],
        target_language="zh"
    )
    print("DOCX翻译:", result)
    
    # TXT文件
    result = document_translation(
        file_urls=["https://example.com/document.txt"],
        target_language="zh"
    )
    print("TXT翻译:", result)
    
    # PPT文件
    result = document_translation(
        file_urls=["https://example.com/presentation.pptx"],
        target_language="zh"
    )
    print("PPT翻译:", result)

if __name__ == "__main__":
    print("文档翻译工具使用示例")
    print("=" * 50)
    
    # 运行示例（注意：这些URL需要替换为实际的文件URL）
    # example_single_file()
    # example_batch_files()
    # example_different_languages()
    # example_format_preservation()
    # example_error_handling()
    # example_advanced_usage()
    # example_file_format_support()
    
    print("\n注意：以上示例中的URL需要替换为实际的文件URL才能正常工作。")
    print("支持的文件格式：PDF, DOCX, DOC, TXT, PPT, PPTX")
    print("支持的语言：zh, en, ja, ko, fr, de, es, ru")
    print("文件大小限制：单文件最大50MB")