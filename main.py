import uvicorn
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from src.utils.logger import get_module_logger
# import sys
from src.utils.config import global_config
from src.utils.database_model import initialize_database


logger = get_module_logger("主程序")
# --- 从 global_config 加载配置 ---
HTTP_HOST = global_config.server_host
HTTP_PORT = global_config.server_port
API_PREFIX = global_config.api_prefix
# --- 从 config.toml 加载配置 ---

# --- FastAPI 应用和主路由 ---
app = FastAPI(
    title="MaiLauncher 后端",
    description="麦麦启动器后端API",
    version="0.0.1"
)

# 此路由将处理 /api/v1下的所有路由
# 其他文件可以导入此路由并向其添加路由。
# 例如，在 another_file.py (例如 src/my_routes.py) 中:
#
#   from main import APIRouterV1 # 如果 main.py 不能直接导入，请调整路径
#   from loguru import logger
#
#   @APIRouterV1.get("/some_feature")
#   async def get_some_feature():
#       logger.info("访问了 /some_feature")
#       return {"feature_name": "我的出色功能"}
#
# 然后，确保在 uvicorn.run() 之前在此 main.py 中导入 'another_file.py'
# 例如：import src.my_routes
#
APIRouterV1 = APIRouter()

# --- CORS 中间件 ---
# 允许所有来源、方法和标头。根据生产环境的需要进行自定义。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS 中间件已配置为允许所有请求。")


# APIRouterV1 上定义的所有路由都将以 API_PREFIX 为前缀
app.include_router(APIRouterV1, prefix=API_PREFIX)
logger.info(f"已包含 API 路由，前缀为：{API_PREFIX}")

@app.get("/")
async def root():
    """
    用于基本服务器运行状况检查的根端点。
    """
    logger.info("调用了 GET / (根路径)")
    return {"message": f"FastAPI 服务器正在运行。API 位于 {API_PREFIX}。文档位于 /docs 或 /redoc。"}

# --- 如何从其他文件注册路由 (示例) ---
# 要使其他文件中的路由生效，您需要确保这些文件已由 main.py 导入。
# 例如，如果您创建了 'src/example_routes.py' 并包含以下内容：
#
# ```python
# # src/example_routes.py
# from main import api_v1_router # 假设 main.py 位于根目录并且可以访问
# from loguru import logger
#
# @api_v1_router.get("/another_feature")
# async def get_another_feature():
#     logger.info("从单独的模块调用了另一个功能端点")
#     return {"feature_details": "此功能在 src/example_routes.py 中定义"}
# ```
#
# 然后，在此 main.py 文件中，取消注释以下行 (如果需要，请调整路径)：
# try:
#     import src.example_routes # 确保此模块存在并且可以导入
#     logger.info("已成功从 src.example_routes 导入路由")
# except ImportError:
#     logger.warning("无法导入 src.example_routes。如果您打算使用它，请创建文件或检查 PYTHONPATH。")


# --- 服务器启动 ---
if __name__ == "__main__":
    logger.info(f"正在 http://{HTTP_HOST}:{HTTP_PORT} 上启动 Uvicorn 服务器")
    logger.info(f"API 文档将位于 http://{HTTP_HOST}:{HTTP_PORT}/docs 和 http://{HTTP_HOST}:{HTTP_PORT}/redoc")
    logger.info(f"{API_PREFIX} 下的 WebSocket 端点将使用 ws://{HTTP_HOST}:{HTTP_PORT}{API_PREFIX}/...")
    
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
    
    uvicorn.run(app, host=HTTP_HOST, port=HTTP_PORT)

