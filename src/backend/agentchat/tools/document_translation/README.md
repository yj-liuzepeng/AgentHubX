# 文档翻译工具 API 文档

## 概述

文档翻译工具是一个功能强大的多语言文档翻译服务，支持PDF、DOCX、DOC、TXT、PPT等多种格式文件的批量翻译。该工具集成了多种翻译引擎，提供高质量的翻译服务，同时保持原文档的格式和排版。

## 功能特性

### 1. 文件格式支持
- **PDF**: 支持文本提取和格式保持
- **DOCX**: 支持段落、表格、样式保持
- **DOC**: 支持旧版Word文档
- **TXT**: 支持各种编码的文本文件
- **PPT/PPTX**: 支持幻灯片内容翻译

### 2. 多语言支持
- **中文 (zh)**: 简体中文
- **英文 (en)**: English
- **日文 (ja)**: 日本語
- **韩文 (ko)**: 한국어
- **法文 (fr)**: Français
- **德文 (de)**: Deutsch
- **西班牙文 (es)**: Español
- **俄文 (ru)**: Русский

### 3. 翻译引擎
- Google翻译API
- 百度翻译API
- 有道翻译API
- 腾讯翻译API
- 自动降级和备用机制

### 4. 安全限制
- 单文件大小限制：50MB
- 支持批量文件处理
- 临时文件自动清理
- 文件类型验证

## API 接口

### 主函数

```python
def document_translation(
    file_urls: List[str],
    target_language: str = 'zh',
    source_language: str = 'auto',
    preserve_formatting: bool = True
) -> str
```

#### 参数说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| file_urls | List[str] | 是 | - | 文件URL列表，支持多个文件同时上传 |
| target_language | str | 否 | 'zh' | 目标语言代码 |
| source_language | str | 否 | 'auto' | 源语言代码，'auto'表示自动检测 |
| preserve_formatting | bool | 否 | True | 是否保持原始格式 |

#### 返回结果

返回字符串格式的处理结果，包含：
- 成功处理的文件列表和下载链接
- 失败的文件列表和错误原因
- 统计信息和操作时间
- 下载链接有效期提示

#### 使用示例

```python
from agentchat.tools.document_translation.action import document_translation

# 单个文件翻译
result = document_translation(
    file_urls=["https://example.com/document.pdf"],
    target_language="zh",
    source_language="en"
)
print(result)

# 批量文件翻译
result = document_translation(
    file_urls=[
        "https://example.com/file1.pdf",
        "https://example.com/file2.docx",
        "https://example.com/file3.txt"
    ],
    target_language="zh",
    preserve_formatting=True
)
print(result)
```

## 错误处理

### 常见错误码

| 错误类型 | 说明 | 解决方案 |
|----------|------|----------|
| 文件下载失败 | 网络问题或文件不存在 | 检查文件链接有效性 |
| 文件格式不支持 | 上传了不支持的文件格式 | 确认文件格式在支持列表中 |
| 文件大小超限 | 文件超过50MB限制 | 压缩文件或分批处理 |
| 解析失败 | 文件损坏或格式错误 | 检查文件完整性 |
| 翻译失败 | 网络问题或API限制 | 重试或联系技术支持 |
| 生成失败 | 内存不足或格式复杂 | 简化文档格式 |

### 异常处理

```python
try:
    result = document_translation(
        file_urls=["https://example.com/document.pdf"],
        target_language="zh"
    )
    print(result)
except Exception as e:
    print(f"翻译失败: {str(e)}")
```

## 配置说明

### 翻译API配置

在初始化翻译引擎时，可以配置多个翻译API：

```python
from agentchat.tools.document_translation.translators import TranslationEngine

config = {
    'google_api_key': 'your-google-api-key',
    'baidu_app_id': 'your-baidu-app-id',
    'baidu_app_key': 'your-baidu-app-key',
    'youdao_app_id': 'your-youdao-app-id',
    'youdao_app_secret': 'your-youdao-app-secret',
    'tencent_secret_id': 'your-tencent-secret-id',
    'tencent_secret_key': 'your-tencent-secret-key'
}

translation_engine = TranslationEngine(config)
```

### 环境变量配置

也可以通过环境变量配置API密钥：

```bash
export GOOGLE_TRANSLATE_API_KEY="your-google-api-key"
export BAIDU_TRANSLATE_APP_ID="your-baidu-app-id"
export BAIDU_TRANSLATE_APP_KEY="your-baidu-app-key"
```

## 性能优化

### 1. 批量处理
- 建议一次处理不超过10个文件
- 大文件建议单独处理
- 合理设置超时时间

### 2. 内存管理
- 自动清理临时文件
- 支持大文件流式处理
- 内存使用监控和限制

### 3. 网络优化
- 支持重试机制
- 连接池管理
- 超时时间配置

## 安全考虑

### 1. 文件安全
- 文件类型白名单验证
- 文件大小限制
- 恶意内容检测

### 2. 数据安全
- 临时文件自动清理
- 传输加密
- 敏感信息脱敏

### 3. 访问控制
- API密钥管理
- 访问频率限制
- 用户权限验证

## 监控和日志

### 1. 日志记录
使用loguru记录详细日志：

```python
from loguru import logger

logger.info("文档翻译开始")
logger.debug(f"文件信息: {file_info}")
logger.warning("翻译API降级")
logger.error("文档处理失败")
```

### 2. 性能监控
- 处理时间统计
- 内存使用监控
- 错误率统计

### 3. 进度跟踪
```python
from agentchat.tools.document_translation.utils import create_progress_tracker

progress = create_progress_tracker(total_steps=100)
progress.update("正在解析文档...", steps=20)
```

## 扩展开发

### 1. 添加新的文件格式支持

```python
from agentchat.tools.document_translation.parsers import BaseParser

class NewFormatParser(BaseParser):
    def supports_format(self, file_extension: str) -> bool:
        return file_extension.lower() == '.newformat'
    
    def parse(self, file_path: str) -> Optional[Dict]:
        # 实现解析逻辑
        pass
```

### 2. 添加新的翻译引擎

```python
from agentchat.tools.document_translation.translators import BaseTranslator

class NewTranslator(BaseTranslator):
    def get_supported_languages(self) -> List[str]:
        # 返回支持的语言列表
        pass
    
    def translate(self, text: str, source_language: str, target_language: str) -> str:
        # 实现翻译逻辑
        pass
```

### 3. 添加新的输出格式

```python
from agentchat.tools.document_translation.generators import BaseGenerator

class NewFormatGenerator(BaseGenerator):
    def supports_format(self, format_type: str) -> bool:
        return format_type.lower() == '.newformat'
    
    def generate(self, content: Dict, output_path: str, original_path: str = None, preserve_formatting: bool = True) -> bool:
        # 实现生成逻辑
        pass
```

## 最佳实践

### 1. 文件准备
- 确保文档格式正确
- 避免使用过于复杂的格式
- 提前压缩大文件

### 2. 翻译质量
- 选择合适的翻译引擎
- 对于专业文档建议使用专业翻译API
- 考虑人工校对重要文档

### 3. 错误处理
- 实现重试机制
- 记录详细的错误日志
- 提供用户友好的错误提示

### 4. 性能调优
- 合理设置并发数
- 监控资源使用情况
- 定期清理临时文件

## 更新日志

### v1.0.0 (2024-01)
- 初始版本发布
- 支持5种文件格式
- 集成4种翻译引擎
- 支持8种语言互译
- 完整的错误处理机制

## 技术支持

如遇到问题，请提供以下信息：
1. 错误信息和堆栈跟踪
2. 相关文件样本（如可能）
3. 操作步骤和参数配置
4. 环境信息（操作系统、Python版本等）

联系方式：
- 邮箱：support@example.com
- 文档：https://docs.example.com/translation
- 问题反馈：https://github.com/example/translation/issues