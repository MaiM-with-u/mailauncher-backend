import os
import shutil
import subprocess
from pathlib import Path
from src.utils.logger import get_module_logger
import stat  # For file permissions
import sys  # 添加sys导入，用于虚拟环境创建
import re  # 添加正则表达式支持，用于配置文件修改
# import errno # For error codes

# Import List for type hinting
from typing import List, Dict, Any

logger = get_module_logger("版本部署工具")


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
        with open(env_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用正则表达式替换 PORT 配置
        pattern = r'PORT\s*=\s*\d+'
        replacement = f'PORT={instance_port}'
        
        if re.search(pattern, content):
            new_content = re.sub(pattern, replacement, content)
            
            # 写回文件
            with open(env_file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            logger.info(f"成功修改 .env 文件端口为 {instance_port} (实例ID: {instance_id})")
            return True
        else:
            logger.warning(f".env 文件中未找到 PORT 配置 (实例ID: {instance_id})")
            return False
            
    except Exception as e:
        logger.error(f"修改 .env 文件失败 (实例ID: {instance_id}): {e}")
        return False


def modify_napcat_config_file(
    config_file_path: Path, 
    napcat_port: str, 
    maibot_port: str, 
    instance_id: str
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
            logger.error(f"config.toml 文件不存在: {config_file_path} (实例ID: {instance_id})")
            return False
        
        # 读取原文件内容
        with open(config_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 替换 Napcat_Server 的 port
        napcat_pattern = r'(\[Napcat_Server\].*?port\s*=\s*)\d+'
        napcat_replacement = rf'\g<1>{napcat_port}'
        content = re.sub(napcat_pattern, napcat_replacement, content, flags=re.DOTALL)
        
        # 替换 MaiBot_Server 的 port
        maibot_pattern = r'(\[MaiBot_Server\].*?port\s*=\s*)\d+'
        maibot_replacement = rf'\g<1>{maibot_port}'
        content = re.sub(maibot_pattern, maibot_replacement, content, flags=re.DOTALL)
        
        # 写回文件
        with open(config_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(
            f"成功修改 napcat-ada config.toml 文件: Napcat端口={napcat_port}, MaiBot端口={maibot_port} (实例ID: {instance_id})"
        )
        return True
        
    except Exception as e:
        logger.error(f"修改 napcat-ada config.toml 文件失败 (实例ID: {instance_id}): {e}")
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
        bool: 设置成功返回True，失败返回False
    """
    logger.info(
        f"开始为服务 {service_name} (实例ID: {instance_id}) 在 {service_path} 设置虚拟环境..."
    )

    try:
        # 将工作目录切换到服务目录
        service_dir = Path(service_path).resolve()
        if not service_dir.exists():
            logger.error(
                f"服务目录 {service_dir} 不存在 (服务: {service_name}, 实例ID: {instance_id})"
            )
            return False

        logger.info(
            f"切换工作目录到: {service_dir} (服务: {service_name}, 实例ID: {instance_id})"
        )

        # 创建虚拟环境目录路径
        venv_path = service_dir / "venv"

        # 1. 创建虚拟环境
        logger.info(
            f"创建虚拟环境 {venv_path} (服务: {service_name}, 实例ID: {instance_id})"
        )
        create_venv_cmd = [sys.executable, "-m", "venv", str(venv_path)]

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
            return True

        # 3. 安装依赖
        logger.info(f"开始安装依赖 (服务: {service_name}, 实例ID: {instance_id})")

        # 在Windows系统中，虚拟环境的Python和pip路径
        if os.name == "nt":
            python_executable = venv_path / "Scripts" / "python.exe"
            pip_executable = venv_path / "Scripts" / "pip.exe"
        else:
            python_executable = venv_path / "bin" / "python"
            pip_executable = venv_path / "bin" / "pip"

        # 升级pip
        logger.info(f"升级pip (服务: {service_name}, 实例ID: {instance_id})")
        upgrade_pip_cmd = [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
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
        else:
            logger.info(f"pip升级成功 (服务: {service_name}, 实例ID: {instance_id})")

        # 安装requirements.txt中的依赖
        install_deps_cmd = [
            str(pip_executable),
            "install",
            "-r",
            str(requirements_file),
        ]

        logger.info(
            f"执行依赖安装命令: {' '.join(install_deps_cmd)} (服务: {service_name}, 实例ID: {instance_id})"
        )

        result = subprocess.run(
            install_deps_cmd,
            cwd=str(service_dir),
            capture_output=True,
            text=True,
            timeout=600,  # 依赖安装可能需要更长时间
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        if result.returncode != 0:
            logger.error(
                f"依赖安装失败 (服务: {service_name}, 实例ID: {instance_id}): {result.stderr}"
            )
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
                logger.error(
                    f"修改 napcat-ada 配置文件失败 (实例ID: {instance_id})"
                )
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
            logger.warning(f"部署路径 {deploy_path} 已存在且非空。正在尝试清空...")
            try:
                # Enhanced directory clearing
                for item in deploy_path.iterdir():
                    if item.is_dir():
                        # Attempt to remove read-only flags from .git directory contents
                        if item.name == ".git":
                            for root, dirs, files in os.walk(item, topdown=False):
                                for name in files:
                                    filename = os.path.join(root, name)
                                    os.chmod(filename, stat.S_IWUSR)
                                for name in dirs:
                                    os.chmod(os.path.join(root, name), stat.S_IWUSR)
                        shutil.rmtree(item, onexc=self._handle_remove_readonly)
                    else:
                        if not os.access(item, os.W_OK):
                            os.chmod(item, stat.S_IWUSR)
                        item.unlink()
                logger.info(f"已清空已存在的部署路径 {deploy_path}")
            except Exception as e:
                logger.error(f"清空部署路径 {deploy_path} 失败: {e}")
                return False

        logger.info(f"准备在 {deploy_path} 创建目录（如果不存在）。")
        deploy_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"目录 {deploy_path} 已确认存在。")

        clone_command = [
            "git",
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
                raise exc_instance  # Raise the original exception instance        else:
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

        logger.info(f"主应用文件部署完成 (实例ID: {instance_id})。开始处理服务部署...")        # 服务部署逻辑 - 使用通用方法处理所有服务
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
