from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any  # Add Dict and Any for type hinting
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
from src.tools.deploy_version import deploy_manager  # 导入部署管理器
from pathlib import Path  # Add Path import

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

    instance_id_str = generate_instance_id(payload.instance_name)
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

        # 使用 deploy_manager 执行实际部署操作
        # 将 payload.install_path 替换为 instance_id_str
        # 并且传入 payload.install_services
        deploy_path = Path(payload.install_path)  # Create Path object for deploy_path
        deploy_success = deploy_manager.deploy_version(
            payload.version,
            deploy_path,  # Pass deploy_path directly
            instance_id_str,
            [
                service.model_dump() for service in payload.install_services
            ],  # 将Pydantic模型转换为字典列表
        )

        if not deploy_success:
            logger.error(
                f"使用 deploy_manager 部署版本 {payload.version} 到实例 {instance_id_str} 失败。"
            )
            # 注意：deploy_version 内部应该已经处理了部分创建文件的清理工作
            raise HTTPException(
                status_code=500,
                detail=f"部署 MaiBot 版本 {payload.version} 失败。请查看日志了解详情。",
            )

        logger.info(
            f"版本 {payload.version} 已成功部署到 {payload.install_path}。现在记录到数据库..."
        )

        try:
            new_instance_obj = instance_manager.create_instance(
                name=payload.instance_name,
                version=payload.version,
                path=payload.install_path,
                status=InstanceStatus.STARTING,
                port=payload.port,
                qq_number=payload.qq_number,
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
async def get_available_versions() -> AvailableVersionsResponse:
    """
    获取可用于部署的版本列表。
    """
    github_api_url: str = "https://api.github.com/repos/MaiM-with-u/MaiBot/tags"
    gitee_api_url: str = (
        "https://gitee.com/api/v5/repos/DrSmooth/MaiBot/tags"  # 备用 Gitee API URL
    )
    default_versions: List[str] = ["main"]  # 移除了 "latest"

    async def fetch_versions_from_url(url: str, source_name: str) -> List[str]:
        logger.info(f"尝试从 {source_name} 获取版本列表: {url}")
        async with httpx.AsyncClient() as client:
            response: httpx.Response = await client.get(url)
            response.raise_for_status()
            tags_data: List[Dict[str, Any]] = response.json()

            versions: List[str] = [
                tag["name"]
                for tag in tags_data
                if "name" in tag
                and isinstance(tag["name"], str)
                and tag["name"].startswith("0.6")
                and tag["name"] != "EasyInstall-windows"
            ]
            # 不再强制添加 "latest"
            if "main" not in versions:  # 仍然保留 main
                versions.insert(0, "main")  # 将 main 放在列表开头
            logger.info(f"从 {source_name} 获取并过滤后的版本列表: {versions}")
            return versions

    try:
        versions: List[str] = await fetch_versions_from_url(github_api_url, "GitHub")
        # 如果过滤后没有0.6.x的版本，但有main，则返回main
        if not any(v.startswith("0.6") for v in versions) and "main" in versions:
            logger.info("GitHub 中未找到 0.6.x 版本，但存在 main 版本。")
        elif not versions:  # 如果 GitHub 返回空列表（无0.6.x也无main）
            logger.warning("GitHub 未返回任何有效版本，尝试 Gitee。")
            raise httpx.RequestError(
                "No valid versions from GitHub"
            )  # 抛出异常以触发 Gitee 逻辑

        return AvailableVersionsResponse(versions=versions)
    except (httpx.HTTPStatusError, httpx.RequestError) as e_gh:
        logger.warning(
            f"请求 GitHub API 失败或未找到有效版本: {e_gh}. 尝试从 Gitee 获取..."
        )
        try:
            versions: List[str] = await fetch_versions_from_url(gitee_api_url, "Gitee")
            if not any(v.startswith("0.6") for v in versions) and "main" in versions:
                logger.info("Gitee 中未找到 0.6.x 版本，但存在 main 版本。")
            elif not versions:  # 如果 Gitee 也返回空列表
                logger.warning("Gitee 未返回任何有效版本，返回默认版本。")
                return AvailableVersionsResponse(
                    versions=default_versions
                )  # 返回仅包含 "main" 的默认列表

            return AvailableVersionsResponse(versions=versions)
        except (httpx.HTTPStatusError, httpx.RequestError) as e_gt:
            logger.error(
                f"请求 Gitee API 也失败或未找到有效版本: {e_gt}. 返回默认版本列表。"
            )
            return AvailableVersionsResponse(versions=default_versions)
        except Exception as e_gt_unknown:
            logger.error(f"从 Gitee 获取版本列表时发生未知错误: {e_gt_unknown}")
            return AvailableVersionsResponse(versions=default_versions)
    except Exception as e_unknown:
        logger.error(f"获取版本列表时发生未知错误: {e_unknown}")
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
