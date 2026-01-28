#!/usr/bin/env python3
"""测试异常处理逻辑"""

def test_exception_handling():
    """测试异常处理是否正常"""
    print("测试异常处理逻辑...")
    
    # 模拟删除操作中的异常
    try:
        # 模拟一个异常
        raise ValueError("测试异常")
    except ValueError as ve:
        print(f"✅ 捕获到预期异常: {ve}")
    except Exception as e:
        print(f"❌ 捕获到未预期异常: {e}")
    
    # 测试信号处理
    import signal
    
    def safe_signal_handler(signum, frame):
        print(f"✅ 信号处理正常: 收到信号 {signum}")
        # 不退出程序
        
    # 临时注册信号处理
    old_handler = signal.signal(signal.SIGTERM, safe_signal_handler)
    
    # 模拟信号
    try:
        # 发送测试信号给自己
        import os
        os.kill(os.getpid(), signal.SIGTERM)
    except:
        pass
    
    # 恢复原始处理
    signal.signal(signal.SIGTERM, old_handler)
    
    print("✅ 异常处理测试完成")

if __name__ == "__main__":
    test_exception_handling()