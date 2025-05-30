# -*- coding: utf-8 -*-
"""
系统托盘图标模块
提供后台运行时的托盘图标和菜单功能
"""

import threading
# import asyncio
from pathlib import Path
from typing import Optional, Callable, Any
from src.utils.logger import get_module_logger

logger = get_module_logger("托盘图标")

try:
    import pystray
    from PIL import Image

    TRAY_AVAILABLE: bool = True
except ImportError:
    logger.warning("pystray 或 PIL 库未安装，托盘图标功能不可用")
    TRAY_AVAILABLE: bool = False


class TrayIcon:
    """系统托盘图标管理器"""

    def __init__(self, shutdown_callback: Optional[Callable[[], None]] = None) -> None:
        self.shutdown_callback = shutdown_callback
        self.icon: Optional[Any] = None  # pystray.Icon type
        self.running: bool = False

    def create_image(self) -> Optional[Any]:  # Returns PIL.Image.Image or None
        """创建托盘图标图像"""
        try:
            # 尝试使用项目中的图标文件
            icon_path = Path(__file__).parent.parent.parent / "assets" / "maimai.ico"
            if icon_path.exists():
                # 对于 .ico 文件，直接用 PIL 打开
                image = Image.open(icon_path)
                # 调整大小为托盘图标标准尺寸
                image = image.resize((64, 64), Image.Resampling.LANCZOS)
                return image
            else:
                logger.warning(f"图标文件不存在: {icon_path}")
        except Exception as e:
            logger.warning(f"加载图标文件失败: {e}")

        # 如果无法加载图标文件，创建一个简单的默认图标
        try:
            # 创建一个简单的彩色方块作为默认图标
            image = Image.new("RGBA", (64, 64), (70, 130, 180, 255))  # 钢蓝色
            return image
        except Exception as e:
            logger.error(f"创建默认图标失败: {e}")
            return None    
    def quit_action(self, icon: Any, item: Any) -> None:
        """退出应用程序"""
        logger.info("用户通过托盘图标请求退出应用程序")
        self.running = False
        
        # 延迟执行关闭回调，给托盘图标时间完成操作
        def delayed_shutdown():
            try:
                if self.shutdown_callback:
                    self.shutdown_callback()
            except Exception as e:
                logger.error(f"执行关闭回调时发生错误: {e}")
            finally:
                # 确保图标停止
                try:
                    icon.stop()
                except Exception as e:
                    logger.error(f"停止托盘图标时发生错误: {e}")
        
        # 在新线程中执行关闭，避免阻塞托盘图标
        shutdown_thread = threading.Thread(target=delayed_shutdown, daemon=True)
        shutdown_thread.start()

    def show_status(self, icon: Any, item: Any) -> None:
        """显示状态信息（可扩展）"""
        logger.info("显示应用程序状态")
        # 这里可以扩展显示更多状态信息

    def create_menu(self) -> Any:
        """创建托盘菜单"""
        return pystray.Menu(
            pystray.MenuItem("MaiLauncher Backend", self.show_status, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("状态信息", self.show_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self.quit_action),
        )

    def run_tray(self) -> None:
        """运行托盘图标（在单独线程中运行）"""
        if not TRAY_AVAILABLE:
            logger.error("托盘图标库不可用，无法启动托盘功能")
            return

        try:
            image = self.create_image()
            if image is None:
                logger.error("无法创建托盘图标图像")
                return

            menu = self.create_menu()

            self.icon = pystray.Icon(
                "MaiLauncher Backend",
                image,
                menu=menu,
                title="MaiLauncher Backend - 后端服务正在运行",
            )

            self.running = True
            logger.info("托盘图标已启动")
            self.icon.run()

        except Exception as e:
            logger.error(f"启动托盘图标时发生错误: {e}", exc_info=True)

    def start(self) -> bool:
        """启动托盘图标（异步启动）"""
        if not TRAY_AVAILABLE:
            logger.warning("托盘图标功能不可用")
            return False

        try:
            # 在单独线程中启动托盘图标
            tray_thread = threading.Thread(target=self.run_tray, daemon=True)
            tray_thread.start()
            logger.info("托盘图标线程已启动")
            return True
        except Exception as e:
            logger.error(f"启动托盘图标线程失败: {e}")
            return False

    def stop(self):
        """停止托盘图标"""
        self.running = False
        if self.icon:
            try:
                self.icon.stop()
                logger.info("托盘图标已停止")
            except Exception as e:
                logger.error(f"停止托盘图标时发生错误: {e}")


def is_tray_available():
    """检查托盘图标功能是否可用"""
    return TRAY_AVAILABLE
