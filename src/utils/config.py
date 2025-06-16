class Config:
    # 硬编码配置值，来源于config.toml
    version: str = "0.0.1"
    server_host: str = "localhost"
    server_port: int = 23456
    debug_level: str = "DEBUG"
    api_prefix: str = "/api/v1"

    def __init__(self):
        pass


global_config = Config()
