from maim_message import (
    MessageBase,
    RouteConfig,
    Router,
    TargetConfig,
)
from fastapi import WebSocket
from starlette.websockets import WebSocketState
from asyncio import Queue
from typing import Dict

import json
import asyncio

from src.utils.logger import get_module_logger
from src.modules.instance_manager import instance_manager

logger = get_module_logger("聊天室API")

message_pool: Dict[str, Queue[MessageBase]] = {}


class MessageInstance:
    def __init__(self, session_id: str, url: str, token: str):
        self.session_id = session_id
        self.url = url
        self.token = token
        self.route_config = RouteConfig(
            {"Launcher", TargetConfig(url=url, token=token, ssl_verify=None)}
        )
        self.router = Router(self.route_config)
        self.router.register_class_handler(self.message_handler)
        logger.debug(f"注册路由成功，对应session: {session_id}")

    async def message_handler(self, message: MessageBase):
        await message_pool[self.session_id].put(message)


class MessagesAPI:
    routers: Dict[str, MessageInstance] = {}
    websocket_session_dict: Dict[str, WebSocket] = {}
    _running: bool
    polling_interval: float

    def __init__(self):
        self._running = False
        self.polling_interval = 0.2

    def add_instance(self, url: str, token: str, session_id: str) -> None:
        """添加到路由字典"""
        if session_id in self.routers:
            raise ValueError(f"Session {session_id} already exists in routers.")
        try:
            self.routers[session_id] = MessageInstance(
                session_id=session_id, url=url, token=token
            )
        except Exception as e:
            logger.error("路由注册出错！")
            raise e

    async def pool_polling(self) -> None:
        while self._running:
            for session_id, message_queue in message_pool.items():
                if message_queue.empty():
                    continue
                message = await message_queue.get()
                await self.forward_message(session_id, message)
            await asyncio.sleep(self.polling_interval)

    async def forward_message(self, session_id: str, raw_message: MessageBase):
        self.websocket_session_dict[session_id].send_json(
            json.dumps(raw_message.to_dict())
        )
        logger.debug(
            f"转发消息到 WebSocket (会话 ID: {session_id}): {raw_message.to_dict()}"
        )

    async def handle_websocket_connection(
        self, websocket: WebSocket, session_id: str
    ) -> None:
        self.websocket_session_dict[session_id] = websocket
        await websocket.accept()
        logger.info(
            f"客户端已连接 (FastAPI)，会话 ID: {session_id}，来自 {websocket.client.host}:{websocket.client.port}"
        )
        # 解析 session_id 获取实例 ID 和类型
        parts = session_id.rpartition("_")
        if not parts[1]:
            err_msg = f"WebSocket 会话 ID 格式无效 (缺少类型部分): {session_id}"
            logger.error(err_msg)
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({"type": "error", "message": err_msg})
                await websocket.close(code=1003)
            return

        instance_short_id, _, _ = parts

        # 验证实例是否存在
        instance = instance_manager.get_instance(instance_short_id)
        if not instance:
            err_msg = f"未找到实例 '{instance_short_id}'"
            logger.error(err_msg)
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({"type": "error", "message": err_msg})
                await websocket.close(code=1003)
            return

        instance_host = instance.host
        instance_port = instance.port
        instance_token = instance.token if hasattr(instance, "token") else None  # 备用
        if not instance_host or not instance_port:
            err_msg = f"实例 '{instance_short_id}' 的 HOST 或 PORT 未设置"
            logger.error(err_msg)
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({"type": "error", "message": err_msg})
                await websocket.close(code=1003)
            return

        if session_id not in self.routers:
            try:
                logger.debug(
                    f"尝试注册路由: {instance_host}:{instance_port}，会话 ID: {session_id}"
                )
                self.add_instance(
                    url=f"ws://{instance_host}:{instance_port}/ws",
                    token=instance_token,
                    session_id=session_id,
                )
            except Exception as e:
                err_msg = f"注册路由失败: {e}"
                logger.error(err_msg)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "error", "message": err_msg})
                    await websocket.close(code=1003)
                return
        if session_id not in message_pool:
            message_pool[session_id] = Queue()


message_api = MessagesAPI()
