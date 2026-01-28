#!/usr/bin/env python3
"""测试删除接口的错误处理"""

import asyncio
import sys
import os

# 添加项目路径到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'backend'))

from agentchat.api.services.knowledge_file import KnowledgeFileService

async def test_delete():
    """测试删除功能"""
    print("开始测试删除功能...")
    
    try:
        # 测试删除一个不存在的文件，验证错误处理
        result = await KnowledgeFileService.delete_knowledge_file('test_nonexistent_id')
        print(f'删除结果: {result}')
    except ValueError as ve:
        print(f'捕获预期异常: {ve}')
    except Exception as e:
        print(f'捕获未预期异常: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_delete())