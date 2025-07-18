from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import asyncio
import os
import shlex
import shutil
from src.modules.instance_manager import (
    InstanceStatus,
)  # instance_manager 已适配SQLModel
from src.utils.logger import get_module_logger
from src.utils.database_model import DB_Service, DB_Instance
from datetime import datetime
from src.utils.database import engine  # SQLModel 引擎
from sqlmodel import Session, select  # SQLModel Session - 添加 select
from winpty import PtyProcess  # type: ignore
from pathlib import Path
from sqlalchemy.exc import IntegrityError
from src.utils.generate_instance_id import generate_instance_id

from src.modules.websocket_manager import (
    active_ptys,
    active_ptys_lock,
    get_pty_command_and_cwd_from_instance,
    PTY_ROWS_DEFAULT,
    PTY_COLS_DEFAULT,
    stop_all_ptys_for_instance,  # 添加此导入
)
from src.modules.instance_manager import instance_manager  # 导入全局 instance_manager

logger = get_module_logger("实例API")
router = APIRouter()


class ServiceInstallConfig(BaseModel):
    name: str = Field(..., description="服务名称")
    path: str = Field(..., description="服务安装路径")
    port: int = Field(..., description="服务端口")
    run_cmd: str = Field(..., description="服务运行命令")


class DeployRequest(BaseModel):
    instance_name: str = Field(..., description="实例名称")
    install_services: List[ServiceInstallConfig] = Field(
        ..., description="要安装的服务列表"
    )
    install_path: str = Field(..., description="MaiBot 安装路径")
    port: int = Field(..., description="MaiBot 主程序端口")
    version: str = Field(..., description="要部署的 MaiBot 版本")
    # 添加可选的分离路径字段，用于支持硬件已有实例
    maibot_path: Optional[str] = Field(
        None, description="MaiBot主程序文件夹路径（用于已有实例）"
    )
    adapter_path: Optional[str] = Field(
        None, description="适配器文件夹路径（用于已有实例）"
    )
    qq_number: Optional[str] = Field(None, description="关联的QQ号")
    host: Optional[str] = Field("localhost", description="实例主机地址")
    token: Optional[str] = Field("", description="实例访问令牌")


class DeployResponse(BaseModel):
    success: bool
    message: str
    instance_id: Optional[str] = None


class AvailableVersionsResponse(BaseModel):
    versions: List[str]


class ServiceInfo(BaseModel):
    name: str
    description: str


class AvailableServicesResponse(BaseModel):
    services: List[ServiceInfo]


# 获取实例 API 的 Pydantic 模型
class ServiceDetail(BaseModel):
    name: str
    path: str
    status: str  # 状态
    port: int


class InstanceDetail(BaseModel):
    id: str  # 实例ID
    name: str  # 实例名称
    status: str  # 状态
    installedAt: Optional[str] = None
    path: str  # 路径
    port: int  # 端口
    services: List[ServiceDetail]  # 服务列表
    version: str  # 版本
    total_runtime: Optional[int] = 0  # 累计运行时长（秒）
    start_count: Optional[int] = 0  # 启动次数
    last_start_time: Optional[str] = None  # 最后一次启动时间（ISO 格式字符串）


class GetInstancesResponse(BaseModel):
    instances: List[InstanceDetail]
    success: bool


# 实例统计 API 的 Pydantic 模型
class InstanceStatsResponse(BaseModel):
    total: int  # 总数
    running: int  # 运行中
    stopped: int  # 已停止


class ActionResponse(BaseModel):
    success: bool
    message: str


SERVICE_TYPES_ALL = ["main", "napcat", "napcat-ada"]
SERVICE_TYPE_MAIN = "main"


# 辅助函数：启动 PTY 进程
async def _start_pty_process(
    session_id: str, instance_short_id: str, type_part: str
) -> bool:
    """
    启动 PTY 进程 - 如果虚拟终端已存在，则向其发送启动命令；
    如果不存在，则创建新的 PTY 进程。
    """
    # 获取启动命令
    pty_command_str, pty_cwd, _ = await get_pty_command_and_cwd_from_instance(
        session_id
    )

    if not pty_command_str:
        logger.error(f"无法确定会话 {session_id} 的 PTY 启动命令。")
        return False

    # 添加详细的调试日志
    logger.info(f"会话 {session_id} 获取到的命令: '{pty_command_str}'")
    logger.info(f"会话 {session_id} 获取到的工作目录: '{pty_cwd}'")

    # 检查命令中是否包含虚拟环境路径
    if "venv" in pty_command_str:
        # 尝试提取虚拟环境 Python 路径进行验证
        import re

        if match := re.search(r'"([^"]*python\.exe)"', pty_command_str):
            python_exe_path = match.group(1)
            logger.info(f"检测到虚拟环境 Python 路径: {python_exe_path}")

            # 验证文件是否存在
            from pathlib import Path

            if not Path(python_exe_path).exists():
                logger.warning(f"虚拟环境 Python 文件不存在: {python_exe_path}")
                logger.warning("这可能导致 PTY 启动失败")
            else:
                logger.info(f"虚拟环境 Python 文件存在且可访问: {python_exe_path}")

    # 首先检查是否有现有的PTY进程
    existing_pty_info = None
    async with active_ptys_lock:
        if session_id in active_ptys:
            existing_pty_info = active_ptys[
                session_id
            ].copy()  # 复制数据以避免在锁外访问

    if (
        existing_pty_info
        and existing_pty_info.get("pty")
        and existing_pty_info["pty"].isalive()
    ):
        # 检查是否已经启动了命令
        if existing_pty_info.get("command_started", False):
            logger.info(f"会话 {session_id} 的命令已在运行。")
            return True

        # 向现有的虚拟终端发送启动命令
        pty_process = existing_pty_info["pty"]

        try:
            # 切换到正确的工作目录
            if pty_cwd and pty_cwd != existing_pty_info.get("working_directory"):
                cd_command = f'cd /d "{pty_cwd}"\r\n'
                pty_process.write(cd_command)
                logger.info(f"已切换到工作目录: {pty_cwd}")

            # 发送启动命令
            start_command = f"{pty_command_str}\r\n"
            pty_process.write(start_command)

            # 使用单独的锁操作来更新状态
            async with active_ptys_lock:
                if session_id in active_ptys:
                    active_ptys[session_id]["command_started"] = True
                    active_ptys[session_id]["working_directory"] = pty_cwd

            logger.info(
                f"已向现有虚拟终端发送启动命令 (会话: {session_id}): {pty_command_str}"
            )
            return True
        except Exception as e:
            logger.error(f"向会话 {session_id} 的虚拟终端发送命令失败: {e}")
            return False
            # 如果虚拟终端不存在，创建新的 PTY 进程（直接执行命令）
    try:
        # 为 PtyProcess.spawn 准备命令
        try:
            # 在Windows上，使用posix=False来正确处理路径
            if os.name == "nt":
                cmd_to_spawn = shlex.split(pty_command_str, posix=False)
            else:
                cmd_to_spawn = shlex.split(pty_command_str)

            if not cmd_to_spawn:
                raise ValueError("命令字符串 shlex.split 后产生空列表")

            # 添加调试日志，显示分割后的命令
            logger.info(f"会话 {session_id} shlex.split 结果: {cmd_to_spawn}")
            # 在 Windows 上验证可执行文件路径
            if os.name == "nt" and cmd_to_spawn:
                executable_path = cmd_to_spawn[0]
                logger.info(
                    f"会话 {session_id} 准备执行的可执行文件: '{executable_path}'"
                )

                # 去掉路径中的引号（如果存在）
                clean_executable_path = executable_path.strip("\"'")
                logger.info(
                    f"会话 {session_id} 清理后的可执行文件路径: '{clean_executable_path}'"
                )

                # 检查可执行文件是否存在
                if not Path(clean_executable_path).exists():
                    logger.error(f"可执行文件不存在: {clean_executable_path}")
                    # 尝试检查是否有权限问题
                    parent_dir = Path(clean_executable_path).parent
                    if parent_dir.exists():
                        logger.info(f"父目录存在: {parent_dir}")
                        # 列出父目录内容以调试
                        try:
                            dir_contents = list(parent_dir.iterdir())
                            logger.info(f"父目录内容: {[f.name for f in dir_contents]}")
                        except Exception as list_err:
                            logger.error(f"无法列出父目录内容: {list_err}")
                    else:
                        logger.error(f"父目录不存在: {parent_dir}")
                else:
                    logger.info(
                        f"可执行文件验证通过: {clean_executable_path}"
                    )  # 更新命令列表，确保路径没有多余的引号
                cmd_to_spawn[0] = clean_executable_path

        except ValueError as e_shlex:
            logger.warning(
                f"会话 {session_id} 的 PTY_COMMAND ('{pty_command_str}') 无法被 shlex 分割: {e_shlex}。将按原样使用。"
            )
            cmd_to_spawn = pty_command_str  # type: ignore

        logger.info(
            f"会话 {session_id} 最终传递给 PtyProcess.spawn 的命令: {cmd_to_spawn}"
        )
        logger.info(f"会话 {session_id} 工作目录: {pty_cwd}")

        # 尝试启动 PTY 进程
        pty_process = None
        try:
            pty_process = PtyProcess.spawn(
                cmd_to_spawn,
                dimensions=(PTY_ROWS_DEFAULT, PTY_COLS_DEFAULT),
                cwd=pty_cwd,
            )
            logger.info(
                f"PTY 进程 (PID: {pty_process.pid}) 已通过 API 为会话 {session_id} 生成。"
            )
        except Exception as spawn_error:
            logger.warning(f"直接启动 PTY 失败: {spawn_error}")

            # 在 Windows 上尝试备用策略：使用 cmd.exe 来执行命令
            if os.name == "nt":
                logger.info(f"会话 {session_id} 尝试使用 cmd.exe 备用策略...")
                try:
                    # 使用 cmd.exe /c 来执行原始命令
                    cmd_wrapper = ["cmd.exe", "/c", pty_command_str]
                    logger.info(
                        f"会话 {session_id} 使用 cmd.exe 包装的命令: {cmd_wrapper}"
                    )

                    pty_process = PtyProcess.spawn(
                        cmd_wrapper,
                        dimensions=(PTY_ROWS_DEFAULT, PTY_COLS_DEFAULT),
                        cwd=pty_cwd,
                    )
                    logger.info(
                        f"PTY 进程 (PID: {pty_process.pid}) 通过 cmd.exe 备用策略为会话 {session_id} 生成。"
                    )
                except Exception as cmd_error:
                    logger.error(f"cmd.exe 备用策略也失败: {cmd_error}")
                    raise spawn_error  # 抛出原始错误
            else:
                raise spawn_error  # 非 Windows 系统直接抛出错误
            raise RuntimeError("无法创建 PTY 进程")

        # 使用单独的锁操作来添加新的PTY
        async with active_ptys_lock:
            active_ptys[session_id] = {
                "pty": pty_process,
                "ws": None,  # API 启动时没有关联的 WebSocket
                "output_task": None,  # 输出任务将由 websocket_manager 启动
                "instance_part": instance_short_id,
                "type_part": type_part,
                "command_started": True,  # 直接启动的命令标记为已启动
                "working_directory": pty_cwd,
            }
        return True
    except Exception as e:
        logger.error(f"为会话 {session_id} 启动 PTY 进程失败: {e}", exc_info=True)
        return False


# 辅助函数：停止 PTY 进程
async def _stop_pty_process(session_id: str) -> bool:
    async with active_ptys_lock:
        if session_id not in active_ptys or not active_ptys[session_id].get("pty"):
            logger.info(
                f"在 active_ptys 中未找到会话 {session_id} 的 PTY 进程或没有 PTY 对象。"
            )
            return True  # 如果未找到，则认为已停止

        pty_info = active_ptys[session_id]
        pty_process = pty_info.get("pty")

        if not (pty_process and pty_process.isalive()):
            logger.info(f"会话 {session_id} 的 PTY 进程已停止或未存活。")
            if session_id in active_ptys:  # 如果条目存在但 PTY 已死，则清理
                active_ptys.pop(session_id, None)
            return True

    # 锁已释放，重新获取以执行 pop 操作
    async with active_ptys_lock:
        pty_info = active_ptys.pop(session_id)  # 从活动列表中移除

    output_task = pty_info.get("output_task")
    if output_task and not output_task.done():
        output_task.cancel()
        try:
            await output_task
        except asyncio.CancelledError:
            logger.info(f"会话 {session_id} 的输出任务已取消。")
        except Exception as e:
            logger.error(f"等待已取消的会话 {session_id} 输出任务时出错: {e}")

    if pty_process and pty_process.isalive():
        try:
            pty_process.terminate(force=True)
            logger.info(f"会话 {session_id} 的 PTY 进程已通过 API 终止。")
        except Exception as e:
            logger.error(f"终止会话 {session_id} 的 PTY 进程时出错: {e}", exc_info=True)
            # 如果终止失败，它可能仍然已停止或变得无响应
            return False  # 指示终止问题
    return True


@router.get("/instances", response_model=GetInstancesResponse)
async def get_instances():
    """
    获取所有 Bot 实例的列表。
    """
    logger.info("收到获取实例列表请求")
    try:
        with Session(engine) as session:
            # 查询所有实例
            db_instances = session.exec(select(DB_Instance)).all()
            response_instances: List[InstanceDetail] = []

            for db_instance in db_instances:
                # 查询每个实例关联的服务
                db_services = session.exec(
                    select(DB_Service).where(
                        DB_Service.instance_id == db_instance.instance_id
                    )
                ).all()

                services_details = [
                    ServiceDetail(
                        name=service.name,
                        path=service.path,
                        status=service.status,
                        port=service.port,
                    )
                    for service in db_services
                ]

                # installedAt 可能是 datetime 对象，需要转换为字符串
                created_at_str = (
                    db_instance.created_at.isoformat()
                    if db_instance.created_at
                    else None
                )

                instance_detail = InstanceDetail(
                    id=db_instance.instance_id,
                    name=db_instance.name,
                    status=db_instance.status.value if isinstance(db_instance.status, InstanceStatus) else db_instance.status,
                    installedAt=created_at_str,
                    path=db_instance.path,
                    port=db_instance.port,
                    services=services_details,
                    version=db_instance.version,
                    total_runtime=db_instance.total_runtime if hasattr(db_instance, 'total_runtime') else 0,
                    start_count=db_instance.start_count if hasattr(db_instance, 'start_count') else 0,
                    last_start_time=db_instance.last_start_time if hasattr(db_instance, 'last_start_time') else None,
                )
                response_instances.append(instance_detail)

            logger.info(f"成功获取 {len(response_instances)} 个实例的详细信息")
            return GetInstancesResponse(instances=response_instances, success=True)

    except Exception as e:
        logger.error(f"获取实例列表时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取实例列表失败: {str(e)}")


@router.get("/instances/stats", response_model=InstanceStatsResponse)
async def get_instance_stats():
    """
    获取实例统计数据，如总数、运行中的数量等。
    """
    logger.info("收到获取实例统计信息请求")
    try:
        with Session(engine) as session:
            db_instances = session.exec(select(DB_Instance)).all()

            total_instances = len(db_instances)
            running_instances = 0
            stopped_instances = 0

            for instance in db_instances:
                # 使用 InstanceStatus 枚举的 .value 进行比较
                if instance.status == InstanceStatus.RUNNING.value:
                    running_instances += 1
                elif instance.status == InstanceStatus.STOPPED.value:
                    stopped_instances += 1
                # 可以根据需要添加对其他状态的计数

            logger.info(
                f"实例统计: 总数={total_instances}, 运行中={running_instances}, 已停止={stopped_instances}"
            )
            return InstanceStatsResponse(
                total=total_instances,
                running=running_instances,
                stopped=stopped_instances,
            )
    except Exception as e:
        logger.error(f"获取实例统计信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取实例统计信息失败: {str(e)}")


@router.get("/instance/{instance_id}/start", response_model=ActionResponse)
async def start_instance(instance_id: str):
    # sourcery skip: use-named-expression
    logger.info(f"收到启动实例 {instance_id} 的请求")
    instance = instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"未找到实例 {instance_id}")

    # 1. 更新实例状态为 STARTING
    instance_manager.update_instance_status(instance_id, InstanceStatus.STARTING)
    logger.info(f"实例 {instance_id} 状态已更新为“启动中”。")
    # 记录启动时间并递增启动次数到数据库，确保 last_start_time 每次都写入并 commit
    now_str = datetime.utcnow().isoformat()
    with Session(engine) as session:
        db_instance = session.exec(select(DB_Instance).where(DB_Instance.instance_id == instance_id)).first()
        if db_instance:
            # 总是写入当前时间，避免 last_start_time 为 NULL
            db_instance.last_start_time = now_str
            # start_count 递增
            db_instance.start_count = (db_instance.start_count or 0) + 1
            session.add(db_instance)
            session.commit()

    started_any_process = False

    # 2. 启动主应用 PTY
    main_session_id = f"{instance_id}_{SERVICE_TYPE_MAIN}"
    logger.info(f"正在尝试启动实例 {instance_id} 的主应用 PTY ({SERVICE_TYPE_MAIN})...")
    if await _start_pty_process(main_session_id, instance_id, SERVICE_TYPE_MAIN):
        started_any_process = True
        logger.info(
            f"实例 {instance_id} 的主应用 PTY ({SERVICE_TYPE_MAIN}) 已启动或已在运行。"
        )
    else:
        logger.warning(
            f"启动实例 {instance_id} 的主应用 PTY ({SERVICE_TYPE_MAIN}) 失败。"
        )

    # 3. 获取已安装的服务
    installed_services = instance_manager.get_instance_services(instance_id)
    if installed_services:
        # 4. 启动已安装服务的 PTY
        logger.info(f"实例 {instance_id} 检测到已安装的服务: {installed_services}")
        for service_detail in installed_services:
            # 从服务详情字典中提取服务名称
            service_name = service_detail.name
            if not service_name:
                logger.warning(f"跳过无效的服务详情（缺少name字段）: {service_detail}")
                continue

            # 确保不会重复启动主应用（如果它也被列为服务的话）
            if service_name == SERVICE_TYPE_MAIN:
                continue

            service_session_id = f"{instance_id}_{service_name}"
            logger.info(f"正在尝试启动实例 {instance_id} 的服务 {service_name} PTY...")
            if await _start_pty_process(service_session_id, instance_id, service_name):
                started_any_process = True
                logger.info(
                    f"实例 {instance_id} 的服务 {service_name} PTY 已启动或已在运行。"
                )
            else:
                logger.warning(
                    f"启动实例 {instance_id} 的服务 {service_name} PTY 失败。"
                )
    else:
        logger.info(f"实例 {instance_id} 没有额外的已安装服务需要启动 PTY。")

    # 5. 根据 PTY 启动结果更新实例状态
    if started_any_process:
        if instance_manager.update_instance_status(instance_id, InstanceStatus.RUNNING):
            logger.info(f"实例 {instance_id} 状态已更新为“运行中”。")
            return ActionResponse(
                success=True, message=f"实例 {instance.name} 组件已启动。"
            )
        else:
            logger.error(f"更新实例 {instance_id} 状态为“运行中”失败。")
            return ActionResponse(
                success=True,  # PTY 可能仍在运行
                message=f"实例 {instance.name} 组件已启动，但状态更新失败。",
            )
    else:
        instance_manager.update_instance_status(instance_id, InstanceStatus.STOPPED)
        logger.warning(
            f"启动实例 {instance_id} 的任何 PTY 进程失败。状态已设置为“已停止”。"
        )
        return ActionResponse(
            success=False, message=f"启动实例 {instance.name} 的任何组件失败。"
        )


@router.get("/instance/{instance_id}/stop", response_model=ActionResponse)
async def stop_instance(instance_id: str):  # sourcery skip: use-named-expression
    logger.info(f"收到停止实例 {instance_id} 的请求")
    instance = instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"未找到实例 {instance_id}")

    # 1. 更新实例状态为 STOPPING
    instance_manager.update_instance_status(instance_id, InstanceStatus.STOPPING)
    logger.info(f"实例 {instance_id} 状态已更新为“停止中”。")

    all_processes_stopped_successfully = (
        True  # 2. 获取需要停止的 PTY 列表（主应用 + 服务）
    )
    pty_types_to_stop = [SERVICE_TYPE_MAIN]
    # 从数据库获取服务列表，而不是依赖 SERVICE_TYPES_ALL
    installed_services = instance_manager.get_instance_services(instance_id)
    if installed_services:
        for service_detail in installed_services:
            # 从服务详情字典中提取服务名称
            service_name = service_detail.name
            if service_name and service_name not in pty_types_to_stop:  # 避免重复
                pty_types_to_stop.append(service_name)

    logger.info(f"实例 {instance_id} 将尝试停止以下 PTY 类型: {pty_types_to_stop}")

    # 3. 迭代并停止每个 PTY
    for pty_type in pty_types_to_stop:
        session_id = f"{instance_id}_{pty_type}"
        logger.info(
            f"正在尝试停止实例 {instance_id} 的 PTY: {pty_type} (会话 ID: {session_id})..."
        )
        if not await _stop_pty_process(session_id):
            all_processes_stopped_successfully = False
            logger.warning(
                f"未能完全停止实例 {instance_id} 的 PTY {pty_type}，或者它没有运行。"
            )
        else:
            logger.info(f"实例 {instance_id} 的 PTY {pty_type} 已停止或没有运行。")

    # 调用 websocket_manager 中的函数来确保所有与此实例相关的 PTY 都已清理
    # 这是一个额外的保障措施
    logger.info(
        f"正在调用 stop_all_ptys_for_instance 清理实例 {instance_id} 的所有剩余 PTY..."
    )
    await stop_all_ptys_for_instance(instance_id)
    logger.info(f"实例 {instance_id} 的 stop_all_ptys_for_instance 清理完成。")

    # 统计本次运行时长并累加到 total_runtime
    with Session(engine) as session:
        db_instance = session.exec(select(DB_Instance).where(DB_Instance.instance_id == instance_id)).first()
        if db_instance:
            if db_instance.last_start_time:
                try:
                    start_time = datetime.fromisoformat(db_instance.last_start_time)
                    now = datetime.utcnow()
                    duration = int((now - start_time).total_seconds())
                    db_instance.total_runtime = (db_instance.total_runtime or 0) + duration
                except Exception as e:
                    logger.warning(f"实例 {instance_id} 运行时长统计失败: {e}")
            db_instance.last_start_time = None
            session.add(db_instance)
            session.commit()
    # 4. 更新实例状态为 STOPPED
    updated_instance = instance_manager.update_instance_status(
        instance_id, InstanceStatus.STOPPED
    )
    if updated_instance:
        logger.info(f"实例 {instance_id} 状态已更新为“已停止”。")
        if all_processes_stopped_successfully:
            return ActionResponse(
                success=True, message=f"实例 {instance.name} 所有组件已成功停止。"
            )
        else:
            return ActionResponse(
                success=True,  # 状态已更新为 STOPPED
                message=f"实例 {instance.name} 组件已停止，但部分 PTY 可能未能完全确认停止。",
            )
    else:
        logger.error(f"更新实例 {instance_id} 状态为“已停止”失败。")
        return ActionResponse(
            success=False,  # 主要操作（状态更新）失败
            message=f"实例 {instance.name} 组件已尝试停止，但状态更新失败。",
        )


@router.post("/instances/add", response_model=DeployResponse)
async def add_existing_instance(payload: DeployRequest):
    # sourcery skip: use-named-expression
    """
    添加硬盘中已有的麦麦实例到系统中。

    该API不会进行实际的部署，而是验证指定路径中是否存在麦麦实例，
    然后将其添加到数据库中进行管理。

    支持两种模式：
    1. 传统模式：使用install_path作为统一路径
    2. 分离模式：使用maibot_path和adapter_path分别指定MaiBot和适配器路径
    """
    logger.info(f"收到添加现有实例请求，实例名称: {payload.instance_name}")

    # 确定使用哪种路径模式
    if payload.maibot_path and payload.adapter_path:
        # 分离模式：分别验证MaiBot和适配器路径
        logger.info(
            f"使用分离路径模式 - MaiBot: {payload.maibot_path}, 适配器: {payload.adapter_path}"
        )

        # 验证MaiBot路径
        maibot_path = Path(payload.maibot_path)
        if not maibot_path.exists():
            logger.error(f"指定的MaiBot路径不存在: {payload.maibot_path}")
            raise HTTPException(
                status_code=400, detail=f"指定的MaiBot路径不存在: {payload.maibot_path}"
            )
        if not maibot_path.is_dir():
            logger.error(f"指定的MaiBot路径不是目录: {payload.maibot_path}")
            raise HTTPException(
                status_code=400,
                detail=f"指定的MaiBot路径不是目录: {payload.maibot_path}",
            )

        # 验证适配器路径
        adapter_path = Path(payload.adapter_path)
        if not adapter_path.exists():
            logger.error(f"指定的适配器路径不存在: {payload.adapter_path}")
            raise HTTPException(
                status_code=400,
                detail=f"指定的适配器路径不存在: {payload.adapter_path}",
            )
        if not adapter_path.is_dir():
            logger.error(f"指定的适配器路径不是目录: {payload.adapter_path}")
            raise HTTPException(
                status_code=400,
                detail=f"指定的适配器路径不是目录: {payload.adapter_path}",
            )


        # 检验MaiBot路径中是否包含bot.py
        bot_py_path = maibot_path / "bot.py"
        if not bot_py_path.exists():
            logger.error(f"MaiBot路径中未找到bot.py: {payload.maibot_path}")
            raise HTTPException(
                status_code=400,
                detail=f"MaiBot路径中未找到bot.py文件: {payload.maibot_path}",
            )

        # 使用MaiBot路径作为主安装路径
        main_install_path = payload.maibot_path

    else:
        # 传统模式：使用install_path作为统一路径
        logger.info(f"使用传统路径模式 - 安装路径: {payload.install_path}")

        install_path = Path(payload.install_path)
        if not install_path.exists():
            logger.error(f"指定的安装路径不存在: {payload.install_path}")
            raise HTTPException(
                status_code=400, detail=f"指定的安装路径不存在: {payload.install_path}"
            )
        if not install_path.is_dir():
            logger.error(f"指定的安装路径不是目录: {payload.install_path}")
            raise HTTPException(
                status_code=400,
                detail=f"指定的安装路径不是目录: {payload.install_path}",
            )
        main_install_path = payload.install_path

    # 验证各个服务路径是否存在
    for service_config in payload.install_services:
        service_path = Path(service_config.path)
        if not service_path.exists():
            logger.error(
                f"服务 {service_config.name} 的路径不存在: {service_config.path}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"服务 {service_config.name} 的路径不存在: {service_config.path}",
            )

        if not service_path.is_dir():
            logger.error(
                f"服务 {service_config.name} 的路径不是目录: {service_config.path}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"服务 {service_config.name} 的路径不是目录: {service_config.path}",
            )

    # 生成实例ID
    instance_id_str = generate_instance_id(payload.instance_name)
    logger.info(f"为实例 {payload.instance_name} 生成的 ID: {instance_id_str}")

    # 创建数据库记录
    with Session(engine) as session:  # 检查实例是否已存在
        existing_instance_check = session.exec(
            select(DB_Instance).where(DB_Instance.instance_id == instance_id_str)
        ).first()

        if existing_instance_check:
            logger.warning(
                f"实例ID {instance_id_str} ({payload.instance_name}) 已存在。"
            )
            raise HTTPException(
                status_code=409,
                detail=f"实例 '{payload.instance_name}' (ID: {instance_id_str}) 已存在。",
            )

        try:  # 创建实例记录
            new_instance_obj = instance_manager.create_instance(
                name=payload.instance_name,
                version=payload.version,
                path=main_install_path,  # 使用main_install_path而不是payload.install_path
                status=InstanceStatus.STOPPED,  # 新添加的实例默认为停止状态
                host=payload.host,
                port=payload.port,
                token=payload.token,
                instance_id=instance_id_str,
                db_session=session,
            )

            if not new_instance_obj:
                logger.error(
                    f"通过 InstanceManager 创建实例 {payload.instance_name} (ID: {instance_id_str}) 失败。"
                )
                raise HTTPException(
                    status_code=500, detail="实例信息保存失败，请查看日志了解详情。"
                )
            # 创建服务记录
            for service_config in payload.install_services:
                db_service = DB_Service(
                    instance_id=instance_id_str,
                    name=service_config.name,
                    path=service_config.path,
                    status="stopped",  # 新添加的服务默认为停止状态
                    port=service_config.port,
                    run_cmd=service_config.run_cmd,  # 使用payload中的run_cmd字段
                )
                session.add(db_service)

            session.commit()
            logger.info(
                f"现有实例 {payload.instance_name} (ID: {instance_id_str}) 及关联服务已成功添加到数据库。"
            )

        except IntegrityError as e:
            session.rollback()
            logger.error(
                f"添加现有实例 {payload.instance_name} 时发生数据库完整性错误: {e}"
            )
            raise HTTPException(status_code=409, detail=f"保存实例信息时发生冲突: {e}")
        except Exception as e:
            session.rollback()
            logger.error(f"添加现有实例 {payload.instance_name} 期间发生意外错误: {e}")
            raise HTTPException(
                status_code=500, detail=f"处理添加实例时发生内部错误: {e}"
            )

    return DeployResponse(
        success=True,
        message=f"现有实例 {payload.instance_name} 已成功添加到系统中。",
        instance_id=instance_id_str,
    )


@router.delete("/instance/{instance_id}/delete", response_model=ActionResponse)
async def delete_instance(instance_id: str):
    """
    删除指定的实例及其关联的所有服务。

    此函数将：
    1. 停止运行中的实例
    2. 清理所有相关的 PTY 进程
    3. 删除数据库中的实例和服务记录
    4. 删除实例和所有服务对应的文件夹
    """
    logger.info(f"收到删除实例 {instance_id} 的请求")

    # 1. 检查实例是否存在
    instance = instance_manager.get_instance(instance_id)
    if not instance:
        logger.warning(f"要删除的实例 {instance_id} 不存在")
        raise HTTPException(status_code=404, detail=f"未找到实例 {instance_id}")

    # 2. 确保实例已停止（可选的安全检查）
    if instance.status == InstanceStatus.RUNNING.value:
        logger.warning(f"实例 {instance_id} 仍在运行中，建议先停止实例再删除")
        # 可以选择强制停止或者要求用户先停止
        # 这里我们先停止实例
        await stop_instance(instance_id)
        logger.info(
            f"实例 {instance_id} 已自动停止"
        )  # 3. 停止并清理所有相关的 PTY 进程
    logger.info(f"正在清理实例 {instance_id} 的所有 PTY 进程...")
    await stop_all_ptys_for_instance(instance_id)

    # 4. 收集需要删除的文件夹路径
    folders_to_delete = []
    services_to_delete = []

    try:
        with Session(engine) as session:
            # 获取所有相关的服务记录，收集路径信息
            services_to_delete = session.exec(
                select(DB_Service).where(DB_Service.instance_id == instance_id)
            ).all()

            # 收集服务文件夹路径
            for service in services_to_delete:
                if service.path and Path(service.path).exists():
                    folders_to_delete.append(service.path)
                    logger.info(
                        f"将删除服务文件夹: {service.path} (服务: {service.name})"
                    )

            # 获取实例记录，收集实例路径
            instance_to_delete = session.exec(
                select(DB_Instance).where(DB_Instance.instance_id == instance_id)
            ).first()

            if instance_to_delete and instance_to_delete.path:
                instance_path = Path(instance_to_delete.path)
                if instance_path.exists():
                    folders_to_delete.append(instance_path)
                    logger.info(f"将删除实例文件夹: {instance_to_delete.path}")

            # 5. 删除数据库记录
            for service in services_to_delete:
                session.delete(service)
                logger.info(f"标记删除服务记录: {service.name} (实例ID: {instance_id})")

            if instance_to_delete:
                session.delete(instance_to_delete)
                logger.info(
                    f"标记删除实例记录: {instance_to_delete.name} (ID: {instance_id})"
                )

            # 6. 提交数据库事务
            session.commit()
            logger.info(f"实例 {instance_id} ({instance.name}) 的数据库记录已删除")

        # 7. 删除文件夹（在数据库事务成功后进行）
        deleted_folders = []
        failed_folders = []

        for folder_path in folders_to_delete:
            try:
                folder_path_obj = Path(folder_path)
                if folder_path_obj.is_dir():
                    shutil.rmtree(folder_path, ignore_errors=False)
                    deleted_folders.append(folder_path)
                    logger.info(f"成功删除文件夹: {folder_path}")
                elif folder_path_obj.exists():
                    logger.warning(f"路径存在但不是文件夹，跳过删除: {folder_path}")
                else:
                    logger.info(f"文件夹不存在，无需删除: {folder_path}")
            except Exception as folder_err:
                failed_folders.append(folder_path)
                logger.error(f"删除文件夹 {folder_path} 失败: {folder_err}")

        # 8. 构建返回消息
        success_msg = f"实例 {instance.name} 已成功删除"
        if deleted_folders:
            success_msg += f"，已删除 {len(deleted_folders)} 个文件夹"
        if failed_folders:
            success_msg += f"，但 {len(failed_folders)} 个文件夹删除失败: {', '.join(failed_folders)}"

        logger.info(
            f"实例 {instance_id} ({instance.name}) 删除完成: 数据库记录已删除，"
            f"成功删除 {len(deleted_folders)} 个文件夹，{len(failed_folders)} 个文件夹删除失败"
        )

        return ActionResponse(success=True, message=success_msg)

    except Exception as e:
        logger.error(f"删除实例 {instance_id} 时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除实例失败: {str(e)}")
