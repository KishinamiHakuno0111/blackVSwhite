# 黑白棋 · 8×8 Windows 单文件版

8×8 源码分支：https://github.com/KishinamiHakuno0111/blackVSwhite/tree/feature/8x8-board

本分支生成独立命名的 8×8 程序，不覆盖 10×10 程序。既有 v1.0.0 Release 是 10×10 版本。

将 `BlackWhiteChess-8x8.exe` 发给对方，双击即可打开 8×8 黑白棋。
不需要安装 Python、下载依赖或复制源码；游戏离线运行。

目标平台为 Windows 10/11 x64，本次在 Windows 10 x64 验证。
不适用于 macOS、Linux 或 32 位 Windows；尚未在其他电脑实测。
首次打开时需解包内置运行库，可能稍等几秒。程序无需管理员权限。

8×8 与 10×10 存档不互通，界面会拒绝错误尺寸的存档，保留当前对局。

## 操作

- 点击棋盘上带小圆圈的位置落子，默认你执黑、AI 执白。
- 右侧可选人机对战、双人对战或 AI 演示；修改设置后点击“开始新局”。
- 快速、均衡、深入分别使用约 0.3、1、3 秒搜索预算。
- 支持悔棋、推荐落点、保存和载入。存档位置由保存对话框选择。
- 双方都不能落子时自动结算，棋子较多的一方获胜。

## 开发者重新打包

在项目根目录的 PowerShell 运行（需要带 Tkinter 的 64 位 Python）：

```powershell
& .\tools\build_windows.ps1
python tools\verify_windows.py
```

构建环境在 `.venv-build`，输出在 `dist/BlackWhiteChess-8x8.exe`。
依赖版本固定在 `requirements-build.txt`，本次使用 Python 3.14.7 和 PyInstaller 6.22.3。
构建脚本显式收集 Tcl/Tk 脚本资源，修复 Tcl 9 内嵌资源未正确随 exe 加载的问题。
Python、Tcl、Tk 和 PyInstaller 的许可文本已随程序嵌入，也包含在分发压缩包中。

验证脚本把 exe 单独复制到含中文和空格的目录，移除 Python/Tcl 环境路径，
运行实际打包程序的鼠标落子、AI 子进程、提示、悔棋、存档、AI 先手及整局结算检查。
报告保存在 `artifacts/packaging-verification-8x8.json`。这不是在全新系统虚拟机中进行的测试。

内置自动检查入口为 `BlackWhiteChess-8x8.exe --smoke-test 报告文件路径`；正常双击不会运行测试。
