from src.utils.database_model import Instances, db
from src.utils.logger import get_module_logger
import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

logger = get_module_logger("实例管理器")


class InstanceStatus(Enum):
    RUNNING = "运行中"
    STOPPED = "停止中"  # 原为 "停止中",保持不变
    STARTING = "启动中"
    MAINTENANCE = "维护中"
    NOT_RUNNING = "未运行"


class Instance:
    """表示一个应用程序实例。"""

    def __init__(
        self,
        instance_id: str,
        name: str,
        version: str,
        path: str,
        status: InstanceStatus,
        port: int,
        id: Optional[int] = None,
        created_at: Optional[datetime.datetime] = None,
    ):
        """
        初始化 Instance 对象。

        参数:
            id (Optional[int]): 实例在数据库中的唯一标识符。
            instance_id (str): 实例的唯一ID字符串。
            name (str): 实例的名称。
            version (str): 实例的版本。
            path (str): 实例的路径。
            status (InstanceStatus): 实例的当前状态。
            port (int): 实例运行的端口号。
            created_at (Optional[datetime.datetime]): 实例的创建时间。如果为 None，则默认为当前时间。
        """
        self.id: Optional[int] = id
        self.instance_id: str = instance_id
        self.name: str = name
        self.version: str = version
        self.path: str = path
        if not isinstance(status, InstanceStatus):
            raise TypeError("状态必须是 InstanceStatus 枚举成员")
        self.status: InstanceStatus = status
        self.port: int = port
        self.created_at: datetime.datetime = created_at or datetime.datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """
        将 Instance 对象转换为字典。

        返回:
            Dict[str, Any]: 包含实例属性的字典。
        """
        return {
            "id": self.id,
            "instance_id": self.instance_id,
            "name": self.name,
            "version": self.version,
            "path": self.path,
            "status": self.status.value,  # 存储枚举值 (字符串)
            "port": self.port,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_db_model(cls, db_instance: Instances) -> "Instance":
        """
        从数据库模型对象创建 Instance 对象。

        参数:
            db_instance (Instances): Peewee 数据库模型实例。

        返回:
            Instance: 根据数据库模型创建的 Instance 对象。
        """
        return cls(
            id=db_instance.id,
            instance_id=db_instance.instance_id,
            name=db_instance.name,
            version=db_instance.version,
            path=db_instance.path,
            status=InstanceStatus(db_instance.status),  # 将数据库中的字符串转换为枚举
            port=db_instance.port,
            created_at=db_instance.created_at,
        )


class InstanceManager:
    """管理应用程序实例的创建、检索、更新和删除。"""

    def __init__(self):
        """初始化 InstanceManager。"""
        pass

    def create_instance(
        self,
        name: str,
        version: str,
        path: str,
        status: InstanceStatus,
        port: int,
        instance_id: str,
    ) -> Optional[Instance]:
        """
        在数据库中创建一个新的实例记录。

        参数:
            name (str): 实例的名称。
            version (str): 实例的版本。
            path (str): 实例的路径。
            status (InstanceStatus): 实例的初始状态。
            port (int): 实例的端口号。
            instance_id (str): 要创建的实例的唯一ID。

        返回:
            Optional[Instance]: 如果创建成功，则返回新的 Instance 对象，否则返回 None。
        """
        try:
            with db.atomic():
                db_instance = Instances.create(
                    instance_id=instance_id,
                    name=name,
                    version=version,
                    path=path,
                    status=status.value,  # 存储枚举值
                    port=port,
                )
                logger.info(f"实例 {name} ({instance_id}) 创建成功。")
                return Instance.from_db_model(db_instance)
        except Exception as e:
            logger.error(f"创建实例 {name} ({instance_id}) 时出错: {e}")
            return None

    def get_instance(self, instance_id: str) -> Optional[Instance]:
        """
        根据实例ID从数据库中检索一个实例。

        参数:
            instance_id (str): 要检索的实例的唯一ID。

        返回:
            Optional[Instance]: 如果找到实例，则返回 Instance 对象，否则返回 None。
        """
        try:
            if db_instance := Instances.get_or_none(
                Instances.instance_id == instance_id
            ):
                return Instance.from_db_model(db_instance)
            logger.info(f"未找到实例ID为 {instance_id} 的实例。")
            return None
        except Exception as e:
            logger.error(f"检索实例 {instance_id} 时出错: {e}")
            return None

    def get_all_instances(self) -> List[Instance]:
        """
        从数据库中检索所有实例。

        返回:
            List[Instance]: 包含所有 Instance 对象的列表。如果出错则返回空列表。
        """
        try:
            db_instances = Instances.select()
            return [Instance.from_db_model(db_i) for db_i in db_instances]
        except Exception as e:
            logger.error(f"检索所有实例时出错: {e}")
            return []

    def update_instance_status(
        self, instance_id: str, new_status: InstanceStatus
    ) -> bool:
        """
        更新数据库中指定实例的状态。

        参数:
            instance_id (str): 要更新状态的实例的唯一ID。
            new_status (InstanceStatus): 实例的新状态。

        返回:
            bool: 如果更新成功则返回 True，否则返回 False。
        """
        try:
            with db.atomic():
                if instance_to_update := Instances.get_or_none(
                    Instances.instance_id == instance_id
                ):
                    instance_to_update.status = new_status.value  # 存储枚举值
                    instance_to_update.save()
                    logger.info(
                        f"实例 {instance_id} 的状态已更新为 {new_status.value}。"
                    )
                    return True

                logger.warning(f"未找到实例ID为 {instance_id} 的实例以更新状态。")
                return False
        except Exception as e:
            logger.error(f"更新实例 {instance_id} 状态时出错: {e}")
            return False

    def update_instance_port(self, instance_id: str, new_port: int) -> bool:
        """
        更新数据库中指定实例的端口号。

        参数:
            instance_id (str): 要更新端口的实例的唯一ID。
            new_port (int): 实例的新端口号。

        返回:
            bool: 如果更新成功则返回 True，否则返回 False。
        """
        try:
            with db.atomic():
                if instance_to_update := Instances.get_or_none(
                    Instances.instance_id == instance_id
                ):
                    instance_to_update.port = new_port
                    instance_to_update.save()
                    logger.info(f"实例 {instance_id} 的端口已更新为 {new_port}。")
                    return True

                logger.warning(f"未找到实例ID为 {instance_id} 的实例以更新端口。")
                return False
        except Exception as e:
            logger.error(f"更新实例 {instance_id} 端口时出错: {e}")
            return False

    def delete_instance(self, instance_id: str) -> bool:
        """
        从数据库中删除指定的实例。

        参数:
            instance_id (str): 要删除的实例的唯一ID。

        返回:
            bool: 如果删除成功则返回 True，否则返回 False。
        """
        try:
            with db.atomic():
                if instance_to_delete := Instances.get_or_none(
                    Instances.instance_id == instance_id
                ):
                    instance_to_delete.delete_instance()  # Peewee 的 delete_instance 方法
                    logger.info(f"实例 {instance_id} 删除成功。")
                    return True

                logger.warning(f"未找到实例ID为 {instance_id} 的实例以进行删除。")
                return False
        except Exception as e:
            logger.error(f"删除实例 {instance_id} 时出错: {e}")
            return False


# 全局实例管理器
instance_manager = InstanceManager()
