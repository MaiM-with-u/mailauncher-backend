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
import subprocess
import sys
import os
import threading
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
            install_status_cache[instance_id] = {}

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
                "last_updated": datetime.now().isoformat(),
            },
        )


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

    # 初始化安装状态缓存
    update_install_status(instance_id_str, "preparing", 0, "正在准备部署...")

    with Session(engine) as session:
        existing_instance_check = session.exec(
            select(Instances).where(Instances.instance_id == instance_id_str)
        ).first()
        if existing_instance_check:
            logger.warning(
                f"实例ID {instance_id_str} ({payload.instance_name}) 已存在。"
            )
            update_install_status(instance_id_str, "failed", 0, "实例已存在")
            raise HTTPException(
                status_code=409,
                detail=f"实例 '{payload.instance_name}' (ID: {instance_id_str}) 已存在。",
            )

        # 更新进度：开始部署
        update_install_status(
            instance_id_str, "installing", 10, "正在下载并部署 MaiBot..."
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
            update_install_status(instance_id_str, "failed", 0, "MaiBot 部署失败")
            # 注意：deploy_version 内部应该已经处理了部分创建文件的清理工作
            raise HTTPException(
                status_code=500,
                detail=f"部署 MaiBot 版本 {payload.version} 失败。请查看日志了解详情。",
            )

        logger.info(
            f"版本 {payload.version} 已成功部署到 {payload.install_path}。现在设置虚拟环境..."
        )

        # 更新进度：部署完成，开始设置环境
        update_install_status(
            instance_id_str, "installing", 40, "MaiBot 部署完成，正在设置虚拟环境..."
        )

        # 设置虚拟环境并安装依赖
        venv_success = await setup_virtual_environment(
            payload.install_path, instance_id_str
        )
        if not venv_success:
            logger.error(f"为实例 {instance_id_str} 设置虚拟环境失败")
            update_install_status(instance_id_str, "failed", 40, "虚拟环境设置失败")
            raise HTTPException(
                status_code=500,
                detail="设置虚拟环境失败。请查看日志了解详情。",
            )

        logger.info("虚拟环境设置成功。现在记录到数据库...")

        # 更新进度：虚拟环境设置完成
        update_install_status(
            instance_id_str, "installing", 80, "虚拟环境设置完成，正在保存实例信息..."
        )

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
                update_install_status(instance_id_str, "failed", 80, "实例信息保存失败")
                raise HTTPException(
                    status_code=500, detail="实例信息保存失败，请查看日志了解详情。"
                )

            # 初始化服务状态
            services_status = []
            for service_config in payload.install_services:
                db_service = Services(
                    instance_id=instance_id_str,
                    name=service_config.name,
                    path=service_config.path,
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

            session.commit()

            # 更新进度：完成部署
            update_install_status(
                instance_id_str, "completed", 100, "部署完成！", services_status
            )

        except IntegrityError as e:
            session.rollback()
            logger.error(
                f"部署实例 {payload.instance_name} 时发生数据库完整性错误: {e}"
            )
            update_install_status(instance_id_str, "failed", 80, f"数据库错误: {e}")
            raise HTTPException(status_code=409, detail=f"保存部署信息时发生冲突: {e}")
        except Exception as e:
            session.rollback()
            logger.error(f"部署实例 {payload.instance_name} 期间发生意外错误: {e}")
            update_install_status(instance_id_str, "failed", 80, f"内部错误: {e}")
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

    # 从缓存获取安装状态
    cached_status = get_cached_install_status(instance_id)

    # 如果状态是 not_found，返回适当的错误
    if cached_status["status"] == "not_found":
        raise HTTPException(
            status_code=404, detail=f"实例 {instance_id} 不存在或尚未开始安装"
        )

    # 转换服务状态为 Pydantic 模型
    services_status = []
    for service_data in cached_status.get("services_install_status", []):
        services_status.append(
            ServiceInstallStatus(
                name=service_data["name"],
                status=service_data["status"],
                progress=service_data["progress"],
                message=service_data["message"],
            )
        )

    return InstallStatusResponse(
        status=cached_status["status"],
        progress=cached_status["progress"],
        message=cached_status["message"],
        services_install_status=services_status,
    )


async def setup_virtual_environment(install_path: str, instance_id: str) -> bool:
    """
    在指定的安装目录中设置虚拟环境并安装依赖。

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

        logger.info(f"切换工作目录到: {install_dir} (实例ID: {instance_id})")

        # 创建虚拟环境目录路径
        venv_path = install_dir / "venv"

        # 1. 创建虚拟环境
        logger.info(f"创建虚拟环境 {venv_path} (实例ID: {instance_id})")
        create_venv_cmd = [sys.executable, "-m", "venv", str(venv_path)]

        result = subprocess.run(
            create_venv_cmd,
            cwd=str(install_dir),
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        if result.returncode != 0:
            logger.error(f"创建虚拟环境失败 (实例ID: {instance_id}): {result.stderr}")
            update_install_status(instance_id, "failed", 45, "虚拟环境创建失败")
            return False

        logger.info(f"虚拟环境创建成功 (实例ID: {instance_id})")

        # 更新状态：虚拟环境创建完成
        update_install_status(
            instance_id, "installing", 55, "虚拟环境创建完成，检查依赖文件..."
        )

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
        update_install_status(instance_id, "installing", 60, "正在升级pip...")

        # 3. 安装依赖
        logger.info(f"开始安装依赖 (实例ID: {instance_id})")

        # 在Windows系统中，虚拟环境的Python和pip路径
        if os.name == "nt":
            python_executable = venv_path / "Scripts" / "python.exe"
            pip_executable = venv_path / "Scripts" / "pip.exe"
        else:
            python_executable = venv_path / "bin" / "python"
            pip_executable = venv_path / "bin" / "pip"

        # 升级pip
        logger.info(f"升级pip (实例ID: {instance_id})")
        upgrade_pip_cmd = [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
        ]

        result = subprocess.run(
            upgrade_pip_cmd,
            cwd=str(install_dir),
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        if result.returncode != 0:
            logger.warning(f"升级pip失败 (实例ID: {instance_id}): {result.stderr}")
            update_install_status(
                instance_id, "installing", 65, "pip升级失败，继续安装依赖..."
            )
        else:
            logger.info(f"pip升级成功 (实例ID: {instance_id})")
            update_install_status(
                instance_id, "installing", 65, "pip升级成功，正在安装依赖..."
            )

        # 安装requirements.txt中的依赖
        install_deps_cmd = [
            str(pip_executable),
            "install",
            "-r",
            str(requirements_file),
        ]

        logger.info(
            f"执行依赖安装命令: {' '.join(install_deps_cmd)} (实例ID: {instance_id})"
        )

        result = subprocess.run(
            install_deps_cmd,
            cwd=str(install_dir),
            capture_output=True,
            text=True,
            timeout=600,  # 依赖安装可能需要更长时间
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        if result.returncode != 0:
            logger.error(f"依赖安装失败 (实例ID: {instance_id}): {result.stderr}")
            update_install_status(instance_id, "failed", 65, "依赖安装失败")
            return False

        logger.info(f"依赖安装成功 (实例ID: {instance_id})")
        logger.info(f"虚拟环境设置完成 (实例ID: {instance_id})")

        # 更新状态：虚拟环境设置完成
        update_install_status(instance_id, "installing", 75, "依赖安装完成")

        return True

    except subprocess.TimeoutExpired:
        logger.error(f"虚拟环境设置超时 (实例ID: {instance_id})")
        update_install_status(instance_id, "failed", 45, "虚拟环境设置超时")
        return False
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

    # 根据操作系统生成不同的激活命令
    if os.name == "nt":  # Windows
        # 检查虚拟环境的Python可执行文件是否存在
        venv_python = venv_path / "Scripts" / "python.exe"
        if venv_python.exists():
            # 直接使用虚拟环境中的Python可执行文件
            # 替换命令中的 "python" 为虚拟环境中的python路径
            if base_command.startswith("python "):
                venv_command = str(venv_python) + base_command[6:]  # 去掉 "python"
            elif base_command == "python":
                venv_command = str(venv_python)
            else:
                # 如果命令不是以python开头，使用激活脚本的方式
                activate_script = venv_path / "Scripts" / "activate.bat"
                venv_command = f'cmd /c "{activate_script} && {base_command}"'
        else:
            logger.warning(
                f"虚拟环境Python可执行文件不存在于 {venv_python}，将使用原始命令"
            )
            return base_command
    else:  # Linux/Unix
        # 检查虚拟环境的Python可执行文件是否存在
        venv_python = venv_path / "bin" / "python"
        if venv_python.exists():
            # 直接使用虚拟环境中的Python可执行文件
            if base_command.startswith("python "):
                venv_command = str(venv_python) + base_command[6:]  # 去掉 "python"
            elif base_command == "python":
                venv_command = str(venv_python)
            else:
                # 如果命令不是以python开头，使用激活脚本的方式
                activate_script = venv_path / "bin" / "activate"
                venv_command = f'bash -c "source {activate_script} && {base_command}"'
        else:
            logger.warning(
                f"虚拟环境Python可执行文件不存在于 {venv_python}，将使用原始命令"
            )
            return base_command

    logger.info(f"生成虚拟环境命令: {base_command} -> {venv_command}")
    return venv_command
