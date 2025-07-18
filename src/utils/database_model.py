from sqlmodel import Field, SQLModel  # 导入SQLModel
from typing import Optional
import datetime
from src.utils.logger import get_module_logger

logger = get_module_logger("数据库模型")  # 日志记录器名称可以保持不变或更改


class DB_Instance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)  # 数据库内部ID，主键
    instance_id: str = Field(
        unique=True, index=True
    )  # 实例的唯一标识符，例如自动生成的ID
    name: str  # 实例的名称，例如 "MaiBot-1"
    version: str  # 实例部署的 MaiBot 版本
    path: str  # 实例在文件系统中的路径
    status: str  # 实例的当前状态 (例如, "running", "stopped", "error")
    host: str  # 实例的地址
    port: int  # 实例运行时占用的端口号
    token: str  # Maim_message所设定的token
    maim_type: str = Field(default="ws")  # Maim_message连接使用的方法 (ws 或 tcp)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now
    )  # 实例创建时间
    last_start_time: Optional[str] = Field(default=None, description="最近一次启动时间（ISO格式字符串）")
    total_runtime: Optional[int] = Field(default=0, description="累计运行时长（秒）")
    start_count: int = Field(default=0, description="启动次数")


class DB_Service(SQLModel, table=True):
    id: Optional[int] = Field(
        default=None, primary_key=True
    )  # 服务记录的数据库内部ID，主键
    instance_id: str = Field(
        index=True
    )  # 关联到Instances表的instance_id，表示该服务属于哪个实例
    name: str  # 服务的名称 (例如, "chat-service", "database-service")
    path: str  # 服务相关文件或可执行文件的路径
    run_cmd: str  # 实例的启动命令
    status: str  # 服务的当前状态 (例如, "active", "inactive", "pending")
    port: int  # 服务运行时占用的端口号（如果适用）
