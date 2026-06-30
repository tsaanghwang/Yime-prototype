# Weasel Yime smoke cases

本文记录 Yime 接入 Weasel/Rime 后的手工烟测。它不是完整验收清单，只覆盖“真的能
作为 Windows 输入法输入汉字”的最短路径。

## 预检查

先运行部署脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\Yime-variable-length\tools\export_and_deploy_weasel_yime.ps1
```

然后检查：

```powershell
Get-Item $env:APPDATA\Rime\yime_variable.schema.yaml
Get-Item $env:APPDATA\Rime\yime_variable.dict.yaml
Get-Item $env:APPDATA\Rime\build\yime_variable.table.bin
Get-Process WeaselServer
Get-WinUserLanguageList
```

若 `WeaselServer` 未运行，可启动：

```powershell
Start-Process C:\dev\weasel\output\WeaselServer.exe
```

## 真实输入烟测

1. 打开 Notepad、浏览器地址栏或任意普通文本框。
2. 用 `Win+Space` 切到 `中文(简体) - 小狼毫`。
3. 输入 `qu`。
4. 候选窗应出现 Yime 词典中的候选，例如 `幅`、`逼`、`媲` 等。
5. 选择第一个候选并确认能上屏为汉字，而不是直接提交拉丁字母。
6. 输入一个明显无效的长码，例如 `zzzzzz`，确认不会崩溃，也不会污染已有文本。
7. 切换中英文状态，确认英文直通和中文候选都能恢复。

## 方案切换烟测

如果机器上还有其他 Rime schema：

1. 按 Rime/Weasel 的方案切换快捷键打开方案列表。
2. 选择 `Yime variable`。
3. 再输入 `qu`，确认候选仍来自 Yime。

如果方案列表中没有 `Yime variable`，优先检查：

- `%AppData%\Rime\default.custom.yaml` 是否包含 `schema: yime_variable`。
- `%AppData%\Rime\build\yime_variable.table.bin` 是否存在。
- 最近一次脚本运行是否成功完成 `rime_deployer --build`。

## 记录格式

每次真实体验测试建议记录：

- 日期和 Yime commit。
- Weasel commit 或本地构建日期。
- schema id，例如 `yime_variable`。
- 输入码和前几个候选。
- 是否能在 Notepad 里稳定上屏。
