"""
翻译引擎模块
集成多种翻译服务，支持多语言互译
"""

import json
import time
import hashlib
import re
import random
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from loguru import logger
import requests

try:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
    from tencentcloud.tmt.v20180321 import tmt_client, models
except ImportError:
    pass

class BaseTranslator(ABC):
    """基础翻译器类"""
    
    @abstractmethod
    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """翻译文本"""
        pass
    
    @abstractmethod
    def get_supported_languages(self) -> List[str]:
        """获取支持的语言列表"""
        pass

class GoogleTranslator(BaseTranslator):
    """Google翻译API"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://translation.googleapis.com/language/translate/v2"
        self.language_map = {
            'zh': 'zh-CN',
            'en': 'en',
            'ja': 'ja',
            'ko': 'ko',
            'fr': 'fr',
            'de': 'de',
            'es': 'es',
            'ru': 'ru'
        }
    
    def get_supported_languages(self) -> List[str]:
        return list(self.language_map.keys())
    
    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """使用Google翻译API"""
        if not self.api_key:
            logger.warning("Google翻译API密钥未配置")
            return self._fallback_translate(text, source_language, target_language)
        
        try:
            # 映射语言代码
            target_lang = self.language_map.get(target_language, target_language)
            source_lang = self.language_map.get(source_language, source_language)
            
            # 构建请求
            params = {
                'key': self.api_key,
                'q': text,
                'target': target_lang,
                'source': source_lang if source_language != 'auto' else '',
                'format': 'text'
            }
            
            response = requests.post(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if 'data' in result and 'translations' in result['data']:
                return result['data']['translations'][0]['translatedText']
            else:
                logger.error(f"Google翻译API返回错误: {result}")
                return self._fallback_translate(text, source_language, target_language)
                
        except Exception as e:
            logger.error(f"Google翻译失败: {str(e)}")
            return self._fallback_translate(text, source_language, target_language)
    
    def _fallback_translate(self, text: str, source_language: str, target_language: str) -> str:
        """备用翻译方法"""
        # 这里可以实现简单的翻译逻辑或返回原文
        logger.warning("使用备用翻译方法，返回原文")
        return text

class BaiduTranslator(BaseTranslator):
    """百度翻译API (支持通用翻译 doc/21 和 领域翻译 doc/22)"""
    
    def __init__(self, app_id: Optional[str] = None, app_key: Optional[str] = None, domain: Optional[str] = None):
        self.app_id = str(app_id).strip() if app_id else None
        self.app_key = str(app_key).strip() if app_key else None
        self.domain = str(domain).strip() if domain else None
        
        # 根据是否有 domain 参数决定使用通用翻译还是领域翻译
        if self.domain:
            self.base_url = "https://fanyi-api.baidu.com/api/trans/vip/fieldtranslate"
        else:
            self.base_url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
            
        self.language_map = {
            'zh': 'zh',
            'en': 'en',
            'ja': 'jp',
            'ko': 'kor',
            'fr': 'fra',
            'de': 'de',
            'es': 'spa',
            'ru': 'ru'
        }
    
    def get_supported_languages(self) -> List[str]:
        return list(self.language_map.keys())
    
    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """使用百度翻译API"""
        if not self.app_id or not self.app_key:
            logger.warning("百度翻译API密钥未配置")
            return self._fallback_translate(text, source_language, target_language)
        
        try:
            # 映射语言代码
            target_lang = self.language_map.get(target_language, target_language)
            source_lang = self.language_map.get(source_language, source_language)
            
            # 生成随机数
            salt = str(random.randint(32768, 65536))
            
            # 生成签名
            if self.domain:
                # 领域翻译签名: appid+q+salt+domain+key
                sign_str = f"{self.app_id}{text}{salt}{self.domain}{self.app_key}"
            else:
                # 通用翻译签名: appid+q+salt+key
                sign_str = f"{self.app_id}{text}{salt}{self.app_key}"
                
            sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
            
            # 构建请求参数
            params = {
                'q': text,
                'from': source_lang if source_language != 'auto' else 'auto',
                'to': target_lang,
                'appid': self.app_id,
                'salt': salt,
                'sign': sign
            }
            
            if self.domain:
                params['domain'] = self.domain
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            # 优先使用 POST 请求以支持较长文本
            response = requests.post(self.base_url, data=params, headers=headers, timeout=30)
            
            # 如果 POST 失败且状态码不是 200，尝试 GET
            if response.status_code != 200:
                logger.warning(f"百度翻译POST请求失败(status={response.status_code})，尝试GET请求")
                response = requests.get(self.base_url, params=params, timeout=30)
            
            response.raise_for_status()
            
            result = response.json()
            
            if 'trans_result' in result:
                # 合并多个翻译结果
                translated_parts = []
                for trans in result['trans_result']:
                    translated_parts.append(trans['dst'])
                return '\n'.join(translated_parts)
            else:
                logger.error(f"百度翻译API返回错误: {result}")
                if result.get('error_code') == '54001':
                    # 记录详细签名信息以供调试 (隐藏 key)
                    masked_key = self.app_key[:4] + "***" + self.app_key[-4:] if self.app_key else "None"
                    if self.domain:
                        debug_sign_str = f"{self.app_id}{text[:10]}...{salt}{self.domain}{masked_key}"
                    else:
                        debug_sign_str = f"{self.app_id}{text[:10]}...{salt}{masked_key}"
                    logger.error(f"签名错误调试: appid={self.app_id}, salt={salt}, sign={sign}, debug_str={debug_sign_str}")
                    logger.error(f"请检查: 1. AppID/Key是否正确 2. 是否开通了对应服务(通用vs领域) 3. 领域参数是否匹配")
                return self._fallback_translate(text, source_language, target_language)
                
        except Exception as e:
            logger.error(f"百度翻译失败: {str(e)}")
            return self._fallback_translate(text, source_language, target_language)
    
    def _fallback_translate(self, text: str, source_language: str, target_language: str) -> str:
        """备用翻译方法"""
        logger.warning("使用备用翻译方法，返回原文")
        return text

class YoudaoTranslator(BaseTranslator):
    """有道翻译API"""
    
    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = "https://openapi.youdao.com/api"
        self.language_map = {
            'zh': 'zh-CHS',
            'en': 'en',
            'ja': 'ja',
            'ko': 'ko',
            'fr': 'fr',
            'de': 'de',
            'es': 'es',
            'ru': 'ru'
        }
    
    def get_supported_languages(self) -> List[str]:
        return list(self.language_map.keys())
    
    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """使用有道翻译API"""
        if not self.app_id or not self.app_secret:
            logger.warning("有道翻译API密钥未配置")
            return self._fallback_translate(text, source_language, target_language)
        
        try:
            # 映射语言代码
            target_lang = self.language_map.get(target_language, target_language)
            source_lang = self.language_map.get(source_language, source_language)
            
            # 生成随机数
            salt = str(int(time.time() * 1000))
            
            # 生成签名
            curtime = str(int(time.time()))
            sign_str = f"{self.app_id}{text}{salt}{curtime}{self.app_secret}"
            sign = hashlib.sha256(sign_str.encode('utf-8')).hexdigest()
            
            # 构建请求参数
            params = {
                'q': text,
                'from': source_lang if source_language != 'auto' else 'auto',
                'to': target_lang,
                'appKey': self.app_id,
                'salt': salt,
                'sign': sign,
                'signType': 'v3',
                'curtime': curtime
            }
            
            response = requests.post(self.base_url, data=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if 'translation' in result:
                return result['translation'][0]
            else:
                logger.error(f"有道翻译API返回错误: {result}")
                return self._fallback_translate(text, source_language, target_language)
                
        except Exception as e:
            logger.error(f"有道翻译失败: {str(e)}")
            return self._fallback_translate(text, source_language, target_language)
    
    def _fallback_translate(self, text: str, source_language: str, target_language: str) -> str:
        """备用翻译方法"""
        logger.warning("使用备用翻译方法，返回原文")
        return text

class TencentTranslator(BaseTranslator):
    """腾讯翻译API"""
    
    def __init__(self, secret_id: Optional[str] = None, secret_key: Optional[str] = None):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.base_url = "https://tmt.tencentcloudapi.com"
        self.language_map = {
            'zh': 'zh',
            'en': 'en',
            'ja': 'ja',
            'ko': 'ko',
            'fr': 'fr',
            'de': 'de',
            'es': 'es',
            'ru': 'ru'
        }
    
    def get_supported_languages(self) -> List[str]:
        return list(self.language_map.keys())
    
    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """使用腾讯翻译API"""
        if not self.secret_id or not self.secret_key:
            logger.warning("腾讯翻译API密钥未配置")
            return self._fallback_translate(text, source_language, target_language)
        
        try:
            # 腾讯翻译API需要特殊签名处理
            # 这里简化处理，实际使用时需要完整的签名算法
            logger.warning("腾讯翻译API需要完整的签名实现")
            return self._fallback_translate(text, source_language, target_language)
            
        except Exception as e:
            logger.error(f"腾讯翻译失败: {str(e)}")
            return self._fallback_translate(text, source_language, target_language)
    
    def _fallback_translate(self, text: str, source_language: str, target_language: str) -> str:
        """备用翻译方法"""
        logger.warning("使用备用翻译方法，返回原文")
        return text

class TranslationEngine:
    """翻译引擎，整合多个翻译服务"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.translators = []
        self._initialize_translators()
    
    def _initialize_translators(self):
        """初始化翻译器"""
        # Google翻译
        if self.config.get('google_api_key'):
            self.translators.append(GoogleTranslator(self.config['google_api_key']))
        
        # 百度翻译
        if self.config.get('baidu_app_id') and self.config.get('baidu_app_key'):
            self.translators.append(
                BaiduTranslator(
                    self.config['baidu_app_id'],
                    self.config['baidu_app_key'],
                    self.config.get('baidu_domain')  # 支持配置领域
                )
            )
        
        # 有道翻译
        if self.config.get('youdao_app_id') and self.config.get('youdao_app_secret'):
            self.translators.append(
                YoudaoTranslator(
                    self.config['youdao_app_id'],
                    self.config['youdao_app_secret']
                )
            )
        
        # 腾讯翻译
        if self.config.get('tencent_secret_id') and self.config.get('tencent_secret_key'):
            self.translators.append(
                TencentTranslator(
                    self.config['tencent_secret_id'],
                    self.config['tencent_secret_key']
                )
            )
        
        # 如果没有配置任何API，添加默认的Google翻译（无API密钥）
        if not self.translators:
            self.translators.append(GoogleTranslator())
            logger.warning("未配置翻译API，使用基础翻译功能")
    
    def translate(self, text: str, source_language: str = 'auto', target_language: str = 'zh') -> str:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            source_language: 源语言代码，默认为auto（自动检测）
            target_language: 目标语言代码，默认为zh（中文）
        
        Returns:
            翻译后的文本
        """
        if not text or not text.strip():
            return text
        
        # 如果源语言和目标语言相同，直接返回原文
        if source_language == target_language:
            return text
        
        # 尝试使用每个翻译器
        for translator in self.translators:
            try:
                result = translator.translate(text, source_language, target_language)
                if result and result != text:
                    logger.info(f"翻译成功：{translator.__class__.__name__}")
                    return result
            except Exception as e:
                logger.warning(f"{translator.__class__.__name__} 翻译失败: {str(e)}")
                continue
        
        # 所有翻译器都失败，返回原文
        logger.error("所有翻译器都失败，返回原文")
        return text
    
    def get_supported_languages(self) -> List[str]:
        """获取支持的语言列表"""
        languages = set()
        for translator in self.translators:
            try:
                langs = translator.get_supported_languages()
                languages.update(langs)
            except Exception as e:
                logger.warning(f"获取{translator.__class__.__name__}支持语言失败: {str(e)}")
                continue
        
        return sorted(list(languages))
    
    def detect_language(self, text: str) -> str:
        """
        检测文本语言
        
        Args:
            text: 要检测的文本
        
        Returns:
            语言代码
        """
        # 简单的语言检测逻辑
        # 实际使用时可以集成专业的语言检测库
        
        if not text or not text.strip():
            return 'unknown'
        
        # 中文字符检测
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        if chinese_chars > len(text) * 0.3:
            return 'zh'
        
        # 日文检测
        japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text))
        if japanese_chars > len(text) * 0.1:
            return 'ja'
        
        # 韩文检测
        korean_chars = len(re.findall(r'[\uac00-\ud7af]', text))
        if korean_chars > len(text) * 0.1:
            return 'ko'
        
        # 俄文检测
        russian_chars = len(re.findall(r'[\u0400-\u04ff]', text))
        if russian_chars > len(text) * 0.1:
            return 'ru'
        
        # 默认返回英文
        return 'en'
