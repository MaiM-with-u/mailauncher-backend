from fastapi import APIRouter, Response
from src.utils.logger import get_module_logger

# import sys
from src.utils.config import global_config
from src.utils.database_model import initialize_database
from src.utils.server import global_server
from src.modules import instance_api
from src.modules import system  # 添加导入

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

global_server.register_router(APIRouterV1, prefix=API_PREFIX)
global_server.register_router(instance_api.router, prefix=API_PREFIX)
global_server.register_router(system.router, prefix=API_PREFIX)  # 注册 system router
logger.info(f"已包含 API 路由，前缀为：{API_PREFIX}")

# --- 服务器启动 ---
if __name__ == "__main__":
    logger.info(f"正在 http://{HTTP_HOST}:{HTTP_PORT} 上启动 Uvicorn 服务器")
    logger.info(
        f"API 文档将位于 http://{HTTP_HOST}:{HTTP_PORT}/docs 和 http://{HTTP_HOST}:{HTTP_PORT}/redoc"
    )
    logger.info(
        f"{API_PREFIX} 下的 WebSocket 端点将使用 ws://{HTTP_HOST}:{HTTP_PORT}{API_PREFIX}/..."
    )

    # 初始化数据库
    logger.info("正在初始化数据库...")
    initialize_database()
    logger.info("数据库初始化完成。")
    # 关于 WebSocket 端口 23457 的说明：
    # FastAPI 集成了 WebSocket，使其与 HTTP 服务器在同一端口上运行 (在此设置中为端口 {HTTP_PORT})。
    # 如果您需要在 *不同* 端口 (例如 23457) 上运行 WebSocket 服务器，
    # 它通常会是一个单独的 Python 应用程序/进程，直接使用像 'websockets' 这样的库，
    # 并且不会是此 FastAPI 应用程序的路由或 Uvicorn 实例的一部分。
    # 示例 WebSocket 端点 '/ws/{{client_id}}' 可通过 ws://{HTTP_HOST}:{HTTP_PORT}{API_PREFIX}/ws/{{client_id}} 访问

    try:
        global_server.run()
    except KeyboardInterrupt:
        logger.info("服务器正在关闭...")
