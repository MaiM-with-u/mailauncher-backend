import os
import sys
from rich.traceback import install
from sqlmodel import create_engine, SQLModel, Session, select
from typing import Optional

# PtyLog 模型现在从 database_model.py 导入
from src.utils.database_model import DB_Service
from src.utils.logger import get_module_logger  # 添加 logger 导入

install(extra_lines=3)  # rich traceback 安装，用于美化异常输出


def get_resource_path(relative_path):
    """获取资源文件的绝对路径，支持PyInstaller打包环境"""
    try:
        # PyInstaller打包环境：获取exe文件所在目录
        # 使用sys.executable获取exe文件路径，而不是临时目录
        if hasattr(sys, "_MEIPASS"):
            # 在PyInstaller环境中，数据文件应该放在exe同级目录
            base_path = os.path.dirname(sys.executable)
        else:
            # 这个分支实际上不会执行，但保留以防万一
            base_path = sys._MEIPASS
    except AttributeError:
        # 开发环境中的路径
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    return os.path.join(base_path, relative_path)


# 定义数据库文件路径
_DB_DIR = get_resource_path("data")
_DB_FILE = os.path.join(_DB_DIR, "MaiLauncher.db")

# 确保数据库目录存在
os.makedirs(_DB_DIR, exist_ok=True)

# SQLModel 引擎
sqlite_url = f"sqlite:///{_DB_FILE}"
engine = create_engine(
    sqlite_url,
    echo=False,  # echo=True 用于在开发时打印SQL语句，生产环境可以关闭
)


def create_db_and_tables():
    """创建数据库和所有在 SQLModel 元数据中定义的表。"""
    # SQLModel.metadata.create_all(engine) 会处理所有已定义的 SQLModel 表
    # 只要相关的模型文件 (如 database_model.py) 被导入到项目中某处，
    # 并且它们继承自 SQLModel，create_all 就能找到它们。
    # 为了明确，可以确保 database_model 在调用此函数之前已被导入。
    # 例如，在 main.py 或 server.py 的顶部导入。
    SQLModel.metadata.create_all(engine)


# PTY 日志相关方法
class Database:
    def __init__(self, engine_to_use):
        self.engine = engine_to_use

    async def get_service_details(
        self, instance_id: str, service_name: str
    ) -> Optional[DB_Service]:
        """
        从数据库检索特定实例和服务的详细信息。
        """
        with Session(self.engine) as session:
            statement = select(DB_Service).where(
                DB_Service.instance_id == instance_id, DB_Service.name == service_name
            )
            return session.exec(statement).first()


# 全局数据库实例 (或者通过依赖注入管理)
# 为简单起见，这里创建一个全局实例，但在 FastAPI 中通常使用 Depends
_db_instance: Optional[Database] = None


def get_db_instance() -> Database:
    """获取全局数据库实例。如果不存在则创建。"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(engine)
    return _db_instance


# 将 initialize_database 函数移到这里
logger_db = get_module_logger("数据库")  # 为 database.py 创建一个 logger 实例


def initialize_database():
    """初始化数据库并创建表（如果它们尚不存在）。"""
    create_db_and_tables()
    logger_db.info("数据库初始化完成，表已创建（如果不存在）。")
