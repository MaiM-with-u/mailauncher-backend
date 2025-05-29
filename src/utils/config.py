import os
import sys
import tomllib
import shutil
from loguru import logger


class Config:
    server_host: str = "localhost"
    server_port: int = 8095
    debug_level: str = "INFO"
    api_prefix: str = "/api/v1"

    def __init__(self):
        self._get_config_path()

    def _get_config_path(self):
        self.config_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "config.toml")
        )    
    def load_config(self):  # sourcery skip: extract-method, move-assign
        include_configs = ["inner", "server", "debug"]
        if os.path.exists(self.config_path):
            with open(self.config_path, "rb") as f:
                try:
                    raw_config = tomllib.load(f)
                except tomllib.TOMLDecodeError as e:
                    logger.critical(
                        f"配置文件bot_config.toml填写有误，请检查第{e.lineno}行第{e.colno}处：{e.msg}"
                    )
                    sys.exit(1)
            for key in include_configs:
                if key not in raw_config:
                    logger.error(f"配置文件中缺少必需的字段: '{key}'")
                    sys.exit(1)
            self.version = raw_config["inner"].get("version", "0.0.1")
            self.server_host = raw_config["server"].get("host", "localhost")
            self.server_port = raw_config["server"].get("port", 8095)
            self.debug_level = raw_config["debug"].get("level", "INFO")
            self.api_prefix = raw_config["server"].get("api_prefix", "/api/v1")
        else:
            logger.error("配置文件不存在！")
            logger.info("正在创建配置文件...")
            shutil.copy(
                os.path.join(self.root_path, "template", "config_template.toml"),
                os.path.join(self.root_path, "config.toml"),
            )
            logger.info("配置文件创建成功，请修改配置文件后重启程序。")
            sys.exit(1)


global_config = Config()
global_config.load_config()
