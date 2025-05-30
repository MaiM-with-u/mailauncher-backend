from fastapi import APIRouter
from pydantic import BaseModel
import datetime
import psutil  # 添加 psutil 导入
import platform  # 添加 platform 导入
import sys  # 添加 sys 导入
from src.utils.logger import get_module_logger  # 添加 logger 导入

router = APIRouter()
logger = get_module_logger("系统API")  # 初始化 logger


def get_cpu_name():
    """
    获取准确的CPU名称，支持Windows、Linux和macOS
    """
    if platform.system() == "Windows":
        try:
            import wmi

            c = wmi.WMI()
            for processor in c.Win32_Processor():
                return processor.Name
        except ImportError:
            logger.warning(
                "请安装 pywin32 和 wmi 库以获取 Windows CPU 名称：pip install pywin32 wmi"
            )
            return "无法获取 CPU 名称 (Windows)"
    elif platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":")[1].strip()
        except FileNotFoundError:
            return "无法获取 CPU 名称 (/proc/cpuinfo 未找到)"
    elif platform.system() == "Darwin":  # macOS
        try:
            import subprocess

            return (
                subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"])
                .decode()
                .strip()
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "无法获取 CPU 名称 (sysctl 命令出错或未找到)"
    else:
        return "不支持的操作系统"


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


class NetworkInterface(BaseModel):
    name: str
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errin: int
    errout: int
    dropin: int
    dropout: int


class NetworkStats(BaseModel):
    interfaces: list[NetworkInterface]
    total_bytes_sent: int
    total_bytes_recv: int
    total_packets_sent: int
    total_packets_recv: int


class SystemMetricsData(BaseModel):
    system_info: SystemInfo
    python_version: str
    cpu_usage_percent: float
    memory_usage: MemoryUsage
    disk_usage_root: DiskUsage
    network_stats: NetworkStats


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
    cpu_name = get_cpu_name()  # 使用新的CPU名称获取函数
    system_info = SystemInfo(
        system=uname.system,
        release=uname.release,
        version=uname.version,
        machine=uname.machine,
        processor=cpu_name,  # 使用准确的CPU名称
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
    disk = psutil.disk_usage("/")
    disk_usage_root = DiskUsage(
        total_gb=round(disk.total / (1024 * 1024 * 1024), 2),
        used_gb=round(disk.used / (1024 * 1024 * 1024), 2),
        free_gb=round(disk.free / (1024 * 1024 * 1024), 2),
        percent=disk.percent,
    )

    # Network Statistics
    net_io = psutil.net_io_counters(pernic=True)
    network_interfaces = []
    total_bytes_sent = 0
    total_bytes_recv = 0
    total_packets_sent = 0
    total_packets_recv = 0

    for interface_name, stats in net_io.items():
        # 排除回环接口和虚拟接口
        if interface_name != "lo" and not interface_name.startswith("vir"):
            network_interfaces.append(
                NetworkInterface(
                    name=interface_name,
                    bytes_sent=stats.bytes_sent,
                    bytes_recv=stats.bytes_recv,
                    packets_sent=stats.packets_sent,
                    packets_recv=stats.packets_recv,
                    errin=stats.errin,
                    errout=stats.errout,
                    dropin=stats.dropin,
                    dropout=stats.dropout,
                )
            )
            total_bytes_sent += stats.bytes_sent
            total_bytes_recv += stats.bytes_recv
            total_packets_sent += stats.packets_sent
            total_packets_recv += stats.packets_recv

    network_stats = NetworkStats(
        interfaces=network_interfaces,
        total_bytes_sent=total_bytes_sent,
        total_bytes_recv=total_bytes_recv,
        total_packets_sent=total_packets_sent,
        total_packets_recv=total_packets_recv,
    )

    logger.debug(
        f"系统指标数据: cpu={cpu_usage_percent}%, mem={memory_usage.percent}%, disk={disk_usage_root.percent}%, network_interfaces={len(network_interfaces)}"
    )  # 添加日志
    return SystemMetricsResponse(
        status="success",
        data=SystemMetricsData(
            system_info=system_info,
            python_version=python_version,
            cpu_usage_percent=cpu_usage_percent,
            memory_usage=memory_usage,
            disk_usage_root=disk_usage_root,
            network_stats=network_stats,
        ),
    )
