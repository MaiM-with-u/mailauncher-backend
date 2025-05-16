from peewee import Model, IntegerField, TextField, DateTimeField
from .database import db
import sys
from .logger import get_module_logger
import datetime

logger = get_module_logger("数据库")


class BaseModel(Model):
    class Meta:
        database = db


class Instances(BaseModel):
    id = IntegerField(primary_key=True)
    instance_id = TextField(unique=True)
    name = TextField()
    version = TextField()
    path = TextField()
    status = TextField()
    port = IntegerField()
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "instances"


class Services(BaseModel):
    instance_id = TextField()
    name = TextField()
    path = TextField()
    status = TextField()
    port = IntegerField()

    class Meta:
        table_name = "services"


def create_tables():
    """
    创建所有在模型中定义的数据库表。
    """
    with db:
        db.create_tables(
            [
                Instances,
                Services,
            ]
        )


def initialize_database():
    """
    检查所有定义的表是否存在，如果不存在则创建它们。
    检查所有表的所有字段是否存在，如果缺失则警告用户并退出程序。
    """
    models = [Instances, Services]
    needs_creation = False
    try:
        with db:  # 管理 table_exists 检查的连接
            for model in models:
                table_name = model._meta.table_name
                if not db.table_exists(model):
                    logger.warning(f"表 '{table_name}' 未找到。")
                    needs_creation = True
                    break  # 一个表丢失，无需进一步检查。
            if not needs_creation:
                # 检查字段
                for model in models:
                    table_name = model._meta.table_name
                    cursor = db.execute_sql(f"PRAGMA table_info('{table_name}')")
                    existing_columns = {row[1] for row in cursor.fetchall()}
                    model_fields = model._meta.fields
                    for field_name in model_fields:
                        if field_name not in existing_columns:
                            logger.error(
                                f"表 '{table_name}' 缺失字段 '{field_name}'，请手动迁移数据库结构后重启程序。"
                            )
                            sys.exit(1)
    except Exception as e:
        logger.exception(f"检查表或字段是否存在时出错: {e}")
        # 如果检查失败（例如数据库不可用），则退出
        return

    if needs_creation:
        logger.info("正在初始化数据库：一个或多个表丢失。正在尝试创建所有定义的表...")
        try:
            create_tables()  # 此函数有其自己的 'with db:' 上下文管理。
            logger.info("数据库表创建过程完成。")
        except Exception as e:
            logger.exception(f"创建表期间出错: {e}")
    else:
        logger.info("所有数据库表及字段均已存在。")
