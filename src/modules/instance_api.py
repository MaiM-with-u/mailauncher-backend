from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from src.modules.instance_manager import (
    InstanceStatus,
)  # instance_manager 已适配SQLModel
from src.utils.logger import get_module_logger
from src.utils.database_model import (
    Services,
    Instances,
)  # SQLModel 版本 - 添加 Instances
from src.utils.database import engine  # SQLModel 引擎
from sqlmodel import Session, select  # SQLModel Session - 添加 select
import asyncio
import shlex
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
    qq_number: Optional[str] = Field(None, description="关联的QQ号")


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
    installedAt: Optional[str] = (
        None  # 假设 installedAt 可能不总是存在或是字符串表示形式
    )
    path: str  # 路径
    port: int  # 端口
    services: List[ServiceDetail]  # 服务列表
    version: str  # 版本


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
    async with active_ptys_lock:
        if (
            session_id in active_ptys
            and active_ptys[session_id].get("pty")
            and active_ptys[session_id]["pty"].isalive()
        ):
            logger.info(f"会话 {session_id} 的 PTY 进程已在运行。")
            return True  # 已在运行

    pty_command_str, pty_cwd, _ = await get_pty_command_and_cwd_from_instance(
        session_id
    )

    if not pty_command_str:
        logger.error(f"无法确定会话 {session_id} 的 PTY 命令。")
        return False

    try:
        # 为 PtyProcess.spawn 准备命令
        try:
            cmd_to_spawn = shlex.split(pty_command_str)
            if not cmd_to_spawn:
                raise ValueError("命令字符串 shlex.split 后产生空列表")
        except ValueError as e_shlex:
            logger.warning(
                f"会话 {session_id} 的 PTY_COMMAND ('{pty_command_str}') 无法被 shlex 分割: {e_shlex}。将按原样使用。"
            )
            cmd_to_spawn = pty_command_str  # type: ignore

        pty_process = PtyProcess.spawn(
            cmd_to_spawn, dimensions=(PTY_ROWS_DEFAULT, PTY_COLS_DEFAULT), cwd=pty_cwd
        )
        logger.info(
            f"PTY 进程 (PID: {pty_process.pid}) 已通过 API 为会话 {session_id} 生成。"
        )

        async with active_ptys_lock:
            active_ptys[session_id] = {
                "pty": pty_process,
                "ws": None,  # API 启动时没有关联的 WebSocket
                "output_task": None,  # 输出任务将由 websocket_manager 启动
                "instance_part": instance_short_id,
                "type_part": type_part,
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
            db_instances = session.exec(select(Instances)).all()
            response_instances: List[InstanceDetail] = []

            for db_instance in db_instances:
                # 查询每个实例关联的服务
                db_services = session.exec(
                    select(Services).where(
                        Services.instance_id == db_instance.instance_id
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
                    status=db_instance.status.value
                    if isinstance(db_instance.status, InstanceStatus)
                    else db_instance.status,  # 处理枚举类型
                    installedAt=created_at_str,  # 使用转换后的字符串
                    path=db_instance.path,
                    port=db_instance.port,
                    services=services_details,
                    version=db_instance.version,
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
            db_instances = session.exec(select(Instances)).all()

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
    logger.info(f"收到启动实例 {instance_id} 的请求")
    instance = instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"未找到实例 {instance_id}")

    # 1. 更新实例状态为 STARTING
    instance_manager.update_instance_status(instance_id, InstanceStatus.STARTING)
    logger.info(f"实例 {instance_id} 状态已更新为“启动中”。")

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
    logger.info(f"实例 {instance_id} 检测到已安装的服务: {installed_services}")

    # 4. 启动已安装服务的 PTY
    if installed_services:
        for service_name in installed_services:
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
        updated_instance = instance_manager.update_instance_status(
            instance_id, InstanceStatus.RUNNING
        )
        if updated_instance:
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
async def stop_instance(instance_id: str):
    logger.info(f"收到停止实例 {instance_id} 的请求")
    instance = instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"未找到实例 {instance_id}")

    # 1. 更新实例状态为 STOPPING
    instance_manager.update_instance_status(instance_id, InstanceStatus.STOPPING)
    logger.info(f"实例 {instance_id} 状态已更新为“停止中”。")

    all_processes_stopped_successfully = True

    # 2. 获取需要停止的 PTY 列表（主应用 + 服务）
    pty_types_to_stop = [SERVICE_TYPE_MAIN]
    # 从数据库获取服务列表，而不是依赖 SERVICE_TYPES_ALL
    installed_services = instance_manager.get_instance_services(instance_id)
    if installed_services:
        for service_name in installed_services:
            if service_name not in pty_types_to_stop:  # 避免重复
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

    # 4. 更新实例状态为 STOPPED
    # 无论个别 PTY 停止是否报告问题，最终都将状态设置为 STOPPED
    # 因为目标是停止实例。
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


@router.post("/add", response_model=DeployResponse)
async def add_existing_instance(payload: DeployRequest):
    """
    添加硬盘中已有的麦麦实例到系统中。

    该API不会进行实际的部署，而是验证指定路径中是否存在麦麦实例，
    然后将其添加到数据库中进行管理。
    """
    logger.info(
        f"收到添加现有实例请求，实例名称: {payload.instance_name}, 路径: {payload.install_path}"
    )

    # 验证主安装路径是否存在
    install_path = Path(payload.install_path)
    if not install_path.exists():
        logger.error(f"指定的安装路径不存在: {payload.install_path}")
        raise HTTPException(
            status_code=400, detail=f"指定的安装路径不存在: {payload.install_path}"
        )

    if not install_path.is_dir():
        logger.error(f"指定的安装路径不是目录: {payload.install_path}")
        raise HTTPException(
            status_code=400, detail=f"指定的安装路径不是目录: {payload.install_path}"
        )

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
    with Session(engine) as session:
        # 检查实例是否已存在
        existing_instance_check = session.exec(
            select(Instances).where(Instances.instance_id == instance_id_str)
        ).first()
        if existing_instance_check:
            logger.warning(
                f"实例ID {instance_id_str} ({payload.instance_name}) 已存在。"
            )
            raise HTTPException(
                status_code=409,
                detail=f"实例 '{payload.instance_name}' (ID: {instance_id_str}) 已存在。",
            )

        try:
            # 创建实例记录
            new_instance_obj = instance_manager.create_instance(
                name=payload.instance_name,
                version=payload.version,
                path=payload.install_path,
                status=InstanceStatus.STOPPED,  # 新添加的实例默认为停止状态
                port=payload.port,
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
                db_service = Services(
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
