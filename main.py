from fastapi import APIRouter, Response, WebSocket
from src.utils.logger import get_module_logger

# import sys
from src.utils.config import global_config

# 修改导入路径: from src.utils.database_model import initialize_database
from src.utils.database import initialize_database  # <--- 修改此行
from src.utils.database import get_db_instance  # 确保导入 get_db_instance
from src.utils.server import global_server
from src.modules import instance_api
from src.modules import system  # 添加导入
from src.modules import deploy_api  # 添加 deploy_api 导入
from src.modules.websocket_manager import (
    handle_websocket_connection,
)  # Import the new handler
import asyncio  # 添加 asyncio 导入

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


global_server.register_router(APIRouterV1, prefix=API_PREFIX)
global_server.register_router(instance_api.router, prefix=API_PREFIX)
global_server.register_router(system.router, prefix=API_PREFIX)  # 注册 system router
global_server.register_router(
    deploy_api.router, prefix=f"{API_PREFIX}/deploy"
)  # 注册 deploy_api router，并添加 /deploy 前缀
logger.info(f"已包含 API 路由，前缀为：{API_PREFIX}")


# --- 服务器启动 ---
async def main():
    logger.info("正在启动MaiLauncher后端服务器...")
    logger.info(f"HTTP 和 WebSocket 服务器将在 http://{HTTP_HOST}:{HTTP_PORT} 上启动")

    # 初始化数据库
    logger.info("正在初始化数据库...")
    initialize_database()
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
        # 仅运行 Uvicorn 服务器，它将处理所有请求
        await server.serve()
    except KeyboardInterrupt:
        logger.info("服务器正在关闭...")
    finally:
        logger.info("服务器已关闭。")


if __name__ == "__main__":
    try:
        asyncio.run(main())  # 使用 asyncio.run 运行主异步函数
    except KeyboardInterrupt:
        logger.info("主程序被中断。")
    except Exception as e:
        logger.error(f"主程序启动时发生未处理的异常: {e}", exc_info=True)
