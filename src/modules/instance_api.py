from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Optional
from src.modules.instance_manager import instance_manager, InstanceStatus
from src.utils.generate_instance_id import generate_instance_id # 假设的实例ID生成函数
from src.utils.logger import get_module_logger
from src.utils.database_model import Services, db # <--- 添加 Services 和 db
from peewee import IntegrityError # <--- 添加 IntegrityError

logger = get_module_logger("实例API")
router = APIRouter()

class ServiceInstallConfig(BaseModel):
    name: str = Field(..., description="服务名称")
    path: str = Field(..., description="服务安装路径")
    port: int = Field(..., description="服务端口")

class DeployRequest(BaseModel):
    instance_name: str = Field(..., description="实例名称")
    install_services: List[ServiceInstallConfig] = Field(..., description="要安装的服务列表")
    install_path: str = Field(..., description="MaiBot 安装路径")
    port: int = Field(..., description="MaiBot 主程序端口")
    version: str = Field(..., description="要部署的 MaiBot 版本") # 与路径参数中的 version 含义可能不同，注意区分
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
        logger.warning(f"路径版本 '{version}' 与请求体版本 '{payload.version}' 不匹配。")
        # 根据实际需求决定如何处理，这里假设以请求体为准或报错
        # raise HTTPException(status_code=400, detail=f"路径版本 '{version}' 与请求体版本 '{payload.version}' 不匹配。")

    # 生成实例ID
    instance_id_str = generate_instance_id(payload.instance_name, payload.install_path)
    logger.info(f"为实例 {payload.instance_name} 生成的 ID: {instance_id_str}")

    # 检查实例是否已存在
    if _existing_instance := instance_manager.get_instance(instance_id_str): # Sourcery建议的修改
        logger.warning(f"实例ID {instance_id_str} ({payload.instance_name}) 已存在。")
        raise HTTPException(status_code=409, detail=f"实例 '{payload.instance_name}' (ID: {instance_id_str}) 已存在。")

    # TODO: 在此处添加实际的部署逻辑
    # 1. 下载指定版本的 MaiBot (如果需要)
    # 2. 解压/安装到 payload.install_path
    # 3. 配置 MaiBot (例如端口, QQ号等)
    # 4. 安装和配置 installServices 中的各个服务
    # 5. 启动 MaiBot 主程序和相关服务 (可能是异步任务)

    try:
        with db.atomic(): # 确保实例创建和服务创建在同一个事务中
            # 创建实例记录到数据库
            new_instance = instance_manager.create_instance(
                name=payload.instance_name,
                version=payload.version, # 使用请求体中的版本
                path=payload.install_path,
                status=InstanceStatus.STARTING, # 初始状态可以设置为 "启动中" 或 "未运行"
                port=payload.port,
                instance_id=instance_id_str
            )

            if not new_instance:
                # instance_manager.create_instance 内部处理了错误并返回 None
                # 此处日志和异常主要为了捕获意外情况或明确指示事务失败点
                logger.error(f"在事务中创建实例 {payload.instance_name} (ID: {instance_id_str}) 失败。")
                raise HTTPException(status_code=500, detail="实例信息保存失败")

            # 更新 services 表
            # 重要警告: 下面的循环假定一个实例可以有多个服务。
            # 如果在 database_model.py 中的 'Services.instance_id' 字段上设置了 UNIQUE 约束，
            # 并且 'payload.install_services' 列表包含多个服务，则此操作将失败。
            # 您需要修改 'Services' 表的定义：为其添加自己的主键，并移除 instance_id 上的 unique 约束。
            for service_config in payload.install_services:
                Services.create(
                    instance_id=instance_id_str,  # 链接到 Instances.instance_id
                    name=service_config.name,
                    path=service_config.path,
                    port=service_config.port,
                    status="PENDING"  # 新注册服务的默认状态
                )
            logger.info(f"为实例 {instance_id_str} 成功记录 {len(payload.install_services)} 个服务。")
            
            # 如果所有操作都成功，事务将在此处提交

    except IntegrityError as ie:
        logger.error(f"数据库完整性错误，实例 {payload.instance_name} (ID: {instance_id_str}): {ie}。这很可能发生在尝试为 'Services' 表（其 'instance_id' 设置为唯一）添加多个服务条目时。")
        raise HTTPException(status_code=409, detail=f"数据库完整性冲突：无法为实例关联服务。请检查服务配置或数据库表结构。详情: {ie}")
    except Exception as e:
        logger.error(f"部署实例 {payload.instance_name} (ID: {instance_id_str}) 或其服务时发生意外错误: {e}")
        raise HTTPException(status_code=500, detail=f"部署过程中发生内部服务器错误: {e}")

    logger.info(f"实例 {payload.instance_name} (ID: {instance_id_str}) 部署任务已提交。")
    return DeployResponse(
        success=True,
        message="部署任务已提交",
        instance_id=instance_id_str
    )

# 可以在 main.py 中引入并注册这个 router
# from src.modules import instance_api
# app.include_router(instance_api.router, prefix="/api/v1", tags=["Instances"])
