from sqlmodel import Field, SQLModel  # 导入SQLModel
from typing import Optional
import datetime
from src.utils.logger import get_module_logger
from src.utils.database import create_db_and_tables

logger = get_module_logger("数据库模型")  # 日志记录器名称可以保持不变或更改


class Instances(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)  # 数据库内部ID，主键
    instance_id: str = Field(
        unique=True, index=True
    )  # 实例的唯一标识符，例如自动生成的ID
    name: str  # 实例的名称，例如 "MaiBot-1"
    version: str  # 实例部署的 MaiBot 版本
    path: str  # 实例在文件系统中的路径
    status: str  # 实例的当前状态 (例如, "running", "stopped", "error")
    port: int  # 实例运行时占用的端口号
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now
    )  # 实例创建时间


class Services(SQLModel, table=True):
    id: Optional[int] = Field(
        default=None, primary_key=True
    )  # 服务记录的数据库内部ID，主键
    instance_id: str = Field(
        index=True
    )  # 关联到Instances表的instance_id，表示该服务属于哪个实例
    name: str  # 服务的名称 (例如, "chat-service", "database-service")
    path: str  # 服务相关文件或可执行文件的路径
    status: str  # 服务的当前状态 (例如, "active", "inactive", "pending")
    port: int  # 服务运行时占用的端口号（如果适用）


def initialize_database():
    """初始化数据库并创建表（如果它们尚不存在）。"""
    # SQLModel 会自动处理表的创建
    # 此处简化，不进行字段级检查和 sys.exit。
    create_db_and_tables()
    logger.info("数据库初始化完成，表已创建（如果不存在）。")
