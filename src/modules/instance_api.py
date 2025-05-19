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
)  # SQLModel version - 添加 Instances
from src.utils.database import engine  # SQLModel engine
from sqlmodel import Session, select  # SQLModel Session - 添加 select

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


# Pydantic Models for Get Instances API
class ServiceDetail(BaseModel):
    name: str
    path: str
    status: str
    port: int

class InstanceDetail(BaseModel):
    id: str
    name: str
    status: str
    installedAt: Optional[str] = None # Assuming installedAt might not always be present or is a string representation
    path: str
    port: int
    services: List[ServiceDetail]
    version: str

class GetInstancesResponse(BaseModel):
    instances: List[InstanceDetail]
    success: bool


# Pydantic Model for Instance Stats API
class InstanceStatsResponse(BaseModel):
    total: int
    running: int
    stopped: int


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
                    select(Services).where(Services.instance_id == db_instance.instance_id)
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
                installed_at_str = db_instance.installed_at.isoformat() if db_instance.installed_at else None

                instance_detail = InstanceDetail(
                    id=db_instance.instance_id,
                    name=db_instance.name,
                    status=db_instance.status.value if isinstance(db_instance.status, InstanceStatus) else db_instance.status, # 处理枚举类型
                    installedAt=installed_at_str, # 使用转换后的字符串
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

            logger.info(f"实例统计: 总数={total_instances}, 运行中={running_instances}, 已停止={stopped_instances}")
            return InstanceStatsResponse(
                total=total_instances,
                running=running_instances,
                stopped=stopped_instances,
            )
    except Exception as e:
        logger.error(f"获取实例统计信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取实例统计信息失败: {str(e)}")
