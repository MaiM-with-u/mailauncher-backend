from fastapi import APIRouter, Response, WebSocket, WebSocketDisconnect
from src.utils.logger import get_module_logger
import signal
import sys

# import sys
from src.utils.config import global_config
from src.utils.database import initialize_database  # <--- 修改此行
from src.utils.database import get_db_instance  # 确保导入 get_db_instance
from src.utils.server import global_server
from src.modules import instance_api
from src.modules import system  # 添加导入
from src.modules import deploy_api  # 添加 deploy_api 导入
from src.modules import maibot_api  # 添加 maibot_api 导入
from src.modules.messages_api import message_api
from src.modules.websocket_manager import (
    handle_websocket_connection,
    shutdown_all_websocket_connections,
)  # Import the new handler and shutdown function
import asyncio  # 添加 asyncio 导入
from src.utils.tray_icon import TrayIcon, is_tray_available  # 添加托盘图标导入

logger = get_module_logger("主程序")
# --- 从 global_config 加载配置 ---
HTTP_HOST = global_config.server_host
HTTP_PORT = global_config.server_port
API_PREFIX = global_config.api_prefix
# --- 从 config.toml 加载配置 ---


APIRouterV1 = APIRouter()


# 直接在 FastAPI app 实例上添加根路径
@global_server.app.get("/", response_class=Response)
async def root_dashboard():
    html_content = """
    <html>
        <head>
            <title>MaiLauncher Backend</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #f0f2f5; color: #333; display: flex; justify-content: center; align-items: center; height: 100vh; text-align: center; }
                .container { background-color: #ffffff; padding: 50px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
                h1 { color: #4A90E2; margin-bottom: 20px; }
                p { font-size: 1.1em; line-height: 1.6; }
                .api-docs-link { display: inline-block; margin-top: 25px; padding: 10px 20px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; }
                .api-docs-link:hover { background-color: #45a049; }
                .footer { margin-top: 30px; font-size: 0.9em; color: #777; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>欢迎来到 MaiLauncher 后端服务</h1>
                <p>这是一个使用 FastAPI 构建的高效后端应用程序。</p>
                <p>您可以通过以下链接访问 API 文档：</p>
                <a href="/docs" class="api-docs-link">查看 API 文档 (/docs)</a>
                <a href="/redoc" class="api-docs-link">查看 ReDoc 文档 (/redoc)</a>
                <div class="footer">
                    <p>&copy; 2025 MaiLauncher. 保留所有权利。</p>
                </div>
            </div>
        </body>
    </html>
    """
    return Response(content=html_content, media_type="text/html")


# APIRouterV1 上定义的所有路由都将以 API_PREFIX 为前缀


# 添加测试API端点
@global_server.app.get("/api/test")
async def test_endpoint():
    return {"status": "success", "message": "后端运行正常", "port": HTTP_PORT}


# 添加简单的WebSocket测试端点
@global_server.app.websocket("/ws")
async def simple_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"收到WebSocket消息: {data}")
            # 处理消息...
            await websocket.send_text(f"收到消息: {data}")
    except WebSocketDisconnect:
        logger.info("WebSocket连接断开")
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
    finally:
        await websocket.close()


# 添加 WebSocket 路由
# 注意：路径中的 {session_id} 将被传递给 handle_websocket_connection
# API_PREFIX 将被应用到这个 WebSocket 路由
@APIRouterV1.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    # 获取数据库实例
    # 理想情况下，您可以使用 FastAPI 的依赖注入系统来提供数据库会话
    # 但为了简单起见，我们在这里直接获取它
    db_instance = get_db_instance()
    await handle_websocket_connection(websocket, session_id, db_instance)


@APIRouterV1.websocket("/chat/{session_id}")
async def websocket_chat_endpoint(websocket: WebSocket, session_id: str):
    """处理聊天 WebSocket 连接"""
    await message_api.handle_websocket_connection(websocket, session_id)


global_server.register_router(APIRouterV1, prefix=API_PREFIX)
global_server.register_router(instance_api.router, prefix=API_PREFIX)
global_server.register_router(system.router, prefix=API_PREFIX)  # 注册 system router
global_server.register_router(
    deploy_api.router, prefix=f"{API_PREFIX}/deploy"
)  # 注册 deploy_api router，并添加 /deploy 前缀
global_server.register_router(maibot_api.router, prefix=API_PREFIX)
logger.info(f"已包含 API 路由，前缀为：{API_PREFIX}")

# --- 全局变量用于优雅关闭 ---
shutdown_event = asyncio.Event()
tray_icon = None  # 全局托盘图标实例
_shutdown_initiated = False  # 标记是否已经开始关闭流程


def signal_handler(signum, frame):
    """处理终止信号"""
    global _shutdown_initiated
    if _shutdown_initiated:
        logger.info(f"收到信号 {signum}，但关闭流程已在进行中，忽略此信号")
        return

    logger.info(f"收到信号 {signum}，开始优雅关闭...")
    _shutdown_initiated = True
    shutdown_event.set()

    # 重置信号处理器以避免重复触发
    if sys.platform != "win32":
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
    else:
        signal.signal(signal.SIGINT, signal.SIG_DFL)


def shutdown_from_tray():
    """从托盘图标触发的关闭函数"""
    global _shutdown_initiated
    if _shutdown_initiated:
        logger.info("托盘图标请求关闭应用程序，但关闭流程已在进行中")
        return

    logger.info("托盘图标请求关闭应用程序")
    _shutdown_initiated = True
    shutdown_event.set()


# --- 服务器启动 ---
async def main():  # sourcery skip: use-contextlib-suppress
    global tray_icon, _shutdown_initiated

    logger.info("正在启动MaiLauncher后端服务器...")
    logger.info(f"HTTP 和 WebSocket 服务器将在 http://{HTTP_HOST}:{HTTP_PORT} 上启动")

    # 设置信号处理器
    if sys.platform != "win32":
        # Unix 系统使用信号处理
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    else:
        # Windows 系统的信号处理
        signal.signal(signal.SIGINT, signal_handler)

    # 初始化数据库
    logger.info("正在初始化数据库...")
    initialize_database()

    # 启动托盘图标（如果可用且运行在无控制台模式）
    if is_tray_available():
        try:
            tray_icon = TrayIcon(shutdown_from_tray)
            if tray_icon.start():
                logger.info("托盘图标已启动，应用程序将在后台运行")
            else:
                logger.warning("托盘图标启动失败")
        except Exception as e:
            logger.error(f"启动托盘图标时发生错误: {e}")
    else:
        logger.info("托盘图标功能不可用，应用程序将在前台运行")
    logger.info("数据库初始化完成。")

    # 启动 Uvicorn 服务器
    from uvicorn import Config, Server

    # Uvicorn 将同时处理 HTTP 和 WebSocket 请求
    config = Config(
        app=global_server.app,
        host=HTTP_HOST,
        port=HTTP_PORT,
        log_level="info",
        ws="auto",
    )
    server = Server(config)

    logger.info("Uvicorn 服务器 (HTTP 和 WebSocket) 正在启动...")

    try:
        # 创建服务器任务
        server_task = asyncio.create_task(server.serve())

        # 创建关闭监听任务
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        # 等待服务器启动或关闭信号
        done, pending = await asyncio.wait(
            [server_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
        )  # 如果收到关闭信号
        if shutdown_task in done:
            logger.info("收到关闭信号，开始优雅关闭...")
            _shutdown_initiated = True

            # 关闭所有 WebSocket 连接
            await shutdown_all_websocket_connections()

            # 停止服务器
            server.should_exit = True
            if not server_task.done():
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass

        # 取消剩余的任务
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except KeyboardInterrupt:
                if not _shutdown_initiated:
                    logger.info("收到键盘中断，开始优雅关闭...")
                    _shutdown_initiated = True
                    # 关闭所有 WebSocket 连接
                    await shutdown_all_websocket_connections()
    except Exception as e:
        logger.error(f"服务器运行时发生错误: {e}", exc_info=True)
        if not _shutdown_initiated:
            _shutdown_initiated = True
            # 关闭所有 WebSocket 连接
            await shutdown_all_websocket_connections()
    finally:
        # 停止托盘图标
        if tray_icon:
            try:
                tray_icon.stop()
                logger.info("托盘图标已停止")
            except Exception as e:
                logger.error(f"停止托盘图标时发生错误: {e}")

        logger.info("服务器已关闭。")


if __name__ == "__main__":
    try:
        asyncio.run(main())  # 使用 asyncio.run 运行主异步函数
    except KeyboardInterrupt:
        logger.info("主程序被键盘中断。")
    except SystemExit:
        logger.info("主程序正常退出。")
    except Exception as e:
        logger.error(f"主程序启动时发生未处理的异常: {e}", exc_info=True)
    finally:
        # 确保程序能够退出
        logger.info("MaiLauncher 后端服务已完全关闭。")
        sys.exit(0)
