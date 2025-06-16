# MaiLauncher 后端 API 文档

## 目录

- [实例管理](#实例管理)
- [部署 API](#部署API)
- [系统 API](#系统API)
- [MaiBot 资源管理 API](#MaiBot资源管理API)
  - [🎨 Emoji 表情包管理](#🎨-emoji-表情包管理)
  - [👤 用户信息管理](#👤-用户信息管理)
  - [🛠️ 资源管理](#🛠️-资源管理)
  - [📊 统计和批量获取 API](#📊-统计和批量获取-api)
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

## MaiBot 资源管理 API

MaiBot 资源管理 API 提供对 MaiBot 实例数据库的 CRUD 操作，包括表情包管理和用户信息管理。

### 🎨 Emoji 表情包管理

#### 创建表情包

- **路径**: `/api/v1/resource/{instance_id}/emoji`
- **方法**: `POST`
- **描述**: 创建新的表情包记录
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "full_path": "/path/to/emoji.png",
    "format": "png",
    "emoji_hash": "abc123def456",
    "description": "开心的表情",
    "emotion": "happy",
    "record_time": 1672531200.0
}
```

- **响应**:

```json
{
    "status": "success",
    "message": "表情包创建成功",
    "data": {
        "emoji_id": 123,
        "person_id": "abc123def456"
    }
}
```

#### 根据ID获取表情包

- **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}`
- **方法**: `GET`
- **描述**: 根据表情包ID获取表情包详细信息
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `emoji_id`: 表情包ID（路径参数）
- **响应**:

```json
{
    "status": "success",
    "data": {
        "id": 123,
        "full_path": "/path/to/emoji.png",
        "format": "png",
        "emoji_hash": "abc123def456",
        "description": "开心的表情",
        "query_count": 5,
        "is_registered": 1,
        "is_banned": 0,
        "emotion": "happy",
        "record_time": 1672531200.0,
        "register_time": 1672531300.0,
        "usage_count": 10,
        "last_used_time": 1672531400.0
    }
}
```

#### 根据哈希获取表情包

- **路径**: `/api/v1/resource/{instance_id}/emoji/hash`
- **方法**: `POST`
- **描述**: 根据表情包哈希值获取表情包详细信息
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "emoji_hash": "abc123def456"
}
```

- **响应**: 同上面的获取表情包响应

#### 搜索表情包

- **路径**: `/api/v1/resource/{instance_id}/emoji/search`
- **方法**: `POST`
- **描述**: 根据条件搜索表情包
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "emotion": "happy",
    "is_registered": 1,
    "is_banned": 0,
    "format": "png",
    "description_like": "开心",
    "limit": 50,
    "offset": 0
}
```

- **响应**:

```json
{
    "status": "success",
    "data": [
        {
            "id": 123,
            "full_path": "/path/to/emoji.png",
            "format": "png",
            "emoji_hash": "abc123def456",
            "description": "开心的表情",
            "emotion": "happy",
            "usage_count": 10
        }
    ],
    "total_count": 1,
    "limit": 50,
    "offset": 0
}
```

#### 更新表情包

- **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}`
- **方法**: `PUT`
- **描述**: 更新表情包信息
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `emoji_id`: 表情包ID（路径参数）
- **请求体**:

```json
{
    "description": "更新后的描述",
    "emotion": "excited",
    "is_registered": 1
}
```

- **响应**:

```json
{
    "status": "success",
    "message": "表情包更新成功"
}
```

#### 删除表情包

- **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}`
- **方法**: `DELETE`
- **描述**: 删除表情包记录
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `emoji_id`: 表情包ID（路径参数）
- **响应**:

```json
{
    "status": "success",
    "message": "表情包删除成功"
}
```

#### 增加表情包使用次数

- **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}/usage`
- **方法**: `POST`
- **描述**: 增加表情包使用次数并更新最后使用时间
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `emoji_id`: 表情包ID（路径参数）
- **响应**:

```json
{
    "status": "success",
    "message": "使用统计更新成功"
}
```

#### 增加表情包查询次数

- **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}/query`
- **方法**: `POST`
- **描述**: 增加表情包查询次数
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `emoji_id`: 表情包ID（路径参数）
- **响应**:

```json
{
    "status": "success",
    "message": "查询统计更新成功"
}
```

### 👤 用户信息管理

#### 创建用户信息

- **路径**: `/api/v1/resource/{instance_id}/person`
- **方法**: `POST`
- **描述**: 创建新的用户信息记录
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "person_id": "user_123456",
    "platform": "qq",
    "user_id": "123456789",
    "person_name": "小明",
    "name_reason": "活泼可爱",
    "nickname": "小明同学",
    "impression": "友善的用户",
    "short_impression": "今天很开心",
    "points": "100",
    "know_times": 1672531200.0,
    "know_since": 1672531200.0,
    "last_know": 1672531200.0
}
```

- **响应**:

```json
{
    "status": "success",
    "message": "用户信息创建成功",
    "data": {
        "record_id": 456,
        "person_id": "user_123456"
    }
}
```

#### 根据记录ID获取用户信息

- **路径**: `/api/v1/resource/{instance_id}/person/record/{record_id}`
- **方法**: `GET`
- **描述**: 根据记录ID获取用户信息
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `record_id`: 记录ID（路径参数）
- **响应**:

```json
{
    "status": "success",
    "data": {
        "id": 456,
        "person_id": "user_123456",
        "person_name": "小明",
        "platform": "qq",
        "user_id": "123456789",
        "nickname": "小明同学",
        "impression": "友善的用户",
        "points": "100",
        "last_know": 1672531200.0
    }
}
```

#### 根据用户ID获取用户信息

- **路径**: `/api/v1/resource/{instance_id}/person/{person_id}`
- **方法**: `GET`
- **描述**: 根据用户唯一ID获取用户信息
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `person_id`: 用户唯一ID（路径参数）
- **响应**: 同上面的用户信息响应

#### 根据平台获取用户信息

- **路径**: `/api/v1/resource/{instance_id}/person/platform`
- **方法**: `POST`
- **描述**: 根据平台和平台用户ID获取用户信息
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "platform": "qq",
    "user_id": "123456789"
}
```

- **响应**: 同上面的用户信息响应

#### 搜索用户信息

- **路径**: `/api/v1/resource/{instance_id}/person/search`
- **方法**: `POST`
- **描述**: 根据条件搜索用户信息
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "platform": "qq",
    "person_name_like": "小明",
    "nickname_like": "同学",
    "impression_like": "友善",
    "has_person_name": true,
    "limit": 50,
    "offset": 0
}
```

- **响应**:

```json
{
    "status": "success",
    "data": [
        {
            "id": 456,
            "person_id": "user_123456",
            "person_name": "小明",
            "platform": "qq",
            "user_id": "123456789",
            "nickname": "小明同学",
            "impression": "友善的用户"
        }
    ],
    "total_count": 1,
    "limit": 50,
    "offset": 0
}
```

#### 更新用户信息

- **路径**: `/api/v1/resource/{instance_id}/person/{person_id}`
- **方法**: `PUT`
- **描述**: 更新用户信息
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `person_id`: 用户唯一ID（路径参数）
- **请求体**:

```json
{
    "person_name": "小明明",
    "impression": "非常友善的用户",
    "points": "150"
}
```

- **响应**:

```json
{
    "status": "success",
    "message": "用户信息更新成功"
}
```

#### 删除用户信息

- **路径**: `/api/v1/resource/{instance_id}/person/{person_id}`
- **方法**: `DELETE`
- **描述**: 删除用户信息记录
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `person_id`: 用户唯一ID（路径参数）
- **响应**:

```json
{
    "status": "success",
    "message": "用户信息删除成功"
}
```

#### 更新用户交互信息

- **路径**: `/api/v1/resource/{instance_id}/person/{person_id}/interaction`
- **方法**: `POST`
- **描述**: 更新用户交互信息（印象、短期印象、分数）并更新最近认识时间
- **参数**:
  - `instance_id`: 实例ID（路径参数）
  - `person_id`: 用户唯一ID（路径参数）
- **请求体**:

```json
{
    "impression_update": "今天表现很好",
    "short_impression_update": "很活跃",
    "points_update": "120"
}
```

- **响应**:

```json
{
    "status": "success",
    "message": "用户交互信息更新成功"
}
```

### 🛠️ 资源管理

#### 获取实例资源信息

- **路径**: `/api/v1/resource/{instance_id}/info`
- **方法**: `GET`
- **描述**: 获取指定实例的数据库资源信息
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **响应**:

```json
{
    "status": "success",
    "message": "获取成功",
    "data": {
        "instance_id": "abc123",
        "instance_name": "MaiBot-1",
        "instance_path": "/path/to/maibot",
        "database": {
            "path": "/path/to/maibot/data/MaiBot.db",
            "exists": true,
            "valid": true,
            "size": 1024000
        },
        "data_folder": {
            "path": "/path/to/maibot/data",
            "exists": true
        }
    }
}
```

#### 获取所有实例资源信息

- **路径**: `/api/v1/resource/all`
- **方法**: `GET`
- **描述**: 获取所有实例的数据库资源信息
- **响应**:

```json
{
    "status": "success",
    "message": "获取成功",
    "data": [
        {
            "instance_id": "abc123",
            "instance_name": "MaiBot-1",
            "database": {
                "exists": true,
                "valid": true,
                "size": 1024000
            }
        }
    ],
    "total_count": 1
}
```

### 📊 统计和批量获取 API

#### 获取表情包总数

- **路径**: `/api/v1/resource/{instance_id}/emoji/count`
- **方法**: `POST`
- **描述**: 获取表情包记录总数，支持条件筛选
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "emotion": "happy",
    "is_registered": 1,
    "is_banned": 0,
    "format": "png",
    "description_like": "开心"
}
```

- **响应**:

```json
{
    "status": "success",
    "message": "成功获取表情包总数: 25",
    "data": {
        "total_count": 25
    }
}
```

#### 批量获取表情包

- **路径**: `/api/v1/resource/{instance_id}/emoji/batch`
- **方法**: `POST`
- **描述**: 批量获取表情包数据，支持分页和条件筛选
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "batch_size": 20,
    "offset": 0,
    "emotion": "happy",
    "is_registered": 1,
    "is_banned": 0,
    "format": "png",
    "description_like": "开心"
}
```

- **响应**:

```json
{
    "status": "success",
    "message": "成功获取 20 条表情包记录",
    "data": [
        {
            "id": 123,
            "full_path": "/path/to/emoji.png",
            "format": "png",
            "emoji_hash": "abc123def456",
            "description": "开心的表情",
            "emotion": "happy",
            "usage_count": 10,
            "query_count": 5,
            "is_registered": 1,
            "is_banned": 0,
            "record_time": 1672531200.0,
            "register_time": 1672531300.0,
            "last_used_time": 1672531400.0
        }
    ],
    "limit": 20,
    "offset": 0
}
```

#### 获取用户信息总数

- **路径**: `/api/v1/resource/{instance_id}/person/count`
- **方法**: `POST`
- **描述**: 获取用户信息记录总数，支持条件筛选
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "platform": "qq",
    "person_name_like": "小明",
    "nickname_like": "同学",
    "impression_like": "友善",
    "has_person_name": true
}
```

- **响应**:

```json
{
    "status": "success",
    "message": "成功获取用户信息总数: 15",
    "data": {
        "total_count": 15
    }
}
```

#### 批量获取用户信息

- **路径**: `/api/v1/resource/{instance_id}/person/batch`
- **方法**: `POST`
- **描述**: 批量获取用户信息数据，支持分页和条件筛选
- **参数**:
  - `instance_id`: 实例ID（路径参数）
- **请求体**:

```json
{
    "batch_size": 30,
    "offset": 0,
    "platform": "qq",
    "person_name_like": "小明",
    "nickname_like": "同学",
    "impression_like": "友善",
    "has_person_name": true
}
```

- **响应**:

```json
{
    "status": "success",
    "message": "成功获取 15 条用户信息记录",
    "data": [
        {
            "id": 456,
            "person_id": "user_123456",
            "person_name": "小明",
            "name_reason": "活泼可爱",
            "platform": "qq",
            "user_id": "123456789",
            "nickname": "小明同学",
            "impression": "友善的用户",
            "short_impression": "今天很开心",
            "points": "100",
            "forgotten_points": "0",
            "info_list": "",
            "know_times": 1672531200.0,
            "know_since": 1672531200.0,
            "last_know": 1672531400.0
        }
    ],
    "limit": 30,
    "offset": 0
}
```

## WebSocket 接口

MaiLauncher 提供 WebSocket 接口用于实时终端交互，支持虚拟终端 (PTY) 连接、命令执行和日志管理。

### 连接

- **路径**: `/ws/{session_id}`
- **协议**: `WebSocket`
- **描述**: 建立 WebSocket 连接用于终端交互
- **参数**:
  - `session_id`: 会话ID，格式为 `{instance_id}_{type}`
    - `instance_id`: 实例ID
    - `type`: 终端类型，可选值：`main`, `napcat`, `nonebot`

### 消息格式

#### 客户端发送消息

**输入命令**:
```json
{
    "type": "input",
    "data": "ls -la\n"
}
```

**Ping 保持连接**:
```json
{
    "type": "ping"
}
```

**请求历史日志**:
```json
{
    "type": "request_history",
    "from_time": 1672531200000,
    "to_time": 1672534800000
}
```

**调整终端大小**:
```json
{
    "type": "resize",
    "cols": 120,
    "rows": 40
}
```

#### 服务端返回消息

**终端输出**:
```json
{
    "type": "output",
    "data": "total 8\ndrwxr-xr-x 3 user user 4096 Jan  1 12:00 .\n"
}
```

**状态信息**:
```json
{
    "type": "status",
    "message": "已连接到 main 终端"
}
```

**历史日志**:
```json
{
    "type": "history_logs",
    "logs": [
        {
            "timestamp": 1672531200000,
            "data": "Command executed successfully\n"
        }
    ],
    "session_id": "abc123_main"
}
```

**错误信息**:
```json
{
    "type": "error",
    "message": "未找到实例 'invalid_id'"
}
```

**Pong 响应**:
```json
{
    "type": "pong"
}
```

### 使用示例

```javascript
// 连接到实例 abc123 的主终端
const ws = new WebSocket('ws://localhost:8080/ws/abc123_main');

ws.onopen = function() {
    console.log('WebSocket 连接已建立');
    
    // 发送命令
    ws.send(JSON.stringify({
        type: 'input',
        data: 'echo "Hello World"\n'
    }));
};

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    
    if (message.type === 'output') {
        console.log('终端输出:', message.data);
    } else if (message.type === 'status') {
        console.log('状态:', message.message);
    }
};

ws.onerror = function(error) {
    console.error('WebSocket 错误:', error);
};

ws.onclose = function() {
    console.log('WebSocket 连接已关闭');
};
```

