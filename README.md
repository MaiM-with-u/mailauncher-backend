# mailauncher-backend
MaiLauncher启动器后端

## 概述

MaiLauncher后端是一个使用FastAPI构建的Python应用程序，旨在管理MaiBot实例的部署和生命周期。它提供了一个HTTP API和WebSocket接口，用于与前端或其他服务进行交互。

## 主要功能

- **实例管理**: 启动、停止、重启和删除MaiBot实例。
- **版本部署**: 部署指定版本的MaiBot，包括其依赖的服务（如NapCat, NoneBot-ada）。
- **状态监控**: 获取实例的运行状态、统计信息和系统性能指标。
- **实时日志**: 通过WebSocket提供实时的安装和实例运行日志。
- **配置管理**: 通过 `config.toml` 文件进行灵活配置。

## 技术栈

- **后端框架**: FastAPI
- **数据库**: SQLite (通过SQLAlchemy进行ORM)
- **异步处理**: asyncio
- **服务器**: Uvicorn

## 项目结构

```
mailauncher-backend/
├── backend_api.md          # API接口文档
├── config.toml             # 主配置文件
├── LICENSE                 # 项目许可证 (GNU General Public License v3)
├── main.py                 # FastAPI应用入口点
├── README.md               # 项目说明文件
├── data/
│   └── MaiLauncher.db      # SQLite数据库文件
├── logs/                   # 日志文件目录
│   ├── app.log             # 应用主日志
│   └── ...                 # 其他按日期生成的日志文件
├── src/
│   ├── modules/            # 核心功能模块
│   │   ├── deploy_api.py
│   │   ├── instance_api.py
│   │   ├── instance_manager.py
│   │   ├── system.py
│   │   └── websocket_manager.py
│   ├── tools/              # 辅助工具脚本
│   │   └── deploy_version.py
│   └── utils/              # 通用工具和辅助函数
│       ├── config.py
│       ├── database_model.py
│       ├── database.py
│       ├── generate_instance_id.py
│       ├── logger.py
│       └── server.py
└── template/
    └── config_template.toml # 配置文件模板
```

## API 文档

详细的API接口说明请参见 `backend_api.md` 文件。

主要的API端点包括：

- 实例管理: `/api/v1/instances`, `/api/v1/instance/{id}/start`, 等。
- 部署API: `/api/v1/deploy/versions`, `/api/v1/deploy/deploy`, 等。
- 系统API: `/api/v1/system/health`, `/api/v1/system/metrics`, 等。
- WebSocket接口: `/api/v1/ws/{session_id}` (用于通用WebSocket通信), 以及特定的日志WebSocket端点。

根路径 `/` 提供一个简单的HTML页面，包含指向API文档的链接。

## 配置

项目的主要配置在 `config.toml` 文件中。一个配置模板 `template/config_template.toml` 可用于初始化配置。

关键配置项包括：
- `[server]`: 服务器主机 (`host`)、端口 (`port`) 和API前缀 (`api_prefix`)。
- `[debug]`: 日志级别 (`level`)。

## 如何运行

1.  **安装依赖**: 
    ```bash
    pip install -r requirements.txt
    ```
2.  **配置**: 复制 `template/config_template.toml` 到项目根目录并重命名为 `config.toml`，然后根据需要修改配置。
3.  **启动服务**:
    ```bash
    python main.py
    ```
    服务将在 `config.toml` 中配置的主机和端口上启动 (默认为 `http://localhost:23456`)。

## 日志

应用程序日志记录在 `logs/` 目录下。主应用日志为 `app.log`，并且会按日期生成单独的日志文件。

## 许可证

本项目采用 [GNU General Public License v3.0](LICENSE) 授权。
