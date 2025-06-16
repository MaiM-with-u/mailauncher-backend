"""
MaiBot 资源管理器
负责管理多实例的 MaiBot 数据库资源
"""

import sqlite3
from typing import Optional, List, Dict, Any
from pathlib import Path

from src.utils.logger import get_module_logger
from src.modules.instance_manager import instance_manager

logger = get_module_logger("MaiBot资源管理器")


class MaiBotResourceManager:
    """
    MaiBot 资源管理器

    负责管理多个 MaiBot 实例的数据库资源，包括：
    - 数据库连接管理
    - 数据库 CRUD 操作
    - 数据库完整性检查
    """

    def __init__(self):
        """初始化 MaiBot 资源管理器"""
        self.db_filename = "MaiBot.db"
        self.data_folder = "data"
        logger.info("MaiBot 资源管理器初始化完成")

    def _get_instance_db_path(self, instance_id: str) -> Optional[Path]:
        """
        获取指定实例的数据库文件路径

        参数:
            instance_id (str): 实例ID

        返回:
            Optional[Path]: 数据库文件路径，如果实例不存在则返回 None
        """
        try:
            instance = instance_manager.get_instance(instance_id)
            if not instance:
                logger.error(f"未找到实例: {instance_id}")
                return None

            # MaiBot 数据库路径: {实例路径}/data/MaiBot.db
            return Path(instance.path) / self.data_folder / self.db_filename
        except Exception as e:
            logger.error(f"获取实例 {instance_id} 数据库路径时出错: {e}")
            return None

    def _get_db_connection(self, instance_id: str) -> Optional[sqlite3.Connection]:
        """
        获取指定实例的数据库连接

        参数:
            instance_id (str): 实例ID

        返回:
            Optional[sqlite3.Connection]: 数据库连接，如果失败则返回 None
        """
        try:
            db_path = self._get_instance_db_path(instance_id)
            if not db_path or not db_path.exists():
                logger.error(f"实例 {instance_id} 的数据库文件不存在: {db_path}")
                return None

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
            return conn
        except Exception as e:
            logger.error(f"连接实例 {instance_id} 数据库时出错: {e}")
            return None

    def _validate_db_file(self, db_path: Path) -> bool:
        """
        验证数据库文件的完整性

        参数:
            db_path (Path): 数据库文件路径

        返回:
            bool: 数据库文件是否有效
        """
        try:
            if not db_path.exists():
                logger.warning(f"数据库文件不存在: {db_path}")
                return False

            # 尝试连接数据库以验证完整性
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.cursor()
                # 执行简单查询来验证数据库结构
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()

            logger.info(f"数据库文件验证成功: {db_path}, 包含 {len(tables)} 个表")
            return True

        except Exception as e:
            logger.error(f"验证数据库文件 {db_path} 时出错: {e}")
            return False

    def get_instance_resource_info(self, instance_id: str) -> Dict[str, Any]:
        """
        获取指定实例的数据库资源信息

        参数:
            instance_id (str): 实例ID

        返回:
            Dict[str, Any]: 包含数据库资源信息的字典
        """
        try:
            instance = instance_manager.get_instance(instance_id)
            if not instance:
                return {"error": f"未找到实例: {instance_id}"}

            db_path = self._get_instance_db_path(instance_id)
            resource_info = {
                "instance_id": instance_id,
                "instance_name": instance.name,
                "instance_path": instance.path,
                "database": {
                    "path": str(db_path) if db_path else None,
                    "exists": db_path.exists() if db_path else False,
                    "valid": self._validate_db_file(db_path) if db_path else False,
                    "size": db_path.stat().st_size
                    if db_path and db_path.exists()
                    else 0,
                },
                "data_folder": {
                    "path": str(Path(instance.path) / self.data_folder),
                    "exists": (Path(instance.path) / self.data_folder).exists(),
                },
            }

            logger.info(f"成功获取实例 {instance_id} 的资源信息")
            return resource_info

        except Exception as e:
            logger.error(f"获取实例 {instance_id} 资源信息时出错: {e}")
            return {"error": str(e)}

    def get_all_instances_resources(self) -> List[Dict[str, Any]]:
        """
        获取所有实例的数据库资源信息

        返回:
            List[Dict[str, Any]]: 所有实例的数据库资源信息列表
        """
        try:
            instances = instance_manager.get_all_instances()
            resources_info = []

            for instance in instances:
                resource_info = self.get_instance_resource_info(instance.instance_id)
                resources_info.append(resource_info)

            logger.info(f"成功获取 {len(resources_info)} 个实例的资源信息")
            return resources_info

        except Exception as e:
            logger.error(f"获取所有实例资源信息时出错: {e}")
            return []

    # ================ Emoji 表情包表 CRUD 操作 ================

    def create_emoji(
        self, instance_id: str, emoji_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建新的表情包记录

        参数:
            instance_id (str): 实例ID
            emoji_data (Dict[str, Any]): 表情包数据，包含以下字段:
                - full_path (str): 表情包完整路径
                - format (str): 表情包格式
                - emoji_hash (str): 表情包哈希
                - description (str, optional): 表情包描述
                - emotion (str, optional): 表情包蕴含的情感
                - record_time (float, optional): 表情包记录时间，默认为当前时间

        返回:
            Dict[str, Any]: 创建结果
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 设置默认值
                import time

                current_time = time.time()

                insert_sql = """
                INSERT INTO Emoji (
                    full_path, format, emoji_hash, description, query_count,
                    is_registered, is_banned, emotion, record_time, register_time,
                    usage_count, last_used_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                values = (
                    emoji_data.get("full_path"),
                    emoji_data.get("format"),
                    emoji_data.get("emoji_hash"),
                    emoji_data.get("description", ""),
                    0,  # query_count
                    0,  # is_registered
                    0,  # is_banned
                    emoji_data.get("emotion", ""),
                    emoji_data.get("record_time", current_time),
                    None,  # register_time
                    0,  # usage_count
                    None,  # last_used_time
                )

                cursor.execute(insert_sql, values)
                emoji_id = cursor.lastrowid

                logger.info(f"成功创建表情包记录，ID: {emoji_id}")
                return {
                    "status": "success",
                    "message": "表情包创建成功",
                    "emoji_id": emoji_id,
                }

        except Exception as e:
            logger.error(f"创建表情包时出错: {e}")
            return {"status": "failed", "message": f"创建失败: {str(e)}"}

    def get_emoji_by_id(self, instance_id: str, emoji_id: int) -> Dict[str, Any]:
        """
        根据ID获取表情包信息

        参数:
            instance_id (str): 实例ID
            emoji_id (int): 表情包ID

        返回:
            Dict[str, Any]: 表情包信息
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM Emoji WHERE id = ?", (emoji_id,))
                row = cursor.fetchone()

                if row:
                    emoji_data = dict(row)
                    logger.info(f"成功获取表情包信息，ID: {emoji_id}")
                    return {"status": "success", "data": emoji_data}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到ID为 {emoji_id} 的表情包",
                    }

        except Exception as e:
            logger.error(f"获取表情包信息时出错: {e}")
            return {"status": "failed", "message": f"获取失败: {str(e)}"}

    def get_emoji_by_hash(self, instance_id: str, emoji_hash: str) -> Dict[str, Any]:
        """
        根据哈希值获取表情包信息

        参数:
            instance_id (str): 实例ID
            emoji_hash (str): 表情包哈希

        返回:
            Dict[str, Any]: 表情包信息
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM Emoji WHERE emoji_hash = ?", (emoji_hash,)
                )
                row = cursor.fetchone()

                if row:
                    emoji_data = dict(row)
                    logger.info(f"成功获取表情包信息，哈希: {emoji_hash}")
                    return {"status": "success", "data": emoji_data}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到哈希为 {emoji_hash} 的表情包",
                    }

        except Exception as e:
            logger.error(f"获取表情包信息时出错: {e}")
            return {"status": "failed", "message": f"获取失败: {str(e)}"}

    def search_emojis(
        self,
        instance_id: str,
        filters: Dict[str, Any] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        搜索表情包

        参数:
            instance_id (str): 实例ID
            filters (Dict[str, Any], optional): 筛选条件，可包含:
                - emotion (str): 情感筛选
                - is_registered (int): 是否注册 (0/1)
                - is_banned (int): 是否禁用 (0/1)
                - format (str): 格式筛选
                - description_like (str): 描述模糊搜索
            limit (int): 限制返回数量
            offset (int): 偏移量

        返回:
            Dict[str, Any]: 搜索结果
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 构建查询条件
                where_conditions = []
                params = []

                if filters:
                    if "emotion" in filters and filters["emotion"]:
                        where_conditions.append("emotion = ?")
                        params.append(filters["emotion"])

                    if "is_registered" in filters:
                        where_conditions.append("is_registered = ?")
                        params.append(filters["is_registered"])

                    if "is_banned" in filters:
                        where_conditions.append("is_banned = ?")
                        params.append(filters["is_banned"])

                    if "format" in filters and filters["format"]:
                        where_conditions.append("format = ?")
                        params.append(filters["format"])

                    if "description_like" in filters and filters["description_like"]:
                        where_conditions.append("description LIKE ?")
                        params.append(f"%{filters['description_like']}%")

                # 构建SQL查询
                where_clause = (
                    " WHERE " + " AND ".join(where_conditions)
                    if where_conditions
                    else ""
                )
                query_sql = f"SELECT * FROM Emoji{where_clause} ORDER BY record_time DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cursor.execute(query_sql, params)
                rows = cursor.fetchall()

                # 获取总数
                count_sql = f"SELECT COUNT(*) FROM Emoji{where_clause}"
                cursor.execute(count_sql, params[:-2])  # 排除 limit 和 offset
                total_count = cursor.fetchone()[0]

                emojis = [dict(row) for row in rows]

                logger.info(f"成功搜索表情包，返回 {len(emojis)} 条记录")
                return {
                    "status": "success",
                    "data": emojis,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                }

        except Exception as e:
            logger.error(f"搜索表情包时出错: {e}")
            return {"status": "failed", "message": f"搜索失败: {str(e)}"}

    def update_emoji(
        self, instance_id: str, emoji_id: int, update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新表情包信息

        参数:
            instance_id (str): 实例ID
            emoji_id (int): 表情包ID
            update_data (Dict[str, Any]): 要更新的数据

        返回:
            Dict[str, Any]: 更新结果
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 构建更新语句
                update_fields = []
                params = []

                allowed_fields = [
                    "full_path",
                    "format",
                    "emoji_hash",
                    "description",
                    "query_count",
                    "is_registered",
                    "is_banned",
                    "emotion",
                    "register_time",
                    "usage_count",
                    "last_used_time",
                ]

                for field, value in update_data.items():
                    if field in allowed_fields:
                        update_fields.append(f"{field} = ?")
                        params.append(value)

                if not update_fields:
                    return {"status": "failed", "message": "没有有效的更新字段"}

                params.append(emoji_id)
                update_sql = f"UPDATE Emoji SET {', '.join(update_fields)} WHERE id = ?"

                cursor.execute(update_sql, params)

                if cursor.rowcount > 0:
                    logger.info(f"成功更新表情包，ID: {emoji_id}")
                    return {"status": "success", "message": "表情包更新成功"}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到ID为 {emoji_id} 的表情包",
                    }

        except Exception as e:
            logger.error(f"更新表情包时出错: {e}")
            return {"status": "failed", "message": f"更新失败: {str(e)}"}

    def delete_emoji(self, instance_id: str, emoji_id: int) -> Dict[str, Any]:
        """
        删除表情包记录

        参数:
            instance_id (str): 实例ID
            emoji_id (int): 表情包ID

        返回:
            Dict[str, Any]: 删除结果
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM Emoji WHERE id = ?", (emoji_id,))

                if cursor.rowcount > 0:
                    logger.info(f"成功删除表情包，ID: {emoji_id}")
                    return {"status": "success", "message": "表情包删除成功"}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到ID为 {emoji_id} 的表情包",
                    }

        except Exception as e:
            logger.error(f"删除表情包时出错: {e}")
            return {"status": "failed", "message": f"删除失败: {str(e)}"}

    def increment_emoji_usage(self, instance_id: str, emoji_id: int) -> Dict[str, Any]:
        """
        增加表情包使用次数并更新最后使用时间

        参数:
            instance_id (str): 实例ID
            emoji_id (int): 表情包ID

        返回:
            Dict[str, Any]: 更新结果
        """
        try:
            import time

            current_time = time.time()

            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()
                update_sql = """
                UPDATE Emoji 
                SET usage_count = usage_count + 1, last_used_time = ?
                WHERE id = ?
                """
                cursor.execute(update_sql, (current_time, emoji_id))

                if cursor.rowcount > 0:
                    logger.info(f"成功更新表情包使用统计，ID: {emoji_id}")
                    return {"status": "success", "message": "使用统计更新成功"}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到ID为 {emoji_id} 的表情包",
                    }

        except Exception as e:
            logger.error(f"更新表情包使用统计时出错: {e}")
            return {"status": "failed", "message": f"更新失败: {str(e)}"}

    def increment_emoji_query(self, instance_id: str, emoji_id: int) -> Dict[str, Any]:
        """
        增加表情包查询次数

        参数:
            instance_id (str): 实例ID
            emoji_id (int): 表情包ID

        返回:
            Dict[str, Any]: 更新结果
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE Emoji SET query_count = query_count + 1 WHERE id = ?",
                    (emoji_id,),
                )

                if cursor.rowcount > 0:
                    logger.info(f"成功更新表情包查询统计，ID: {emoji_id}")
                    return {"status": "success", "message": "查询统计更新成功"}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到ID为 {emoji_id} 的表情包",
                    }

        except Exception as e:
            logger.error(f"更新表情包查询统计时出错: {e}")
            return {"status": "failed", "message": f"更新失败: {str(e)}"}

    # ================ PersonInfo 用户信息表 CRUD 操作 ================

    def create_person_info(
        self, instance_id: str, person_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建新的用户信息记录

        参数:
            instance_id (str): 实例ID
            person_data (Dict[str, Any]): 用户信息数据，包含以下字段:
                - person_id (str): 用户唯一id
                - person_name (str, optional): bot给用户的起名
                - name_reason (str, optional): 起名原因
                - platform (str): 平台
                - user_id (str): 用户平台id
                - nickname (str, optional): 用户平台昵称
                - impression (str, optional): 印象
                - short_impression (str, optional): 短期印象
                - points (str, optional): 分数
                - forgotten_points (str, optional): 遗忘分数
                - info_list (str, optional): 信息列表
                - know_times (float, optional): 认识时间
                - know_since (float, optional): 认识瞬间描述
                - last_know (float, optional): 最近一次认识

        返回:
            Dict[str, Any]: 创建结果
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 检查 person_id 是否已存在
                cursor.execute(
                    "SELECT id FROM person_info WHERE person_id = ?",
                    (person_data.get("person_id"),),
                )
                if cursor.fetchone():
                    return {
                        "status": "failed",
                        "message": f"用户ID {person_data.get('person_id')} 已存在",
                    }

                insert_sql = """
                INSERT INTO person_info (
                    person_id, person_name, name_reason, platform, user_id,
                    nickname, impression, short_impression, points, forgotten_points,
                    info_list, know_times, know_since, last_know
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                values = (
                    person_data.get("person_id"),
                    person_data.get("person_name", ""),
                    person_data.get("name_reason", ""),
                    person_data.get("platform"),
                    person_data.get("user_id"),
                    person_data.get("nickname", ""),
                    person_data.get("impression", ""),
                    person_data.get("short_impression", ""),
                    person_data.get("points", ""),
                    person_data.get("forgotten_points", ""),
                    person_data.get("info_list", ""),
                    person_data.get("know_times"),
                    person_data.get("know_since"),
                    person_data.get("last_know"),
                )

                cursor.execute(insert_sql, values)
                record_id = cursor.lastrowid

                logger.info(
                    f"成功创建用户信息记录，ID: {record_id}, 用户ID: {person_data.get('person_id')}"
                )
                return {
                    "status": "success",
                    "message": "用户信息创建成功",
                    "record_id": record_id,
                    "person_id": person_data.get("person_id"),
                }

        except Exception as e:
            logger.error(f"创建用户信息时出错: {e}")
            return {"status": "failed", "message": f"创建失败: {str(e)}"}

    def get_person_info_by_id(self, instance_id: str, record_id: int) -> Dict[str, Any]:
        """
        根据记录ID获取用户信息

        参数:
            instance_id (str): 实例ID
            record_id (int): 记录ID

        返回:
            Dict[str, Any]: 用户信息
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM person_info WHERE id = ?", (record_id,))
                row = cursor.fetchone()

                if row:
                    person_data = dict(row)
                    logger.info(f"成功获取用户信息，记录ID: {record_id}")
                    return {"status": "success", "data": person_data}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到ID为 {record_id} 的用户信息",
                    }

        except Exception as e:
            logger.error(f"获取用户信息时出错: {e}")
            return {"status": "failed", "message": f"获取失败: {str(e)}"}

    def get_person_info_by_person_id(
        self, instance_id: str, person_id: str
    ) -> Dict[str, Any]:
        """
        根据用户唯一ID获取用户信息

        参数:
            instance_id (str): 实例ID
            person_id (str): 用户唯一ID

        返回:
            Dict[str, Any]: 用户信息
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM person_info WHERE person_id = ?", (person_id,)
                )
                row = cursor.fetchone()

                if row:
                    person_data = dict(row)
                    logger.info(f"成功获取用户信息，用户ID: {person_id}")
                    return {"status": "success", "data": person_data}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到用户ID为 {person_id} 的用户信息",
                    }

        except Exception as e:
            logger.error(f"获取用户信息时出错: {e}")
            return {"status": "failed", "message": f"获取失败: {str(e)}"}

    def get_person_info_by_platform_user(
        self, instance_id: str, platform: str, user_id: str
    ) -> Dict[str, Any]:
        """
        根据平台和平台用户ID获取用户信息

        参数:
            instance_id (str): 实例ID
            platform (str): 平台
            user_id (str): 平台用户ID

        返回:
            Dict[str, Any]: 用户信息
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM person_info WHERE platform = ? AND user_id = ?",
                    (platform, user_id),
                )
                row = cursor.fetchone()

                if row:
                    person_data = dict(row)
                    logger.info(
                        f"成功获取用户信息，平台: {platform}, 用户ID: {user_id}"
                    )
                    return {"status": "success", "data": person_data}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到平台 {platform} 用户ID {user_id} 的用户信息",
                    }

        except Exception as e:
            logger.error(f"获取用户信息时出错: {e}")
            return {"status": "failed", "message": f"获取失败: {str(e)}"}

    def search_person_info(
        self,
        instance_id: str,
        filters: Dict[str, Any] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        搜索用户信息

        参数:
            instance_id (str): 实例ID
            filters (Dict[str, Any], optional): 筛选条件，可包含:
                - platform (str): 平台筛选
                - person_name_like (str): 用户名模糊搜索
                - nickname_like (str): 昵称模糊搜索
                - impression_like (str): 印象模糊搜索
                - has_person_name (bool): 是否有用户名
            limit (int): 限制返回数量
            offset (int): 偏移量

        返回:
            Dict[str, Any]: 搜索结果
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 构建查询条件
                where_conditions = []
                params = []

                if filters:
                    if "platform" in filters and filters["platform"]:
                        where_conditions.append("platform = ?")
                        params.append(filters["platform"])

                    if "person_name_like" in filters and filters["person_name_like"]:
                        where_conditions.append("person_name LIKE ?")
                        params.append(f"%{filters['person_name_like']}%")

                    if "nickname_like" in filters and filters["nickname_like"]:
                        where_conditions.append("nickname LIKE ?")
                        params.append(f"%{filters['nickname_like']}%")

                    if "impression_like" in filters and filters["impression_like"]:
                        where_conditions.append("impression LIKE ?")
                        params.append(f"%{filters['impression_like']}%")

                    if "has_person_name" in filters:
                        if filters["has_person_name"]:
                            where_conditions.append(
                                "person_name IS NOT NULL AND person_name != ''"
                            )
                        else:
                            where_conditions.append(
                                "(person_name IS NULL OR person_name = '')"
                            )

                # 构建SQL查询
                where_clause = (
                    " WHERE " + " AND ".join(where_conditions)
                    if where_conditions
                    else ""
                )
                query_sql = f"SELECT * FROM person_info{where_clause} ORDER BY last_know DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cursor.execute(query_sql, params)
                rows = cursor.fetchall()

                # 获取总数
                count_sql = f"SELECT COUNT(*) FROM person_info{where_clause}"
                cursor.execute(count_sql, params[:-2])  # 排除 limit 和 offset
                total_count = cursor.fetchone()[0]

                persons = [dict(row) for row in rows]

                logger.info(f"成功搜索用户信息，返回 {len(persons)} 条记录")
                return {
                    "status": "success",
                    "data": persons,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                }

        except Exception as e:
            logger.error(f"搜索用户信息时出错: {e}")
            return {"status": "failed", "message": f"搜索失败: {str(e)}"}

    def update_person_info(
        self, instance_id: str, person_id: str, update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新用户信息

        参数:
            instance_id (str): 实例ID
            person_id (str): 用户唯一ID
            update_data (Dict[str, Any]): 要更新的数据

        返回:
            Dict[str, Any]: 更新结果
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 构建更新语句
                update_fields = []
                params = []

                allowed_fields = [
                    "person_name",
                    "name_reason",
                    "platform",
                    "user_id",
                    "nickname",
                    "impression",
                    "short_impression",
                    "points",
                    "forgotten_points",
                    "info_list",
                    "know_times",
                    "know_since",
                    "last_know",
                ]

                for field, value in update_data.items():
                    if field in allowed_fields:
                        update_fields.append(f"{field} = ?")
                        params.append(value)

                if not update_fields:
                    return {"status": "failed", "message": "没有有效的更新字段"}

                params.append(person_id)
                update_sql = f"UPDATE person_info SET {', '.join(update_fields)} WHERE person_id = ?"

                cursor.execute(update_sql, params)

                if cursor.rowcount > 0:
                    logger.info(f"成功更新用户信息，用户ID: {person_id}")
                    return {"status": "success", "message": "用户信息更新成功"}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到用户ID为 {person_id} 的用户信息",
                    }

        except Exception as e:
            logger.error(f"更新用户信息时出错: {e}")
            return {"status": "failed", "message": f"更新失败: {str(e)}"}

    def delete_person_info(self, instance_id: str, person_id: str) -> Dict[str, Any]:
        """
        删除用户信息记录

        参数:
            instance_id (str): 实例ID
            person_id (str): 用户唯一ID

        返回:
            Dict[str, Any]: 删除结果
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM person_info WHERE person_id = ?", (person_id,)
                )

                if cursor.rowcount > 0:
                    logger.info(f"成功删除用户信息，用户ID: {person_id}")
                    return {"status": "success", "message": "用户信息删除成功"}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到用户ID为 {person_id} 的用户信息",
                    }

        except Exception as e:
            logger.error(f"删除用户信息时出错: {e}")
            return {"status": "failed", "message": f"删除失败: {str(e)}"}

    def update_person_interaction(
        self,
        instance_id: str,
        person_id: str,
        impression_update: str = None,
        short_impression_update: str = None,
        points_update: str = None,
    ) -> Dict[str, Any]:
        """
        更新用户交互信息（印象、短期印象、分数）并更新最近认识时间

        参数:
            instance_id (str): 实例ID
            person_id (str): 用户唯一ID
            impression_update (str, optional): 新的印象信息
            short_impression_update (str, optional): 新的短期印象信息
            points_update (str, optional): 新的分数信息

        返回:
            Dict[str, Any]: 更新结果
        """
        try:
            import time

            current_time = time.time()

            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 构建更新字段
                update_fields = ["last_know = ?"]
                params = [current_time]

                if impression_update is not None:
                    update_fields.append("impression = ?")
                    params.append(impression_update)

                if short_impression_update is not None:
                    update_fields.append("short_impression = ?")
                    params.append(short_impression_update)

                if points_update is not None:
                    update_fields.append("points = ?")
                    params.append(points_update)

                params.append(person_id)
                update_sql = f"UPDATE person_info SET {', '.join(update_fields)} WHERE person_id = ?"

                cursor.execute(update_sql, params)
                if cursor.rowcount > 0:
                    logger.info(f"成功更新用户交互信息，用户ID: {person_id}")
                    return {"status": "success", "message": "用户交互信息更新成功"}
                else:
                    return {
                        "status": "failed",
                        "message": f"未找到用户ID为 {person_id} 的用户信息",
                    }

        except Exception as e:
            logger.error(f"更新用户交互信息时出错: {e}")
            return {"status": "failed", "message": f"更新失败: {str(e)}"}

    # ================ Emoji 统计和批量获取方法 ================

    def get_emoji_count(
        self, instance_id: str, filters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        获取表情包记录总数

        参数:
            instance_id (str): 实例ID
            filters (Dict[str, Any], optional): 筛选条件

        返回:
            Dict[str, Any]: 包含总数的响应
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 构建查询条件
                where_conditions = []
                params = []

                if filters:
                    if filters.get("emotion"):
                        where_conditions.append("emotion = ?")
                        params.append(filters["emotion"])

                    if filters.get("is_registered") is not None:
                        where_conditions.append("is_registered = ?")
                        params.append(filters["is_registered"])

                    if filters.get("is_banned") is not None:
                        where_conditions.append("is_banned = ?")
                        params.append(filters["is_banned"])

                    if filters.get("format"):
                        where_conditions.append("format = ?")
                        params.append(filters["format"])

                    if filters.get("description_like"):
                        where_conditions.append("description LIKE ?")
                        params.append(f"%{filters['description_like']}%")

                where_clause = (
                    " WHERE " + " AND ".join(where_conditions)
                    if where_conditions
                    else ""
                )
                count_sql = f"SELECT COUNT(*) FROM Emoji{where_clause}"

                cursor.execute(count_sql, params)
                total_count = cursor.fetchone()[0]

                logger.info(
                    f"获取表情包总数成功，实例: {instance_id}, 总数: {total_count}"
                )
                return {
                    "status": "success",
                    "data": {"total_count": total_count},
                    "message": f"成功获取表情包总数: {total_count}",
                }

        except Exception as e:
            logger.error(f"获取表情包总数时出错: {e}")
            return {"status": "failed", "message": f"获取失败: {str(e)}"}

    def get_emoji_batch(
        self,
        instance_id: str,
        batch_size: int = 50,
        offset: int = 0,
        filters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        批量获取表情包数据

        参数:
            instance_id (str): 实例ID
            batch_size (int): 批次大小
            offset (int): 偏移量
            filters (Dict[str, Any], optional): 筛选条件

        返回:
            Dict[str, Any]: 包含表情包列表的响应
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 构建查询条件
                where_conditions = []
                params = []

                if filters:
                    if filters.get("emotion"):
                        where_conditions.append("emotion = ?")
                        params.append(filters["emotion"])

                    if filters.get("is_registered") is not None:
                        where_conditions.append("is_registered = ?")
                        params.append(filters["is_registered"])

                    if filters.get("is_banned") is not None:
                        where_conditions.append("is_banned = ?")
                        params.append(filters["is_banned"])

                    if filters.get("format"):
                        where_conditions.append("format = ?")
                        params.append(filters["format"])

                    if filters.get("description_like"):
                        where_conditions.append("description LIKE ?")
                        params.append(f"%{filters['description_like']}%")

                where_clause = (
                    " WHERE " + " AND ".join(where_conditions)
                    if where_conditions
                    else ""
                )
                params.extend([batch_size, offset])

                query_sql = f"""
                SELECT id, full_path, format, emoji_hash, description, query_count, 
                       is_registered, is_banned, emotion, record_time, register_time, 
                       usage_count, last_used_time
                FROM Emoji{where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """

                cursor.execute(query_sql, params)
                rows = cursor.fetchall()

                # 转换为字典列表
                emoji_list = []
                for row in rows:
                    emoji_dict = {
                        "id": row[0],
                        "full_path": row[1],
                        "format": row[2],
                        "emoji_hash": row[3],
                        "description": row[4],
                        "query_count": row[5],
                        "is_registered": row[6],
                        "is_banned": row[7],
                        "emotion": row[8],
                        "record_time": row[9],
                        "register_time": row[10],
                        "usage_count": row[11],
                        "last_used_time": row[12],
                    }
                    emoji_list.append(emoji_dict)

                logger.info(
                    f"批量获取表情包成功，实例: {instance_id}, 批次大小: {batch_size}, 偏移: {offset}, 返回数量: {len(emoji_list)}"
                )
                return {
                    "status": "success",
                    "data": emoji_list,
                    "batch_size": batch_size,
                    "offset": offset,
                    "returned_count": len(emoji_list),
                    "message": f"成功获取 {len(emoji_list)} 条表情包记录",
                }

        except Exception as e:
            logger.error(f"批量获取表情包时出错: {e}")
            return {"status": "failed", "message": f"获取失败: {str(e)}"}

    # ================ PersonInfo 统计和批量获取方法 ================

    def get_person_info_count(
        self, instance_id: str, filters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        获取用户信息记录总数

        参数:
            instance_id (str): 实例ID
            filters (Dict[str, Any], optional): 筛选条件

        返回:
            Dict[str, Any]: 包含总数的响应
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 构建查询条件
                where_conditions = []
                params = []

                if filters:
                    if filters.get("platform"):
                        where_conditions.append("platform = ?")
                        params.append(filters["platform"])

                    if filters.get("person_name_like"):
                        where_conditions.append("person_name LIKE ?")
                        params.append(f"%{filters['person_name_like']}%")

                    if filters.get("nickname_like"):
                        where_conditions.append("nickname LIKE ?")
                        params.append(f"%{filters['nickname_like']}%")

                    if filters.get("impression_like"):
                        where_conditions.append("impression LIKE ?")
                        params.append(f"%{filters['impression_like']}%")

                    if filters.get("has_person_name") is not None:
                        if filters["has_person_name"]:
                            where_conditions.append(
                                "person_name IS NOT NULL AND person_name != ''"
                            )
                        else:
                            where_conditions.append(
                                "(person_name IS NULL OR person_name = '')"
                            )

                where_clause = (
                    " WHERE " + " AND ".join(where_conditions)
                    if where_conditions
                    else ""
                )
                count_sql = f"SELECT COUNT(*) FROM person_info{where_clause}"

                cursor.execute(count_sql, params)
                total_count = cursor.fetchone()[0]

                logger.info(
                    f"获取用户信息总数成功，实例: {instance_id}, 总数: {total_count}"
                )
                return {
                    "status": "success",
                    "data": {"total_count": total_count},
                    "message": f"成功获取用户信息总数: {total_count}",
                }

        except Exception as e:
            logger.error(f"获取用户信息总数时出错: {e}")
            return {"status": "failed", "message": f"获取失败: {str(e)}"}

    def get_person_info_batch(
        self,
        instance_id: str,
        batch_size: int = 50,
        offset: int = 0,
        filters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        批量获取用户信息数据

        参数:
            instance_id (str): 实例ID
            batch_size (int): 批次大小
            offset (int): 偏移量
            filters (Dict[str, Any], optional): 筛选条件

        返回:
            Dict[str, Any]: 包含用户信息列表的响应
        """
        try:
            conn = self._get_db_connection(instance_id)
            if not conn:
                return {"status": "failed", "message": "无法连接到数据库"}

            with conn:
                cursor = conn.cursor()

                # 构建查询条件
                where_conditions = []
                params = []

                if filters:
                    if filters.get("platform"):
                        where_conditions.append("platform = ?")
                        params.append(filters["platform"])

                    if filters.get("person_name_like"):
                        where_conditions.append("person_name LIKE ?")
                        params.append(f"%{filters['person_name_like']}%")

                    if filters.get("nickname_like"):
                        where_conditions.append("nickname LIKE ?")
                        params.append(f"%{filters['nickname_like']}%")

                    if filters.get("impression_like"):
                        where_conditions.append("impression LIKE ?")
                        params.append(f"%{filters['impression_like']}%")

                    if filters.get("has_person_name") is not None:
                        if filters["has_person_name"]:
                            where_conditions.append(
                                "person_name IS NOT NULL AND person_name != ''"
                            )
                        else:
                            where_conditions.append(
                                "(person_name IS NULL OR person_name = '')"
                            )

                where_clause = (
                    " WHERE " + " AND ".join(where_conditions)
                    if where_conditions
                    else ""
                )
                params.extend([batch_size, offset])

                query_sql = f"""
                SELECT id, person_id, person_name, name_reason, platform, user_id, 
                       nickname, impression, short_impression, points, forgotten_points, 
                       info_list, know_times, know_since, last_know
                FROM person_info{where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """

                cursor.execute(query_sql, params)
                rows = cursor.fetchall()

                # 转换为字典列表
                person_info_list = []
                for row in rows:
                    person_dict = {
                        "id": row[0],
                        "person_id": row[1],
                        "person_name": row[2],
                        "name_reason": row[3],
                        "platform": row[4],
                        "user_id": row[5],
                        "nickname": row[6],
                        "impression": row[7],
                        "short_impression": row[8],
                        "points": row[9],
                        "forgotten_points": row[10],
                        "info_list": row[11],
                        "know_times": row[12],
                        "know_since": row[13],
                        "last_know": row[14],
                    }
                    person_info_list.append(person_dict)

                logger.info(
                    f"批量获取用户信息成功，实例: {instance_id}, 批次大小: {batch_size}, 偏移: {offset}, 返回数量: {len(person_info_list)}"
                )
                return {
                    "status": "success",
                    "data": person_info_list,
                    "batch_size": batch_size,
                    "offset": offset,
                    "returned_count": len(person_info_list),
                    "message": f"成功获取 {len(person_info_list)} 条用户信息记录",
                }

        except Exception as e:
            logger.error(f"批量获取用户信息时出错: {e}")
            return {"status": "failed", "message": f"获取失败: {str(e)}"}


# 全局 MaiBot 资源管理器实例
maibot_resource_manager = MaiBotResourceManager()
