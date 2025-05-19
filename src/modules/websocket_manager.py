import asyncio
from fastapi import WebSocket
from starlette.websockets import WebSocketState, WebSocketDisconnect
from winpty import PtyProcess  # type: ignore
import json
import shlex
from typing import Dict, Any, Tuple, Optional
import logging

from src.utils.database import Database, get_db_instance
from src.modules.instance_manager import instance_manager, InstanceStatus

logger = logging.getLogger(__name__)

PTY_COLS_DEFAULT = 80
PTY_ROWS_DEFAULT = 25
MAX_LOG_HISTORY = 1000

active_ptys: Dict[str, Dict[str, Any]] = {}
active_ptys_lock = asyncio.Lock()


async def get_pty_command_and_cwd_from_instance(
    instance_id_full: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    db = get_db_instance()
    parts = instance_id_full.rpartition("_")
    if not parts[1]:
        logger.warning(f"PTY 配置的 session_id 格式无效: {instance_id_full}")
        return None, None, None

    instance_short_id, _, type_part = parts

    instance = instance_manager.get_instance(instance_short_id)
    if not instance:
        logger.warning(f"在 instance_manager 中未找到实例 '{instance_short_id}'。")
        return None, None, None

    base_path = instance.path
    status_value = (
        instance.status.value
        if isinstance(instance.status, InstanceStatus)
        else instance.status
    )

    pty_command: Optional[str] = None
    pty_cwd: Optional[str] = None

    if type_part == "main":
        pty_command = "python .\\\\bot.py"
        pty_cwd = base_path
        logger.info(f"为 'main' 类型配置 PTY: 命令='{pty_command}', CWD='{pty_cwd}'")
    elif type_part in ["napcat", "napcat-ada"]:
        service_details = await db.get_service_details(instance_short_id, type_part)
        if service_details and service_details.path:
            pty_cwd = service_details.path
            if type_part == "napcat":
                pty_command = f"CHCP 65001 & start http://127.0.0.1:6099/webui/web_login?token=napcat & NapCatWinBootMain.exe {instance.qq_number}"
            elif type_part == "napcat-ada":
                pty_command = "python .\\\\main.py"
            logger.info(
                f"为服务 '{type_part}' 配置 PTY: 命令='{pty_command}', CWD='{pty_cwd}'"
            )
        else:
            logger.warning(
                f"无法从数据库获取服务 '{type_part}' (实例: '{instance_short_id}') 的详细信息或路径。"
            )
            return None, None, status_value
    else:
        logger.warning(
            f"未知的 PTY 类型: '{type_part}' (实例: '{instance_short_id}')。无法确定命令。"
        )
        return None, None, status_value

    logger.info(
        f"实例 {instance_id_full} 的 PTY 配置: 命令='{pty_command}', CWD='{pty_cwd}', 状态='{status_value}'"
    )
    return pty_command, pty_cwd, status_value


async def pty_output_to_websocket_and_db(
    session_id: str, pty_process: PtyProcess, websocket: WebSocket, db: Database
):
    """
    读取 PTY 输出，将其发送到 WebSocket (FastAPI version)，并存储到数据库。
    """
    try:
        while True:
            try:
                byte_data = await asyncio.to_thread(pty_process.read, 10240)
                if not byte_data:
                    logger.info(f"PTY 读取为会话 {session_id} 返回了无数据 (EOF)。")
                    break
                try:
                    str_data = byte_data.decode("utf-8")
                except UnicodeDecodeError:
                    str_data = byte_data.decode("utf-8", errors="replace")
                    logger.warning(
                        f"会话 {session_id} 发生 Unicode 解码错误，已使用替换字符。"
                    )

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

                await db.add_pty_log(session_id, str_data, MAX_LOG_HISTORY)

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
    """
    await websocket.accept()
    logger.info(
        f"客户端已连接 (FastAPI)，会话 ID: {session_id}，来自 {websocket.client.host}:{websocket.client.port}"
    )

    pty_process: Optional[PtyProcess] = None
    read_task: Optional[asyncio.Task] = None

    pty_command_str, pty_cwd, _ = await get_pty_command_and_cwd_from_instance(
        session_id
    )

    if not pty_command_str:
        err_msg = f"无法确定会话 {session_id} 的 PTY 命令。实例或类型可能无效或未配置。"
        logger.error(err_msg)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"type": "error", "message": err_msg})
            await websocket.close(code=1008)
        return

    async with active_ptys_lock:
        if (
            session_id in active_ptys
            and active_ptys[session_id].get("pty")
            and active_ptys[session_id]["pty"].isalive()
        ):
            logger.warning(f"会话 {session_id} 已激活。正在关闭新的连接。")
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.send_json(
                        {"type": "error", "message": "会话已被其他客户端激活。"}
                    )
                except RuntimeError:
                    pass
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=1008)
            return

    try:
        historical_logs = await db.get_pty_logs(session_id, MAX_LOG_HISTORY)
        if historical_logs:
            logger.info(
                f"正在向客户端发送 {len(historical_logs)} 条会话 {session_id} 的历史日志。"
            )
            log_batch = [log.log_content for log in historical_logs]
            if websocket.client_state != WebSocketState.CONNECTED:
                logger.warning(f"发送会话 {session_id} 的历史日志前 WebSocket 已关闭。")
                return
            await websocket.send_json({"type": "history", "data": log_batch})

        if websocket.client_state != WebSocketState.CONNECTED:
            logger.warning(f"启动 PTY 前 WebSocket 已为会话 {session_id} 关闭。")
            return

        try:
            cmd_to_spawn_list = shlex.split(pty_command_str)
            if not cmd_to_spawn_list:
                raise ValueError("命令字符串 shlex.split 后产生空列表")
        except ValueError as e_shlex:
            logger.warning(
                f"会话 {session_id} 的 PTY_COMMAND ('{pty_command_str}') 无法被 shlex 分割: {e_shlex}。将按原样使用。"
            )
            cmd_to_spawn_list = pty_command_str  # type: ignore

        pty_process = PtyProcess.spawn(
            cmd_to_spawn_list,
            dimensions=(PTY_ROWS_DEFAULT, PTY_COLS_DEFAULT),
            cwd=pty_cwd,
        )
        logger.info(
            f"PTY 进程 (PID: {pty_process.pid}) 已为会话 {session_id} 启动，命令: '{pty_command_str}'，CWD: {pty_cwd or '默认'}"
        )

        instance_short_id, _, type_part = session_id.rpartition("_")
        async with active_ptys_lock:
            active_ptys[session_id] = {
                "pty": pty_process,
                "ws": websocket,
                "output_task": None,
                "instance_part": instance_short_id,
                "type_part": type_part,
            }

        read_task = asyncio.create_task(
            pty_output_to_websocket_and_db(session_id, pty_process, websocket, db)
        )
        async with active_ptys_lock:
            if session_id in active_ptys:
                active_ptys[session_id]["output_task"] = read_task
            else:
                logger.error(
                    f"会话 {session_id} 在存储 output_task 前消失。正在取消任务。"
                )
                read_task.cancel()

        while True:
            if not (pty_process and pty_process.isalive()):
                logger.warning(f"会话 {session_id} 的 PTY 进程不存活。")
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(
                        {"type": "status", "message": "PTY 进程已终止。"}
                    )
                break

            message_str = await websocket.receive_text()

            try:
                msg_data = json.loads(message_str)
                msg_type = msg_data.get("type")

                if msg_type == "input":
                    pty_input_data = msg_data.get("data")
                    if isinstance(pty_input_data, str):
                        try:
                            pty_process.write(pty_input_data.encode("utf-8"))
                        except Exception as e_write:
                            logger.error(
                                f"向会话 {session_id} 的 PTY 写入时出错: {e_write}"
                            )
                            if not pty_process.isalive():
                                if websocket.client_state == WebSocketState.CONNECTED:
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
        logger.info(f"会话 {session_id} 的客户端已断开连接 (WebSocketDisconnect)。")
    except Exception as e_main:
        logger.error(
            f"handle_websocket_connection 中发生意外错误 (会话 {session_id}): {e_main}",
            exc_info=True,
        )
    finally:
        logger.info(f"正在为会话 {session_id} 进行清理...")
        if read_task and not read_task.done():
            read_task.cancel()
            try:
                await read_task
            except asyncio.CancelledError:
                logger.info(f"会话 {session_id} 的 PTY 输出任务已成功取消。")
            except Exception as e_task_cancel:
                logger.error(
                    f"等待已取消的会话 {session_id} PTY 输出任务时出错: {e_task_cancel}"
                )

        async with active_ptys_lock:
            if session_id in active_ptys:
                pty_info = active_ptys.pop(session_id)
                pty_process_to_kill = pty_info.get("pty")
                if pty_process_to_kill and pty_process_to_kill.isalive():
                    logger.info(
                        f"正在终止会话 {session_id} 的 PTY 进程 (PID: {pty_process_to_kill.pid})。"
                    )
                    try:
                        pty_process_to_kill.terminate(force=True)
                    except Exception as e_term:
                        logger.error(f"终止会话 {session_id} 的 PTY 时出错: {e_term}")

        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except RuntimeError as e_close:
                logger.warning(
                    f"关闭会话 {session_id} 的 WebSocket 时发生运行时错误 (可能已自行关闭): {e_close}"
                )

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


try:
    from winpty import PtyProcess  # type: ignore
except ImportError:
    logger.critical("未安装 winpty 库。此模块无法运行。请安装: pip install winpty")
