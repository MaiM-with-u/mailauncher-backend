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

from src.modules.websocket_manager import (
    active_ptys,
    active_ptys_lock,
    get_pty_command_and_cwd_from_instance,
    PTY_ROWS_DEFAULT,
    PTY_COLS_DEFAULT,
)
from src.modules.instance_manager import instance_manager  # 导入全局 instance_manager

logger = get_module_logger("实例API")
router = APIRouter()


class ServiceInstallConfig(BaseModel):
    name: str = Field(..., description="服务名称")
    path: str = Field(..., description="服务安装路径")
    port: int = Field(..., description="服务端口")


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
                installed_at_str = (
                    db_instance.installed_at.isoformat()
                    if db_instance.installed_at
                    else None
                )

                instance_detail = InstanceDetail(
                    id=db_instance.instance_id,
                    name=db_instance.name,
                    status=db_instance.status.value
                    if isinstance(db_instance.status, InstanceStatus)
                    else db_instance.status,  # 处理枚举类型
                    installedAt=installed_at_str,  # 使用转换后的字符串
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

    started_any_service = False
    for service_type in SERVICE_TYPES_ALL:
        session_id = f"{instance_id}_{service_type}"
        if await _start_pty_process(session_id, instance_id, service_type):
            started_any_service = True
            logger.info(f"实例 {instance_id} 的服务 {service_type} 已启动或已在运行。")
        else:
            logger.warning(f"启动实例 {instance_id} 的服务 {service_type} 失败。")

    if started_any_service:
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
            # 即使数据库更新失败，PTY 可能仍在运行。
            return ActionResponse(
                success=True,
                message=f"实例 {instance.name} 组件已启动，但状态更新失败。",
            )
    else:
        # 如果没有服务启动，我们可能不想更改总体状态，除非它已经停止。
        # 为简单起见，如果没有任何启动，则报告启动失败。
        logger.warning(f"启动实例 {instance_id} 的任何服务失败。")
        return ActionResponse(
            success=False, message=f"启动实例 {instance.name} 的任何组件失败。"
        )


@router.get("/instance/{instance_id}/stop", response_model=ActionResponse)
async def stop_instance(instance_id: str):
    logger.info(f"收到停止实例 {instance_id} 的请求")
    instance = instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"未找到实例 {instance_id}")

    all_services_stopped = True
    for service_type in SERVICE_TYPES_ALL:
        session_id = f"{instance_id}_{service_type}"
        if not await _stop_pty_process(session_id):
            all_services_stopped = False
            logger.warning(
                f"未能完全停止实例 {instance_id} 的服务 {service_type}，或者它没有运行。"
            )
        else:
            logger.info(f"实例 {instance_id} 的服务 {service_type} 已停止或没有运行。")

    # 如果所有组件都确认已停止，则将状态更新为“已停止”。
    # _stop_pty_process 如果已停止或成功停止，则返回 True。
    # 因此，如果 all_services_stopped 为 True，则所有相关的 PTY 现在都被视为非活动状态。
    if all_services_stopped:
        updated_instance = instance_manager.update_instance_status(
            instance_id, InstanceStatus.STOPPED
        )
        if updated_instance:
            logger.info(f"实例 {instance_id} 状态已更新为“已停止”。")
            return ActionResponse(
                success=True, message=f"实例 {instance.name} 组件已停止。"
            )
        else:
            logger.error(f"更新实例 {instance_id} 状态为“已停止”失败。")
            return ActionResponse(
                success=True,
                message=f"实例 {instance.name} 组件已停止，但状态更新失败。",
            )
    else:
        # 如果某些服务未能停止，实例可能处于部分状态。
        # 我们反映并非所有内容都可以确认为已停止。
        # 总体实例状态可能保持“运行中”或不确定状态。
        # 目前，如果并非所有服务都完全停止，则不要更改状态。
        logger.warning(f"无法确认实例 {instance_id} 的所有服务都已停止。")
        return ActionResponse(
            success=False, message=f"无法确认实例 {instance.name} 的所有组件都已停止。"
        )


@router.get("/instance/{instance_id}/restart", response_model=ActionResponse)
async def restart_instance(instance_id: str):
    logger.info(f"收到重启实例 {instance_id} (主服务) 的请求")
    instance = instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"未找到实例 {instance_id}")

    service_type = SERVICE_TYPE_MAIN  # 重启仅影响主服务
    session_id = f"{instance_id}_{service_type}"

    logger.info(f"正在停止实例 {instance_id} 的服务 {service_type}...")
    stopped = await _stop_pty_process(session_id)
    if stopped:
        logger.info(
            f"实例 {instance_id} 的服务 {service_type} 已停止。正在等待片刻后重启..."
        )
        await asyncio.sleep(1)  # 短暂暂停

        logger.info(f"正在启动实例 {instance_id} 的服务 {service_type}...")
        started = await _start_pty_process(session_id, instance_id, service_type)
        if started:
            updated_instance = instance_manager.update_instance_status(
                instance_id, InstanceStatus.RUNNING
            )
            if updated_instance:
                logger.info(
                    f"实例 {instance_id} (主服务) 已重启并且状态已更新为“运行中”。"
                )
            else:
                logger.error(
                    f"实例 {instance_id} (主服务) 已重启，但状态更新为“运行中”失败。"
                )
            return ActionResponse(
                success=True, message=f"实例 {instance.name} (主服务) 已重启。"
            )
        else:
            logger.error(f"停止实例 {instance_id} 的服务 {service_type} 后启动失败。")
            # 如果启动失败，实例状态可能为“已停止”。
            # 如果它正在运行并且未能重新启动，则考虑将其设置为“已停止”。
            current_db_instance = instance_manager.get_instance(instance_id)
            if (
                current_db_instance
                and current_db_instance.status == InstanceStatus.RUNNING
            ):
                instance_manager.update_instance_status(
                    instance_id, InstanceStatus.STOPPED
                )
            return ActionResponse(
                success=False,
                message=f"重启实例 {instance.name} (主服务) 失败。停止后无法启动。",
            )
    else:
        logger.error(
            f"作为重启的一部分，停止实例 {instance_id} 的服务 {service_type} 失败。"
        )
        return ActionResponse(
            success=False, message=f"重启实例 {instance.name} (主服务) 失败。无法停止。"
        )
