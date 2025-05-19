from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Optional
from src.modules.instance_manager import (
    instance_manager,
    InstanceStatus,
)
from src.utils.generate_instance_id import generate_instance_id
from src.utils.logger import get_module_logger
from src.utils.database_model import (
    Services,
    Instances,
)
from src.utils.database import engine
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
import httpx

logger = get_module_logger("部署API")  # 修改 logger 名称
router = APIRouter()


# Pydantic Models from instance_api.py (related to deploy)
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


class ServiceInstallStatus(BaseModel):
    name: str
    status: str  # e.g., "pending", "installing", "completed", "failed"
    progress: int = Field(..., ge=0, le=100)
    message: str


class InstallStatusResponse(BaseModel):
    status: str  # Overall status: "installing", "completed", "failed"
    progress: int = Field(..., ge=0, le=100)
    message: str
    services_install_status: List[ServiceInstallStatus]


@router.post("/deploy", response_model=DeployResponse)  # 修改路径为 /deploy
async def deploy_maibot(payload: DeployRequest = Body(...)):
    """
    部署指定版本的 MaiBot。
    """
    logger.info(
        f"收到部署请求，版本: {payload.version}, 实例名称: {payload.instance_name}"
    )

    instance_id_str = generate_instance_id(payload.instance_name, payload.install_path)
    logger.info(f"为实例 {payload.instance_name} 生成的 ID: {instance_id_str}")

    with Session(engine) as session:
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

        # TODO: 在此处添加实际的部署逻辑
        try:
            new_instance_obj = instance_manager.create_instance(
                name=payload.instance_name,
                version=payload.version,
                path=payload.install_path,
                status=InstanceStatus.STARTING,
                port=payload.port,
                instance_id=instance_id_str,
                db_session=session,
            )

            if not new_instance_obj:
                logger.error(
                    f"通过 InstanceManager 创建实例 {payload.instance_name} (ID: {instance_id_str}) 失败，但未引发异常。"
                )
                raise HTTPException(
                    status_code=500, detail="实例信息保存失败，请查看日志了解详情。"
                )

            for service_config in payload.install_services:
                db_service = Services(
                    instance_id=instance_id_str,
                    name=service_config.name,
                    path=service_config.path,
                    status="pending",
                    port=service_config.port,
                )
                session.add(db_service)

            session.commit()

        except IntegrityError as e:
            session.rollback()
            logger.error(
                f"部署实例 {payload.instance_name} 时发生数据库完整性错误: {e}"
            )
            raise HTTPException(status_code=409, detail=f"保存部署信息时发生冲突: {e}")
        except Exception as e:
            session.rollback()
            logger.error(f"部署实例 {payload.instance_name} 期间发生意外错误: {e}")
            raise HTTPException(status_code=500, detail=f"处理部署时发生内部错误: {e}")

    logger.info(
        f"实例 {payload.instance_name} (ID: {instance_id_str}) 及关联服务已成功记录到数据库。"
    )
    return DeployResponse(
        success=True,
        message=f"MaiBot 版本 {payload.version} 的实例 {payload.instance_name} 部署任务已启动并记录。",
        instance_id=instance_id_str,
    )


@router.get(
    "/versions", response_model=AvailableVersionsResponse
)  # 修改路径为 /versions
async def get_available_versions():
    """
    获取可用于部署的版本列表。
    """
    github_api_url = "https://api.github.com/repos/MaiM-with-u/MaiBot/tags"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(github_api_url)
            response.raise_for_status()
            tags_data = response.json()

            versions = [
                tag["name"]
                for tag in tags_data
                if "name" in tag and tag["name"] != "EasyInstall-windows"
            ]
            if "latest" not in versions:
                versions.insert(0, "latest")
            if "main" not in versions:
                versions.insert(1, "main")

            logger.info(f"从 GitHub 获取的版本列表: {versions}")
            return AvailableVersionsResponse(versions=versions)
    except httpx.HTTPStatusError as e:
        logger.error(
            f"请求 GitHub API 失败: {e.response.status_code} - {e.response.text}"
        )
        default_versions = ["latest", "main"]
        logger.warning(f"GitHub API 请求失败，返回默认版本列表: {default_versions}")
        return AvailableVersionsResponse(versions=default_versions)
    except httpx.RequestError as e:
        logger.error(f"连接到 GitHub API 时发生错误: {e}")
        default_versions = ["latest", "main"]
        logger.warning(f"GitHub API 连接错误，返回默认版本列表: {default_versions}")
        return AvailableVersionsResponse(versions=default_versions)
    except Exception as e:
        logger.error(f"获取版本列表时发生未知错误: {e}")
        default_versions = ["latest", "main"]
        logger.warning(
            f"获取版本列表时发生未知错误，返回默认版本列表: {default_versions}"
        )
        return AvailableVersionsResponse(versions=default_versions)


@router.get(
    "/services", response_model=AvailableServicesResponse
)  # 修改路径为 /services
async def get_available_services():
    """
    获取可以部署的服务列表。
    """
    hardcoded_services = [
        ServiceInfo(name="napcat", description="NapCat 服务"),
        ServiceInfo(name="nonebot-ada", description="NoneBot-ada 服务"),
    ]
    logger.info(f"返回可用服务列表: {hardcoded_services}")
    return AvailableServicesResponse(services=hardcoded_services)


@router.get(
    "/install-status/{instance_id}", response_model=InstallStatusResponse
)  # 修改路径为 /install-status/{instance_id}
async def get_install_status(instance_id: str):
    """
    检查安装进度和状态。
    """
    logger.info(f"收到检查安装状态请求，实例ID: {instance_id}")
    # TODO: 实现从数据库或缓存中获取实际的安装状态和进度
    mock_services_status = [
        ServiceInstallStatus(
            name="napcat",
            status="installing",
            progress=50,
            message="正在安装 NapCat",
        ),
        ServiceInstallStatus(
            name="nonebot-ada",
            status="installing",
            progress=30,
            message="正在安装 NoneBot-ada",
        ),
    ]
    overall_progress = sum(s.progress for s in mock_services_status) // len(
        mock_services_status
    )
    return InstallStatusResponse(
        status="installing",
        progress=overall_progress,
        message="正在安装依赖...",
        services_install_status=mock_services_status,
    )
