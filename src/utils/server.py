from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware  # 新增导入
from typing import Optional
from uvicorn import Config, Server as UvicornServer
import asyncio

# import os
from .logger import get_module_logger
from .config import global_config
from rich.traceback import install

logger = get_module_logger("服务器")

install(extra_lines=3)


class Server:
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        app_name: str = "MaiLauncher",
    ):
        self.app = FastAPI(title=app_name)
        self._host: str = "127.0.0.1"
        self._port: int = 8080
        self._server: Optional[UvicornServer] = None
        self.set_address(host, port)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        logger.info("CORS 中间件已配置为允许所有请求。")

    def register_router(self, router: APIRouter, prefix: str = ""):
        """注册路由

        APIRouter 用于对相关的路由端点进行分组和模块化管理：
        1. 可以将相关的端点组织在一起，便于管理
        2. 支持添加统一的路由前缀
        3. 可以为一组路由添加共同的依赖项、标签等

        示例:
            router = APIRouter()

            @router.get("/users")
            def get_users():
                return {"users": [...]}

            @router.post("/users")
            def create_user():
                return {"msg": "user created"}

            # 注册路由，添加前缀 "/api/v1"
            server.register_router(router, prefix="/api/v1")
        """
        self.app.include_router(router, prefix=prefix)

    def set_address(self, host: Optional[str] = None, port: Optional[int] = None):
        """设置服务器地址和端口"""
        if host:
            self._host = host
        if port:
            self._port = port

    def run(self):
        """启动服务器"""
        # 禁用 uvicorn 默认日志和访问日志
        config = Config(app=self.app, host=self._host, port=self._port)
        self._server = UvicornServer(config=config)
        try:
            logger.info(
                f"服务器准备在 http://{self._host}:{self._port} 启动 (同步模式)"
            )
            asyncio.run(self._server.serve())
            logger.info(f"服务器已在 http://{self._host}:{self._port} 停止")
        except KeyboardInterrupt:
            logger.info(
                "服务器接收到中断信号 (KeyboardInterrupt)，将通过 finally 关闭。"
            )
            raise  # Uvicorn's serve() should handle KI and exit cleanly, this ensures propagation if not.
        except Exception as e:
            logger.error(f"服务器运行期间发生错误: {str(e)}")
            # The original code called self.shutdown() here too.
            # UvicornServer.serve() has its own finally that calls its shutdown.
            # Re-raising to match original behavior of propagating the error.
            raise RuntimeError(f"服务器运行错误: {str(e)}") from e
        finally:
            logger.info("服务器 run 方法执行完毕，执行 finally 中的 shutdown。")
            self.shutdown()  # Call synchronous shutdown

    def shutdown(self):
        """安全关闭服务器"""
        if self._server:
            logger.info("请求关闭服务器...")
            # Check if Uvicorn server instance thinks it's started
            if hasattr(self._server, "started") and self._server.started:
                self._server.should_exit = True  # Signal Uvicorn server to exit
                try:
                    # Run Uvicorn's own async shutdown method
                    logger.info("执行 UvicornServer.shutdown()...")
                    asyncio.run(self._server.shutdown())
                    logger.info("UvicornServer.shutdown() 调用完成。")
                except RuntimeError as e:
                    # Handle cases where asyncio.run() cannot be called (e.g., another loop running, loop closed)
                    logger.warning(
                        f"关闭服务器时执行 asyncio.run(self._server.shutdown()) 出错: {e}. 服务器可能已在关闭过程中或事件循环不可用。"
                    )
                except Exception as e:
                    logger.error(f"关闭服务器时发生未知错误: {e}")
            else:
                logger.info(
                    "服务器未在运行状态或已被标记为退出，无需执行 UvicornServer.shutdown()。"
                )
            self._server = None  # Clear our reference to the server instance
        else:
            logger.info("服务器实例不存在，无需关闭。")

    def get_app(self) -> FastAPI:
        """获取 FastAPI 实例"""
        return self.app


global_server = Server(host=global_config.server_host, port=global_config.server_port)
