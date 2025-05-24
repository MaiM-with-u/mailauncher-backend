import os
import shutil
import subprocess
from pathlib import Path
from src.utils.logger import get_module_logger
from src.modules.instance_manager import instance_manager

logger = get_module_logger("版本部署工具")


class DeployManager:
    def __init__(self):
        self.primary_repo_url = "https://github.com/MaiM-with-u/MaiBot"
        self.secondary_repo_url = "https://gitee.com/DrSmooth/MaiBot"
        # 项目根目录 e:\\MaimBot\\mailauncher-backend
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.template_dir = self.project_root / "template"

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
                for item in deploy_path.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                logger.info(f"已清空已存在的部署路径 {deploy_path}")
            except Exception as e:
                logger.error(f"清空部署路径 {deploy_path} 失败: {e}")
                return False

        deploy_path.mkdir(parents=True, exist_ok=True)

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
        logger.info(f"尝试从 {repo_url} 克隆版本 {version_tag} 到 {deploy_path}...")

        try:
            process = subprocess.Popen(
                clone_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            stdout, stderr = process.communicate(timeout=300)

            if process.returncode == 0:
                logger.info(
                    f"成功从 {repo_url} 克隆版本 {version_tag} 到 {deploy_path}"
                )
                git_dir = deploy_path / ".git"
                if git_dir.exists() and git_dir.is_dir():
                    logger.info(f"删除克隆下来的 .git 目录: {git_dir}")
                    shutil.rmtree(git_dir)
                return True
            else:
                logger.error(
                    f"从 {repo_url} 克隆失败 (版本: {version_tag})。返回码: {process.returncode}"
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
                process.kill()
                process.communicate()
            return False
        except Exception as e:
            logger.error(
                f"执行 Git 克隆时发生未知错误 ({repo_url}, 版本: {version_tag}): {e}"
            )
            return False

    def deploy_version(
        self, version_tag: str, instance_id: str
    ) -> bool:  # Changed install_path_str to instance_id
        logger.info(f"开始为实例 ID {instance_id} 部署版本 {version_tag}")

        instance = instance_manager.get_instance(instance_id)
        if not instance:
            logger.error(f"部署失败：找不到实例ID {instance_id}。")
            return False

        if not instance.path:
            logger.error(f"部署失败：实例ID {instance_id} 的路径未设置。")
            return False

        deploy_path = Path(instance.path).resolve()
        logger.info(f"获取到实例 {instance_id} 的部署路径: {deploy_path}")

        cloned_successfully = self._run_git_clone(
            self.primary_repo_url, version_tag, deploy_path
        )
        if not cloned_successfully:
            logger.warning(
                f"主仓库 {self.primary_repo_url} 克隆失败 (实例ID: {instance_id})，尝试备用仓库 {self.secondary_repo_url}"
            )
            cloned_successfully = self._run_git_clone(
                self.secondary_repo_url, version_tag, deploy_path
            )
            if not cloned_successfully:
                logger.error(
                    f"主仓库和备用仓库均克隆失败 (实例ID: {instance_id})。部署中止。"
                )
                if deploy_path.exists():
                    logger.info(
                        f"清理部署失败的路径: {deploy_path} (实例ID: {instance_id})"
                    )
                    shutil.rmtree(deploy_path, ignore_errors=True)
                return False

        logger.info(f"代码已成功克隆到 {deploy_path} (实例ID: {instance_id})")

        config_dir = deploy_path / "config"
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"成功创建/确认文件夹: {config_dir} (实例ID: {instance_id})")
        except OSError as e:
            logger.error(
                f"创建 config 文件夹 {config_dir} 失败 (实例ID: {instance_id}): {e}"
            )
            shutil.rmtree(deploy_path, ignore_errors=True)  # 清理
            return False

        template_files_to_copy = {
            "bot_config_template.toml": "bot_config.toml",
            "Ipmm_config_template.toml": "Ipmm_config.toml",
        }
        for template_name, final_name in template_files_to_copy.items():
            source_file = self.template_dir / template_name
            destination_file = config_dir / final_name
            try:
                if not source_file.exists():
                    logger.error(
                        f"模板文件 {source_file} 不存在 (实例ID: {instance_id})。"
                    )
                    shutil.rmtree(deploy_path, ignore_errors=True)  # 清理
                    return False
                shutil.copy2(source_file, destination_file)
                logger.info(
                    f"成功复制 {source_file} 到 {destination_file} (实例ID: {instance_id})"
                )
            except Exception as e:
                logger.error(
                    f"复制文件 {source_file} 到 {destination_file} 失败 (实例ID: {instance_id}): {e}"
                )
                shutil.rmtree(deploy_path, ignore_errors=True)  # 清理
                return False

        env_template_file = self.template_dir / "template.env"
        env_final_file = deploy_path / ".env"
        try:
            if not env_template_file.exists():
                logger.error(
                    f"模板 .env 文件 {env_template_file} 不存在 (实例ID: {instance_id})。"
                )
                shutil.rmtree(deploy_path, ignore_errors=True)  # 清理
                return False
            shutil.copy2(env_template_file, env_final_file)
            logger.info(
                f"成功复制 {env_template_file} 到 {env_final_file} (实例ID: {instance_id})"
            )
        except Exception as e:
            logger.error(
                f"复制文件 {env_template_file} 到 {env_final_file} 失败 (实例ID: {instance_id}): {e}"
            )
            shutil.rmtree(deploy_path, ignore_errors=True)  # 清理
            return False

        logger.info(
            f"版本 {version_tag} 成功部署到 {deploy_path} (实例ID: {instance_id})"
        )
        return True


deploy_manager = DeployManager()
