# PIME / Rime adapter for Yime

本文记录 Yime 数据接入 PIME 的当前约定。PIME 不是 Yime 的子模块；这里仅记录 Yime 应如何向 PIME 提供数据，以及本地验证过的集成边界。

## 角色边界

- Yime：生成等长模式、变长模式、省键模式的运行时编码数据。
- Yime Rime 导出器：把指定模式导出为 Rime schema/dict。
- PIME Go backend：消费 Rime schema/dict，并把输入请求转交给 Rime 输入法实现。
- PIME TSF 外壳：注册为 Windows 系统输入法，并把宿主应用中的按键事件转发给 backend。

Yime 不直接调用 TSF/COM，也不直接加载 PIME TSF DLL。

## 本地路径

当前本机验证路径：

- Yime：`C:\dev\Yime-variable-length`
- PIME：`C:\dev\Pime`
- PIME 安装目录：`C:\Program Files (x86)\PIME`
- PIME Rime 数据目录：`C:\dev\Pime\go-backend\input_methods\rime\data`
- PIME 用户 Rime 数据目录：`%AppData%\PIME\Rime`

这些路径是本地验证记录，不是代码硬约束。

## Yime 侧导出

Yime 侧仍使用同一个导出器：

```powershell
python C:\dev\Yime-variable-length\yime\export_rime_yime.py --mode variable --code-form layout-key --output-dir C:\dev\Yime-variable-length\.generated\rime
```

可选模式：

- `full`：等长模式
- `variable`：变长模式
- `shorthand`：省键模式

默认建议先验证 `variable`，因为它是当前主要试验路径。

## PIME 侧消费

PIME 侧需要把 Yime 导出的 schema/dict 放入其 Rime 数据目录，并确保 Go backend 打包时包含这些文件。当前 PIME 仓库已有辅助脚本用于从 Yime 导出并复制数据：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\Pime\tools\deploy-yime-rime-data.ps1
```

随后构建 PIME Go backend：

```powershell
cd C:\dev\Pime
$env:PATH = "C:\Program Files\Go\bin;$env:PATH"
cmd /c go-backend\build.bat
```

## 已知关键约束

PIME TSF DLL 通过 C++ 读取 backend 返回的 JSON。Go backend 返回给 TSF 的 `return` 字段必须是 JSON boolean，而不是数字 `1` 或 `0`。

错误形态：

```json
{"return":1}
```

正确形态：

```json
{"return":true}
```

如果字段类型不匹配，C++ 侧读取 bool 时可能抛异常，并导致 Notepad、IDE 等宿主进程退出。

## 当前状态

截至 2026-07-01：

- PIME 本地分支 `codex/pime-upstream-sync` 已可编译。
- PIME 已能安装到 `C:\Program Files (x86)\PIME`。
- PIME Go/Rime 路线已经能实际输入汉字。
- 该路线仍处于集成原型阶段，尚未完成稳定性验收。

## 建议烟测

1. 确认 `PIMELauncher.exe` 正在运行。
2. 打开 Notepad。
3. 切换到 PIME Go/Rime 输入法。
4. 输入一个 Yime 已知编码，例如 `qu`。
5. 确认候选来自 Yime/Rime 数据，并能上屏汉字。
6. 测试无效长码、中英文切换、退格和连续输入。
7. 检查 Windows Application 日志，确认没有新的宿主崩溃。
