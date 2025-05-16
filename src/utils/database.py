import os
from peewee import SqliteDatabase
from rich.traceback import install

install(extra_lines=3)

# 定义数据库文件路径
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DB_DIR = os.path.join(ROOT_PATH, "data")
_DB_FILE = os.path.join(_DB_DIR, "MaiLauncher.db")

# 确保数据库目录存在
os.makedirs(_DB_DIR, exist_ok=True)

# 全局 Peewee SQLite 数据库访问点
db = SqliteDatabase(_DB_FILE)