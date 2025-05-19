import os
from rich.traceback import install
from sqlmodel import create_engine, SQLModel  # 导入SQLModel相关

install(extra_lines=3)

# 定义数据库文件路径
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DB_DIR = os.path.join(ROOT_PATH, "data")
_DB_FILE = os.path.join(_DB_DIR, "MaiLauncher.db")

# 确保数据库目录存在
os.makedirs(_DB_DIR, exist_ok=True)

# SQLModel 引擎
sqlite_url = f"sqlite:///{_DB_FILE}"
engine = create_engine(
    sqlite_url, echo=True
)  # echo=True 用于在开发时打印SQL语句，生产环境可以关闭


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
