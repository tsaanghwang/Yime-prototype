# Weasel / Rime adapter for Yime

本文记录当前已经跑通的 Windows 系统级输入法路径：Yime 生成 Rime
schema/dict，由 librime 编译用户数据，再由 Weasel 作为 TSF 前端消费。

## 当前定位

- Yime 仍负责生成三种编码模式的数据：等长模式、变长模式、省键模式。
- Rime 导出器负责把其中一种模式导出为 `yime_*.schema.yaml` 和
  `yime_*.dict.yaml`。
- Weasel 不直接理解 Yime 内部数据库，只消费 Rime 的 schema/dict 和编译后的
  `build/*.bin`。

## 本机验证路径

当前验证使用以下本机路径：

- Yime: `C:\dev\Yime-variable-length`
- Weasel: `C:\dev\weasel`
- Boost: `C:\dev\librime\deps\boost-1.89.0`
- Weasel shared data: `C:\dev\weasel\output\data`
- Rime user data: `%AppData%\Rime`

这些路径不是代码约束；新机器上可以通过脚本参数覆盖。

## Weasel 构建前提

Visual Studio Build Tools 需要包含 C++ 工具链、Windows SDK、CMake，以及 ATL/MFC。
本次可用的 ATL/MFC 组件为：

```powershell
Microsoft.VisualStudio.Component.VC.14.44.17.14.MFC
```

缺少 ATL/MFC 时，Weasel 会在编译 `WeaselTSF` 时找不到 `atlbase.h`。

`C:\dev\weasel\env.bat` 当前验证过的关键配置如下：

```bat
set WEASEL_ROOT=%CD%
set BOOST_ROOT=C:\dev\librime\deps\boost-1.89.0
set BJAM_TOOLSET=msvc-14.3
set CMAKE_GENERATOR="Visual Studio 17 2022"
set PLATFORM_TOOLSET=v143
set common_cmake_flags=%common_cmake_flags% -DCMAKE_GENERATOR_INSTANCE:PATH="C:\BuildTools"
set DEVTOOLS_PATH=C:\BuildTools\MSBuild\Current\Bin\amd64;C:\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin;
```

构建命令：

```powershell
cmd /c """C:\BuildTools\Common7\Tools\VsDevCmd.bat"" -arch=x64 -host_arch=x64 && cd /d C:\dev\weasel && build.bat boost"
cmd /c """C:\BuildTools\Common7\Tools\VsDevCmd.bat"" -arch=x64 -host_arch=x64 && cd /d C:\dev\weasel && build.bat rime"
cmd /c """C:\BuildTools\Common7\Tools\VsDevCmd.bat"" -arch=x64 -host_arch=x64 && cd /d C:\dev\weasel && build.bat weasel"
```

构建成功后，关键产物位于：

- `C:\dev\weasel\output\weaselx64.dll`
- `C:\dev\weasel\output\WeaselServer.exe`
- `C:\dev\weasel\output\WeaselSetup.exe`
- `C:\dev\weasel\librime\build_x64\bin\Release\rime_deployer.exe`

## 准备 Weasel shared data

Weasel 输出目录需要有 librime 的基础 shared data。当前验证用法是：

```powershell
Copy-Item C:\dev\weasel\librime\data\minimal\* C:\dev\weasel\output\data -Recurse -Force
New-Item -ItemType Directory C:\dev\weasel\output\data\opencc -Force
Copy-Item C:\dev\weasel\librime\share\opencc\* C:\dev\weasel\output\data\opencc -Recurse -Force
```

## 一键导出并部署 Yime

默认部署变长模式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\Yime-variable-length\tools\export_and_deploy_weasel_yime.ps1
```

等长模式和省键模式也可以导出：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\Yime-variable-length\tools\export_and_deploy_weasel_yime.ps1 -Mode full
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\Yime-variable-length\tools\export_and_deploy_weasel_yime.ps1 -Mode shorthand
```

脚本会：

- 调用 `yime/export_rime_yime.py` 生成 Rime schema/dict。
- 复制生成物到 `%AppData%\Rime`。
- 备份并写入 `default.custom.yaml` 和 `user.yaml`，把当前 schema 设为候选方案。
- 调用 `rime_deployer.exe --build` 编译用户数据。

如需同时注册或启动 Weasel：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\Yime-variable-length\tools\export_and_deploy_weasel_yime.ps1 -RegisterWeasel -StartWeaselServer
```

`-RegisterWeasel` 会调用 `WeaselSetup.exe /s`，可能需要管理员权限。

## 验证点

部署后应能看到：

- `%AppData%\Rime\yime_variable.schema.yaml`
- `%AppData%\Rime\yime_variable.dict.yaml`
- `%AppData%\Rime\build\yime_variable.table.bin`

系统级注册可用下面的命令检查：

```powershell
Get-WinUserLanguageList
Get-Process WeaselServer
```

中文简体语言列表中应出现 Weasel 的 TSF profile；`WeaselServer.exe` 应在运行。

## 注意

WeaselDeployer 首次运行时可能打开 UI，尤其是在配置文件为空或需要初始化时。
为了减少自动化中的阻塞，Yime 当前脚本直接调用 librime 的 `rime_deployer.exe
--build`。
