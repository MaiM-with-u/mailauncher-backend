# 路径展开问题修复说明

## 问题描述

在部署过程中发现后端路径处理不统一的问题：
- 主 MaiBot 实例路径被正确展开：`E:\Collection\桌面\mailauncher-backend\MaiBot\Deployments\MaiBot-Dev7689`
- napcat-ada 服务路径未被展开：`E:\Collection\桌面\mailauncher-backend\~\MaiBot\Deployments\MaiBot-Dev7689\napcat-ada`

这导致 Git 克隆命令在尝试克隆 napcat-ada 服务时找不到正确的路径。

## 根本原因

在 `src/modules/deploy_api.py` 的 `perform_deployment_background` 函数中：

1. **主实例路径展开正常**：主实例的 `install_path` 被正确展开（第 423-444 行）
2. **服务路径未展开**：传递给 `deploy_manager.deploy_version` 和保存到数据库的服务配置中的路径仍然包含未展开的 `~` 符号

## 修复内容

### 修复1：为 deploy_manager 展开服务路径

在调用 `deploy_manager.deploy_version` 之前，展开所有服务配置中的路径：

```python
# 准备展开后的服务配置给 deploy_manager
expanded_services = []
for service in payload.install_services:
    service_dict = service.model_dump()
    service_path = service_dict["path"]
    
    # 展开服务路径中的 ~ 符号（如果存在）
    if service_path.startswith("~"):
        current_dir = Path.cwd()
        if service_path.startswith("~/") or service_path.startswith("~\\"):
            relative_path = service_path[2:]
            service_path = str(current_dir / relative_path)
        else:
            relative_path = service_path[1:] if len(service_path) > 1 else ""
            if relative_path:
                service_path = str(current_dir / relative_path)
            else:
                service_path = str(current_dir)
        service_dict["path"] = service_path
        logger.info(
            f"为 deploy_manager 展开服务路径: {service.path} -> {service_path} (服务: {service.name}, 实例ID: {instance_id_str})"
        )
    
    expanded_services.append(service_dict)
```

### 修复2：数据库保存时展开服务路径

在保存服务配置到数据库时，也展开路径：

```python
for service_config in payload.install_services:
    # 展开服务路径中的 ~ 符号（如果存在）
    service_path = service_config.path
    if service_path.startswith("~"):
        current_dir = Path.cwd()
        if service_path.startswith("~/") or service_path.startswith("~\\"):
            relative_path = service_path[2:]
            service_path = str(current_dir / relative_path)
        else:
            relative_path = service_path[1:] if len(service_path) > 1 else ""
            if relative_path:
                service_path = str(current_dir / relative_path)
            else:
                service_path = str(current_dir)
        logger.info(
            f"展开服务路径: {service_config.path} -> {service_path} (服务: {service_config.name}, 实例ID: {instance_id_str})"
        )
    
    db_service = DB_Service(
        instance_id=instance_id_str,
        name=service_config.name,
        path=service_path,  # 使用展开后的路径
        status="pending",
        port=service_config.port,
        run_cmd=service_config.run_cmd,
    )
```

## 测试验证

修复后，在部署包含 napcat-ada 服务的实例时，日志应该显示：

```
为 deploy_manager 展开服务路径: ~/MaiBot/Deployments/MaiBot-DevXXXX/napcat-ada -> E:\Collection\桌面\mailauncher-backend\MaiBot\Deployments\MaiBot-DevXXXX\napcat-ada
展开服务路径: ~/MaiBot/Deployments/MaiBot-DevXXXX/napcat-ada -> E:\Collection\桌面\mailauncher-backend\MaiBot\Deployments\MaiBot-DevXXXX\napcat-ada
```

Git 克隆命令也将使用正确的绝对路径。

## 影响范围

此修复影响：
- 所有使用相对路径（`~` 开头）的服务部署
- 数据库中保存的服务路径记录
- 传递给部署管理器的服务配置

## 兼容性

此修复向后兼容，不会影响已经使用绝对路径的现有部署。

## 修复日期

2025年6月20日

## 修复文件

- `src/modules/deploy_api.py`
