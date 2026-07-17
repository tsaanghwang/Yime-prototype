# Windows frontends status

本文记录 `codex/yime-distribution-frontends` 分支上，Yime 面向 Windows 系统级输入法前端的当前状态。

## 定位

Yime 仓库只作为输入方案的数据源和导出工具仓库，不承载 Weasel、librime 或 PIME 的源码。

当前边界如下：

- Yime 负责生成三种编码模式的数据：等长模式、变长模式、省键模式。
- Rime 导出器负责把其中一种模式导出为 Rime schema/dict。
- Weasel/Rime 消费导出的 schema/dict，并由 librime 编译为用户数据。
- PIME 目前作为另一条 TSF 外壳验证路径，消费同一批 Rime schema/dict 数据。

## 当前分支状态

- 分支：`codex/yime-distribution-frontends`
- 已有 Rime 导出入口：`yime/export_rime_yime.py`
- 已有 Weasel 部署入口：`tools/export_and_deploy_weasel_yime.ps1`
- 支持导出模式：`full`、`variable`、`shorthand`
- 默认导出模式：`variable`

## Weasel / Rime 路线

当前已跑通的路径：

1. Yime 从运行时数据库导出 `yime_*.schema.yaml` 和 `yime_*.dict.yaml`。
2. 部署脚本把导出物复制到 Rime user data 目录。
3. 脚本调用 `rime_deployer.exe --build` 编译 Rime 用户数据。
4. Weasel 作为系统级输入法前端消费编译后的 Rime 数据。

常用命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\Yime-variable-length\tools\export_and_deploy_weasel_yime.ps1 -Mode variable
```

本地隔离烟测可指定临时目录，避免覆盖真实 `%AppData%\Rime`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\Yime-variable-length\tools\export_and_deploy_weasel_yime.ps1 -Mode variable -OutputDir C:\dev\Yime-variable-length\.generated\rime-smoke\variable -RimeUserDir C:\dev\Yime-variable-length\.generated\rime-user-smoke\variable -NoBackup
```

## PIME 路线

当前已跑通的路径：

1. Yime 导出 Rime schema/dict。
2. PIME Go backend 中的 Rime 输入法目录消费这些导出物。
3. PIME TSF 外壳通过 Go backend 调用 Rime 数据。
4. 本地实测已经达到“能输字”的状态。

PIME 侧源码和构建产物位于 `C:\dev\Pime`，不纳入 Yime 仓库。

当前 PIME 路线仍是集成原型状态，重点风险包括：

- TSF DLL 运行在宿主进程内，异常会影响 Notepad、IDE 等宿主。
- Go backend 返回给 C++ TSF 的 JSON 字段类型必须严格匹配。
- 真实输入体验还需要继续覆盖候选、翻页、提交、退格、中英文切换和长时间稳定性。

## 最近一次 Yime 侧基线

2026-07-01 当前基线：

- `python -m pytest`：`215 passed, 1 skipped`
- Rime 导出器支持三种模式：`full`、`variable`、`shorthand`
- Weasel/Rime 和 PIME 均已证明可以消费 Yime 导出的数据

三种模式的隔离 Rime 导出/编译烟测结果：

| mode | rows | codes | schema |
| --- | ---: | ---: | --- |
| `full` | 468166 | 309753 | `yime_full` |
| `variable` | 468166 | 309731 | `yime_variable` |
| `shorthand` | 468166 | 309730 | `yime_shorthand` |

以上烟测使用 `.generated/rime-smoke/*` 和 `.generated/rime-user-smoke/*`，不覆盖真实 `%AppData%/Rime`。

## 下一步

优先级建议：

1. 保持 Yime 仓库只输出数据和部署脚本，避免把前端源码混入本仓库。
2. 每次改运行时数据或编码模式后，跑三种模式的 Rime 导出烟测。
3. 在 PIME 和 Weasel 两个外部仓库分别记录各自构建、安装、崩溃排查和 UI 体验问题。
4. 等稳定性足够后，再考虑把导出物打成可复现的试用包。
