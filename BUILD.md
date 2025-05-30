# MaiLauncher Backend - Cross-Platform Build

这个项目现在支持在 Windows、Linux 和 macOS 三个平台上自动构建可执行文件。

## 自动化构建

### GitHub Actions 工作流

项目配置了 GitHub Actions 工作流 (`.github/workflows/build.yml`)，会在以下情况下自动触发构建：

- 推送到 `main`、`master` 或 `develop` 分支
- 创建针对这些分支的 Pull Request

### 构建矩阵

工作流使用矩阵策略同时在三个平台上构建：

| 平台 | Python 版本 | 输出文件名 | Spec 文件 |
|------|-------------|------------|-----------|
| Windows | 3.12 | MaiLauncher-Backend.exe | main.spec |
| Linux | 3.12 | MaiLauncher-Backend | main-linux.spec |
| macOS | 3.12 | MaiLauncher-Backend | main-macos.spec |

### 工件和发布

- **构建工件**: 每次构建都会上传平台特定的可执行文件作为工件，保留30天
- **自动发布**: 当推送到 `main` 分支时，会自动创建预发布版本，包含所有三个平台的可执行文件

## 本地构建

### 环境准备

1. 安装 Python 3.12
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

### 平台特定构建

#### Windows
```powershell
pyinstaller main.spec
```

#### Linux
```bash
pyinstaller main-linux.spec
```

#### macOS
```bash
pyinstaller main-macos.spec
```

## 依赖管理

项目使用平台特定的依赖管理：

- `requirements.txt`: 当前配置，包含平台特定条件
- `requirements-cross-platform.txt`: 详细的跨平台配置示例

Windows 特定依赖（仅在 Windows 上安装）：
- `pywin32`: Windows API 绑定
- `pywinpty`: Windows 伪终端支持

## Spec 文件配置

- `main.spec`: Windows 构建配置（包含图标和版本信息）
- `main-linux.spec`: Linux 构建配置
- `main-macos.spec`: macOS 构建配置

## 注意事项

1. **图标文件**: Windows 版本使用 `.ico` 格式图标，Linux/macOS 版本不包含图标配置
2. **权限**: Linux/macOS 构建后会自动设置可执行权限
3. **依赖缓存**: GitHub Actions 使用平台特定的 pip 缓存以加速构建
4. **构建优化**: 所有平台都启用了 UPX 压缩以减小文件大小

## 故障排除

如果遇到构建问题：

1. 检查 Python 版本兼容性
2. 确认所有依赖都正确安装
3. 查看 GitHub Actions 日志获取详细错误信息
4. 确保 `data` 目录存在且可访问

## 发布流程

1. 推送代码到 `main` 分支
2. GitHub Actions 自动开始构建
3. 构建完成后，三个平台的可执行文件会自动发布到 Releases 页面
4. 发布版本标记为预发布 (prerelease)，包含提交信息
