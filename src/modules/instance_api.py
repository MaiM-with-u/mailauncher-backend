from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Optional
from src.modules.instance_manager import (
    instance_manager,
    InstanceStatus,
)  # instance_manager 已适配SQLModel
from src.utils.generate_instance_id import generate_instance_id
from src.utils.logger import get_module_logger
from src.utils.database_model import Services  # SQLModel version
from src.utils.database import engine  # SQLModel engine
from sqlmodel import Session  # SQLModel Session
from sqlalchemy.exc import IntegrityError  # SQLAlchemy的IntegrityError

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


@router.post("/deploy/{version}", response_model=DeployResponse)
async def deploy_version(version: str, payload: DeployRequest = Body(...)):
    """
    部署指定版本的 MaiBot。
    """
    logger.info(f"收到部署请求，版本: {version}, 实例名称: {payload.instance_name}")

    # 检查版本是否一致 (路径参数 vs 请求体中的 version)
    if version != payload.version:
        logger.warning(
            f"路径版本 '{version}' 与请求体版本 '{payload.version}' 不匹配。"
        )

    # 生成实例ID
    instance_id_str = generate_instance_id(payload.instance_name, payload.install_path)
    logger.info(f"为实例 {payload.instance_name} 生成的 ID: {instance_id_str}")

    # 检查实例是否已存在
    if instance_manager.get_instance(instance_id_str):
        logger.warning(f"实例ID {instance_id_str} ({payload.instance_name}) 已存在。")
        raise HTTPException(
            status_code=409,
            detail=f"实例 '{payload.instance_name}' (ID: {instance_id_str}) 已存在。",
        )

    # TODO: 在此处添加实际的部署逻辑
    # 1. 下载指定版本的 MaiBot (如果需要)
    # 2. 解压/安装到 payload.install_path
    # 3. 配置 MaiBot (例如端口, QQ号等)
    # 4. 安装和配置 installServices 中的各个服务
    # 5. 启动 MaiBot 主程序和相关服务 (可能是异步任务)

    try:
        with Session(engine) as session:  # 使用 SQLModel Session
            # Instance Manager 的 create_instance 已经适配 SQLModel
            # 它内部处理 session.add, commit, refresh
            new_instance_obj = instance_manager.create_instance(
                name=payload.instance_name,
                version=payload.version,
                path=payload.install_path,
                status=InstanceStatus.STARTING,
                port=payload.port,
                instance_id=instance_id_str,
            )

            if not new_instance_obj:
                logger.error(
                    f"通过 InstanceManager 创建实例 {payload.instance_name} (ID: {instance_id_str}) 失败。"
                )
                # 此处假设 instance_manager.create_instance 失败会返回 None 且已记录具体错误
                raise HTTPException(
                    status_code=500, detail="实例信息保存失败，请查看日志了解详情。"
                )

            # 创建 Services 记录
            for service_config in payload.install_services:
                db_service = Services(
                    instance_id=instance_id_str,
                    name=service_config.name,
                    path=service_config.path,
                    port=service_config.port,
                    status="PENDING",
                )
                session.add(db_service)

            session.commit()  # 一次性提交所有服务和实例（如果 instance_manager 不自己 commit 的话）
            # 如果 instance_manager.create_instance 内部已经 commit,
            # 这里的 commit 只针对 services。为安全起见，确保事务边界清晰。
            # 理想情况下，整个 deploy_version 的数据库操作应在一个事务内。
            # 考虑到 instance_manager.create_instance 已经是一个封装好的操作，
            # 我们在这里为 services 单独 commit，或者将 instance_manager 的创建逻辑也纳入此处的 session。
            # 当前的 instance_manager.create_instance 实现是独立的事务单元。
            # 为了简单起见，这里我们假设 services 的创建是紧随其后的独立提交。
            # 更优的方案是调整 instance_manager.create_instance 接受一个可选的 session 参数。

            logger.info(
                f"为实例 {instance_id_str} 成功记录 {len(payload.install_services)} 个服务。"
            )

    except IntegrityError as ie:  # 使用 SQLAlchemy 的 IntegrityError
        # 注意：Services 表的 instance_id 字段已移除 unique 约束，所以此处的 IntegrityError
        # 更可能是由于其他约束（如 Services 表的 id 主键冲突，但不应该发生）或数据库问题。
        logger.error(
            f"数据库完整性错误，实例 {payload.instance_name} (ID: {instance_id_str}): {ie}。"
        )
        raise HTTPException(
            status_code=409, detail=f"数据库完整性冲突：无法为实例关联服务。详情: {ie}"
        )
    except Exception as e:
        logger.error(
            f"部署实例 {payload.instance_name} (ID: {instance_id_str}) 或其服务时发生意外错误: {e}"
        )
        # 应该在这里回滚，但由于 instance_manager 的事务是独立的，只能回滚 services 的部分
        # session.rollback() # 如果 services 的 add 在此 session 中
        raise HTTPException(
            status_code=500, detail=f"部署过程中发生内部服务器错误: {e}"
        )

    logger.info(
        f"实例 {payload.instance_name} (ID: {instance_id_str}) 部署任务已提交。"
    )
    return DeployResponse(
        success=True, message="部署任务已提交", instance_id=instance_id_str
    )


# 可以在 main.py 中引入并注册这个 router
# from src.modules import instance_api
# app.include_router(instance_api.router, prefix="/api/v1", tags=["Instances"])
