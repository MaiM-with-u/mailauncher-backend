from fastapi import APIRouter
from pydantic import BaseModel
import datetime
import psutil  # 添加 psutil 导入
import platform  # 添加 platform 导入
import sys  # 添加 sys 导入
from src.utils.logger import get_module_logger  # 添加 logger 导入

router = APIRouter()
logger = get_module_logger("系统API")  # 初始化 logger

class HealthCheckResponse(BaseModel):
    status: str
    time: str

# Pydantic Models for System Metrics
class SystemInfo(BaseModel):
    system: str
    release: str
    version: str
    machine: str
    processor: str

class MemoryUsage(BaseModel):
    total_mb: float
    available_mb: float
    percent: float
    used_mb: float
    free_mb: float

class DiskUsage(BaseModel):
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float

class SystemMetricsData(BaseModel):
    system_info: SystemInfo
    python_version: str
    cpu_usage_percent: float
    memory_usage: MemoryUsage
    disk_usage_root: DiskUsage

class SystemMetricsResponse(BaseModel):
    status: str
    data: SystemMetricsData

@router.get("/system/health", response_model=HealthCheckResponse)
async def health_check():
    """
    检查后端服务的健康状态。
    """
    logger.info("收到健康检查请求")  # 添加日志
    current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return HealthCheckResponse(status="success", time=current_time)

@router.get("/system/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics():
    """
    获取系统性能指标，如 CPU、内存使用率等。
    """
    logger.info("收到获取系统性能指标请求")  # 添加日志
    # System Info
    uname = platform.uname()
    system_info = SystemInfo(
        system=uname.system,
        release=uname.release,
        version=uname.version,
        machine=uname.machine,
        processor=uname.processor if hasattr(uname, 'processor') else 'N/A'  # uname.processor might not be available on all systems
    )

    # Python Version
    python_version = sys.version

    # CPU Usage
    cpu_usage_percent = psutil.cpu_percent(interval=1)

    # Memory Usage
    mem = psutil.virtual_memory()
    memory_usage = MemoryUsage(
        total_mb=round(mem.total / (1024 * 1024), 2),
        available_mb=round(mem.available / (1024 * 1024), 2),
        percent=mem.percent,
        used_mb=round(mem.used / (1024 * 1024), 2),
        free_mb=round(mem.free / (1024 * 1024), 2),
    )

    # Disk Usage (Root Partition)
    disk = psutil.disk_usage('/')
    disk_usage_root = DiskUsage(
        total_gb=round(disk.total / (1024 * 1024 * 1024), 2),
        used_gb=round(disk.used / (1024 * 1024 * 1024), 2),
        free_gb=round(disk.free / (1024 * 1024 * 1024), 2),
        percent=disk.percent,
    )

    logger.debug(f"系统指标数据: cpu={cpu_usage_percent}%, mem={memory_usage.percent}%, disk={disk_usage_root.percent}%")  # 添加日志
    return SystemMetricsResponse(
        status="success",
        data=SystemMetricsData(
            system_info=system_info,
            python_version=python_version,
            cpu_usage_percent=cpu_usage_percent,
            memory_usage=memory_usage,
            disk_usage_root=disk_usage_root,
        ),
    )
