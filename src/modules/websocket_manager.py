import asyncio
from fastapi import WebSocket
from starlette.websockets import WebSocketState, WebSocketDisconnect
from winpty import PtyProcess  # type: ignore
import json
from typing import Dict, Any, Tuple, Optional
import logging

from src.utils.database import Database, get_db_instance
from src.modules.instance_manager import instance_manager, InstanceStatus
from src.utils.database_model import Instances
from src.modules.deploy_api import generate_venv_command

logger = logging.getLogger(__name__)

PTY_COLS_DEFAULT = 80
PTY_ROWS_DEFAULT = 25

active_ptys: Dict[str, Dict[str, Any]] = {}
active_ptys_lock = asyncio.Lock()


async def get_pty_command_and_cwd_from_instance(
    instance_id_full: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    db = get_db_instance()
    parts = instance_id_full.rpartition("_")
    if not parts[1]:
        logger.warning(
            f"PTY 配置的 session_id 格式无效 (缺少类型部分): {instance_id_full}"
        )
        return None, None, None

    instance_short_id, _, type_part = parts

    instance: Optional[Instances] = instance_manager.get_instance(instance_short_id)
    if not instance:
        logger.warning(f"在 instance_manager 中未找到实例 '{instance_short_id}'。")
        return None, None, None

    status_value = (
        instance.status.value
        if isinstance(instance.status, InstanceStatus)
        else instance.status
    )
    pty_command: Optional[str] = None
    pty_cwd: Optional[str] = None

    if type_part == "main":
        # 主程序 PTY 配置
        base_command = "python bot.py"
        pty_cwd = instance.path
        # 使用虚拟环境激活的命令
        pty_command = generate_venv_command(base_command, pty_cwd)
        logger.info(
            f"为 'main' 类型 (实例 '{instance_short_id}') 配置 PTY: 基础命令='{base_command}', 虚拟环境命令='{pty_command}', CWD='{pty_cwd}'"
        )
    else:  # Adapter/Service PTY configuration (type_part is the service name)
        logger.info(
            f"为服务 '{type_part}' (实例 '{instance_short_id}') 配置 PTY。"
        )  # 1. 获取实例的已安装服务列表
        installed_services = instance_manager.get_instance_services(instance_short_id)
        if not isinstance(installed_services, list):
            logger.error(
                f"获取实例 '{instance_short_id}' 的服务列表失败或返回格式不正确。无法验证服务 '{type_part}'"
            )
            return None, None, status_value

        # 提取服务名称列表
        installed_service_names = [
            service.get("name") for service in installed_services if service.get("name")
        ]

        # 2. 检查请求的服务是否在已安装列表中
        if type_part not in installed_service_names:
            logger.warning(
                f"服务 '{type_part}' 未在实例 '{instance_short_id}' 的已安装服务列表中找到。"
                f"已安装的服务: {installed_service_names}. PTY 将不会启动。"
            )
            return None, None, status_value

        # 3. 从数据库获取服务详情，包括 run_cmd
        service_details = await db.get_service_details(instance_short_id, type_part)
        if (
            service_details
            and service_details.path
            and hasattr(service_details, "run_cmd")
            and service_details.run_cmd
        ):
            pty_cwd = service_details.path
            base_command = service_details.run_cmd  # 使用 Services 表中的 run_cmd 字段
            # 使用虚拟环境激活的命令
            pty_command = generate_venv_command(base_command, pty_cwd)

            logger.info(
                f"从数据库为服务 '{type_part}' (实例 '{instance_short_id}') 配置 PTY: "
                f"基础命令='{base_command}', 虚拟环境命令='{pty_command}', CWD='{pty_cwd}'"
            )
        else:
            # 详细记录配置失败的原因
            if not service_details:
                logger.warning(
                    f"无法从数据库获取有效服务 '{type_part}' (实例: '{instance_short_id}') 的详细信息，即使它在服务列表中。PTY 将不会启动。"
                )
            elif not service_details.path:
                logger.warning(
                    f"服务 '{type_part}' (实例: '{instance_short_id}') 的路径 (path) 缺失。PTY 将不会启动。"
                )
            elif not hasattr(service_details, "run_cmd") or not service_details.run_cmd:
                logger.warning(
                    f"服务 '{type_part}' (实例: '{instance_short_id}') 的启动命令 (run_cmd) 缺失或为空。PTY 将不会启动。"
                )
            else:
                logger.warning(
                    f"为服务 '{type_part}' (实例: '{instance_short_id}') 配置 PTY 失败，配置不完整。PTY 将不会启动。"
                )
            return None, None, status_value  # 返回 None 表示无法配置 PTY

    # 确保 pty_command 和 pty_cwd 在成功路径上都被设置
    if not pty_command or not pty_cwd:
        logger.error(
            f"PTY 配置不完整或失败: 命令='{pty_command}', CWD='{pty_cwd}' (实例: '{instance_id_full}')。"
        )
        return None, None, status_value

    logger.info(
        f"实例 {instance_id_full} 的 PTY 配置完成: 命令='{pty_command}', CWD='{pty_cwd}', 状态='{status_value}'"
    )
    return pty_command, pty_cwd, status_value


async def pty_output_to_websocket(
    session_id: str, pty_process: PtyProcess, websocket: WebSocket, db: Database
):
    """
    读取 PTY 输出，将其发送到 WebSocket (FastAPI version)。不再存储到数据库。
    """
    try:
        while True:
            try:
                data = await asyncio.to_thread(pty_process.read, 10240)
                if not data:
                    logger.info(f"PTY 读取为会话 {session_id} 返回了无数据 (EOF)。")
                    break

                # 处理可能返回字节或字符串的情况
                if isinstance(data, bytes):
                    try:
                        str_data = data.decode("utf-8")
                    except UnicodeDecodeError:
                        str_data = data.decode("utf-8", errors="replace")
                        logger.warning(
                            f"会话 {session_id} 发生 Unicode 解码错误，已使用替换字符。"
                        )
                elif isinstance(data, str):
                    str_data = data
                else:
                    logger.warning(
                        f"会话 {session_id} 的 PTY 返回了未知类型的数据: {type(data)}"
                    )
                    str_data = str(data)

                if websocket.client_state == WebSocketState.CONNECTED:
                    try:
                        await websocket.send_json({"type": "output", "data": str_data})
                    except RuntimeError as e_send_runtime:
                        logger.warning(
                            f"发送 PTY 输出到 WebSocket (会话 {session_id}) 时发生运行时错误 (可能已关闭): {e_send_runtime}"
                        )
                        break
                    except Exception as e_send:
                        logger.error(
                            f"发送 PTY 输出到 WebSocket (会话 {session_id}) 时出错: {e_send}"
                        )
                        break
                else:
                    logger.info(
                        f"WebSocket (会话 {session_id}) 不再连接。停止 PTY 输出。"
                    )
                    break

            except Exception as e_read:
                logger.error(
                    f"会话 {session_id} 的 PTY 读取错误 (PTY 进程可能已关闭): {e_read}"
                )
                break
    except Exception as e:
        logger.error(
            f"pty_output_to_websocket_and_db 中发生意外错误 (会话 {session_id}): {e}"
        )
    finally:
        logger.info(f"会话 {session_id} 的 PTY 输出转发任务已完成。")


async def handle_websocket_connection(
    websocket: WebSocket, session_id: str, db: Database
):
    """
    处理单个 WebSocket 连接 (FastAPI version)。
    session_id 是从路径中提取的部分，例如 "yourinstanceid_main"。
    不再发送历史日志。
    创建虚拟终端但不直接执行命令，等待前端调用实例启动API后才开始运行。
    """
    await websocket.accept()
    logger.info(
        f"客户端已连接 (FastAPI)，会话 ID: {session_id}，来自 {websocket.client.host}:{websocket.client.port}"
    )

    # 解析 session_id 获取实例 ID 和类型
    parts = session_id.rpartition("_")
    if not parts[1]:
        err_msg = f"WebSocket 会话 ID 格式无效 (缺少类型部分): {session_id}"
        logger.error(err_msg)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"type": "error", "message": err_msg})
            await websocket.close(code=1003)
        return

    instance_short_id, _, type_part = parts

    # 验证实例是否存在
    instance = instance_manager.get_instance(instance_short_id)
    if not instance:
        err_msg = f"未找到实例 '{instance_short_id}'"
        logger.error(err_msg)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"type": "error", "message": err_msg})
            await websocket.close(code=1003)
        return

    pty_process: Optional[PtyProcess] = None
    read_task: Optional[asyncio.Task] = None

    try:        # 检查是否已经有活跃的 PTY 进程
        existing_pty_info = None
        async with active_ptys_lock:
            if (
                session_id in active_ptys
                and active_ptys[session_id].get("pty")
                and active_ptys[session_id]["pty"].isalive()
            ):
                existing_pty_info = active_ptys[session_id]

        if existing_pty_info:
            # PTY 已存在，直接连接到现有进程
            pty_process = existing_pty_info["pty"]

            # 更新 WebSocket 连接（在锁外更新）
            async with active_ptys_lock:
                if session_id in active_ptys:
                    active_ptys[session_id]["ws"] = websocket

            logger.info(f"连接到现有的 PTY 进程 (会话: {session_id})")

            # 如果 PTY 已经在运行命令，启动输出读取任务
            if existing_pty_info.get("command_started", False):
                read_task = asyncio.create_task(
                    pty_output_to_websocket(session_id, pty_process, websocket, db)
                )
                async with active_ptys_lock:
                    if session_id in active_ptys:
                        active_ptys[session_id]["output_task"] = read_task
        else:
            # 创建新的虚拟终端，但不执行命令
            logger.info(f"为会话 {session_id} 创建虚拟终端 (不执行命令)")

            # 获取工作目录
            pty_cwd = None
            if type_part == "main":
                pty_cwd = instance.path
            else:
                # 对于服务，从数据库获取服务详情
                service_details = await db.get_service_details(
                    instance_short_id, type_part
                )
                if service_details and service_details.path:
                    pty_cwd = service_details.path
                else:
                    pty_cwd = instance.path  # 回退到实例路径

            # 创建空的 PTY 进程（使用 cmd 作为默认 shell）
            pty_process = PtyProcess.spawn(
                ["cmd.exe"],  # 使用 Windows cmd 作为默认 shell
                dimensions=(PTY_ROWS_DEFAULT, PTY_COLS_DEFAULT),
                cwd=pty_cwd,
            )
            logger.info(
                f"虚拟终端已创建 (会话: {session_id}, PID: {pty_process.pid})"
            )            # 保存到 active_ptys，标记为未开始命令
            async with active_ptys_lock:
                active_ptys[session_id] = {
                    "pty": pty_process,
                    "ws": websocket,
                    "output_task": None,
                    "instance_part": instance_short_id,
                    "type_part": type_part,
                    "command_started": False,  # 标记命令尚未开始
                    "working_directory": pty_cwd,
                }

            # 启动输出读取任务（用于显示 shell 提示符）
            read_task = asyncio.create_task(
                pty_output_to_websocket(session_id, pty_process, websocket, db)
            )

            # 更新输出任务（使用单独的锁操作）
            async with active_ptys_lock:
                if session_id in active_ptys:
                    active_ptys[session_id]["output_task"] = read_task

        if not pty_process:
            err_msg = f"无法创建虚拟终端 (会话: {session_id})"
            logger.error(err_msg)
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({"type": "error", "message": err_msg})
                await websocket.close(code=1003)
            return

        # 发送连接成功消息
        if websocket.client_state == WebSocketState.CONNECTED:
            status_msg = f"已连接到 {type_part} 终端"
            async with active_ptys_lock:
                if session_id in active_ptys and not active_ptys[session_id].get(
                    "command_started", False
                ):
                    status_msg += " (等待启动命令)"

            await websocket.send_json(
                {"type": "status", "message": status_msg}
            )  # 处理 WebSocket 消息
        while True:
            try:
                message_str = await websocket.receive_text()

                try:
                    msg_data = json.loads(message_str)
                    msg_type = msg_data.get("type")
                    if msg_type == "input":
                        pty_input_data = msg_data.get("data")
                        if isinstance(pty_input_data, str):
                            try:
                                if pty_process and pty_process.isalive():
                                    pty_process.write(pty_input_data)
                                else:
                                    logger.warning(
                                        f"PTY 进程已停止，无法发送消息 (会话: {session_id})"
                                    )
                                    break
                            except Exception as e_write:
                                logger.error(
                                    f"向会话 {session_id} 的 PTY 写入时出错: {e_write}"
                                )
                                if not pty_process.isalive():
                                    if (
                                        websocket.client_state
                                        == WebSocketState.CONNECTED
                                    ):
                                        await websocket.send_json(
                                            {
                                                "type": "status",
                                                "message": "PTY 进程在写入错误后终止。",
                                            }
                                        )
                                    break
                    elif msg_type == "resize":
                        cols = msg_data.get("cols", PTY_COLS_DEFAULT)
                        rows = msg_data.get("rows", PTY_ROWS_DEFAULT)
                        try:
                            if pty_process and pty_process.isalive():
                                pty_process.setwinsize(rows, cols)
                                logger.info(
                                    f"已将会话 {session_id} 的 PTY 大小调整为 {cols}x{rows}"
                                )
                        except Exception as e_resize:
                            logger.error(
                                f"调整会话 {session_id} 的 PTY 大小时出错: {e_resize}"
                            )
                    else:
                        logger.warning(
                            f"收到来自会话 {session_id} 的未知消息类型 '{msg_type}'"
                        )

                except json.JSONDecodeError:
                    logger.warning(
                        f"收到来自会话 {session_id} 客户端的非 JSON 消息或格式错误的 JSON: {message_str}"
                    )
                except Exception as e_msg_proc:
                    logger.error(f"处理会话 {session_id} 的消息时出错: {e_msg_proc}")
                    if pty_process and not pty_process.isalive():
                        logger.warning(
                            f"会话 {session_id} 的 PTY 进程已死亡。正在中断消息循环。"
                        )
                        if websocket.client_state == WebSocketState.CONNECTED:
                            await websocket.send_json(
                                {"type": "status", "message": "PTY 进程意外终止。"}
                            )
                        break
            except WebSocketDisconnect:
                logger.info(f"客户端断开连接 (会话: {session_id})")
                break
            except Exception as e:
                logger.error(f"处理 WebSocket 消息时出错 (会话: {session_id}): {e}")
                break

    except WebSocketDisconnect:
        logger.info(f"会话 {session_id} 的客户端已断开连接 (WebSocketDisconnect)。")
    except Exception as e_main:
        logger.error(
            f"handle_websocket_connection 中发生意外错误 (会话 {session_id}): {e_main}",
            exc_info=True,
        )
    finally:
        logger.info(f"正在为会话 {session_id} 进行清理...")

        # 取消输出任务
        if read_task and not read_task.done():
            read_task.cancel()
            try:
                await asyncio.wait_for(read_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"等待会话 {session_id} 输出任务取消时出错: {e}")

        # 更新 active_ptys 中的 WebSocket 连接为 None（但保留 PTY 进程）
        async with active_ptys_lock:
            if session_id in active_ptys:
                active_ptys[session_id]["ws"] = None
                active_ptys[session_id]["output_task"] = None

        # 关闭 WebSocket 连接
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception as e:
                logger.warning(f"关闭 WebSocket 连接时出错 (会话: {session_id}): {e}")

        logger.info(f"会话 {session_id} 的清理完成。")


async def send_command_to_pty(session_id: str, command: str) -> tuple[bool, str]:
    log_command = f"{command[:50]}..." if len(command) > 50 else command
    logger.info(f"尝试向会话 {session_id} 发送命令。命令: '{log_command}'")

    async with active_ptys_lock:
        if session_id in active_ptys:
            pty_info = active_ptys[session_id]
            pty_process = pty_info.get("pty")

            if pty_process and pty_process.isalive():
                try:
                    pty_process.write(command.encode("utf-8"))
                    logger.info(f"命令已成功发送到会话 {session_id} 的 PTY。")
                    return True, f"命令已发送到会话 {session_id}。"
                except Exception as e:
                    logger.error(f"向会话 {session_id} 的 PTY 写入命令时出错: {e}")
                    return False, f"向会话 {session_id} 的 PTY 写入命令时出错: {e}"
            else:
                logger.warning(f"未找到会话 {session_id} 的 PTY 进程或该进程未存活。")
                return False, f"会话 {session_id} 的 PTY 进程未激活或未找到。"
        else:
            logger.warning(f"未找到 ID 为 {session_id} 的活动 PTY 会话。")
            return False, f"未找到 ID 为 {session_id} 的活动 PTY 会话。"


async def stop_all_ptys_for_instance(instance_short_id: str) -> dict:
    """
    Stops all PTY processes associated with a given instance_short_id.
    This includes the main PTY and any adapter PTYs.
    Returns a dictionary with success status and message.
    """
    logger.info(f"请求停止实例 '{instance_short_id}' 的所有 PTY 进程。")
    terminated_sessions_info = []
    failed_to_terminate_sessions_info = []

    sessions_to_process = []
    # Lock before accessing active_ptys
    async with active_ptys_lock:
        for session_id, pty_info_dict in active_ptys.items():
            if pty_info_dict.get("instance_part") == instance_short_id:
                sessions_to_process.append(session_id)

    if not sessions_to_process:
        msg = f"未找到实例 '{instance_short_id}' 的活动 PTY 会话。"
        logger.info(msg)
        return {
            "success": True,
            "message": msg,
            "terminated_details": [],
            "failed_details": [],
        }

    for session_id in sessions_to_process:
        logger.info(
            f"正在处理实例 '{instance_short_id}' 的 PTY 会话 '{session_id}' 的终止..."
        )

        pty_info_to_clean = None
        # Lock again to safely pop from active_ptys
        async with active_ptys_lock:
            if session_id in active_ptys:  # Re-check if still exists
                pty_info_to_clean = active_ptys.pop(session_id)
            else:
                # Already removed or cleaned up, possibly by its own disconnect logic
                logger.warning(f"PTY 会话 '{session_id}' 在尝试终止前已被移除或处理。")
                terminated_sessions_info.append(
                    {"id": session_id, "status": "already_gone", "type": "unknown"}
                )
                continue

        # pty_info_to_clean should not be None if it was popped
        read_task = pty_info_to_clean.get("output_task")
        pty_process = pty_info_to_clean.get("pty")
        websocket = pty_info_to_clean.get("ws")
        current_type_part = pty_info_to_clean.get("type_part", "unknown_type")
        session_label = f"{session_id} (type: {current_type_part})"

        # 1. Cancel the output reading task
        if read_task and not read_task.done():
            read_task.cancel()
            try:
                await read_task  # Wait for cancellation to complete
            except asyncio.CancelledError:
                logger.info(f"PTY 输出任务 for session '{session_label}' 已成功取消。")
            except Exception as e_task_cancel:
                logger.error(
                    f"等待已取消的 PTY 输出任务 for session '{session_label}' 时出错: {e_task_cancel}"
                )

        # 2. Terminate the PTY process
        pty_terminated_successfully = False
        if pty_process:
            if pty_process.isalive():
                logger.info(
                    f"正在终止 PTY 进程 (PID: {pty_process.pid}) for session '{session_label}'。"
                )
                try:
                    pty_process.terminate(force=True)
                    logger.info(
                        f"PTY 进程 (PID: {pty_process.pid}) for session '{session_label}' terminate signal sent."
                    )
                    pty_terminated_successfully = True
                except Exception as e_term:
                    logger.error(
                        f"终止 PTY for session '{session_label}' 时出错: {e_term}"
                    )
                    failed_to_terminate_sessions_info.append(
                        {
                            "id": session_id,
                            "type": current_type_part,
                            "error": str(e_term),
                        }
                    )
            else:  # PTY process exists but is not alive
                logger.info(f"PTY 进程 for session '{session_label}' 已停止。")
                pty_terminated_successfully = True  # Already stopped
        else:  # No PTY process object found in the pty_info
            logger.warning(
                f"PTY 会话 '{session_label}' 的 pty_info 中未找到 PTY 进程对象。"
            )
            # Consider this 'terminated' as there's nothing to kill, or an anomaly.
            pty_terminated_successfully = True

        # 3. Close the WebSocket connection associated with this PTY (if any and connected)
        if websocket and websocket.client_state == WebSocketState.CONNECTED:
            logger.info(f"正在关闭 WebSocket 连接 for session '{session_label}'。")
            try:
                # Notify client before closing
                await websocket.send_json(
                    {"type": "status", "message": "实例已停止，PTY 被服务器终止。"}
                )
                await websocket.close(code=1000)  # Normal closure
            except (
                RuntimeError
            ) as e_ws_runtime:  # e.g., sending on an already closed socket
                logger.warning(
                    f"关闭 WebSocket for session '{session_label}' 时发生运行时错误: {e_ws_runtime}"
                )
            except Exception as e_ws_close:  # Other errors during close
                logger.error(
                    f"关闭 WebSocket for session '{session_label}' 时发生错误: {e_ws_close}"
                )

        if pty_terminated_successfully:
            # Add to terminated list only if not already marked as failed
            if not any(
                f_item["id"] == session_id
                for f_item in failed_to_terminate_sessions_info
            ):
                terminated_sessions_info.append(
                    {
                        "id": session_id,
                        "type": current_type_part,
                        "status": "terminated",
                    }
                )
        # If not pty_terminated_successfully and not in failed_to_terminate_sessions_info, it implies an issue not caught by PTY termination try-except
        # This case might need more specific logging or error handling if it occurs.
        # For now, it means it wasn't explicitly successful, nor did it log a PTY termination error.

    final_message = f"实例 '{instance_short_id}' 的 PTY 停止处理完成。"
    success_overall = not bool(failed_to_terminate_sessions_info)

    logger.info(final_message)
    # Detailed logging for debugging
    if terminated_sessions_info:
        logger.debug(
            f"Terminated session details for instance '{instance_short_id}': {terminated_sessions_info}"
        )
    if failed_to_terminate_sessions_info:
        logger.debug(
            f"Failed to terminate session details for instance '{instance_short_id}': {failed_to_terminate_sessions_info}"
        )

    return {
        "success": success_overall,
        "message": final_message,
        "terminated_details": terminated_sessions_info,
        "failed_details": failed_to_terminate_sessions_info,
    }


async def shutdown_all_websocket_connections():
    """
    优雅地关闭所有活跃的 WebSocket 连接和 PTY 进程。
    在服务器关闭时调用，确保所有连接和进程都被正确清理。
    """
    logger.info("开始关闭所有 WebSocket 连接和 PTY 进程...")

    sessions_to_close = []

    # 获取所有活跃的会话
    async with active_ptys_lock:
        sessions_to_close = list(active_ptys.keys())

    if not sessions_to_close:
        logger.info("没有活跃的 WebSocket 连接需要关闭。")
        return

    logger.info(f"找到 {len(sessions_to_close)} 个活跃的 WebSocket 连接，正在关闭...")

    # 并发关闭所有连接
    close_tasks = []
    for session_id in sessions_to_close:
        task = asyncio.create_task(_close_single_session(session_id))
        close_tasks.append(task)

    # 等待所有关闭任务完成，设置超时
    try:
        await asyncio.wait_for(
            asyncio.gather(*close_tasks, return_exceptions=True),
            timeout=10.0,  # 10秒超时
        )
        logger.info("所有 WebSocket 连接已成功关闭。")
    except asyncio.TimeoutError:
        logger.warning("关闭 WebSocket 连接超时，强制退出。")
    except Exception as e:
        logger.error(f"关闭 WebSocket 连接时发生错误: {e}")


async def _close_single_session(session_id: str):
    """
    关闭单个 WebSocket 会话的辅助函数。
    """
    try:
        logger.debug(f"正在关闭会话: {session_id}")

        pty_info = None
        async with active_ptys_lock:
            if session_id in active_ptys:
                pty_info = active_ptys.pop(session_id)

        if not pty_info:
            logger.debug(f"会话 {session_id} 已被移除或不存在。")
            return

        # 1. 取消输出任务
        read_task = pty_info.get("output_task")
        if read_task and not read_task.done():
            read_task.cancel()
            try:
                await asyncio.wait_for(read_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"取消会话 {session_id} 的输出任务时出错: {e}")

        # 2. 终止 PTY 进程
        pty_process = pty_info.get("pty")
        if pty_process and pty_process.isalive():
            try:
                pty_process.terminate(force=True)
                logger.debug(f"PTY 进程已终止 (会话: {session_id})")
            except Exception as e:
                logger.warning(f"终止会话 {session_id} 的 PTY 进程时出错: {e}")

        # 3. 关闭 WebSocket 连接
        websocket = pty_info.get("ws")
        if websocket and websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_json(
                    {"type": "status", "message": "服务器正在关闭，连接即将断开。"}
                )
                await websocket.close(code=1001)  # Going Away
                logger.debug(f"WebSocket 连接已关闭 (会话: {session_id})")
            except Exception as e:
                logger.warning(f"关闭会话 {session_id} 的 WebSocket 时出错: {e}")

        logger.debug(f"会话 {session_id} 已成功关闭。")

    except Exception as e:
        logger.error(f"关闭会话 {session_id} 时发生意外错误: {e}")


try:
    from winpty import PtyProcess  # type: ignore
except ImportError:
    logger.critical("未安装 winpty 库。此模块无法运行。请安装: pip install pywinpty")
