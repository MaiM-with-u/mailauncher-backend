from src.utils.database_model import DB_Instance, DB_Service  # SQLModel version
from src.utils.database import engine  # SQLModel engine
from sqlmodel import Session, select  # SQLModel session and select

from src.utils.logger import get_module_logger
import datetime
from enum import Enum
from typing import Optional, List

logger = get_module_logger("实例管理器")


class InstanceStatus(Enum):
    RUNNING = "运行中"
    STOPPED = "已停止"
    STARTING = "启动中"
    STOPPING = "停止中"
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
        host: str,
        port: int,
        token: str,
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

    @classmethod
    def from_db_model(cls, db_instance: DB_Instance) -> "Instance":
        """
        从数据库模型对象创建 Instance 对象。

        参数:
            db_instance (DB_Instance): SQLModel 数据库模型实例。

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
            host=db_instance.host,
            port=db_instance.port,
            token=db_instance.token,
            created_at=db_instance.created_at,
        )


class InstanceManager:
    """管理应用程序实例的创建、检索、更新和删除。"""

    def __init__(self):
        """初始化 InstanceManager。"""
        pass

    def _execute_query(
        self, query, operation_name: str, instance_id: Optional[str] = None
    ):  # sourcery skip: extract-method
        """执行数据库查询并处理常见的异常。"""
        try:
            with Session(engine) as session:
                result = session.exec(query).first()
                if result:
                    # 在 session 关闭前访问所有需要的属性，避免 DetachedInstanceError
                    # 触发属性加载以确保数据在 session 关闭后仍然可用
                    _ = result.id
                    _ = result.instance_id
                    _ = result.name
                    _ = result.version
                    _ = result.path
                    _ = result.status
                    _ = result.port
                    _ = result.created_at
                session.commit()
                return result
        except Exception as e:
            log_msg = f"{operation_name}时出错"
            if instance_id:
                log_msg += f" (实例ID: {instance_id})"
            log_msg += f": {e}"
            logger.error(log_msg)
            return None

    def create_instance(
        self,
        name: str,
        version: str,
        path: str,
        status: InstanceStatus,
        host: str,
        port: int,
        token: str,
        instance_id: str,
        db_session: Optional[Session] = None,  # 添加可选的 db_session 参数
    ) -> Optional[Instance]:
        """
        在数据库中创建一个新的实例记录。
        如果提供了 db_session，则实例将添加到该会话中但不会提交；提交由调用方负责。
        返回的 Instance 对象将在添加到会话成功后填充 ID。

        参数:
            name (str): 实例的名称。
            version (str): 实例的版本。
            path (str): 实例的路径。
            status (InstanceStatus): 实例的初始状态。
            port (int): 实例的端口号。
            instance_id (str): 要创建的实例的唯一ID。
            db_session (Optional[Session]): 用于数据库操作的可选SQLModel会话。

        返回:
            Optional[Instance]: 如果创建成功，则返回新的 Instance 对象，否则返回 None (如果内部管理会话时出错) 或引发异常 (如果使用提供的会话时出错)。        引发:
            Exception: 如果使用提供的 db_session 时在数据库操作期间发生错误。
        """
        db_model_instance = DB_Instance(
            instance_id=instance_id,
            name=name,
            version=version,
            path=path,
            status=status.value,
            host=host,
            port=port,
            token=token,
        )

        if db_session:
            try:
                db_session.add(db_model_instance)
                db_session.flush()  # 确保 ID 被填充
                db_session.refresh(db_model_instance)  # 刷新以从数据库状态更新所有属性
                logger.info(f"实例 {name} ({instance_id}) 已添加到提供的会话。")
                return Instance.from_db_model(db_model_instance)
            except Exception as e:
                logger.error(f"向提供的会话添加实例 {name} ({instance_id}) 时出错: {e}")
                raise  # 重新引发异常，以便调用方可以处理事务
        else:
            # 内部管理会话
            try:
                with Session(engine) as session:
                    session.add(db_model_instance)
                    session.commit()
                    session.refresh(db_model_instance)
                    logger.info(f"实例 {name} ({instance_id}) 创建成功并已提交。")
                    return Instance.from_db_model(db_model_instance)
            except Exception as e:
                logger.error(f"创建并提交实例 {name} ({instance_id}) 时出错: {e}")
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
            with Session(engine) as session:
                statement = select(DB_Instance).where(
                    DB_Instance.instance_id == instance_id
                )
                db_instance = session.exec(statement).first()
                return Instance.from_db_model(db_instance) if db_instance else None
        except Exception as e:
            logger.error(f"获取实例时出错 (实例ID: {instance_id}): {e}")
            return None

    def get_all_instances(self) -> List[Instance]:
        """
        从数据库中检索所有实例。

        返回:
            List[Instance]: 包含所有实例的 Instance 对象列表。
        """
        try:
            with Session(engine) as session:
                statement = select(DB_Instance)
                results = session.exec(statement).all()
                return [Instance.from_db_model(db_instance) for db_instance in results]
        except Exception as e:
            logger.error(f"获取所有实例时出错: {e}")
            return []

    def get_instance_services(self, instance_id: str) -> List[DB_Service]:
        """
        根据实例ID从数据库中检索该实例安装的所有服务的详细信息列表。

        参数:
            instance_id (str): 要检索服务的实例的唯一ID。

        返回:
            List[Dict[str, Any]]: 包含所有服务详细信息的字典列表。
                                    每个字典包含: "id", "instance_id", "name", "path", "run_cmd", "status", "port"。
                                    如果找不到实例或发生错误，则返回空列表。
        """
        db_services: List[DB_Service] = []
        try:
            with Session(engine) as session:
                # 首先检查实例是否存在
                instance_exists_statement = select(DB_Instance).where(
                    DB_Instance.instance_id == instance_id
                )
                instance_db = session.exec(instance_exists_statement).first()
                if not instance_db:
                    logger.warning(
                        f"尝试获取服务详细列表失败：未找到实例 {instance_id}。"
                    )
                    return []

                # 获取与 instance_id 关联的所有服务
                statement = select(DB_Service).where(
                    DB_Service.instance_id == instance_id
                )
                db_services = session.exec(statement).all()  # Returns List[DB_Service]

                logger.info(
                    f"成功检索到实例 {instance_id} 的服务详细列表: {db_services}"
                )
        except Exception as e:
            logger.error(f"获取实例 {instance_id} 的服务详细列表时出错: {e}")
            return []  # Return empty list on error
        return db_services

    def update_instance_status(
        self, instance_id: str, new_status: InstanceStatus
    ) -> Optional[Instance]:  # sourcery skip: extract-method
        """
        更新数据库中现有实例的状态。

        参数:
            instance_id (str): 要更新的实例的唯一ID。
            new_status (InstanceStatus): 要设置的新状态。

        返回:
            Optional[Instance]: 如果更新成功，则返回更新后的 Instance 对象，否则返回 None。
        """
        try:
            with Session(engine) as session:
                if not (
                    db_instance := session.exec(
                        select(DB_Instance).where(
                            DB_Instance.instance_id == instance_id
                        )
                    ).first()
                ):
                    logger.warning(f"尝试更新状态失败：未找到实例 {instance_id}。")
                    return None

                db_instance.status = new_status.value
                session.add(db_instance)
                session.commit()
                session.refresh(db_instance)
                logger.info(f"实例 {instance_id} 的状态已更新为 {new_status.value}。")
                return Instance.from_db_model(db_instance)
        except Exception as e:
            logger.error(f"更新实例 {instance_id} 状态时出错: {e}")
            return None

    def update_instance_port(
        self, instance_id: str, new_port: int
    ) -> Optional[Instance]:  # sourcery skip: extract-method
        """
        更新数据库中现有实例的端口号。

        参数:
            instance_id (str): 要更新的实例的唯一ID。
            new_port (int): 要设置的新端口号。

        返回:
            Optional[Instance]: 如果更新成功，则返回更新后的 Instance 对象，否则返回 None。
        """
        try:
            with Session(engine) as session:
                if not (
                    db_instance := session.exec(
                        select(DB_Instance).where(
                            DB_Instance.instance_id == instance_id
                        )
                    ).first()
                ):
                    logger.warning(f"尝试更新端口失败：未找到实例 {instance_id}。")
                    return None

                db_instance.port = new_port
                session.add(db_instance)
                session.commit()
                session.refresh(db_instance)
                logger.info(f"实例 {instance_id} 的端口已更新为 {new_port}。")
                return Instance.from_db_model(db_instance)
        except Exception as e:
            logger.error(f"更新实例 {instance_id} 端口时出错: {e}")
            return None

    def delete_instance(self, instance_id: str) -> bool:
        """
        从数据库中删除一个实例。

        参数:
            instance_id (str): 要删除的实例的唯一ID。

        返回:
            bool: 如果删除成功则返回 True，否则返回 False。
        """
        try:
            with Session(engine) as session:
                if not (
                    db_instance := session.exec(
                        select(DB_Instance).where(
                            DB_Instance.instance_id == instance_id
                        )
                    ).first()
                ):
                    logger.warning(f"尝试删除失败：未找到实例 {instance_id}。")
                    return False

                session.delete(db_instance)
                session.commit()
                logger.info(f"实例 {instance_id} 已成功删除。")
                return True
        except Exception as e:
            logger.error(f"删除实例 {instance_id} 时出错: {e}")
            return False


# 全局实例管理器
instance_manager = InstanceManager()
