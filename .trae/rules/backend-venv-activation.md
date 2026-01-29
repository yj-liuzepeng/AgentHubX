1.  调试后端Python项目前，必须激活项目根目录下的venv虚拟环境，确保依赖与全局环境隔离，避免版本冲突。
2.  本地开发激活命令：
    - Windows: venv\Scripts\activate
    - macOS/Linux: source venv/bin/activate
3.  验证方式：激活成功后终端前缀会显示 `(venv)`，调试前需确认该标识存在。
4.  注意事项：调试结束后可执行 `deactivate` 退出虚拟环境，禁止在未激活虚拟环境的状态下运行调试命令。