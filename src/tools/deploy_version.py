import os
import shutil
import subprocess
from pathlib import Path
from src.utils.logger import get_module_logger
import stat  # For file permissions
import sys  # 添加sys导入，用于虚拟环境创建
import re  # 添加正则表达式支持，用于配置文件修改
import hashlib  # 添加hashlib导入，用于生成确认文件哈希
# import errno # For error codes

# Import List for type hinting
from typing import List, Dict, Any, Callable, Optional

logger = get_module_logger("版本部署工具")

# 声明全局日志回调函数变量
_log_callback: Optional[Callable[[str, str, str], None]] = None

def set_log_callback(callback: Callable[[str, str, str], None]):
    """
    设置日志回调函数
    
    Args:
        callback: 回调函数，接受(instance_id, message, level)参数
    """
    global _log_callback
    _log_callback = callback

def _add_log(instance_id: str, message: str, level: str = "info"):
    """
    添加日志，如果设置了回调函数则调用，否则只记录到标准日志
    """
    logger.info(f"[{instance_id}] {message}")
    if _log_callback:
        _log_callback(instance_id, message, level)


def get_python_executable() -> str:
    """
    获取正确的Python解释器路径，处理PyInstaller打包环境。

    Returns:
        str: Python解释器的路径
    """
    # 检测是否在PyInstaller打包的环境中运行
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        logger.info("检测到PyInstaller环境，寻找系统Python解释器...")

        # 尝试常见的Python安装路径
        potential_paths = [
            # Python Launcher
            "py",
            "python",
            "python3",
            # 常见安装路径
            r"C:\Python312\python.exe",
            r"C:\Python311\python.exe",
            r"C:\Python310\python.exe",
            r"C:\Python39\python.exe",
            r"C:\Python38\python.exe",
            # AppData Local 路径
            os.path.expanduser(r"~\AppData\Local\Programs\Python\Python312\python.exe"),
            os.path.expanduser(r"~\AppData\Local\Programs\Python\Python311\python.exe"),
            os.path.expanduser(r"~\AppData\Local\Programs\Python\Python310\python.exe"),
            # Program Files 路径
            r"C:\Program Files\Python312\python.exe",
            r"C:\Program Files\Python311\python.exe",
            r"C:\Program Files\Python310\python.exe",
        ]

        for python_path in potential_paths:
            try:
                # 测试Python解释器是否可用
                result = subprocess.run(
                    [python_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                if result.returncode == 0:
                    logger.info(f"找到可用的Python解释器: {python_path}")
                    logger.info(f"Python版本: {result.stdout.strip()}")
                    return python_path
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue

        # 如果都不行，尝试使用whereis或where命令查找
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["where", "python"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                result = subprocess.run(
                    ["which", "python3"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            if result.returncode == 0:
                python_path = result.stdout.strip().split("\n")[0]
                logger.info(f"通过系统命令找到Python解释器: {python_path}")
                return python_path
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        logger.error("在PyInstaller环境中未能找到可用的Python解释器")
        raise RuntimeError(
            "未能找到可用的Python解释器。请确保Python已正确安装并添加到系统PATH。"
        )
    else:
        # 非PyInstaller环境，使用sys.executable
        logger.info(f"使用当前Python解释器: {sys.executable}")
        return sys.executable


def get_git_executable() -> str:
    """
    获取正确的Git可执行文件路径，处理PyInstaller打包环境。

    Returns:
        str: Git可执行文件的路径
    """
    # 检测是否在PyInstaller打包的环境中运行
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        logger.info("检测到PyInstaller环境，寻找系统Git...")

        # 尝试常见的Git安装路径
        potential_paths = [
            "git",  # 系统PATH中的git
            r"C:\Program Files\Git\bin\git.exe",
            r"C:\Program Files (x86)\Git\bin\git.exe",
            r"C:\Git\bin\git.exe",
            # 便携版Git路径
            r"C:\PortableGit\bin\git.exe",
        ]

        for git_path in potential_paths:
            try:
                # 测试Git是否可用
                result = subprocess.run(
                    [git_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                if result.returncode == 0:
                    logger.info(f"找到可用的Git: {git_path}")
                    logger.info(f"Git版本: {result.stdout.strip()}")
                    return git_path
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue

        # 尝试使用where命令查找
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["where", "git"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                result = subprocess.run(
                    ["which", "git"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            if result.returncode == 0:
                git_path = result.stdout.strip().split("\n")[0]
                logger.info(f"通过系统命令找到Git: {git_path}")
                return git_path
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        logger.error("在PyInstaller环境中未能找到可用的Git")
        raise RuntimeError("未能找到可用的Git。请确保Git已正确安装并添加到系统PATH。")
    else:
        # 非PyInstaller环境，直接使用git命令
        logger.info("使用系统Git命令")
        return "git"


def modify_env_file(env_file_path: Path, instance_port: str, instance_id: str) -> bool:
    """
    修改 .env 文件中的端口配置。

    Args:
        env_file_path: .env 文件路径
        instance_port: 实例端口
        instance_id: 实例ID

    Returns:
        bool: 修改成功返回True，失败返回False
    """
    logger.info(f"开始修改 .env 文件端口配置 (实例ID: {instance_id})")

    try:
        if not env_file_path.exists():
            logger.error(f".env 文件不存在: {env_file_path} (实例ID: {instance_id})")
            return False

        # 读取原文件内容
        with open(env_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 使用正则表达式替换 PORT 配置
        pattern = r"PORT\s*=\s*\d+"
        replacement = f"PORT={instance_port}"

        if re.search(pattern, content):
            new_content = re.sub(pattern, replacement, content)

            # 写回文件
            with open(env_file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            logger.info(
                f"成功修改 .env 文件端口为 {instance_port} (实例ID: {instance_id})"
            )
            return True
        else:
            logger.warning(f".env 文件中未找到 PORT 配置 (实例ID: {instance_id})")
            return False

    except Exception as e:
        logger.error(f"修改 .env 文件失败 (实例ID: {instance_id}): {e}")
        return False


def modify_napcat_config_file(
    config_file_path: Path, napcat_port: str, maibot_port: str, instance_id: str
) -> bool:
    """
    修改 napcat-ada 服务的 config.toml 文件。

    Args:
        config_file_path: config.toml 文件路径
        napcat_port: Napcat 服务端口
        maibot_port: MaiBot 主实例端口
        instance_id: 实例ID

    Returns:
        bool: 修改成功返回True，失败返回False
    """
    logger.info(f"开始修改 napcat-ada config.toml 文件 (实例ID: {instance_id})")

    try:
        if not config_file_path.exists():
            logger.error(
                f"config.toml 文件不存在: {config_file_path} (实例ID: {instance_id})"
            )
            return False

        # 读取原文件内容
        with open(config_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 替换 Napcat_Server 的 port
        napcat_pattern = r"(\[Napcat_Server\].*?port\s*=\s*)\d+"
        napcat_replacement = rf"\g<1>{napcat_port}"
        content = re.sub(napcat_pattern, napcat_replacement, content, flags=re.DOTALL)

        # 替换 MaiBot_Server 的 port
        maibot_pattern = r"(\[MaiBot_Server\].*?port\s*=\s*)\d+"
        maibot_replacement = rf"\g<1>{maibot_port}"
        content = re.sub(
            maibot_pattern, maibot_replacement, content, flags=re.DOTALL
        )  # 写回文件
        with open(config_file_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(
            f"成功修改 napcat-ada config.toml 文件: Napcat端口={napcat_port}, MaiBot端口={maibot_port} (实例ID: {instance_id})"
        )
        return True

    except Exception as e:
        logger.error(
            f"修改 napcat-ada config.toml 文件失败 (实例ID: {instance_id}): {e}"
        )
        return False


def create_agreement_confirmation_files(deploy_path: Path, instance_id: str) -> bool:
    """
    在主程序根目录创建确认文件来自动同意用户协议和隐私政策。

    Args:
        deploy_path: 主程序部署路径
        instance_id: 实例ID

    Returns:
        bool: 创建成功返回True，失败返回False
    """
    logger.info(f"开始创建用户协议和隐私政策确认文件 (实例ID: {instance_id})")

    try:
        eula_file = deploy_path / "EULA.md"
        privacy_file = deploy_path / "PRIVACY.md"
        eula_confirm_file = deploy_path / "eula.confirmed"
        privacy_confirm_file = deploy_path / "privacy.confirmed"

        # 检查EULA文件是否存在并计算哈希值
        if eula_file.exists():
            with open(eula_file, "r", encoding="utf-8") as f:
                eula_content = f.read()
            eula_hash = hashlib.md5(eula_content.encode("utf-8")).hexdigest()

            # 创建EULA确认文件
            eula_confirm_file.write_text(eula_hash, encoding="utf-8")
            logger.info(
                f"成功创建EULA确认文件: {eula_confirm_file} (实例ID: {instance_id})"
            )
        else:
            logger.warning(
                f"EULA.md 文件不存在，跳过EULA确认文件创建 (实例ID: {instance_id})"
            )

        # 检查隐私政策文件是否存在并计算哈希值
        if privacy_file.exists():
            with open(privacy_file, "r", encoding="utf-8") as f:
                privacy_content = f.read()
            privacy_hash = hashlib.md5(privacy_content.encode("utf-8")).hexdigest()

            # 创建隐私政策确认文件
            privacy_confirm_file.write_text(privacy_hash, encoding="utf-8")
            logger.info(
                f"成功创建隐私政策确认文件: {privacy_confirm_file} (实例ID: {instance_id})"
            )
        else:
            logger.warning(
                f"PRIVACY.md 文件不存在，跳过隐私政策确认文件创建 (实例ID: {instance_id})"
            )

        logger.info(f"用户协议和隐私政策确认文件创建完成 (实例ID: {instance_id})")
        return True

    except Exception as e:
        logger.error(f"创建用户协议和隐私政策确认文件失败 (实例ID: {instance_id}): {e}")
        return False


def setup_service_virtual_environment(
    service_path: str, service_name: str, instance_id: str
) -> bool:
    """
    在指定的服务目录中设置虚拟环境并安装依赖。

    Args:
        service_path: 服务目录路径
        service_name: 服务名称
        instance_id: 实例ID

    Returns:
        bool: 设置成功返回True，失败返回False    """
    logger.info(
        f"开始为服务 {service_name} (实例ID: {instance_id}) 在 {service_path} 设置虚拟环境..."
    )
    _add_log(instance_id, f"🔧 开始设置 {service_name} 虚拟环境", "info")

    try:
        # 将工作目录切换到服务目录
        service_dir = Path(service_path).resolve()
        if not service_dir.exists():
            logger.error(
                f"服务目录 {service_dir} 不存在 (服务: {service_name}, 实例ID: {instance_id})"
            )
            _add_log(instance_id, f"❌ 服务目录不存在: {service_dir}", "error")
            return False
        logger.info(
            f"切换工作目录到: {service_dir} (服务: {service_name}, 实例ID: {instance_id})"
        )
        _add_log(instance_id, f"📁 服务目录: {service_dir}", "info")

        # 创建虚拟环境目录路径
        venv_path = service_dir / "venv"        # 获取正确的Python解释器路径
        try:
            python_executable = get_python_executable()
            _add_log(instance_id, f"🐍 Python解释器: {python_executable}", "info")
        except RuntimeError as e:
            logger.error(
                f"获取Python解释器失败 (服务: {service_name}, 实例ID: {instance_id}): {e}"
            )
            _add_log(instance_id, f"❌ 获取Python解释器失败: {e}", "error")
            return False

        # 1. 创建虚拟环境
        logger.info(
            f"创建虚拟环境 {venv_path} (服务: {service_name}, 实例ID: {instance_id})"
        )
        _add_log(instance_id, f"🔨 创建虚拟环境: {venv_path.name}", "info")
        logger.info(
            f"使用Python解释器: {python_executable} (服务: {service_name}, 实例ID: {instance_id})"
        )
        create_venv_cmd = [python_executable, "-m", "venv", str(venv_path)]
        
        result = subprocess.run(
            create_venv_cmd,
            cwd=str(service_dir),
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        
        if result.returncode != 0:
            logger.error(
                f"创建虚拟环境失败 (服务: {service_name}, 实例ID: {instance_id}): {result.stderr}"
            )
            _add_log(instance_id, f"❌ 虚拟环境创建失败: {result.stderr or '未知错误'}", "error")
            return False

        logger.info(f"虚拟环境创建成功 (服务: {service_name}, 实例ID: {instance_id})")

        # 2. 检查requirements.txt是否存在
        requirements_file = service_dir / "requirements.txt"
        if not requirements_file.exists():
            logger.warning(
                f"requirements.txt 文件不存在于 {service_dir} (服务: {service_name}, 实例ID: {instance_id})"
            )
            logger.info(
                f"跳过依赖安装步骤 (服务: {service_name}, 实例ID: {instance_id})"
            )
            return True  # 3. 安装依赖
        logger.info(f"开始安装依赖 (服务: {service_name}, 实例ID: {instance_id})")

        # 在Windows系统中，虚拟环境的Python和pip路径
        if os.name == "nt":
            venv_python_executable = venv_path / "Scripts" / "python.exe"
            venv_pip_executable = venv_path / "Scripts" / "pip.exe"
        else:
            venv_python_executable = venv_path / "bin" / "python"
            venv_pip_executable = venv_path / "bin" / "pip"

        # 验证虚拟环境中的Python可执行文件是否存在
        if not venv_python_executable.exists():
            logger.error(
                f"虚拟环境Python可执行文件不存在: {venv_python_executable} (服务: {service_name}, 实例ID: {instance_id})"
            )
            return False

        logger.info(
            f"使用虚拟环境Python: {venv_python_executable} (服务: {service_name}, 实例ID: {instance_id})"
        )  # 升级pip
        logger.info(f"升级pip (服务: {service_name}, 实例ID: {instance_id})")
        upgrade_pip_cmd = [
            str(venv_python_executable),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",            "-i",
            "https://mirrors.aliyun.com/pypi/simple/",
            "--trusted-host",
            "mirrors.aliyun.com",
        ]
        
        result = subprocess.run(
            upgrade_pip_cmd,
            cwd=str(service_dir),
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        
        if result.returncode != 0:
            logger.warning(
                f"升级pip失败 (服务: {service_name}, 实例ID: {instance_id}): {result.stderr}"
            )
            _add_log(instance_id, f"⚠️ pip升级失败，但继续安装依赖", "warning")
        else:
            logger.info(
                f"pip升级成功 (服务: {service_name}, 实例ID: {instance_id})"
            )
            _add_log(instance_id, f"✅ pip升级成功", "success")
            
        # 安装requirements.txt中的依赖
        _add_log(instance_id, f"📦 开始安装 {service_name} 依赖包", "info")
        install_deps_cmd = [
            str(venv_pip_executable),
            "install",
            "-r",
            str(requirements_file),
            "-i",
            "https://mirrors.aliyun.com/pypi/simple/",
            "--trusted-host",
            "mirrors.aliyun.com",
        ]

        logger.info(
            f"执行依赖安装命令: {' '.join(install_deps_cmd)} (服务: {service_name}, 实例ID: {instance_id})"
        )

        try:
            result = subprocess.run(
                install_deps_cmd,
                cwd=str(service_dir),
                capture_output=True,
                text=True,
                timeout=900,  # 增加超时时间到15分钟
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else "未知错误"
                logger.error(
                    f"依赖安装失败 (服务: {service_name}, 实例ID: {instance_id}): {error_msg}"
                )
                
                # 记录详细的错误信息用于调试
                if result.stdout:
                    logger.error(f"pip stdout: {result.stdout}")
                if result.stderr:
                    logger.error(f"pip stderr: {result.stderr}")
                    
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"依赖安装超时 (服务: {service_name}, 实例ID: {instance_id})")
            return False

        logger.info(f"依赖安装成功 (服务: {service_name}, 实例ID: {instance_id})")
        logger.info(f"虚拟环境设置完成 (服务: {service_name}, 实例ID: {instance_id})")

        return True

    except subprocess.TimeoutExpired:
        logger.error(f"虚拟环境设置超时 (服务: {service_name}, 实例ID: {instance_id})")
        return False
    except Exception as e:
        logger.error(
            f"设置虚拟环境时发生异常 (服务: {service_name}, 实例ID: {instance_id}): {e}"
        )
        return False


class DeployManager:
    def __init__(self):
        self.primary_repo_url = "https://github.com/MaiM-with-u/MaiBot"
        self.secondary_repo_url = "https://gitee.com/DrSmooth/MaiBot"

        # 服务特定的仓库 URL 映射
        self.service_repos = {
            "napcat-ada": {
                "primary": "https://github.com/MaiM-with-u/MaiBot-Napcat-Adapter",
                "secondary": "https://gitee.com/DrSmooth/MaiBot-Napcat-Adapter",
                "branch": "main",
                "template_config": "template_config.toml",
                "final_config": "config.toml",
            }
        }  # 保持向后兼容性
        self.napcat_ada_primary_repo_url = self.service_repos["napcat-ada"]["primary"]
        self.napcat_ada_secondary_repo_url = self.service_repos["napcat-ada"][
            "secondary"
        ]

    def _deploy_service(
        self,
        service_config: Dict[str, Any],
        instance_id: str,
        resolved_deploy_path: Path,
        main_instance_port: str = None,
    ) -> bool:
        """
        部署单个服务的通用方法。

        Args:
            service_config: 服务配置字典
            instance_id: 实例ID
            resolved_deploy_path: 主应用部署路径，用于清理时使用
            main_instance_port: 主实例端口，用于配置服务连接

        Returns:
            bool: 部署成功返回True，失败返回False
        """
        service_name = service_config.get("name")
        service_path_str = service_config.get("path")

        if not service_name:
            logger.error(f"服务配置缺少 'name' 字段 (实例ID: {instance_id})")
            return False

        if not service_path_str:
            logger.error(
                f"服务 '{service_name}' 配置缺少 'path' 字段 (实例ID: {instance_id})"
            )
            return False

        if service_name not in self.service_repos:
            logger.warning(
                f"不支持的服务类型: '{service_name}' (实例ID: {instance_id})"
            )
            logger.info(f"跳过服务 '{service_name}' 的部署 (实例ID: {instance_id})")
            return True  # 跳过不支持的服务，不视为错误

        service_deploy_path = Path(service_path_str).resolve()
        service_repo_info = self.service_repos[service_name]

        logger.info(
            f"开始部署服务 '{service_name}' 到: {service_deploy_path} (实例ID: {instance_id})"
        )

        # 克隆服务代码
        cloned_service_successfully = self._run_git_clone(
            service_repo_info["primary"],
            service_repo_info["branch"],
            service_deploy_path,
        )

        if not cloned_service_successfully:
            logger.warning(
                f"从主仓库克隆 '{service_name}' 服务失败，尝试备用仓库 (实例ID: {instance_id})"
            )
            cloned_service_successfully = self._run_git_clone(
                service_repo_info["secondary"],
                service_repo_info["branch"],
                service_deploy_path,
            )

        if not cloned_service_successfully:
            logger.error(
                f"从主仓库和备用仓库均克隆 '{service_name}' 服务失败 (实例ID: {instance_id})"
            )
            if service_deploy_path.exists():
                shutil.rmtree(service_deploy_path, ignore_errors=True)
            return False

        logger.info(
            f"服务 '{service_name}' 代码已成功克隆到 {service_deploy_path} (实例ID: {instance_id})"
        )

        # 复制服务配置文件 - 使用服务自己的 template 目录
        template_config_name = service_repo_info["template_config"]
        final_config_name = service_repo_info["final_config"]
        service_template_dir = service_deploy_path / "template"
        source_service_config = service_template_dir / template_config_name
        destination_service_config = service_deploy_path / final_config_name

        try:
            if not source_service_config.exists():
                logger.warning(
                    f"服务模板配置文件 {source_service_config} 不存在，跳过配置文件复制 (服务: {service_name}, 实例ID: {instance_id})"
                )
            else:
                shutil.copy2(source_service_config, destination_service_config)
                logger.info(
                    f"成功复制服务配置文件 {source_service_config} 到 {destination_service_config} (实例ID: {instance_id})"
                )
        except Exception as e:
            logger.error(
                f"复制服务配置文件失败: {e} (服务: {service_name}, 实例ID: {instance_id})"
            )
            if service_deploy_path.exists():
                shutil.rmtree(service_deploy_path, ignore_errors=True)
            return False

        # 设置服务的虚拟环境
        logger.info(f"开始为服务 '{service_name}' 设置虚拟环境 (实例ID: {instance_id})")
        venv_success = setup_service_virtual_environment(
            str(service_deploy_path), service_name, instance_id
        )
        if not venv_success:
            logger.error(
                f"为服务 '{service_name}' 设置虚拟环境失败 (实例ID: {instance_id})"
            )
            if service_deploy_path.exists():
                shutil.rmtree(service_deploy_path, ignore_errors=True)
            return False

        # 修改服务特定的配置文件
        if service_name == "napcat-ada" and main_instance_port:
            logger.info(f"开始修改 napcat-ada 配置文件 (实例ID: {instance_id})")
            config_file_path = service_deploy_path / final_config_name
            service_port = service_config.get("port", "8095")  # 默认使用8095端口

            config_success = modify_napcat_config_file(
                config_file_path, service_port, main_instance_port, instance_id
            )
            if not config_success:
                logger.error(f"修改 napcat-ada 配置文件失败 (实例ID: {instance_id})")
                if service_deploy_path.exists():
                    shutil.rmtree(service_deploy_path, ignore_errors=True)
                return False

        logger.info(
            f"服务 '{service_name}' 部署和虚拟环境设置成功 (实例ID: {instance_id})"
        )
        return True

    def _run_git_clone(
        self, repo_url: str, version_tag: str, deploy_path: Path
    ) -> bool:
        """
        克隆指定版本到指定路径。
        源代码将直接位于 deploy_path 下。
        """
        if deploy_path.exists() and any(deploy_path.iterdir()):
            logger.error(
                f"部署路径 {deploy_path} 已存在且非空，无法继续部署。请清空目录后重试。"
            )
            return False
        deploy_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"目录 {deploy_path} 已确认存在。")

        # 获取正确的Git可执行文件路径
        try:
            git_executable = get_git_executable()
        except RuntimeError as e:
            logger.error(f"获取Git可执行文件失败: {e}")
            return False

        clone_command = [
            git_executable,
            "clone",
            "--branch",
            version_tag,
            "--depth",
            "1",  # 浅克隆，只获取指定版本历史
            repo_url,
            str(deploy_path),  # 将仓库内容直接克隆到 deploy_path
        ]
        logger.info(
            f"准备执行 Git clone 命令: {' '.join(clone_command)} (版本: {version_tag})"
        )
        logger.info(f"尝试从 {repo_url} 克隆版本 {version_tag} 到 {deploy_path}...")
        logger.debug(f"执行的 Git 命令: {' '.join(clone_command)}")

        try:
            logger.info("开始执行 Git clone 命令...")
            process = subprocess.Popen(
                clone_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            stdout, stderr = process.communicate(timeout=300)
            logger.info(f"Git clone 命令执行完毕。返回码: {process.returncode}")

            if process.returncode == 0:
                logger.info(
                    f"成功从 {repo_url} 克隆版本 {version_tag} 到 {deploy_path}"
                )
                try:
                    cloned_contents = os.listdir(deploy_path)
                    logger.info(f"克隆后的目录 {deploy_path} 内容: {cloned_contents}")
                except Exception as e_list:
                    logger.error(f"列出目录 {deploy_path} 内容失败: {e_list}")

                git_dir = deploy_path / ".git"
                if git_dir.is_dir():
                    logger.info(f"保留 .git 目录: {git_dir}")
                else:
                    logger.warning(f"克隆完成后未找到 .git 目录: {git_dir}")
                return True
            else:
                logger.error(
                    f"从 {repo_url} 克 clone 失败 (版本: {version_tag})。返回码: {process.returncode}"
                )
                logger.error(f"Git Stdout: {stdout.strip()}")
                logger.error(f"Git Stderr: {stderr.strip()}")
                return False
        except FileNotFoundError:
            logger.error("Git 命令未找到。请确保 Git 已安装并已添加到系统 PATH。")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Git 克隆操作超时 ({repo_url}, 版本: {version_tag})。")
            if process:
                logger.info(
                    f"由于超时，正在终止 Git 进程 (PID: {process.pid if hasattr(process, 'pid') else 'N/A'}) "
                )
                process.kill()
                process.communicate()
                logger.info("Git 进程已终止。")
            return False
        except Exception as e:
            logger.error(
                f"执行 Git 克隆时发生未知错误 ({repo_url}, 版本: {version_tag}): {e}"
            )
            return False

    def _handle_remove_readonly(self, func, path, exc_info):
        """
        Error handler for shutil.rmtree.

        If the error is due to an access error (read only file)
        it attempts to add write permission and then retries the
        remove. If the error is for another reason it re-raises
        the error.

        Note: exc_info is now a required parameter for onexc.
        """
        # Check if file access error
        # exc_info[0] is the exception type, exc_info[1] is the exception instance
        exc_type, exc_instance, _ = exc_info  # Unpack the exc_info tuple
        if isinstance(exc_instance, PermissionError):
            if not os.access(path, os.W_OK):
                # Try to change the perm
                os.chmod(path, stat.S_IWUSR)
                # Retry the function
                func(path)
            else:
                # Re-raise the error if it's not a permission issue we can fix
                raise exc_instance  # Raise the original exception instance
        else:
            # Re-raise other errors
            raise exc_instance  # Raise the original exception instance

    def deploy_version(
        self,
        version_tag: str,
        deploy_path: Path,  # MODIFIED: Accept deploy_path directly
        instance_id: str,
        services_to_install: List[Dict[str, Any]],
        instance_port: str,  # 新增: 实例端口参数
    ) -> bool:
        # MODIFIED: Updated log message and use resolved deploy_path
        resolved_deploy_path = deploy_path.resolve()
        logger.info(
            f"开始为实例 ID {instance_id} 部署版本 {version_tag} 到路径 {resolved_deploy_path}"
        )

        logger.info(
            f"部署操作将在以下绝对路径执行: {resolved_deploy_path} (实例ID: {instance_id})"
        )

        cloned_successfully = self._run_git_clone(
            self.primary_repo_url, version_tag, resolved_deploy_path
        )
        if not cloned_successfully:
            logger.warning(
                f"主仓库 {self.primary_repo_url} 克隆失败 (实例ID: {instance_id})，尝试备用仓库 {self.secondary_repo_url}"
            )
            cloned_successfully = self._run_git_clone(
                self.secondary_repo_url, version_tag, resolved_deploy_path
            )
            if not cloned_successfully:
                logger.error(
                    f"主仓库和备用仓库均克隆失败 (实例ID: {instance_id})。部署中止。"
                )
                if resolved_deploy_path.exists():
                    logger.info(
                        f"清理部署失败的路径: {resolved_deploy_path} (实例ID: {instance_id})"
                    )
                    shutil.rmtree(resolved_deploy_path, ignore_errors=True)
                return False

        logger.info(f"代码已成功克隆到 {resolved_deploy_path} (实例ID: {instance_id})")

        # 创建用户协议和隐私政策确认文件
        confirmation_success = create_agreement_confirmation_files(
            resolved_deploy_path, instance_id
        )
        if not confirmation_success:
            logger.warning(
                f"创建确认文件失败，但不影响部署继续进行 (实例ID: {instance_id})"
            )

        config_dir = resolved_deploy_path / "config"
        template_dir = resolved_deploy_path / "template"
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"成功创建/确认文件夹: {config_dir} (实例ID: {instance_id})")
        except OSError as e:
            logger.error(
                f"创建 config 文件夹 {config_dir} 失败 (实例ID: {instance_id}): {e}"
            )
            shutil.rmtree(resolved_deploy_path, ignore_errors=True)  # 清理
            return False

        template_files_to_copy = {
            "bot_config_template.toml": "bot_config.toml",
            "lpmm_config_template.toml": "lpmm_config.toml",
        }
        for template_name, final_name in template_files_to_copy.items():
            source_file = template_dir / template_name
            destination_file = config_dir / final_name
            try:
                if not source_file.exists():
                    logger.error(
                        f"模板文件 {source_file} 不存在 (实例ID: {instance_id})。"
                    )
                    shutil.rmtree(resolved_deploy_path, ignore_errors=True)  # 清理
                    return False
                shutil.copy2(source_file, destination_file)
                logger.info(
                    f"成功复制 {source_file} 到 {destination_file} (实例ID: {instance_id})"
                )
            except Exception as e:
                logger.error(
                    f"复制文件 {source_file} 到 {destination_file} 失败 (实例ID: {instance_id}): {e}"
                )
                shutil.rmtree(resolved_deploy_path, ignore_errors=True)  # 清理
                return False

        env_template_file = template_dir / "template.env"
        env_final_file = resolved_deploy_path / ".env"
        try:
            if not env_template_file.exists():
                logger.error(
                    f"模板 .env 文件 {env_template_file} 不存在 (实例ID: {instance_id})。"
                )
                shutil.rmtree(resolved_deploy_path, ignore_errors=True)  # 清理
                return False  # Added return False based on similar logic above
            shutil.copy2(env_template_file, env_final_file)
            logger.info(
                f"成功复制 {env_template_file} 到 {env_final_file} (实例ID: {instance_id})"
            )
        except Exception as e:
            logger.error(
                f"复制文件 {env_template_file} 到 {env_final_file} 失败 (实例ID: {instance_id}): {e}"
            )
            shutil.rmtree(resolved_deploy_path, ignore_errors=True)  # 清理
            return False

        # 修改 .env 文件中的端口配置
        logger.info(f"开始修改主程序 .env 文件端口配置 (实例ID: {instance_id})")
        env_success = modify_env_file(env_final_file, instance_port, instance_id)
        if not env_success:
            logger.error(f"修改主程序 .env 文件失败 (实例ID: {instance_id})")
            shutil.rmtree(resolved_deploy_path, ignore_errors=True)  # 清理
            return False

        logger.info(
            f"主应用文件部署完成 (实例ID: {instance_id})。开始处理服务部署..."
        )  # 服务部署逻辑 - 使用通用方法处理所有服务
        services_deployed = 0
        total_services = len(services_to_install)
        for service_config in services_to_install:
            service_name = service_config.get("name", "unknown")
            logger.info(
                f"正在部署服务 '{service_name}' ({services_deployed + 1}/{total_services}) (实例ID: {instance_id})"
            )

            service_success = self._deploy_service(
                service_config, instance_id, resolved_deploy_path, instance_port
            )
            if not service_success:
                logger.error(
                    f"服务 '{service_name}' 部署失败，终止整个部署过程 (实例ID: {instance_id})"
                )
                shutil.rmtree(resolved_deploy_path, ignore_errors=True)
                return False

            services_deployed += 1
            logger.info(
                f"服务 '{service_name}' 部署完成 ({services_deployed}/{total_services}) (实例ID: {instance_id})"
            )

        if total_services == 0:
            logger.info(f"未指定要部署的服务，跳过服务部署步骤 (实例ID: {instance_id})")
        else:
            logger.info(
                f"所有服务 ({services_deployed}/{total_services}) 部署完成 (实例ID: {instance_id})"
            )

        logger.info(
            f"版本 {version_tag} 及所选服务已成功部署到 {resolved_deploy_path} (实例ID: {instance_id})"
        )
        return True


deploy_manager = DeployManager()
