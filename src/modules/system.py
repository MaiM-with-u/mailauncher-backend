from fastapi import APIRouter
from pydantic import BaseModel
import datetime
import psutil  # 添加 psutil 导入
import platform  # 添加 platform 导入
import sys  # 添加 sys 导入
from src.utils.logger import get_module_logger  # 添加 logger 导入
from pathlib import Path  # 添加 Path 导入
import re  # 添加正则表达式导入

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


def get_current_version():
    """
    获取当前后端版本信息
    """
    try:
        version_file = Path(__file__).parent.parent.parent / "version_info.txt"
        if version_file.exists():
            content = version_file.read_text(encoding='utf-8')
            # 从 version_info.txt 提取版本号
            # 查找 filevers=(0, 1, 0, 1) 格式
            filevers_match = re.search(r'filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)', content)
            if filevers_match:
                major, minor, patch, build = filevers_match.groups()
                if build == '1':
                    # 如果 build 为 1，表示预览版
                    return f"{major}.{minor}.{patch}-Preview.{build}"
                else:
                    return f"{major}.{minor}.{patch}"
        
        # 如果没有找到版本文件或格式不匹配，返回默认版本
        return "0.1.0-Preview.2"
    except Exception as e:
        logger.error(f"获取版本信息时出错: {e}")
        return "0.1.0-Preview.2"


def convert_version_to_number(version_string):
    """
    将版本字符串转换为内部数字格式
    例如: "0.1.0-Preview.3" -> 103
    """
    try:
        # 移除预览版标识并提取数字
        version_clean = re.sub(r'-Preview\.(\d+)', r'.\1', version_string)
        parts = version_clean.split('.')
        
        if len(parts) >= 3:
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2])
            build = int(parts[3]) if len(parts) > 3 else 0
            
            # 转换为内部数字: major*1000 + minor*100 + patch*10 + build
            return major * 1000 + minor * 100 + patch * 10 + build
        
        return 0
    except Exception as e:
        logger.error(f"版本转换错误: {e}")
        return 0


# 添加版本相关的 Pydantic 模型
class VersionInfo(BaseModel):
    version: str
    internal_version: int
    release_date: str
    release_notes: str


class CurrentVersionResponse(BaseModel):
    status: str
    data: VersionInfo


class VersionCheckResponse(BaseModel):
    status: str
    data: dict


class VersionHistoryResponse(BaseModel):
    status: str
    data: list[VersionInfo]


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


@router.get("/version/current", response_model=CurrentVersionResponse)
async def get_current_version_info():
    """
    获取当前后端版本信息
    """
    logger.info("收到获取当前版本信息请求")
    
    current_version = get_current_version()
    internal_version = convert_version_to_number(current_version)
    
    version_info = VersionInfo(
        version=current_version,
        internal_version=internal_version,
        release_date="2025-01-03",  # 可以从配置文件或其他地方获取
        release_notes="当前运行版本"
    )
    
    return CurrentVersionResponse(status="success", data=version_info)


@router.get("/version/check", response_model=VersionCheckResponse)
async def check_for_updates():
    """
    检查是否有可用的更新版本
    """
    logger.info("收到检查更新请求")
    
    current_version = get_current_version()
    current_internal = convert_version_to_number(current_version)
    
    # 模拟版本检查 - 在实际应用中，这里应该连接到更新服务器
    # 这里返回一个示例更新信息
    latest_version = "0.1.0-Preview.3"
    latest_internal = convert_version_to_number(latest_version)
    
    has_update = latest_internal > current_internal
    
    update_info = {
        "current_version": current_version,
        "current_internal": current_internal,
        "latest_version": latest_version,
        "latest_internal": latest_internal,
        "has_update": has_update,
        "update_url": "https://github.com/MaiM-with-u/MaiLauncher/releases" if has_update else None,
        "release_notes": "修复了一些bug并提升了性能" if has_update else "您已使用最新版本",
        "last_check": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    
    return VersionCheckResponse(status="success", data=update_info)


@router.get("/version/history", response_model=VersionHistoryResponse)
async def get_version_history():
    """
    获取版本历史记录
    """
    logger.info("收到获取版本历史请求")
    
    # 模拟版本历史数据 - 在实际应用中，这些数据应该来自数据库或配置文件
    version_history = [
        VersionInfo(
            version="0.1.0-Preview.3",
            internal_version=103,
            release_date="2025-01-05",
            release_notes="修复了连接稳定性问题，优化了性能"
        ),
        VersionInfo(
            version="0.1.0-Preview.2",
            internal_version=102,
            release_date="2025-01-03",
            release_notes="添加了版本检查功能，改进了用户界面"
        ),
        VersionInfo(
            version="0.1.0-Preview.1",
            internal_version=101,
            release_date="2025-01-01",
            release_notes="初始预览版本发布"
        ),
        VersionInfo(
            version="0.1.0",
            internal_version=100,
            release_date="2024-12-30",
            release_notes="正式版本发布"
        )
    ]
    
    return VersionHistoryResponse(status="success", data=version_history)
