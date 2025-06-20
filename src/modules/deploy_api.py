from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any  # Add Dict and Any for type hinting
from pathlib import Path  # 添加 Path 导入
from src.modules.instance_manager import (
    instance_manager,
    InstanceStatus,
)
from src.utils.generate_instance_id import generate_instance_id
from src.utils.logger import get_module_logger
from src.utils.database_model import (
    DB_Service,
    DB_Instance,
)
from src.utils.database import engine
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
import httpx
from src.tools.deploy_version import (
    deploy_manager,
    get_python_executable,
    set_log_callback,
)  # 导入部署管理器和Python路径检测器
import subprocess
import os
import threading
import asyncio
import time
from datetime import datetime

logger = get_module_logger("部署API")  # 修改 logger 名称
router = APIRouter()

# 全局缓存用于存储安装状态
install_status_cache: Dict[str, Dict] = {}
cache_lock = threading.Lock()


# Pydantic Models from instance_api.py (related to deploy)
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
    host: str = Field(default="127.0.0.1", description="实例的主机地址")
    token: str = Field(default="", description="Maim_message所设定的token")
    # qq_number: Optional[str] = Field(None, description="关联的QQ号")


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


class LogEntry(BaseModel):
    timestamp: str
    message: str
    level: str  # "info", "warning", "error", "success"


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
    logs: List[LogEntry] = Field(default_factory=list, description="详细安装日志")


# 缓存操作函数
def update_install_status(
    instance_id: str,
    status: str,
    progress: int,
    message: str,
    services_status: List[Dict] = None,
):
    """
    更新实例的安装状态到缓存

    Args:
        instance_id: 实例ID
        status: 整体状态 ("preparing", "installing", "completed", "failed")
        progress: 整体进度 (0-100)
        message: 状态消息
        services_status: 服务状态列表
    """
    with cache_lock:
        if instance_id not in install_status_cache:
            install_status_cache[instance_id] = {
                "start_time": time.time(),  # 记录开始时间
                "logs": [],  # 添加详细日志数组
            }

        install_status_cache[instance_id].update(
            {
                "status": status,
                "progress": progress,
                "message": message,
                "services_install_status": services_status or [],
                "last_updated": datetime.now().isoformat(),
            }
        )

    logger.info(f"更新实例 {instance_id} 安装状态: {status} ({progress}%) - {message}")


def add_install_log(instance_id: str, message: str, level: str = "info"):
    """
    添加安装日志到缓存，同时输出到后端日志系统

    Args:
        instance_id: 实例ID
        message: 日志消息
        level: 日志级别 ("info", "warning", "error", "success")
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {"timestamp": timestamp, "message": message, "level": level}

    with cache_lock:
        if instance_id not in install_status_cache:
            install_status_cache[instance_id] = {"start_time": time.time(), "logs": []}

        # 保持最近200条日志，避免内存过大
        if len(install_status_cache[instance_id]["logs"]) >= 200:
            install_status_cache[instance_id]["logs"].pop(0)

        install_status_cache[instance_id]["logs"].append(log_entry)

    # 同时记录到标准日志系统，使用不同的日志级别
    full_message = f"[{instance_id}] {message}"
    if level == "error":
        logger.error(full_message)
    elif level == "warning":
        logger.warning(full_message)
    elif level == "success":
        logger.info(f"✅ {full_message}")
    else:  # info 或其他级别
        logger.info(full_message)


def update_service_status(
    instance_id: str, service_name: str, status: str, progress: int, message: str
):
    """
    更新特定服务的安装状态

    Args:
        instance_id: 实例ID
        service_name: 服务名称
        status: 服务状态
        progress: 服务进度 (0-100)
        message: 状态消息
    """
    with cache_lock:
        if instance_id not in install_status_cache:
            install_status_cache[instance_id] = {
                "status": "installing",
                "progress": 0,
                "message": "正在准备安装...",
                "services_install_status": [],
                "last_updated": datetime.now().isoformat(),
            }

        services_status = install_status_cache[instance_id].get(
            "services_install_status", []
        )

        # 查找现有服务状态或创建新的
        service_found = False
        for service in services_status:
            if service["name"] == service_name:
                service.update(
                    {"status": status, "progress": progress, "message": message}
                )
                service_found = True
                break

        if not service_found:
            services_status.append(
                {
                    "name": service_name,
                    "status": status,
                    "progress": progress,
                    "message": message,
                }
            )

        # 计算整体进度
        if services_status:
            overall_progress = sum(s["progress"] for s in services_status) // len(
                services_status
            )
            install_status_cache[instance_id]["progress"] = overall_progress

        install_status_cache[instance_id]["services_install_status"] = services_status
        install_status_cache[instance_id]["last_updated"] = datetime.now().isoformat()

    logger.info(
        f"更新实例 {instance_id} 服务 {service_name} 状态: {status} ({progress}%) - {message}"
    )


def get_cached_install_status(instance_id: str) -> Dict:
    """
    从缓存获取安装状态

    Args:
        instance_id: 实例ID

    Returns:
        Dict: 安装状态数据
    """
    with cache_lock:
        return install_status_cache.get(
            instance_id,
            {
                "status": "not_found",
                "progress": 0,
                "message": "实例不存在或尚未开始安装",
                "services_install_status": [],
                "logs": [],
                "last_updated": datetime.now().isoformat(),
            },
        )


@router.post("/deploy", response_model=DeployResponse)  # 修改路径为 /deploy
async def deploy_maibot(
    payload: DeployRequest = Body(...), background_tasks: BackgroundTasks = None
):
    """
    部署指定版本的 MaiBot。
    """
    logger.info(
        f"收到部署请求，版本: {payload.version}, 实例名称: {payload.instance_name}"
    )

    instance_id_str = generate_instance_id(payload.instance_name)
    logger.info(
        f"为实例 {payload.instance_name} 生成的 ID: {instance_id_str}"
    )  # 初始化安装状态缓存
    update_install_status(instance_id_str, "preparing", 0, "正在准备部署...")

    with Session(engine) as session:
        existing_instance_check = session.exec(
            select(DB_Instance).where(DB_Instance.instance_id == instance_id_str)
        ).first()

        if existing_instance_check:
            logger.warning(
                f"实例ID {instance_id_str} ({payload.instance_name}) 已存在。"
            )
            update_install_status(instance_id_str, "failed", 0, "实例已存在")
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"实例 '{payload.instance_name}' 已存在",
                    "detail": f"实例ID {instance_id_str} 已在数据库中注册，请使用不同的实例名称或删除现有实例",
                    "error_code": "INSTANCE_EXISTS",
                },
            )

    # 将部署过程添加到后台任务
    if background_tasks:
        background_tasks.add_task(
            perform_deployment_background, payload, instance_id_str
        )
    else:
        # 如果没有 background_tasks（例如在测试中），创建一个异步任务
        asyncio.create_task(perform_deployment_background(payload, instance_id_str))

    logger.info(
        f"实例 {payload.instance_name} (ID: {instance_id_str}) 部署任务已启动。"
    )
    return DeployResponse(
        success=True,
        message=f"MaiBot 版本 {payload.version} 的实例 {payload.instance_name} 部署任务已启动。",
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
                and tag["name"].startswith("0.7")
                and tag["name"] != "EasyInstall-windows"
            ]
            # 不再强制添加 "latest"
            if "main" not in versions:  # 仍然保留 main
                versions.insert(0, "main")  # 将 main 放在列表开头
            # 在版本列表最后添加 dev
            versions.append("dev")
            logger.info(f"从 {source_name} 获取并过滤后的版本列表: {versions}")
            return versions

    try:
        versions: List[str] = await fetch_versions_from_url(
            github_api_url, "GitHub"
        )  # 如果过滤后没有0.7.x的版本，但有main，则返回main
        if not any(v.startswith("0.7") for v in versions) and "main" in versions:
            logger.info("GitHub 中未找到 0.7.x 版本，但存在 main 版本。")
        elif not versions:  # 如果 GitHub 返回空列表（无0.7.x也无main）
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
            if not any(v.startswith("0.7") for v in versions) and "main" in versions:
                logger.info("Gitee 中未找到 0.7.x 版本，但存在 main 版本。")
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
    检查安装进度和状态，包括详细的诊断信息
    """
    logger.info(f"收到检查安装状态请求，实例ID: {instance_id}")

    try:
        with cache_lock:
            status_info = install_status_cache.get(instance_id)

        if not status_info:
            # 检查实例是否已经完成部署
            with Session(engine) as session:
                instance = session.get(DB_Instance, instance_id)
                if instance:
                    return InstallStatusResponse(
                        status="completed",
                        progress=100,
                        message="实例部署已完成",
                        services_install_status=[],
                        logs=[],
                    )

            raise HTTPException(
                status_code=404, detail=f"实例 {instance_id} 不存在或尚未开始安装"
            )

        # 检查是否是长时间卡在某个阶段
        current_progress = status_info.get("progress", 0)
        start_time = status_info.get("start_time", time.time())
        elapsed_time = time.time() - start_time

        # 如果卡在依赖安装阶段超过5分钟
        if (
            status_info.get("status") == "installing"
            and 70 <= current_progress <= 73
            and elapsed_time > 300
        ):
            status_info["message"] += (
                f" (已进行{int(elapsed_time / 60)}分钟，大型依赖包安装需要较长时间)"
            )

        # 如果卡在Git克隆阶段超过3分钟
        elif (
            status_info.get("status") == "installing"
            and 20 <= current_progress <= 40
            and elapsed_time > 180
        ):
            status_info["message"] += (
                f" (已进行{int(elapsed_time / 60)}分钟，正在从官方源下载，请耐心等待)"
            )

        # 转换服务状态为 Pydantic 模型
        services_status = []
        for service_data in status_info.get("services_install_status", []):
            services_status.append(
                ServiceInstallStatus(
                    name=service_data["name"],
                    status=service_data["status"],
                    progress=service_data["progress"],
                    message=service_data["message"],
                )
            )

        # 转换日志为 Pydantic 模型
        logs = []
        for log_data in status_info.get("logs", []):
            logs.append(
                LogEntry(
                    timestamp=log_data["timestamp"],
                    message=log_data["message"],
                    level=log_data["level"],
                )
            )

        return InstallStatusResponse(
            status=status_info.get("status", "unknown"),
            progress=status_info.get("progress", 0),
            message=status_info.get("message", ""),
            services_install_status=services_status,
            logs=logs,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取安装状态时发生错误: {e}")
        raise HTTPException(status_code=500, detail="获取安装状态失败")


async def perform_deployment_background(payload: DeployRequest, instance_id_str: str):
    """
    在后台执行部署任务的异步函数
    """
    try:  # 更新进度：验证安装路径
        update_install_status(instance_id_str, "installing", 5, "阶段1/4: 准备部署环境")
        add_install_log(
            instance_id_str, "🔍 阶段1/4: 准备部署环境 - 开始验证安装路径", "info"
        )

        # 验证安装路径
        # 如果路径以~开头，展开为相对于当前工作目录的路径
        install_path = payload.install_path
        logger.info(
            f"原始路径: '{install_path}', 长度: {len(install_path)}, 第一个字符: '{install_path[0] if install_path else 'None'}' (实例ID: {instance_id_str})"
        )
        add_install_log(instance_id_str, f"📁 原始安装路径: {install_path}", "info")

        logger.info(
            f"检查是否以~开头: {install_path.startswith('~')} (实例ID: {instance_id_str})"
        )

        if install_path.startswith("~"):
            # 获取当前工作目录（启动器后端的根目录）
            current_dir = Path.cwd()
            logger.info(f"当前工作目录: {current_dir} (实例ID: {instance_id_str})")

            # 将~替换为当前工作目录
            if install_path.startswith("~/") or install_path.startswith("~\\"):
                # 移除 ~/ 或 ~\ 前缀，然后与当前目录拼接
                relative_path = install_path[2:]
                logger.info(
                    f"相对路径部分: '{relative_path}' (实例ID: {instance_id_str})"
                )
                install_path = str(current_dir / relative_path)
            else:  # 只有 ~ 的情况，移除~前缀
                relative_path = install_path[1:] if len(install_path) > 1 else ""
                if relative_path:
                    install_path = str(current_dir / relative_path)
                else:
                    install_path = str(current_dir)
            logger.info(
                f"展开~路径: {payload.install_path} -> {install_path} (实例ID: {instance_id_str})"
            )
            add_install_log(
                instance_id_str,
                f"📂 路径展开: {payload.install_path} -> {install_path}",
                "info",
            )
        else:
            logger.info(f"路径不以~开头，不进行展开 (实例ID: {instance_id_str})")

        deploy_path = Path(install_path)
        add_install_log(
            instance_id_str, f"📍 目标部署路径: {deploy_path.resolve()}", "info"
        )

        # 记录收到的路径信息
        logger.info(f"收到部署路径: {payload.install_path} (实例ID: {instance_id_str})")
        logger.info(f"处理后的路径: {install_path} (实例ID: {instance_id_str})")
        logger.info(
            f"解析后的绝对路径: {deploy_path.resolve()} (实例ID: {instance_id_str})"
        )

        # 检查父目录是否存在，如果不存在则尝试创建
        if not deploy_path.parent.exists():
            logger.info(
                f"父目录不存在，尝试创建: {deploy_path.parent} (实例ID: {instance_id_str})"
            )
            add_install_log(
                instance_id_str, f"📁 创建父目录: {deploy_path.parent}", "info"
            )
            try:
                deploy_path.parent.mkdir(parents=True, exist_ok=True)
                logger.info(
                    f"成功创建父目录: {deploy_path.parent} (实例ID: {instance_id_str})"
                )
                add_install_log(instance_id_str, "✅ 父目录创建成功", "success")
            except Exception as e:
                logger.error(
                    f"创建父目录失败 {deploy_path.parent}: {e} (实例ID: {instance_id_str})"
                )
                add_install_log(
                    instance_id_str, f"❌ 父目录创建失败: {str(e)}", "error"
                )
                update_install_status(
                    instance_id_str, "failed", 5, f"无法创建安装路径: {str(e)}"
                )
                return

        # 检查目标路径是否已存在实例
        if deploy_path.exists() and any(deploy_path.iterdir()):
            logger.warning(
                f"目标路径已存在文件: {deploy_path} (实例ID: {instance_id_str})"
            )
            add_install_log(
                instance_id_str, "⚠️ 目标路径已存在文件，将进行覆盖安装", "warning"
            )
            # 不强制失败，允许覆盖安装（但记录警告）
            logger.info(
                f"继续部署到现有路径，可能会覆盖文件 (实例ID: {instance_id_str})"
            )

        # 验证路径权限（尝试在目标路径创建测试文件）
        add_install_log(instance_id_str, "🔐 验证路径写入权限", "info")
        try:
            test_file = deploy_path.parent / f"test_write_{instance_id_str}.tmp"
            test_file.touch()
            test_file.unlink()
            add_install_log(instance_id_str, "✅ 路径权限验证通过", "success")
            logger.info(f"路径权限验证通过 (实例ID: {instance_id_str})")
        except Exception as e:
            logger.error(f"路径权限验证失败: {e} (实例ID: {instance_id_str})")
            update_install_status(
                instance_id_str, "failed", 5, f"路径权限不足: {str(e)}"
            )
            return  # 更新进度：开始下载
        update_install_status(
            instance_id_str,
            "installing",
            10,
            "阶段1/4: 准备部署环境 - 正在连接到代码仓库",
        )

        # 更新进度：准备部署文件
        update_install_status(
            instance_id_str,
            "installing",
            20,
            "阶段2/4: 使用Git克隆MaiBot - 正在下载源代码",
        )
        add_install_log(
            instance_id_str, "📦 阶段2/4: 使用Git克隆MaiBot - 开始下载源代码", "info"
        )  # 使用 deploy_manager 执行实际部署操作        # 将 payload.install_path 替换为 instance_id_str
        # 并且传入 payload.install_services
        # 在线程池中执行同步的部署操作，避免阻塞事件循环
        loop = asyncio.get_event_loop()  # 更新进度：开始解压和配置
        update_install_status(
            instance_id_str,
            "installing",
            25,
            "阶段2/4: 使用Git克隆MaiBot - 正在解压和配置文件",
        )

        # 准备展开后的服务配置给 deploy_manager
        expanded_services = []
        for service in payload.install_services:
            service_dict = service.model_dump()
            service_path = service_dict["path"]
            # 展开服务路径中的 ~ 符号（如果存在）
            if service_path.startswith("~"):
                current_dir = Path.cwd()
                if service_path.startswith("~/") or service_path.startswith("~\\"):
                    relative_path = service_path[2:]
                    service_path = str(current_dir / relative_path)
                else:
                    relative_path = service_path[1:] if len(service_path) > 1 else ""
                    if relative_path:
                        service_path = str(current_dir / relative_path)
                    else:
                        service_path = str(current_dir)
                service_dict["path"] = service_path
                logger.info(
                    f"为 deploy_manager 展开服务路径: {service.path} -> {service_path} (服务: {service.name}, 实例ID: {instance_id_str})"
                )

            expanded_services.append(service_dict)  # 设置日志回调函数
        set_log_callback(add_install_log)
        add_install_log(
            instance_id_str, "🚀 阶段2/4: 使用Git克隆MaiBot - 开始部署核心文件", "info"
        )
        add_install_log(instance_id_str, f"📦 部署版本: {payload.version}", "info")
        add_install_log(instance_id_str, f"📂 目标路径: {deploy_path}", "info")
        add_install_log(
            instance_id_str,
            "💡 正在从官方源下载MaiBot核心文件，请保持网络连接稳定",
            "info",
        )

        # 如果有napcat相关服务，添加相应日志
        napcat_services = [
            s for s in payload.install_services if "napcat" in s.name.lower()
        ]
        if napcat_services:
            add_install_log(
                instance_id_str,
                "🔧 阶段2/4: 检测到Napcat服务配置，将同时克隆Napcat-ada",
                "info",
            )
            for service in napcat_services:
                add_install_log(
                    instance_id_str,
                    f"📋 服务: {service.name} -> {service.path}",
                    "info",
                )

        # 更新进度并开始调用deploy_manager
        update_install_status(
            instance_id_str,
            "installing",
            30,
            "阶段2/4: 使用Git克隆MaiBot - 开始执行Git克隆操作",
        )
        add_install_log(
            instance_id_str, "🔄 开始调用deploy_manager执行Git克隆操作", "info"
        )
        add_install_log(
            instance_id_str,
            f"🔧 调用参数: 版本={payload.version}, 路径={deploy_path}",
            "info",
        )

        # 创建一个定时任务来监控deploy_manager的执行
        deploy_start_time = time.time()

        async def monitor_deploy_progress():
            """监控部署进度，定期输出日志"""
            try:
                while True:
                    await asyncio.sleep(15)  # 每15秒检查一次
                    elapsed = time.time() - deploy_start_time
                    minutes = int(elapsed / 60)
                    if minutes > 0:
                        add_install_log(
                            instance_id_str,
                            f"⏳ Git克隆进行中... 已用时{minutes}分钟，请耐心等待",
                            "info",
                        )
                    else:
                        add_install_log(
                            instance_id_str,
                            f"⏳ Git克隆进行中... 已用时{int(elapsed)}秒",
                            "info",
                        )
            except asyncio.CancelledError:
                pass

        # 启动监控任务
        monitor_task = asyncio.create_task(monitor_deploy_progress())

        try:
            deploy_success = await loop.run_in_executor(
                None,
                deploy_manager.deploy_version,
                payload.version,
                deploy_path,
                instance_id_str,
                expanded_services,  # 使用展开后的服务配置
                str(payload.port),  # 添加缺失的 instance_port 参数
            )
        finally:
            # 无论成功还是失败都要取消监控任务
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

        add_install_log(
            instance_id_str,
            f"✅ deploy_manager执行完成，结果: {deploy_success}",
            "info",
        )

        if not deploy_success:
            logger.error(
                f"使用 deploy_manager 部署版本 {payload.version} 到实例 {instance_id_str} 失败。"
            )
            add_install_log(instance_id_str, "❌ 阶段2/4: Git克隆MaiBot失败", "error")
            update_install_status(instance_id_str, "failed", 30, "MaiBot 部署失败")
            return

        add_install_log(
            instance_id_str, "✅ 阶段2/4: 使用Git克隆MaiBot完成", "success"
        )  # 更新进度：部署文件完成
        update_install_status(
            instance_id_str,
            "installing",
            40,
            "阶段2/4: 克隆MaiBot完成，正在验证文件完整性",
        )

        logger.info(
            f"版本 {payload.version} 已成功部署到 {install_path}。现在设置虚拟环境..."
        )  # 更新进度：开始环境配置
        update_install_status(
            instance_id_str,
            "installing",
            50,
            "阶段3/4: 创建虚拟环境 - 正在准备Python环境",
        )  # 设置虚拟环境并安装依赖
        logger.info(f"开始为实例 {instance_id_str} 在 {install_path} 设置虚拟环境...")
        add_install_log(
            instance_id_str, "🐍 阶段3/4: 创建虚拟环境 - 开始设置Python虚拟环境", "info"
        )
        update_install_status(
            instance_id_str,
            "installing",
            55,
            "阶段3/4: 创建虚拟环境 - 正在创建虚拟环境",
        )

        venv_success = await setup_virtual_environment_background(
            install_path,
            instance_id_str,  # 使用展开后的路径
        )

        if not venv_success:
            logger.error(f"为实例 {instance_id_str} 设置虚拟环境失败")
            add_install_log(instance_id_str, "❌ 阶段3/4: 虚拟环境设置失败", "error")
            update_install_status(instance_id_str, "failed", 40, "虚拟环境设置失败")
            return

        logger.info("虚拟环境设置成功。现在记录到数据库...")
        add_install_log(instance_id_str, "✅ 阶段3/4: 创建虚拟环境完成", "success")
        add_install_log(
            instance_id_str, "💾 阶段4/4: 后端记录数据库 - 开始保存实例信息", "info"
        )  # 更新进度：虚拟环境设置完成
        update_install_status(
            instance_id_str,
            "installing",
            85,
            "阶段4/4: 后端记录数据库 - 正在保存实例信息",
        )
        # 在数据库中保存实例信息
        await save_instance_to_database(payload, instance_id_str, install_path)

    except Exception as e:
        logger.error(f"后台部署任务发生异常 (实例ID: {instance_id_str}): {e}")

        # 构建详细的错误信息
        error_details = {
            "message": "部署过程中发生错误",
            "detail": str(e),
            "error_type": type(e).__name__,
            "instance_id": instance_id_str,
        }

        # 根据异常类型提供更具体的错误信息
        if "permission" in str(e).lower() or "access" in str(e).lower():
            error_details["message"] = "权限不足或文件访问被拒绝"
            error_details["suggestion"] = "请检查安装路径的写入权限，或以管理员身份运行"
        elif "network" in str(e).lower() or "connection" in str(e).lower():
            error_details["message"] = "网络连接失败"
            error_details["suggestion"] = "请检查网络连接，稍后重试"
        elif "disk" in str(e).lower() or "space" in str(e).lower():
            error_details["message"] = "磁盘空间不足"
            error_details["suggestion"] = "请释放磁盘空间后重试"

        update_install_status(
            instance_id_str,
            "failed",
            0,
            f"{error_details['message']}: {error_details['detail']}",
        )


async def save_instance_to_database(
    payload: DeployRequest, instance_id_str: str, expanded_install_path: str
):
    """
    将实例信息保存到数据库
    """
    try:  # 更新状态：开始数据库操作
        update_install_status(
            instance_id_str,
            "installing",
            87,
            "阶段4/4: 后端记录数据库 - 正在创建实例信息",
        )

        with Session(engine) as session:
            new_instance_obj = instance_manager.create_instance(
                name=payload.instance_name,
                version=payload.version,
                path=expanded_install_path,  # 使用展开后的路径
                status=InstanceStatus.STOPPED,  # 初始状态为 STOPPED
                host=payload.host,
                port=payload.port,
                token=payload.token,
                instance_id=instance_id_str,
                db_session=session,
            )

            if not new_instance_obj:
                logger.error(
                    f"通过 InstanceManager 创建实例 {payload.instance_name} (ID: {instance_id_str}) 失败，但未引发异常。"
                )
                update_install_status(instance_id_str, "failed", 82, "实例信息保存失败")
                return  # 更新状态：创建服务配置
            update_install_status(
                instance_id_str,
                "installing",
                85,
                "阶段4/4: 后端记录数据库 - 正在配置服务信息",
            )

            # 初始化服务状态
            services_status = []
            for service_config in payload.install_services:
                # 展开服务路径中的 ~ 符号（如果存在）
                service_path = service_config.path
                if service_path.startswith("~"):
                    current_dir = Path.cwd()
                    if service_path.startswith("~/") or service_path.startswith("~\\"):
                        relative_path = service_path[2:]
                        service_path = str(current_dir / relative_path)
                    else:
                        relative_path = (
                            service_path[1:] if len(service_path) > 1 else ""
                        )
                        if relative_path:
                            service_path = str(current_dir / relative_path)
                        else:
                            service_path = str(current_dir)
                    logger.info(
                        f"展开服务路径: {service_config.path} -> {service_path} (服务: {service_config.name}, 实例ID: {instance_id_str})"
                    )

                db_service = DB_Service(
                    instance_id=instance_id_str,
                    name=service_config.name,
                    path=service_path,  # 使用展开后的路径
                    status="pending",
                    port=service_config.port,
                    run_cmd=service_config.run_cmd,  # 添加 run_cmd
                )
                session.add(db_service)

                # 添加到服务状态列表
                services_status.append(
                    {
                        "name": service_config.name,
                        "status": "pending",
                        "progress": 0,
                        "message": "等待安装",
                    }
                )

            # 更新状态：提交数据库事务
            update_install_status(
                instance_id_str,
                "installing",
                90,
                "阶段4/4: 后端记录数据库 - 正在保存配置到数据库",
            )

            session.commit()
            add_install_log(
                instance_id_str,
                "✅ 阶段4/4: 后端记录数据库 - 数据库保存成功",
                "success",
            )

            # 更新状态：最终完成
            update_install_status(
                instance_id_str,
                "installing",
                95,
                "阶段4/4: 后端记录数据库 - 正在完成最后配置",
            )
            add_install_log(
                instance_id_str, "🔧 阶段4/4: 后端记录数据库 - 完成最后配置", "info"
            )
            # 更新进度：完成部署
            update_install_status(
                instance_id_str,
                "completed",
                100,
                "部署完成！所有4个阶段已完成",
                services_status,
            )
            add_install_log(
                instance_id_str,
                "🎉 部署完成！实例已成功创建 - 所有4个阶段已完成",
                "success",
            )
            add_install_log(
                instance_id_str, f"📍 实例路径: {expanded_install_path}", "info"
            )

            # 安排延迟清理缓存
            asyncio.create_task(cleanup_install_status_cache(instance_id_str))

            logger.info(
                f"实例 {payload.instance_name} (ID: {instance_id_str}) 及关联服务已成功记录到数据库。"
            )

    except IntegrityError as e:
        logger.error(f"部署实例 {payload.instance_name} 时发生数据库完整性错误: {e}")
        update_install_status(instance_id_str, "failed", 80, f"数据库错误: {e}")
    except Exception as e:
        logger.error(f"部署实例 {payload.instance_name} 期间发生意外错误: {e}")
        update_install_status(instance_id_str, "failed", 80, f"内部错误: {e}")


async def setup_virtual_environment_background(
    install_path: str, instance_id: str
) -> bool:
    """
    在后台线程中设置虚拟环境并安装依赖的异步版本

    Args:
        install_path: 安装目录路径
        instance_id: 实例ID

    Returns:
        bool: 设置成功返回True，失败返回False
    """
    logger.info(f"开始为实例 {instance_id} 在 {install_path} 设置虚拟环境...")

    # 更新状态：开始设置虚拟环境
    update_install_status(instance_id, "installing", 45, "正在创建虚拟环境...")

    try:
        # 将工作目录切换到安装目录
        install_dir = Path(install_path).resolve()
        if not install_dir.exists():
            logger.error(f"安装目录 {install_dir} 不存在 (实例ID: {instance_id})")
            update_install_status(instance_id, "failed", 45, "安装目录不存在")
            return False

        # 更新状态：验证安装目录
        update_install_status(
            instance_id, "installing", 47, "安装目录验证完成，正在初始化虚拟环境..."
        )

        logger.info(f"切换工作目录到: {install_dir} (实例ID: {instance_id})")

        # 创建虚拟环境目录路径
        venv_path = install_dir / "venv"  # 更新状态：开始创建虚拟环境
        update_install_status(
            instance_id,
            "installing",
            50,
            "阶段3/4: 创建虚拟环境 - 正在创建Python虚拟环境",
        )
        add_install_log(
            instance_id, "🐍 阶段3/4: 创建虚拟环境 - 开始创建Python虚拟环境", "info"
        )

        # 1. 创建虚拟环境
        logger.info(f"创建虚拟环境 {venv_path} (实例ID: {instance_id})")

        # 获取正确的Python解释器路径
        try:
            python_executable = get_python_executable()
        except RuntimeError as e:
            logger.error(f"获取Python解释器失败 (实例ID: {instance_id}): {e}")
            update_install_status(
                instance_id, "failed", 50, f"Python解释器获取失败: {str(e)}"
            )
            return False

        logger.info(f"使用Python解释器: {python_executable} (实例ID: {instance_id})")
        create_venv_cmd = [python_executable, "-m", "venv", str(venv_path)]

        # 在线程池中执行虚拟环境创建，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                create_venv_cmd,
                cwd=str(install_dir),
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ),
        )

        if result.returncode != 0:
            logger.error(f"创建虚拟环境失败 (实例ID: {instance_id}): {result.stderr}")
            update_install_status(instance_id, "failed", 45, "虚拟环境创建失败")
            return False

        logger.info(f"虚拟环境创建成功 (实例ID: {instance_id})")
        add_install_log(instance_id, "✅ 阶段3/4: Python虚拟环境创建成功", "success")

        # 更新状态：虚拟环境创建完成
        update_install_status(
            instance_id,
            "installing",
            55,
            "阶段3/4: 创建虚拟环境 - 虚拟环境创建完成，检查依赖文件",
        )
        add_install_log(instance_id, "📋 阶段3/4: 创建虚拟环境 - 检查依赖文件", "info")

        # 2. 检查requirements.txt是否存在
        requirements_file = install_dir / "requirements.txt"
        if not requirements_file.exists():
            logger.warning(
                f"requirements.txt 文件不存在于 {install_dir} (实例ID: {instance_id})"
            )
            logger.info(f"跳过依赖安装步骤 (实例ID: {instance_id})")
            update_install_status(
                instance_id, "installing", 75, "未找到依赖文件，跳过依赖安装"
            )
            return True

        # 更新状态：开始安装依赖
        update_install_status(
            instance_id, "installing", 58, "阶段3/4: 安装依赖包 - 正在准备依赖安装"
        )
        add_install_log(
            instance_id, "🚀 阶段3/4: 安装依赖包 - 准备开始依赖安装", "info"
        )

        # 3. 安装依赖
        logger.info(f"开始安装依赖 (实例ID: {instance_id})")
        add_install_log(
            instance_id, "📋 阶段3/4: 安装依赖包 - 开始分析依赖列表", "info"
        )

        # 更新状态：正在升级pip
        update_install_status(
            instance_id, "installing", 60, "阶段3/4: 安装依赖包 - 正在升级pip"
        )
        add_install_log(instance_id, "🔧 阶段3/4: 安装依赖包 - 开始升级pip工具", "info")

        # 在Windows系统中，虚拟环境的Python和pip路径
        if os.name == "nt":
            python_executable = venv_path / "Scripts" / "python.exe"
            pip_executable = venv_path / "Scripts" / "pip.exe"
        else:
            python_executable = venv_path / "bin" / "python"
            pip_executable = venv_path / "bin" / "pip"  # 升级pip
        logger.info(f"升级pip (实例ID: {instance_id})")
        upgrade_pip_cmd = [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "-i",
            "https://mirrors.aliyun.com/pypi/simple/",
            "--trusted-host",
            "mirrors.aliyun.com",
        ]

        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                upgrade_pip_cmd,
                cwd=str(install_dir),
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ),
        )

        if result.returncode != 0:
            logger.warning(f"升级pip失败 (实例ID: {instance_id}): {result.stderr}")
            add_install_log(instance_id, "⚠️ pip升级失败，继续安装依赖", "warning")
            update_install_status(
                instance_id, "installing", 65, "pip升级失败，继续安装依赖..."
            )
        else:
            logger.info(f"pip升级成功 (实例ID: {instance_id})")
            add_install_log(
                instance_id, "✅ 阶段3/4: 安装依赖包 - pip升级成功", "success"
            )
            update_install_status(
                instance_id,
                "installing",
                65,
                "阶段3/4: 安装依赖包 - pip升级成功，正在安装依赖",
            )

        # 更新状态：开始安装依赖包
        update_install_status(
            instance_id, "installing", 68, "阶段3/4: 安装依赖包 - 正在安装Python依赖包"
        )
        add_install_log(
            instance_id, "📦 阶段3/4: 安装依赖包 - 开始安装Python依赖包", "info"
        )

        # 安装requirements.txt中的依赖
        install_deps_cmd = [
            str(pip_executable),
            "install",
            "-r",
            str(requirements_file),
            "-i",
            "https://mirrors.aliyun.com/pypi/simple/",
            "--trusted-host",
            "mirrors.aliyun.com",
        ]

        logger.info(
            f"执行依赖安装命令: {' '.join(install_deps_cmd)} (实例ID: {instance_id})"
        )
        add_install_log(
            instance_id, "🔧 执行安装命令: pip install -r requirements.txt", "info"
        )

        # 更新状态：正在执行依赖安装
        update_install_status(instance_id, "installing", 70, "正在执行依赖安装命令...")
        add_install_log(
            instance_id,
            "💡 正在安装Python依赖包，这是最耗时的步骤，可能需要5-15分钟",
            "info",
        )

        # 创建一个异步函数来执行pip安装并提供实时反馈
        async def install_dependencies_with_feedback():
            try:
                # 先更新状态表示开始安装
                update_install_status(
                    instance_id,
                    "installing",
                    71,
                    "阶段3/4: 安装依赖包 - 正在下载和安装依赖包",
                )
                add_install_log(
                    instance_id, "⬇️ 阶段3/4: 安装依赖包 - 开始下载依赖包", "info"
                )
                add_install_log(
                    instance_id, "🔄 阶段3/4: 安装依赖包 - pip安装进程启动中", "info"
                )

                # 执行pip安装命令
                process = await asyncio.create_subprocess_exec(
                    *install_deps_cmd,
                    cwd=str(install_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )

                add_install_log(
                    instance_id, "✅ 阶段3/4: 安装依赖包 - pip安装进程已启动", "success"
                )
                add_install_log(
                    instance_id,
                    "📚 阶段3/4: 安装依赖包 - 正在分析requirements.txt文件",
                    "info",
                )

                # 启动进度跟踪任务
                progress_task = asyncio.create_task(
                    track_pip_installation_progress(instance_id, process, 71)
                )

                try:
                    # 等待进程完成，最多等待15分钟
                    add_install_log(
                        instance_id, "⏳ 依赖安装进行中，请耐心等待...", "info"
                    )
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=900
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    logger.error(f"依赖安装超时 (实例ID: {instance_id})")
                    add_install_log(instance_id, "❌ 依赖安装超时", "error")
                    update_install_status(
                        instance_id, "failed", 70, "依赖安装超时，请检查网络连接并重试"
                    )
                    return False
                finally:
                    # 取消进度更新任务
                    progress_task.cancel()
                    try:
                        await progress_task
                    except asyncio.CancelledError:
                        pass

                # 检查安装结果
                if process.returncode != 0:
                    error_msg = (
                        stderr.decode("utf-8", errors="ignore")
                        if stderr
                        else "未知错误"
                    )
                    logger.error(f"依赖安装失败 (实例ID: {instance_id}): {error_msg}")
                    add_install_log(
                        instance_id, f"❌ 依赖安装失败: {error_msg[:100]}", "error"
                    )
                    # 根据错误类型提供更具体的错误信息
                    if (
                        "timeout" in error_msg.lower()
                        or "timed out" in error_msg.lower()
                    ):
                        update_install_status(
                            instance_id,
                            "failed",
                            70,
                            "依赖安装超时，请检查网络连接并重试",
                        )
                    elif (
                        "permission" in error_msg.lower()
                        or "access" in error_msg.lower()
                    ):
                        update_install_status(
                            instance_id, "failed", 70, "权限不足，请以管理员身份运行"
                        )
                    elif "space" in error_msg.lower() or "disk" in error_msg.lower():
                        update_install_status(
                            instance_id, "failed", 70, "磁盘空间不足，请清理磁盘空间"
                        )
                    else:
                        update_install_status(
                            instance_id,
                            "failed",
                            70,
                            f"依赖安装失败：{error_msg[:100]}",
                        )
                    return False
                else:
                    add_install_log(
                        instance_id,
                        "✅ 阶段3/4: 安装依赖包 - 依赖包安装完成",
                        "success",
                    )
                    add_install_log(
                        instance_id,
                        "🎯 阶段3/4: 安装依赖包 - 依赖解析和安装成功",
                        "success",
                    )

                return True

            except Exception as e:
                logger.error(f"依赖安装过程中发生异常 (实例ID: {instance_id}): {e}")
                add_install_log(instance_id, f"❌ 安装过程异常: {str(e)}", "error")
                update_install_status(
                    instance_id, "failed", 70, f"安装过程异常：{str(e)}"
                )
                return False

        # 执行依赖安装
        install_success = await install_dependencies_with_feedback()

        if not install_success:
            return False  # 更新状态：依赖安装成功
        update_install_status(
            instance_id,
            "installing",
            73,
            "阶段3/4: 安装依赖包 - 依赖安装成功，正在验证安装结果",
        )
        add_install_log(
            instance_id, "✅ 阶段3/4: 安装依赖包 - 所有依赖包安装完成", "success"
        )

        logger.info(f"依赖安装成功 (实例ID: {instance_id})")
        logger.info(f"虚拟环境设置完成 (实例ID: {instance_id})")
        add_install_log(
            instance_id, "🎉 阶段3/4: 创建虚拟环境 - 虚拟环境配置完成", "success"
        )

        # 更新状态：虚拟环境设置完成
        update_install_status(
            instance_id, "installing", 75, "阶段3/4: 创建虚拟环境完成"
        )

        return True

    except Exception as e:
        logger.error(f"设置虚拟环境时发生异常 (实例ID: {instance_id}): {e}")
        update_install_status(instance_id, "failed", 45, f"虚拟环境设置异常: {str(e)}")
        return False


def generate_venv_command(base_command: str, working_directory: str) -> str:
    """
    生成带虚拟环境激活的启动命令。

    Args:
        base_command: 基础运行命令（如 "python bot.py"）
        working_directory: 工作目录路径

    Returns:
        str: 带虚拟环境激活的完整命令
    """
    working_dir = Path(working_directory).resolve()
    venv_path = working_dir / "venv"

    # 检查虚拟环境是否存在
    if not venv_path.exists():
        logger.warning(f"虚拟环境不存在于 {venv_path}，将使用原始命令")
        return base_command

    # 检查虚拟环境是否为目录
    if not venv_path.is_dir():
        logger.warning(f"虚拟环境路径 {venv_path} 不是目录，将使用原始命令")
        return base_command

    # 根据操作系统生成不同的激活命令
    if os.name == "nt":  # Windows
        # 检查虚拟环境的Python可执行文件是否存在且可执行
        venv_python = venv_path / "Scripts" / "python.exe"
        if venv_python.exists() and venv_python.is_file():
            try:
                # 测试Python可执行文件是否可用
                test_result = subprocess.run(
                    [str(venv_python), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if test_result.returncode != 0:
                    logger.warning(
                        f"虚拟环境Python可执行文件 {venv_python} 无法正常运行，将使用原始命令"
                    )
                    return base_command
            except (
                subprocess.TimeoutExpired,
                subprocess.SubprocessError,
                OSError,
            ) as e:
                logger.warning(
                    f"测试虚拟环境Python可执行文件 {venv_python} 时出错: {e}，将使用原始命令"
                )
                return base_command

            # 直接使用虚拟环境中的Python可执行文件
            # 替换命令中的 "python" 为虚拟环境中的python路径，并添加引号
            if base_command.startswith("python "):
                venv_command = (
                    f'"{str(venv_python)}"{base_command[6:]}'  # 去掉 "python"，添加引号
                )
            elif base_command == "python":
                venv_command = f'"{str(venv_python)}"'  # 添加引号
            else:
                # 如果命令不是以python开头，使用激活脚本的方式
                activate_script = venv_path / "Scripts" / "activate.bat"
                if activate_script.exists():
                    venv_command = f'cmd /c "{activate_script} && {base_command}"'
                else:
                    logger.warning(
                        f"虚拟环境激活脚本 {activate_script} 不存在，将使用原始命令"
                    )
                    return base_command
        else:
            logger.warning(
                f"虚拟环境Python可执行文件不存在或不是文件: {venv_python}，将使用原始命令"
            )
            return base_command
    else:  # Linux/Unix
        # 检查虚拟环境的Python可执行文件是否存在且可执行
        venv_python = venv_path / "bin" / "python"
        if venv_python.exists() and venv_python.is_file():
            try:
                # 测试Python可执行文件是否可用
                test_result = subprocess.run(
                    [str(venv_python), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if test_result.returncode != 0:
                    logger.warning(
                        f"虚拟环境Python可执行文件 {venv_python} 无法正常运行，将使用原始命令"
                    )
                    return base_command
            except (
                subprocess.TimeoutExpired,
                subprocess.SubprocessError,
                OSError,
            ) as e:
                logger.warning(
                    f"测试虚拟环境Python可执行文件 {venv_python} 时出错: {e}，将使用原始命令"
                )
                return base_command

            # 直接使用虚拟环境中的Python可执行文件
            if base_command.startswith("python "):
                venv_command = str(venv_python) + base_command[6:]  # 去掉 "python"
            elif base_command == "python":
                venv_command = str(venv_python)
            else:
                # 如果命令不是以python开头，使用激活脚本的方式
                activate_script = venv_path / "bin" / "activate"
                if activate_script.exists():
                    venv_command = (
                        f'bash -c "source {activate_script} && {base_command}"'
                    )
                else:
                    logger.warning(
                        f"虚拟环境激活脚本 {activate_script} 不存在，将使用原始命令"
                    )
                    return base_command
        else:
            logger.warning(
                f"虚拟环境Python可执行文件不存在或不是文件: {venv_python}，将使用原始命令"
            )
            return base_command

    logger.info(f"生成虚拟环境命令: {base_command} -> {venv_command}")
    return venv_command


# 添加一个专门的依赖安装进度跟踪器
async def track_pip_installation_progress(
    instance_id: str, process, base_progress: int = 70
):
    """
    跟踪pip安装过程并提供实时进度更新

    Args:
        instance_id: 实例ID
        process: 异步进程对象
        base_progress: 基础进度值
    """
    try:
        progress = base_progress
        last_update = time.time()
        log_last_update = time.time()
        log_interval = 10  # 每10秒输出一次日志
        status_index = 0
        start_time = time.time()

        status_messages = [
            ("正在解析依赖关系...", "🔍 解析依赖关系中"),
            ("正在下载依赖包...", "⬇️ 下载依赖包中"),
            ("正在安装Python包...", "📦 安装Python包中"),
            ("正在编译扩展模块...", "🔨 编译扩展模块中"),
            ("正在配置包依赖...", "⚙️ 配置包依赖中"),
        ]

        # 立即输出第一条日志
        if status_messages:
            _, first_log_msg = status_messages[0]
            add_install_log(instance_id, first_log_msg, "info")
            status_index = 1

        while process.returncode is None:
            current_time = time.time()

            # 每3秒更新一次进度状态
            if current_time - last_update >= 3:
                if progress < base_progress + 2:
                    progress += 1
                status_msg_index = min(status_index - 1, len(status_messages) - 1)
                if status_msg_index >= 0:
                    status_msg, _ = status_messages[status_msg_index]
                    update_install_status(
                        instance_id, "installing", progress, status_msg
                    )
                last_update = current_time

            # 每10秒输出一次详细日志
            if current_time - log_last_update >= log_interval:
                if status_index < len(status_messages):
                    _, log_msg = status_messages[status_index]
                    add_install_log(instance_id, log_msg, "info")
                    status_index += 1
                else:
                    # 如果状态消息用完了，显示通用的等待消息
                    elapsed_minutes = int((current_time - start_time) / 60)
                    if elapsed_minutes > 0:
                        add_install_log(
                            instance_id,
                            f"⏳ 依赖安装继续进行中... 已用时{elapsed_minutes}分钟",
                            "info",
                        )
                    else:
                        elapsed_seconds = int(current_time - start_time)
                        add_install_log(
                            instance_id,
                            f"⏳ 依赖安装进行中... 已用时{elapsed_seconds}秒",
                            "info",
                        )

                log_last_update = current_time

            await asyncio.sleep(1)

    except asyncio.CancelledError:
        # 进程完成时正常取消
        pass
    except Exception as e:
        logger.error(f"跟踪安装进度时出错 (实例ID: {instance_id}): {e}")
        add_install_log(instance_id, f"⚠️ 进度跟踪异常: {str(e)}", "warning")


async def cleanup_install_status_cache(instance_id: str, delay_seconds: int = 30):
    """
    延迟清理安装状态缓存，给前端足够时间读取完成状态

    Args:
        instance_id: 实例ID
        delay_seconds: 延迟时间（秒）
    """
    await asyncio.sleep(delay_seconds)

    with cache_lock:
        if instance_id in install_status_cache:
            status = install_status_cache[instance_id].get("status")
            if status in ["completed", "failed"]:
                del install_status_cache[instance_id]
                logger.info(f"已清理实例 {instance_id} 的安装状态缓存")
