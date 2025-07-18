from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
import tomlkit
from dotenv import dotenv_values
from src.modules.maibot_res_manager import maibot_resource_manager
from src.modules.instance_manager import instance_manager
from src.utils.logger import get_module_logger

logger = get_module_logger("MaiBot资源API")
router = APIRouter()


# ================ Pydantic 模型定义 ================


# 基础响应模型
class BaseResponse(BaseModel):
    status: str = Field(..., description="响应状态: success 或 failed")
    message: Optional[str] = Field(None, description="响应消息")


class DataResponse(BaseResponse):
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")


class ListResponse(BaseResponse):
    data: Optional[List[Dict[str, Any]]] = Field(None, description="响应数据列表")
    total_count: Optional[int] = Field(None, description="总记录数")
    limit: Optional[int] = Field(None, description="每页记录数")
    offset: Optional[int] = Field(None, description="偏移量")


# ================ Emoji 表情包相关模型 ================


class EmojiCreateRequest(BaseModel):
    full_path: str = Field(..., description="表情包完整路径")
    format: str = Field(..., description="表情包格式")
    emoji_hash: str = Field(..., description="表情包哈希")
    description: Optional[str] = Field("", description="表情包描述")
    emotion: Optional[str] = Field("", description="表情包蕴含的情感")
    record_time: Optional[float] = Field(None, description="表情包记录时间")


class EmojiUpdateRequest(BaseModel):
    full_path: Optional[str] = Field(None, description="表情包完整路径")
    format: Optional[str] = Field(None, description="表情包格式")
    emoji_hash: Optional[str] = Field(None, description="表情包哈希")
    description: Optional[str] = Field(None, description="表情包描述")
    emotion: Optional[str] = Field(None, description="表情包蕴含的情感")
    is_registered: Optional[int] = Field(None, description="表情包是否被注册")
    is_banned: Optional[int] = Field(None, description="表情包是否被禁用")


class EmojiSearchRequest(BaseModel):
    emotion: Optional[str] = Field(None, description="情感筛选")
    is_registered: Optional[int] = Field(None, description="是否注册 (0/1)")
    is_banned: Optional[int] = Field(None, description="是否禁用 (0/1)")
    format: Optional[str] = Field(None, description="格式筛选")
    description_like: Optional[str] = Field(None, description="描述模糊搜索")
    limit: Optional[int] = Field(100, description="限制返回数量")
    offset: Optional[int] = Field(0, description="偏移量")


class EmojiHashRequest(BaseModel):
    emoji_hash: str = Field(..., description="表情包哈希")


# ================ PersonInfo 用户信息相关模型 ================


class PersonInfoCreateRequest(BaseModel):
    person_id: str = Field(..., description="用户唯一id")
    platform: str = Field(..., description="平台")
    user_id: str = Field(..., description="用户平台id")
    person_name: Optional[str] = Field("", description="bot给用户的起名")
    name_reason: Optional[str] = Field("", description="起名原因")
    nickname: Optional[str] = Field("", description="用户平台昵称")
    impression: Optional[str] = Field("", description="印象")
    short_impression: Optional[str] = Field("", description="短期印象")
    points: Optional[str] = Field("", description="分数")
    forgotten_points: Optional[str] = Field("", description="遗忘分数")
    info_list: Optional[str] = Field("", description="信息列表")
    know_times: Optional[float] = Field(None, description="认识时间")
    know_since: Optional[float] = Field(None, description="认识瞬间描述")
    last_know: Optional[float] = Field(None, description="最近一次认识")


class PersonInfoUpdateRequest(BaseModel):
    person_name: Optional[str] = Field(None, description="bot给用户的起名")
    name_reason: Optional[str] = Field(None, description="起名原因")
    platform: Optional[str] = Field(None, description="平台")
    user_id: Optional[str] = Field(None, description="用户平台id")
    nickname: Optional[str] = Field(None, description="用户平台昵称")
    impression: Optional[str] = Field(None, description="印象")
    short_impression: Optional[str] = Field(None, description="短期印象")
    points: Optional[str] = Field(None, description="分数")
    forgotten_points: Optional[str] = Field(None, description="遗忘分数")
    info_list: Optional[str] = Field(None, description="信息列表")
    know_times: Optional[float] = Field(None, description="认识时间")
    know_since: Optional[float] = Field(None, description="认识瞬间描述")
    last_know: Optional[float] = Field(None, description="最近一次认识")


class PersonInfoSearchRequest(BaseModel):
    platform: Optional[str] = Field(None, description="平台筛选")
    person_name_like: Optional[str] = Field(None, description="用户名模糊搜索")
    nickname_like: Optional[str] = Field(None, description="昵称模糊搜索")
    impression_like: Optional[str] = Field(None, description="印象模糊搜索")
    has_person_name: Optional[bool] = Field(None, description="是否有用户名")
    limit: Optional[int] = Field(100, description="限制返回数量")
    offset: Optional[int] = Field(0, description="偏移量")


class PersonInfoInteractionRequest(BaseModel):
    impression_update: Optional[str] = Field(None, description="新的印象信息")
    short_impression_update: Optional[str] = Field(None, description="新的短期印象信息")
    points_update: Optional[str] = Field(None, description="新的分数信息")


class PlatformUserRequest(BaseModel):
    platform: str = Field(..., description="平台")
    user_id: str = Field(..., description="用户平台id")


# ================ 批量获取相关模型 ================


class BatchRequest(BaseModel):
    batch_size: Optional[int] = Field(50, description="批次大小，默认50")
    offset: Optional[int] = Field(0, description="偏移量，默认0")


class EmojiCountRequest(BaseModel):
    emotion: Optional[str] = Field(None, description="情感筛选")
    is_registered: Optional[int] = Field(None, description="是否注册 (0/1)")
    is_banned: Optional[int] = Field(None, description="是否禁用 (0/1)")
    format: Optional[str] = Field(None, description="格式筛选")
    description_like: Optional[str] = Field(None, description="描述模糊搜索")


class EmojiBatchRequest(BatchRequest):
    emotion: Optional[str] = Field(None, description="情感筛选")
    is_registered: Optional[int] = Field(None, description="是否注册 (0/1)")
    is_banned: Optional[int] = Field(None, description="是否禁用 (0/1)")
    format: Optional[str] = Field(None, description="格式筛选")
    description_like: Optional[str] = Field(None, description="描述模糊搜索")


class PersonInfoCountRequest(BaseModel):
    platform: Optional[str] = Field(None, description="平台筛选")
    person_name_like: Optional[str] = Field(None, description="用户名模糊搜索")
    nickname_like: Optional[str] = Field(None, description="昵称模糊搜索")
    impression_like: Optional[str] = Field(None, description="印象模糊搜索")
    has_person_name: Optional[bool] = Field(None, description="是否有用户名")


class PersonInfoBatchRequest(BatchRequest):
    platform: Optional[str] = Field(None, description="平台筛选")
    person_name_like: Optional[str] = Field(None, description="用户名模糊搜索")
    nickname_like: Optional[str] = Field(None, description="昵称模糊搜索")
    impression_like: Optional[str] = Field(None, description="印象模糊搜索")
    has_person_name: Optional[bool] = Field(None, description="是否有用户名")


# ================ 配置文件相关模型 ================


class ConfigRequest(BaseModel):
    instance_id: str = Field(..., description="实例ID")


class ConfigUpdateRequest(BaseModel):
    instance_id: str = Field(..., description="实例ID")
    config_data: Dict[str, Any] = Field(..., description="配置数据")


class EnvUpdateRequest(BaseModel):
    instance_id: str = Field(..., description="实例ID")
    env_data: Dict[str, str] = Field(..., description="环境变量数据")


# ================ Emoji 表情包 API ================


@router.post("/resource/{instance_id}/emoji", response_model=DataResponse)
async def create_emoji(instance_id: str, request: EmojiCreateRequest):
    """
    创建新的表情包记录

    - **路径**: `/api/v1/resource/{instance_id}/emoji`
    - **方法**: `POST`
    - **描述**: 创建新的表情包记录
    """
    logger.info(f"收到创建表情包请求，实例ID: {instance_id}")

    try:
        result = maibot_resource_manager.create_emoji(
            instance_id=instance_id, emoji_data=request.dict()
        )

        logger.info(f"表情包创建结果: {result}")
        return DataResponse(**result)

    except Exception as e:
        logger.error(f"创建表情包时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建表情包失败: {str(e)}")


@router.get("/resource/{instance_id}/emoji/{emoji_id}", response_model=DataResponse)
async def get_emoji_by_id(instance_id: str, emoji_id: int):
    """
    根据ID获取表情包信息

    - **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}`
    - **方法**: `GET`
    - **描述**: 根据表情包ID获取表情包详细信息
    """
    logger.info(f"收到获取表情包请求，实例ID: {instance_id}, 表情包ID: {emoji_id}")

    try:
        result = maibot_resource_manager.get_emoji_by_id(
            instance_id=instance_id, emoji_id=emoji_id
        )

        logger.info(f"表情包获取结果: {result}")
        return DataResponse(**result)

    except Exception as e:
        logger.error(f"获取表情包时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取表情包失败: {str(e)}")


@router.post("/resource/{instance_id}/emoji/hash", response_model=DataResponse)
async def get_emoji_by_hash(instance_id: str, request: EmojiHashRequest):
    """
    根据哈希值获取表情包信息

    - **路径**: `/api/v1/resource/{instance_id}/emoji/hash`
    - **方法**: `POST`
    - **描述**: 根据表情包哈希值获取表情包详细信息
    """
    logger.info(
        f"收到根据哈希获取表情包请求，实例ID: {instance_id}, 哈希: {request.emoji_hash}"
    )

    try:
        result = maibot_resource_manager.get_emoji_by_hash(
            instance_id=instance_id, emoji_hash=request.emoji_hash
        )

        logger.info(f"表情包获取结果: {result}")
        return DataResponse(**result)

    except Exception as e:
        logger.error(f"根据哈希获取表情包时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取表情包失败: {str(e)}")


@router.post("/resource/{instance_id}/emoji/search", response_model=ListResponse)
async def search_emojis(instance_id: str, request: EmojiSearchRequest):
    """
    搜索表情包

    - **路径**: `/api/v1/resource/{instance_id}/emoji/search`
    - **方法**: `POST`
    - **描述**: 根据条件搜索表情包
    """
    logger.info(f"收到搜索表情包请求，实例ID: {instance_id}")

    try:
        # 过滤掉 None 值的参数
        filters = {
            k: v
            for k, v in request.dict().items()
            if v is not None and k not in ["limit", "offset"]
        }

        result = maibot_resource_manager.search_emojis(
            instance_id=instance_id,
            filters=filters,
            limit=request.limit or 100,
            offset=request.offset or 0,
        )

        logger.info(f"表情包搜索结果: 找到 {len(result.get('data', []))} 条记录")
        return ListResponse(**result)

    except Exception as e:
        logger.error(f"搜索表情包时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"搜索表情包失败: {str(e)}")


@router.put("/resource/{instance_id}/emoji/{emoji_id}", response_model=BaseResponse)
async def update_emoji(instance_id: str, emoji_id: int, request: EmojiUpdateRequest):
    """
    更新表情包信息

    - **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}`
    - **方法**: `PUT`
    - **描述**: 更新表情包信息
    """
    logger.info(f"收到更新表情包请求，实例ID: {instance_id}, 表情包ID: {emoji_id}")

    try:
        # 过滤掉 None 值的参数
        update_data = {k: v for k, v in request.dict().items() if v is not None}

        if not update_data:
            return BaseResponse(status="failed", message="没有提供要更新的字段")

        result = maibot_resource_manager.update_emoji(
            instance_id=instance_id, emoji_id=emoji_id, update_data=update_data
        )

        logger.info(f"表情包更新结果: {result}")
        return BaseResponse(**result)

    except Exception as e:
        logger.error(f"更新表情包时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新表情包失败: {str(e)}")


@router.delete("/resource/{instance_id}/emoji/{emoji_id}", response_model=BaseResponse)
async def delete_emoji(instance_id: str, emoji_id: int):
    """
    删除表情包记录

    - **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}`
    - **方法**: `DELETE`
    - **描述**: 删除表情包记录
    """
    logger.info(f"收到删除表情包请求，实例ID: {instance_id}, 表情包ID: {emoji_id}")

    try:
        result = maibot_resource_manager.delete_emoji(
            instance_id=instance_id, emoji_id=emoji_id
        )

        logger.info(f"表情包删除结果: {result}")
        return BaseResponse(**result)

    except Exception as e:
        logger.error(f"删除表情包时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除表情包失败: {str(e)}")


@router.post(
    "/resource/{instance_id}/emoji/{emoji_id}/usage", response_model=BaseResponse
)
async def increment_emoji_usage(instance_id: str, emoji_id: int):
    """
    增加表情包使用次数

    - **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}/usage`
    - **方法**: `POST`
    - **描述**: 增加表情包使用次数并更新最后使用时间
    """
    logger.info(
        f"收到增加表情包使用次数请求，实例ID: {instance_id}, 表情包ID: {emoji_id}"
    )

    try:
        result = maibot_resource_manager.increment_emoji_usage(
            instance_id=instance_id, emoji_id=emoji_id
        )

        logger.info(f"表情包使用次数更新结果: {result}")
        return BaseResponse(**result)

    except Exception as e:
        logger.error(f"更新表情包使用次数时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新表情包使用次数失败: {str(e)}")


@router.post(
    "/resource/{instance_id}/emoji/{emoji_id}/query", response_model=BaseResponse
)
async def increment_emoji_query(instance_id: str, emoji_id: int):
    """
    增加表情包查询次数

    - **路径**: `/api/v1/resource/{instance_id}/emoji/{emoji_id}/query`
    - **方法**: `POST`
    - **描述**: 增加表情包查询次数
    """
    logger.info(
        f"收到增加表情包查询次数请求，实例ID: {instance_id}, 表情包ID: {emoji_id}"
    )

    try:
        result = maibot_resource_manager.increment_emoji_query(
            instance_id=instance_id, emoji_id=emoji_id
        )

        logger.info(f"表情包查询次数更新结果: {result}")
        return BaseResponse(**result)

    except Exception as e:
        logger.error(f"更新表情包查询次数时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新表情包查询次数失败: {str(e)}")


# ================ PersonInfo 用户信息 API ================


@router.post("/resource/{instance_id}/person", response_model=DataResponse)
async def create_person_info(instance_id: str, request: PersonInfoCreateRequest):
    """
    创建新的用户信息记录

    - **路径**: `/api/v1/resource/{instance_id}/person`
    - **方法**: `POST`
    - **描述**: 创建新的用户信息记录
    """
    logger.info(f"收到创建用户信息请求，实例ID: {instance_id}")

    try:
        result = maibot_resource_manager.create_person_info(
            instance_id=instance_id, person_data=request.dict()
        )

        logger.info(f"用户信息创建结果: {result}")
        return DataResponse(**result)

    except Exception as e:
        logger.error(f"创建用户信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建用户信息失败: {str(e)}")


@router.get(
    "/resource/{instance_id}/person/record/{record_id}", response_model=DataResponse
)
async def get_person_info_by_record_id(instance_id: str, record_id: int):
    """
    根据记录ID获取用户信息

    - **路径**: `/api/v1/resource/{instance_id}/person/record/{record_id}`
    - **方法**: `GET`
    - **描述**: 根据记录ID获取用户信息
    """
    logger.info(f"收到获取用户信息请求，实例ID: {instance_id}, 记录ID: {record_id}")

    try:
        result = maibot_resource_manager.get_person_info_by_id(
            instance_id=instance_id, record_id=record_id
        )

        logger.info(f"用户信息获取结果: {result}")
        return DataResponse(**result)

    except Exception as e:
        logger.error(f"获取用户信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取用户信息失败: {str(e)}")


@router.get("/resource/{instance_id}/person/{person_id}", response_model=DataResponse)
async def get_person_info_by_person_id(instance_id: str, person_id: str):
    """
    根据用户ID获取用户信息

    - **路径**: `/api/v1/resource/{instance_id}/person/{person_id}`
    - **方法**: `GET`
    - **描述**: 根据用户唯一ID获取用户信息
    """
    logger.info(f"收到获取用户信息请求，实例ID: {instance_id}, 用户ID: {person_id}")

    try:
        result = maibot_resource_manager.get_person_info_by_person_id(
            instance_id=instance_id, person_id=person_id
        )

        logger.info(f"用户信息获取结果: {result}")
        return DataResponse(**result)

    except Exception as e:
        logger.error(f"获取用户信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取用户信息失败: {str(e)}")


@router.post("/resource/{instance_id}/person/platform", response_model=DataResponse)
async def get_person_info_by_platform_user(
    instance_id: str, request: PlatformUserRequest
):
    """
    根据平台和用户ID获取用户信息

    - **路径**: `/api/v1/resource/{instance_id}/person/platform`
    - **方法**: `POST`
    - **描述**: 根据平台和平台用户ID获取用户信息
    """
    logger.info(f"收到根据平台获取用户信息请求，实例ID: {instance_id}")

    try:
        result = maibot_resource_manager.get_person_info_by_platform_user(
            instance_id=instance_id, platform=request.platform, user_id=request.user_id
        )

        logger.info(f"用户信息获取结果: {result}")
        return DataResponse(**result)

    except Exception as e:
        logger.error(f"根据平台获取用户信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取用户信息失败: {str(e)}")


@router.post("/resource/{instance_id}/person/search", response_model=ListResponse)
async def search_person_info(instance_id: str, request: PersonInfoSearchRequest):
    """
    搜索用户信息

    - **路径**: `/api/v1/resource/{instance_id}/person/search`
    - **方法**: `POST`
    - **描述**: 根据条件搜索用户信息
    """
    logger.info(f"收到搜索用户信息请求，实例ID: {instance_id}")

    try:
        # 过滤掉 None 值的参数
        filters = {
            k: v
            for k, v in request.dict().items()
            if v is not None and k not in ["limit", "offset"]
        }

        result = maibot_resource_manager.search_person_info(
            instance_id=instance_id,
            filters=filters,
            limit=request.limit or 100,
            offset=request.offset or 0,
        )

        logger.info(f"用户信息搜索结果: 找到 {len(result.get('data', []))} 条记录")
        return ListResponse(**result)

    except Exception as e:
        logger.error(f"搜索用户信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"搜索用户信息失败: {str(e)}")


@router.put("/resource/{instance_id}/person/{person_id}", response_model=BaseResponse)
async def update_person_info(
    instance_id: str, person_id: str, request: PersonInfoUpdateRequest
):
    """
    更新用户信息

    - **路径**: `/api/v1/resource/{instance_id}/person/{person_id}`
    - **方法**: `PUT`
    - **描述**: 更新用户信息
    """
    logger.info(f"收到更新用户信息请求，实例ID: {instance_id}, 用户ID: {person_id}")

    try:
        # 过滤掉 None 值的参数
        update_data = {k: v for k, v in request.dict().items() if v is not None}

        if not update_data:
            return BaseResponse(status="failed", message="没有提供要更新的字段")

        result = maibot_resource_manager.update_person_info(
            instance_id=instance_id, person_id=person_id, update_data=update_data
        )

        logger.info(f"用户信息更新结果: {result}")
        return BaseResponse(**result)

    except Exception as e:
        logger.error(f"更新用户信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新用户信息失败: {str(e)}")


@router.delete(
    "/resource/{instance_id}/person/{person_id}", response_model=BaseResponse
)
async def delete_person_info(instance_id: str, person_id: str):
    """
    删除用户信息记录

    - **路径**: `/api/v1/resource/{instance_id}/person/{person_id}`
    - **方法**: `DELETE`
    - **描述**: 删除用户信息记录
    """
    logger.info(f"收到删除用户信息请求，实例ID: {instance_id}, 用户ID: {person_id}")

    try:
        result = maibot_resource_manager.delete_person_info(
            instance_id=instance_id, person_id=person_id
        )

        logger.info(f"用户信息删除结果: {result}")
        return BaseResponse(**result)

    except Exception as e:
        logger.error(f"删除用户信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除用户信息失败: {str(e)}")


@router.post(
    "/resource/{instance_id}/person/{person_id}/interaction",
    response_model=BaseResponse,
)
async def update_person_interaction(
    instance_id: str, person_id: str, request: PersonInfoInteractionRequest
):
    """
    更新用户交互信息

    - **路径**: `/api/v1/resource/{instance_id}/person/{person_id}/interaction`
    - **方法**: `POST`
    - **描述**: 更新用户交互信息（印象、短期印象、分数）并更新最近认识时间
    """
    logger.info(f"收到更新用户交互信息请求，实例ID: {instance_id}, 用户ID: {person_id}")

    try:
        result = maibot_resource_manager.update_person_interaction(
            instance_id=instance_id,
            person_id=person_id,
            impression_update=request.impression_update,
            short_impression_update=request.short_impression_update,
            points_update=request.points_update,
        )

        logger.info(f"用户交互信息更新结果: {result}")
        return BaseResponse(**result)

    except Exception as e:
        logger.error(f"更新用户交互信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新用户交互信息失败: {str(e)}")


# ================ 资源管理 API ================


@router.get("/resource/{instance_id}/info", response_model=DataResponse)
async def get_instance_resource_info(instance_id: str):
    """
    获取指定实例的资源信息

    - **路径**: `/api/v1/resource/{instance_id}/info`
    - **方法**: `GET`
    - **描述**: 获取指定实例的数据库资源信息
    """
    logger.info(f"收到获取实例资源信息请求，实例ID: {instance_id}")

    try:
        result = maibot_resource_manager.get_instance_resource_info(instance_id)

        logger.info(f"实例资源信息获取结果: {result}")
        return DataResponse(
            status="success" if "error" not in result else "failed",
            message=result.get("error") if "error" in result else "获取成功",
            data=result if "error" not in result else None,
        )

    except Exception as e:
        logger.error(f"获取实例资源信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取实例资源信息失败: {str(e)}")


@router.get("/resource/all", response_model=ListResponse)
async def get_all_instances_resources():
    """
    获取所有实例的资源信息

    - **路径**: `/api/v1/resource/all`
    - **方法**: `GET`
    - **描述**: 获取所有实例的数据库资源信息
    """
    logger.info("收到获取所有实例资源信息请求")

    try:
        result = maibot_resource_manager.get_all_instances_resources()

        logger.info(f"所有实例资源信息获取结果: 获取到 {len(result)} 个实例的信息")
        return ListResponse(
            status="success", message="获取成功", data=result, total_count=len(result)
        )

    except Exception as e:
        logger.error(f"获取所有实例资源信息时发生错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"获取所有实例资源信息失败: {str(e)}"
        )


# ================ Emoji 统计和批量获取 API ================


@router.post("/resource/{instance_id}/emoji/count", response_model=DataResponse)
async def get_emoji_count(instance_id: str, request: EmojiCountRequest):
    """
    获取表情包记录总数

    - **路径**: `/api/v1/resource/{instance_id}/emoji/count`
    - **方法**: `POST`
    - **描述**: 获取表情包记录总数，支持条件筛选
    """
    logger.info(f"收到获取表情包总数请求，实例ID: {instance_id}")

    try:
        result = maibot_resource_manager.get_emoji_count(
            instance_id=instance_id, filters=request.dict(exclude_none=True)
        )

        logger.info(f"表情包总数获取结果: {result}")
        return DataResponse(**result)

    except Exception as e:
        logger.error(f"获取表情包总数时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取表情包总数失败: {str(e)}")


@router.post("/resource/{instance_id}/emoji/batch", response_model=ListResponse)
async def get_emoji_batch(instance_id: str, request: EmojiBatchRequest):
    """
    批量获取表情包数据

    - **路径**: `/api/v1/resource/{instance_id}/emoji/batch`
    - **方法**: `POST`
    - **描述**: 批量获取表情包数据，支持分页和条件筛选
    """
    logger.info(
        f"收到批量获取表情包请求，实例ID: {instance_id}, 批次大小: {request.batch_size}, 偏移: {request.offset}"
    )

    try:
        filters = request.dict(exclude={"batch_size", "offset"}, exclude_none=True)
        result = maibot_resource_manager.get_emoji_batch(
            instance_id=instance_id,
            batch_size=request.batch_size,
            offset=request.offset,
            filters=filters if filters else None,
        )

        if result["status"] == "success":
            logger.info(
                f"批量获取表情包成功: 返回 {result.get('returned_count', 0)} 条记录"
            )
            return ListResponse(
                status=result["status"],
                message=result["message"],
                data=result["data"],
                total_count=None,  # 如果需要总数，可以额外调用 get_emoji_count
                limit=result["batch_size"],
                offset=result["offset"],
            )
        else:
            return ListResponse(**result)

    except Exception as e:
        logger.error(f"批量获取表情包时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量获取表情包失败: {str(e)}")


# ================ PersonInfo 统计和批量获取 API ================


@router.post("/resource/{instance_id}/person/count", response_model=DataResponse)
async def get_person_info_count(instance_id: str, request: PersonInfoCountRequest):
    """
    获取用户信息记录总数

    - **路径**: `/api/v1/resource/{instance_id}/person/count`
    - **方法**: `POST`
    - **描述**: 获取用户信息记录总数，支持条件筛选
    """
    logger.info(f"收到获取用户信息总数请求，实例ID: {instance_id}")

    try:
        result = maibot_resource_manager.get_person_info_count(
            instance_id=instance_id, filters=request.dict(exclude_none=True)
        )

        logger.info(f"用户信息总数获取结果: {result}")
        return DataResponse(**result)

    except Exception as e:
        logger.error(f"获取用户信息总数时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取用户信息总数失败: {str(e)}")


@router.post("/resource/{instance_id}/person/batch", response_model=ListResponse)
async def get_person_info_batch(instance_id: str, request: PersonInfoBatchRequest):
    """
    批量获取用户信息数据

    - **路径**: `/api/v1/resource/{instance_id}/person/batch`
    - **方法**: `POST`
    - **描述**: 批量获取用户信息数据，支持分页和条件筛选
    """
    logger.info(
        f"收到批量获取用户信息请求，实例ID: {instance_id}, 批次大小: {request.batch_size}, 偏移: {request.offset}"
    )

    try:
        filters = request.dict(exclude={"batch_size", "offset"}, exclude_none=True)
        result = maibot_resource_manager.get_person_info_batch(
            instance_id=instance_id,
            batch_size=request.batch_size,
            offset=request.offset,
            filters=filters if filters else None,
        )

        if result["status"] == "success":
            logger.info(
                f"批量获取用户信息成功: 返回 {result.get('returned_count', 0)} 条记录"
            )
            return ListResponse(
                status=result["status"],
                message=result["message"],
                data=result["data"],
                total_count=None,  # 如果需要总数，可以额外调用 get_person_info_count
                limit=result["batch_size"],
                offset=result["offset"],
            )
        else:
            return ListResponse(**result)

    except Exception as e:
        logger.error(f"批量获取用户信息时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量获取用户信息失败: {str(e)}")


# ================ Bot Config API ================


@router.get("/resources/{instance_id}/config/get", response_model=DataResponse)
async def get_bot_config(instance_id: str):
    """
    获取指定实例的bot配置文件内容

    Args:
        instance_id: 实例ID

    Returns:
        DataResponse: 包含bot配置的JSON数据
    """
    try:
        # 获取实例信息
        instance = instance_manager.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

        # 构建配置文件路径
        config_path = os.path.join(instance.path, "config", "bot_config.toml")

        # 检查文件是否存在
        if not os.path.exists(config_path):
            raise HTTPException(
                status_code=404, detail=f"Bot配置文件不存在: {config_path}"
            )
        # 读取并解析TOML文件
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = tomlkit.load(f).unwrap()

            logger.info(f"成功获取实例 {instance_id} 的bot配置")
            return DataResponse(
                status="success", message="获取bot配置成功", data=config_data
            )
        except tomlkit.exceptions.TOMLKitError as e:
            raise HTTPException(status_code=400, detail=f"TOML文件格式错误: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取bot配置时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取bot配置失败: {str(e)}")


@router.post("/resources/{instance_id}/config/update", response_model=BaseResponse)
async def update_bot_config(instance_id: str, config_update: ConfigUpdateRequest):
    """
    更新指定实例的bot配置文件

    Args:
        instance_id: 实例ID
        config_update: 配置更新请求

    Returns:
        BaseResponse: 操作结果
    """
    try:
        # 获取实例信息
        instance = instance_manager.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

        # 构建配置文件路径
        config_path = os.path.join(instance.path, "config", "bot_config.toml")
        # 确保配置目录存在
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)

        # 写入TOML文件
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                tomlkit.dump(config_update.config_data, f)

            logger.info(f"成功更新实例 {instance_id} 的bot配置")
            return BaseResponse(status="success", message="更新bot配置成功")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"写入TOML文件失败: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新bot配置时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新bot配置失败: {str(e)}")


# ================ LPMM Config API ================


@router.get("/resources/{instance_id}/lpmm/get", response_model=DataResponse)
async def get_lpmm_config(instance_id: str):
    """
    获取指定实例的LPMM配置文件内容

    Args:
        instance_id: 实例ID

    Returns:
        DataResponse: 包含LPMM配置的JSON数据
    """
    try:
        # 获取实例信息
        instance = instance_manager.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

        # 构建配置文件路径
        config_path = os.path.join(instance.path, "config", "lpmm_config.toml")

        # 检查文件是否存在
        if not os.path.exists(config_path):
            raise HTTPException(
                status_code=404, detail=f"LPMM配置文件不存在: {config_path}"
            )
        # 读取并解析TOML文件
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = tomlkit.load(f).unwrap()

            logger.info(f"成功获取实例 {instance_id} 的LPMM配置")
            return DataResponse(
                status="success", message="获取LPMM配置成功", data=config_data
            )
        except tomlkit.exceptions.TOMLKitError as e:
            raise HTTPException(status_code=400, detail=f"TOML文件格式错误: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取LPMM配置时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取LPMM配置失败: {str(e)}")


@router.post("/resources/{instance_id}/lpmm/update", response_model=BaseResponse)
async def update_lpmm_config(instance_id: str, config_update: ConfigUpdateRequest):
    """
    更新指定实例的LPMM配置文件

    Args:
        instance_id: 实例ID
        config_update: 配置更新请求

    Returns:
        BaseResponse: 操作结果
    """
    try:
        # 获取实例信息
        instance = instance_manager.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

        # 构建配置文件路径
        config_path = os.path.join(instance.path, "config", "lpmm_config.toml")
        # 确保配置目录存在
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)

        # 写入TOML文件
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                tomlkit.dump(config_update.config_data, f)

            logger.info(f"成功更新实例 {instance_id} 的LPMM配置")
            return BaseResponse(status="success", message="更新LPMM配置成功")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"写入TOML文件失败: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新LPMM配置时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新LPMM配置失败: {str(e)}")


# ================ ENV File API ================


@router.get("/resources/{instance_id}/env/get", response_model=DataResponse)
async def get_env_config(instance_id: str):
    """
    获取指定实例的环境变量配置

    Args:
        instance_id: 实例ID

    Returns:
        DataResponse: 包含环境变量的JSON数据
    """
    try:
        # 获取实例信息
        instance = instance_manager.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

        # 构建环境变量文件路径
        env_path = os.path.join(instance.path, ".env")

        # 检查文件是否存在
        if not os.path.exists(env_path):
            raise HTTPException(
                status_code=404, detail=f"环境变量文件不存在: {env_path}"
            )

        # 使用python-dotenv解析.env文件
        try:
            env_data = dotenv_values(env_path)

            logger.info(f"成功获取实例 {instance_id} 的环境变量配置")
            return DataResponse(
                status="success",
                message="获取环境变量配置成功",
                data=dict(env_data),  # 转换为普通字典
            )
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"解析环境变量文件失败: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取环境变量配置时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取环境变量配置失败: {str(e)}")


@router.post("/resources/{instance_id}/env/update", response_model=BaseResponse)
async def update_env_config(instance_id: str, env_update: EnvUpdateRequest):
    """
    更新指定实例的环境变量配置

    Args:
        instance_id: 实例ID
        env_update: 环境变量更新请求

    Returns:
        BaseResponse: 操作结果
    """
    try:
        # 获取实例信息
        instance = instance_manager.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

        # 构建环境变量文件路径
        env_path = os.path.join(instance.path, ".env")

        # 写入.env文件
        try:
            with open(env_path, "w", encoding="utf-8") as f:
                for key, value in env_update.env_data.items():
                    # 处理值中的特殊字符，如果值包含空格或特殊字符需要加引号
                    if " " in value or '"' in value or "'" in value or "\n" in value:
                        # 转义双引号并用双引号包围
                        escaped_value = value.replace('"', '\\"')
                        f.write(f'{key}="{escaped_value}"\n')
                    else:
                        f.write(f"{key}={value}\n")

            logger.info(f"成功更新实例 {instance_id} 的环境变量配置")
            return BaseResponse(status="success", message="更新环境变量配置成功")
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"写入环境变量文件失败: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新环境变量配置时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新环境变量配置失败: {str(e)}")


# ================ Adapter Config API ================


@router.get("/resources/{instance_id}/adapter/napcat/get", response_model=DataResponse)
async def get_adapter_config(instance_id: str):
    """
    获取指定实例的适配器配置文件内容

    Args:
        instance_id: 实例ID

    Returns:
        DataResponse: 包含适配器配置的JSON数据
    """
    try:
        # 获取实例信息
        instance = instance_manager.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

        # 构建配置文件路径
        config_path = os.path.join(instance.path, "napcat-ada", "config.toml")
        template_path = os.path.join(
            instance.path, "napcat-ada", "template", "template_config.toml"
        )

        # 检查配置文件是否存在
        if not os.path.exists(config_path):
            # 检查模板文件是否存在
            if os.path.exists(template_path):
                try:
                    # 确保目标目录存在
                    config_dir = os.path.dirname(config_path)
                    os.makedirs(config_dir, exist_ok=True)

                    # 复制模板文件到配置文件位置
                    import shutil

                    shutil.copy2(template_path, config_path)
                    logger.info(f"已从模板文件创建适配器配置文件: {config_path}")
                except Exception as e:
                    raise HTTPException(
                        status_code=500, detail=f"复制模板文件失败: {str(e)}"
                    )
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"适配器配置文件和模板文件都不存在: {config_path}, {template_path}",
                )

        # 读取并解析TOML文件
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = tomlkit.load(f).unwrap()

            logger.info(f"成功获取实例 {instance_id} 的适配器配置")
            return DataResponse(
                status="success", message="获取适配器配置成功", data=config_data
            )
        except tomlkit.exceptions.TOMLKitError as e:
            raise HTTPException(status_code=400, detail=f"TOML文件格式错误: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取适配器配置时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取适配器配置失败: {str(e)}")


@router.post(
    "/resources/{instance_id}/adapter/napcat/update", response_model=BaseResponse
)
async def update_adapter_config(instance_id: str, config_update: ConfigUpdateRequest):
    """
    更新指定实例的适配器配置文件

    Args:
        instance_id: 实例ID
        config_update: 配置更新请求

    Returns:
        BaseResponse: 操作结果
    """
    try:
        # 获取实例信息
        instance = instance_manager.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"实例 {instance_id} 不存在")

        # 构建配置文件路径
        config_path = os.path.join(instance.path, "napcat-ada", "config.toml")
        template_path = os.path.join(
            instance.path, "napcat-ada", "template", "template_config.toml"
        )

        # 确保配置目录存在
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)

        # 如果配置文件不存在且模板文件存在，先复制模板文件
        if not os.path.exists(config_path) and os.path.exists(template_path):
            try:
                import shutil

                shutil.copy2(template_path, config_path)
                logger.info(f"已从模板文件创建适配器配置文件: {config_path}")
            except Exception as e:
                logger.warning(f"复制模板文件失败，将直接创建新配置文件: {str(e)}")

        # 写入TOML文件
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                tomlkit.dump(config_update.config_data, f)

            logger.info(f"成功更新实例 {instance_id} 的适配器配置")
            return BaseResponse(status="success", message="更新适配器配置成功")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"写入TOML文件失败: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新适配器配置时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新适配器配置失败: {str(e)}")
