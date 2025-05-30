# MaiLauncher 后端 API 文档

## 目录

- [实例管理](#实例管理)
- [部署 API](#部署API)
- [日志 API](#日志API)
- [系统 API](#系统API)
- [WebSocket 接口](#WebSocket接口)

## 实例管理

### 获取实例列表

- **路径**: `/api/v1/instances`
- **方法**: `GET`
- **描述**: 获取所有 Bot 实例的列表
- **响应**:

```json
{
  "instances": [
    {
      "id": "a2fe529b51999fc2d45df5196c6c50a46a608fa1",
      "name": "maibot-stable-1",
      "status": "running",
      "installedAt": "1747404418536",
      "path": "D:\\MaiBot\\MaiBot-1",
      "port": 8000,
      "services": [
        {
          "name": "napcat",
          "path": "D:\\MaiBot\\MaiBot-1\\napcat",
          "status": "running",
          "port": 8095
        },
        {
          "name": "nonebot-ada",
          "path": "D:\\MaiBot\\MaiBot-1\\nonebot-ada",
          "status": "stopped",
          "port": 18002
        }
      ]
      "version": "0.6.3",
    }
  ],
  "success": true
}
```

### 获取实例统计信息

- **路径**: `/api/v1/instances/stats`
- **方法**: `GET`
- **描述**: 获取实例统计数据，如总数、运行中的数量等
- **响应**:

```json
{
  "total": 3,
  "running": 2,
  "stopped": 1
}
```

### 启动实例

- **路径**: `/api/v1/instance/{id}/start`
- **方法**: `GET`
- **描述**: 启动指定的实例
- **参数**:
  - `id`: 实例ID（路径参数）
- **响应**:

```json
{
  "success": true,
  "message": "实例 {id.name} 已启动"
}
```

### 停止实例

- **路径**: `/api/v1/instance/{id}/stop`
- **方法**: `GET`
- **描述**: 停止指定的实例
- **参数**:
  - `id`: 实例ID（路径参数）
- **响应**:

```json
{
  "success": true,
  "message": "实例 {id.name} 已停止"
}
```

### 重启实例

- **路径**: `/api/v1/instance/{id}/restart`
- **方法**: `GET`
- **描述**: 重启指定的实例
- **参数**:
  - `id`: 实例ID（路径参数）
- **响应**:

```json
{
  "success": true,
  "message": "实例 {id.name} 已重启"
}
```

### 删除实例

- **路径**: `/api/v1/instance/{id}/delete`
- **方法**: `DELETE`
- **描述**: 删除指定的实例
- **参数**:
  - `id`: 实例ID（路径参数）
- **响应**:

```json
{
  "success": true,
  "message": "实例 {id.name} 已删除"
}
```

### 启动 NapCat 服务

- **路径**: `/api/v1/start/{id}/napcat`
- **方法**: `GET`
- **描述**: 为指定实例启动 NapCat 服务
- **参数**:
  - `id`: 实例ID（路径参数）
- **响应**:

```json
{
  "success": true,
  "message": "实例 {id.name} 的NapCat服务已启动"
}
```

### 启动 Ncpcat-ada 服务

- **路径**: `/api/v1/start/{id}/nonebot`
- **方法**: `GET`
- **描述**: 为指定实例启动 Napcat-ada 服务
- **参数**:
  - `id`: 实例ID（路径参数）
- **响应**:

```json
{
  "success": true,
  "message": "实例 {id.name} 的Napcat-ada服务已启动"
}
```



## 部署 API

### 获取可用版本

- **路径**: `/api/v1/deploy/versions`
- **方法**: `GET`
- **描述**: 获取可用于部署的版本列表
- **响应**:

```json
{
  "versions": ["latest", "main",  "v0.6.3", "v0.6.2", "v0.6.1"]
}
```

### 获取可以部署的服务列表
- **路径**: `/api/v1/deploy/services`
- **方法**: `GET`
- **描述**: 获取可以部署的服务列表
- **响应**:

```json
{
  "services": [
    {
      "name": "napcat",
      "description": "NapCat 服务"
    },
    {
      "name": "nonebot-ada",
      "description": "NoneBot-ada 服务"
    },
    {
      "name": "nonebot",
      "description": "NoneBot 服务"
    }
  ]
}
```


### 部署版本

- **路径**: `/api/v1/deploy/deploy`
- **方法**: `POST`
- **描述**: 部署指定版本的 MaiBot
- **请求体**:

```json
{
  "instance_name": "maibot-instance-1",
  "install_services":[
    {
      "name": "napcat",
      "path": "D:\\MaiBot\\MaiBot-1\\napcat",
      "port": 8095,
      "run_cmd": "python main.py"
    },
    {
      "name": "nonebot-ada",
      "path": "D:\\MaiBot\\MaiBot-1\\nonebot-ada",
      "port": 18002,
      "run_cmd": "python bot.py"
    }
  ],
  "install_path": "D:\\MaiBot\\MaiBot-1",
  "port": 8000,
  "version": "latest"
}
```

- **响应**:

```json
{
  "success": true,
  "message": "部署任务已提交",
  "instance_id": "a2fe529b51999fc2d45df5196c6c50a46a608fa1"
}
```

### 检查安装状态

- **路径**: `/api/v1/install-status/{instanceId}`
- **方法**: `GET`
- **描述**: 检查安装进度和状态
- **参数**:
  - `instanceId`: 实例ID（路径参数）
- **响应**:

```json
{
  "status": "installing",
  "progress": 50,
  "message": "正在安装依赖...",
  "services_install_status":[
    {
      "name": "napcat",
      "status": "installing",
      "progress": 50,
      "message": "正在安装 NapCat"
    },
    {
      "name": "nonebot-ada",
      "status": "installing",
      "progress": 30,
      "message": "正在安装 NoneBot-ada"
    }
  ],
}
```

### 添加现有实例

- **路径**: `/api/v1/instances/add`
- **方法**: `POST`
- **描述**: 添加硬盘中已有的麦麦实例到系统中。该API不会进行实际的部署，而是验证指定路径中是否存在麦麦实例，然后将其添加到数据库中进行管理。
- **请求体**:

```json
{
  "instance_name": "maibot-existing-1",
  "install_services":[
    {
      "name": "napcat",
      "path": "D:\\MaiBot\\MaiBot-existing\\napcat",
      "port": 8095,
      "run_cmd": "python main.py"
    },
    {
      "name": "nonebot-ada",
      "path": "D:\\MaiBot\\MaiBot-existing\\nonebot-ada",
      "port": 18002,
      "run_cmd": "python bot.py"
    }
  ],
  "install_path": "D:\\MaiBot\\MaiBot-existing",
  "port": 8000,
  "version": "0.6.3"
}
```

- **响应**:

```json
{
  "success": true,
  "message": "现有实例 maibot-existing-1 已成功添加到系统中。",
  "instance_id": "b3fe529b51999fc2d45df5196c6c50a46a608fb2"
}
```

- **错误响应**:

```json
{
  "detail": "指定的安装路径不存在: D:\\MaiBot\\MaiBot-nonexistent"
}
```

```json
{
  "detail": "服务 napcat 的路径不存在: D:\\MaiBot\\MaiBot-existing\\napcat"
}
```

```json
{
  "detail": "实例 'maibot-existing-1' (ID: b3fe529b51999fc2d45df5196c6c50a46a608fb2) 已存在。"
}
```



## 系统 API

### 健康检查

- **路径**: `/api/v1/system/health`
- **方法**: `GET`
- **描述**: 检查后端服务的健康状态
- **响应**:

```json
{
  "status": "success",
  "time": "2023-10-15T12:00:00Z"
}
```

<!-- ### 获取系统状态

- **路径**: `/api/v1/status`
- **方法**: `GET`
- **描述**: 获取系统各组件的状态
- **响应**:

```json
{
  "mongodb": { "status": "running", "info": "本地实例" },
  "napcat": { "status": "running", "info": "端口 8095" },
  "napcat_ada": { "status": "stopped", "info": "" },
  "maibot": { "status": "stopped", "info": "" }
}
``` -->

### 获取系统性能指标

- **路径**: `/api/v1/system/metrics`
- **方法**: `GET`
- **描述**: 获取系统性能指标，如 CPU、内存使用率等
- **响应**:

```json
{
    "status": "success",
    "data": {
        "system_info": {
            "system": "Windows",
            "release": "11",
            "version": "10.0.26100",
            "machine": "AMD64",
            "processor": "Intel(R) Core(TM) i9-14900HX "
        },
        "python_version": "3.12.4 (tags/v3.12.4:8e8a4ba, Jun  6 2024, 19:30:16) [MSC v.1940 64 bit (AMD64)]",
        "cpu_usage_percent": 18.8,
        "memory_usage": {
            "total_mb": 32386.52,
            "available_mb": 10222.87,
            "percent": 68.4,
            "used_mb": 22163.65,
            "free_mb": 10222.87
        },
        "disk_usage_root": {
            "total_gb": 726.17,
            "used_gb": 506.15,
            "free_gb": 220.02,
            "percent": 69.7
        }
    }
}
```

## WebSocket 接口

### 安装日志 WebSocket

- **路径**: `/api/v1/logs/ws`
- **描述**: 通过 WebSocket 连接接收实时安装日志
- **消息格式**:

```json
{
  "time": "2023-10-15 10:00:00",
  "level": "INFO",
  "message": "正在安装依赖...",
  "source": "install"
}
```

### 实例日志 WebSocket

- **路径**: `/api/v1/logs/instance/{id}/ws`
- **描述**: 通过 WebSocket 连接接收指定实例的实时日志
- **参数**:
  - `id`: 实例ID（路径参数）

