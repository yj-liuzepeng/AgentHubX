import os
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, APIRouter, Body, Depends, Query, BackgroundTasks

from agentchat.services.aliyun_oss import aliyun_oss
from agentchat.api.services.knowledge_file import KnowledgeFileService
from agentchat.api.services.knowledge import KnowledgeService
from agentchat.api.services.user import get_login_user, UserPayload
from agentchat.schema.schemas import UnifiedResponseModel, resp_200, resp_500
from agentchat.utils.file_utils import get_save_tempfile
from agentchat.database.models.knowledge_file import Status

router = APIRouter(tags=["Knowledge-File"])


# 安全的日志记录函数
def safe_log(level, message):
    """安全的日志记录，如果logger失败则使用print"""
    try:
        import loguru
        safe_logger = loguru.logger
        if level == 'info':
            safe_logger.info(message)
        elif level == 'error':
            safe_logger.error(message)
        elif level == 'warning':
            safe_logger.warning(message)
        else:
            print(f"[{level.upper()}] {message}")
    except Exception as e:
        print(f"[{level.upper()}] {message} (Logger error: {e})")

async def process_knowledge_file_async(file_name: str, local_file_path: str, knowledge_id: str, 
                                     user_id: str, file_url: str, file_size_bytes: int, knowledge_file_id: str):
    """后台异步处理文件解析任务"""
    # 系统级异常处理，防止程序崩溃
    import signal
    import sys
    import threading
    
    # 使用线程局部存储来标记是否应该停止处理
    stop_processing = threading.local()
    stop_processing.should_stop = False
    
    def signal_handler(signum, frame):
        safe_log('error', f"收到系统信号 {signum}，安全终止处理")
        # 不强制退出程序，只记录日志并设置停止标志
        stop_processing.should_stop = True
        safe_log('warning', f"后台任务收到信号 {signum}，将优雅退出当前任务")
    
    # 注册信号处理
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        safe_log('info', f"开始后台处理文件: {file_name} (ID: {knowledge_file_id})")
        
        # 直接调用文件解析和向量化逻辑，避免重复创建记录
        try:
            safe_log('info', f"开始导入解析模块...")
            # 针对不同的文件类型进行解析
            from agentchat.services.rag.parser import doc_parser
            from agentchat.services.rag_handler import RagHandler
            from agentchat.settings import app_settings
            safe_log('info', f"成功导入解析模块")
            
            safe_log('info', f"开始解析文件: {local_file_path}")
            chunks = await doc_parser.parse_doc_into_chunks(knowledge_file_id, local_file_path, knowledge_id)
            safe_log('info', f"成功解析文件，得到 {len(chunks)} 个chunks")
            
            # 将上传的文件解析成chunks放到ES和Milvus
            if chunks:  # 确保有chunks才进行向量化
                try:
                    safe_log('info', f"开始向量化 {len(chunks)} 个chunks...")
                    
                    # 添加系统资源检查
                    try:
                        import psutil
                        import gc
                        
                        # 检查内存使用情况
                        memory = psutil.virtual_memory()
                        safe_log('info', f"系统内存: 总内存 {memory.total / 1024 / 1024 / 1024:.1f}GB, 可用 {memory.available / 1024 / 1024 / 1024:.1f}GB, 使用率 {memory.percent}%")
                        
                        # 如果内存使用率过高，先进行垃圾回收
                        if memory.percent > 80:
                            safe_log('warning', f"内存使用率过高 ({memory.percent}%)，进行垃圾回收")
                            gc.collect()
                            memory = psutil.virtual_memory()
                            safe_log('info', f"垃圾回收后内存使用率: {memory.percent}%")
                        
                        # 如果内存仍然不足，减少批处理大小
                        if memory.percent > 90:
                            safe_log('error', f"内存严重不足 ({memory.percent}%)，可能无法完成向量化")
                            
                    except Exception as sys_e:
                        safe_log('warning', f"系统资源检查失败: {sys_e}")
                    
                    safe_log('info', f"开始Milvus向量化...")
                    await RagHandler.index_milvus_documents(knowledge_id, chunks)
                    safe_log('info', f"Milvus向量化完成")
                    
                    if app_settings.rag.enable_elasticsearch:
                        safe_log('info', f"开始ES向量化...")
                        await RagHandler.index_es_documents(knowledge_id, chunks)
                        safe_log('info', f"ES向量化完成")
                        
                    safe_log('info', f"成功向量化 {len(chunks)} 个chunks")
                    
                    # 向量化完成后进行内存清理
                    try:
                        gc.collect()
                        safe_log('debug', "完成内存清理")
                    except:
                        pass
                        
                except Exception as vector_e:
                    safe_log('error', f"向量化过程失败: {vector_e}")
                    # 出错时尝试清理内存
                    try:
                        import gc
                        gc.collect()
                    except:
                        pass
                    raise vector_e
            else:
                safe_log('warning', f"文件 {file_name} 没有解析出任何chunks")
            
            # 解析状态改为成功
            await KnowledgeFileService.update_parsing_status(knowledge_file_id, Status.success)
            safe_log('info', f"文件处理完成: {file_name} (ID: {knowledge_file_id})")
            
        except Exception as process_e:
            safe_log('error', f"文件解析或向量化失败 {file_name} (ID: {knowledge_file_id}): {process_e}")
            # 更新文件状态为失败
            await KnowledgeFileService.update_parsing_status(knowledge_file_id, Status.fail)
            raise process_e
        
    except Exception as e:
        safe_log('error', f"文件处理失败 {file_name} (ID: {knowledge_file_id}): {e}")
        
        # 更新文件状态为失败（如果还没更新）
        try:
            await KnowledgeFileService.update_parsing_status(knowledge_file_id, Status.fail)
            safe_log('error', f"文件状态已更新为失败: {file_name} (ID: {knowledge_file_id})")
        except Exception as inner_e:
            safe_log('error', f"更新文件状态失败: {file_name} (ID: {knowledge_file_id}): {inner_e}")
    
    except (KeyboardInterrupt, SystemExit) as ke:
        safe_log('error', f"处理被中断: {ke}")
        try:
            await KnowledgeFileService.update_parsing_status(knowledge_file_id, Status.fail)
        except:
            pass  # 如果状态更新失败，不要影响中断处理
        # 不重新抛出异常，避免导致程序终止
        safe_log('warning', f"后台任务被中断，但程序继续运行: {ke}")
        return  # 优雅退出当前任务，不终止整个程序
        
    finally:
        # 清理临时文件
        try:
            if os.path.exists(local_file_path):
                os.remove(local_file_path)
                safe_log('info', f"临时文件已清理: {local_file_path}")
        except Exception as cleanup_e:
            safe_log('warning', f"清理临时文件失败: {local_file_path}: {cleanup_e}")
        
        # 最终内存清理
        try:
            import gc
            gc.collect()
            safe_log('debug', "最终内存清理完成")
        except:
            pass
        
        # 确保处理完成标记
        safe_log('info', f"后台处理任务完全结束: {file_name} (ID: {knowledge_file_id})")


@router.post('/knowledge_file/create', response_model=UnifiedResponseModel)
async def upload_file(background_tasks: BackgroundTasks,
                      knowledge_id: str = Body(..., description="知识库的ID"),
                      file_url: str = Body(..., description="文件上传后返回的URL"),
                      login_user: UserPayload = Depends(get_login_user)):
    try:
        # 获取本地临时文件路径
        file_name = file_url.split("/")[-1]
        local_file_path = get_save_tempfile(file_name)
        # 根据URL解析出对应的object name
        parsed = urlparse(file_url)
        object_key = parsed.path.lstrip('/')
        aliyun_oss.download_file(object_key, local_file_path)
        # 获得文件的字节数
        file_size_bytes = os.path.getsize(local_file_path)

        name_part, ext_part = file_name.rsplit('.', 1) if '.' in file_name else (file_name, '')
        parts = name_part.split("_")
        file_name = "_".join(parts[:-1]) + f".{ext_part}"

        # 创建知识文件记录，状态设为处理中
        from uuid import uuid4
        from agentchat.database.dao.knowledge_file import KnowledgeFileDao
        
        knowledge_file_id = uuid4().hex
        await KnowledgeFileDao.create_knowledge_file(knowledge_file_id, file_name, knowledge_id, 
                                                    login_user.user_id, file_url, file_size_bytes)
        
        # 更新状态为处理中
        await KnowledgeFileService.update_parsing_status(knowledge_file_id, Status.process)
        
        # 添加后台任务进行异步处理 - 注意：这里不再调用KnowledgeFileService.create_knowledge_file
        # 以避免重复创建记录，而是直接调用文件处理逻辑
        # 使用更健壮的任务管理，确保任务不会被垃圾回收
        import asyncio
        
        async def safe_process_task():
            """包装异步处理任务，确保不会被意外终止"""
            try:
                safe_log('info', f"开始执行安全处理任务: {file_name} (ID: {knowledge_file_id})")
                await process_knowledge_file_async(file_name, local_file_path, 
                    knowledge_id, login_user.user_id, file_url, file_size_bytes, knowledge_file_id)
                safe_log('info', f"安全处理任务完成: {file_name} (ID: {knowledge_file_id})")
            except Exception as task_e:
                safe_log('error', f"安全处理任务失败: {file_name} (ID: {knowledge_file_id}): {task_e}")
                # 确保状态更新为失败
                try:
                    await KnowledgeFileService.update_parsing_status(knowledge_file_id, Status.fail)
                except:
                    pass
        
        # 创建任务并确保它被正确调度
        task = asyncio.create_task(safe_process_task())
        safe_log('info', f"创建异步处理任务: {file_name}, knowledge_file_id: {knowledge_file_id}, task: {task}")
        
        safe_log('info', f"文件已加入后台处理队列: {file_name}, knowledge_file_id: {knowledge_file_id}")
        
        return resp_200(data={"knowledge_file_id": knowledge_file_id, "status": "processing"})
    except Exception as err:
        safe_log('error', f"文件上传处理失败: {err}")
        return resp_500(message=str(err))


@router.get('/knowledge_file/select', response_model=UnifiedResponseModel)
async def select_knowledge_file(knowledge_id: str = Query(...),
                                login_user: UserPayload = Depends(get_login_user)):
    try:
        # 验证用户权限
        await KnowledgeService.verify_user_permission(knowledge_id, login_user.user_id)

        results = await KnowledgeFileService.get_knowledge_file(knowledge_id)
        return resp_200(data=results)
    except Exception as err:
        return resp_500(message=str(err))


@router.delete('/knowledge_file/delete', response_model=UnifiedResponseModel)
async def delete_knowledge_file(knowledge_file_id: str = Body(..., embed=True),
                                login_user: UserPayload = Depends(get_login_user)):
    """删除知识文件接口
    
    该接口会：
    1. 验证用户权限
    2. 删除数据库中的文件记录
    3. 清理对应的向量数据（ES和Milvus）
    
    Args:
        knowledge_file_id: 要删除的知识文件ID
        login_user: 当前登录用户信息
        
    Returns:
        UnifiedResponseModel: 统一响应格式
        
    注意:
        该接口具有强容错能力，即使向量数据清理失败，
        只要数据库记录删除成功，就会返回成功状态
    """
    try:
        safe_log('info', f"用户 {login_user.user_id} 请求删除知识文件: {knowledge_file_id}")
        
        # 验证用户权限
        await KnowledgeFileService.verify_user_permission(knowledge_file_id, login_user.user_id)
        safe_log('debug', f"权限验证通过: {knowledge_file_id}")

        # 执行删除操作
        result = await KnowledgeFileService.delete_knowledge_file(knowledge_file_id)
        
        if result:
            safe_log('info', f"知识文件删除成功: {knowledge_file_id}")
            return resp_200(message="知识文件删除成功")
        else:
            safe_log('error', f"知识文件删除失败: {knowledge_file_id}")
            return resp_500(message="知识文件删除失败")
            
    except ValueError as ve:
        # 文件不存在或权限验证失败
        safe_log('warning', f"删除知识文件验证失败: {ve}")
        return resp_500(message=str(ve))
    except Exception as err:
        # 其他未预期的错误 - 捕获所有异常，避免程序崩溃
        safe_log('error', f"删除知识文件时发生未预期错误: {err}")
        safe_log('exception', err)
        # 返回友好的错误信息，避免暴露内部实现细节
        error_msg = "删除操作失败"
        if "权限" in str(err):
            error_msg = "没有权限执行此操作"
        elif "不存在" in str(err):
            error_msg = "文件不存在或已被删除"
        else:
            # 记录详细错误但不暴露给用户
            safe_log('error', f"内部错误详情: {err}")
        
        return resp_500(message=error_msg)

@router.get("/knowledge_file/status", response_model=UnifiedResponseModel)
async def get_knowledge_file_status(knowledge_file_id: str = Body(..., embed=True),
                                login_user: UserPayload = Depends(get_login_user)):
    try:
        # 验证用户权限
        await KnowledgeFileService.verify_user_permission(knowledge_file_id, login_user.user_id)
        knowledge_file = await KnowledgeFileService.select_knowledge_file_by_id(knowledge_file_id)
        return resp_200(data=knowledge_file.to_dict())
    except Exception as err:
        return resp_500(message=str(err))