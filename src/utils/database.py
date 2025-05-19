import os
from rich.traceback import install
from sqlmodel import create_engine, SQLModel, Session, select
from typing import List, Optional

# PtyLog 模型现在从 database_model.py 导入
# 确保 Services 也被导入
from src.utils.database_model import PtyLog, Services 
from src.utils.logger import get_module_logger # 添加 logger 导入

install(extra_lines=3) # rich traceback 安装，用于美化异常输出

# 定义数据库文件路径
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DB_DIR = os.path.join(ROOT_PATH, "data")
_DB_FILE = os.path.join(_DB_DIR, "MaiLauncher.db")

# 确保数据库目录存在
os.makedirs(_DB_DIR, exist_ok=True)

# SQLModel 引擎
sqlite_url = f"sqlite:///{_DB_FILE}"
engine = create_engine(
    sqlite_url, echo=False # echo=True 用于在开发时打印SQL语句，生产环境可以关闭
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

    async def add_pty_log(self, session_id: str, log_content: str, max_history: int):
        """
        向数据库添加一条 PTY 日志，并根据 max_history 修剪旧日志。
        """
        with Session(self.engine) as session:
            # 添加新日志
            db_log = PtyLog(session_id=session_id, log_content=log_content)
            session.add(db_log)
            
            # 如果需要，修剪旧日志
            # 计算当前会话的日志数量
            # SQLAlchemy 核心方式 (更高效，但需要导入 func):
            # from sqlalchemy import func
            # count_statement = select(func.count(PtyLog.id)).where(PtyLog.session_id == session_id)
            # current_log_count = session.exec(count_statement).scalar_one_or_none() or 0
            
            # 使用 select().all() 然后 len() 的简化方式
            statement_count = select(PtyLog).where(PtyLog.session_id == session_id)
            results_count = session.exec(statement_count).all()
            current_log_count = len(results_count)

            if current_log_count > max_history:
                num_to_delete = current_log_count - max_history
                # 查询要删除的最旧的日志条目
                statement_oldest = (
                    select(PtyLog)
                    .where(PtyLog.session_id == session_id)
                    .order_by(PtyLog.timestamp) # 最旧的在前
                    .limit(num_to_delete)
                )
                logs_to_delete = session.exec(statement_oldest).all()
                for log_item in logs_to_delete:
                    session.delete(log_item)
            
            session.commit() # 提交事务

    async def get_pty_logs(self, session_id: str, limit: int) -> List[PtyLog]:
        """
        从数据库检索指定会话的 PTY 日志，按时间顺序（从旧到新）。
        """
        with Session(self.engine) as session:
            statement = (
                select(PtyLog)
                .where(PtyLog.session_id == session_id)
                .order_by(PtyLog.timestamp.desc()) # 最新的在前
                .limit(limit)
            )
            results = session.exec(statement).all()
            return results[::-1] # 返回按时间顺序排列的结果 (最旧的在前)

    async def get_service_details(self, instance_id: str, service_name: str) -> Optional[Services]:
        """
        从数据库检索特定实例和服务的详细信息。
        """
        with Session(self.engine) as session:
            statement = select(Services).where(Services.instance_id == instance_id, Services.name == service_name)
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
logger_db = get_module_logger("数据库") # 为 database.py 创建一个 logger 实例

def initialize_database():
    """初始化数据库并创建表（如果它们尚不存在）。"""
    create_db_and_tables()
    logger_db.info("数据库初始化完成，表已创建（如果不存在）。")
