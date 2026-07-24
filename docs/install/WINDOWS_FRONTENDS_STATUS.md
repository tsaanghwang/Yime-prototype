# Windows frontends status

本文记录 Yime 面向 Windows 系统级输入法前端的当前状态。它只说明消费者边界和已经验证的集成路径，
不把某个历史分支名、测试条数或本机绝对路径当作长期接口。

## 定位

Python 原型仓库负责拼音来源、音节语义、三模式编码、布局投影和词库交接资产，不承载 Weasel、
librime 或 PIME 的源码。Windows Yime 仓库负责正式导入和部署；Weasel/PIME 是消费前端。

当前边界如下：

- 原型只向 Windows Yime 交接等长 `yime_full.dict.yaml` 这一份系统词典输入。
- Windows Yime 的正式导入器从等长输入确定性派生等长、变长、省键三模式词典。
- Rime 导出器负责把选定模式导出为 Rime schema/dict。
- Weasel/Rime 消费导出的 schema/dict，并由 librime 编译为用户数据。
- PIME 目前作为另一条 TSF 外壳验证路径，消费同一批 Rime schema/dict 数据。

原型交接入口和验收条件见
[新版词库交接到 Windows Yime](../project/WINDOWS_YIME_LEXICON_HANDOFF.md)。

## 当前实现状态

- 原型准备入口：`tools/prepare_windows_yime_lexicon.ps1`
- Windows Yime Rime 导出入口：`yime/export_rime_yime.py`
- Windows Yime Weasel 部署入口：`tools/export_and_deploy_weasel_yime.ps1`
- 支持导出模式：`full`、`variable`、`shorthand`
- 默认导出模式：`variable`

具体路径属于外部 Windows Yime 仓库，不应在原型仓库中复制一套实现或硬编码本机位置。

## Weasel / Rime 路线

当前已跑通的路径：

1. Yime 从运行时数据库导出 `yime_*.schema.yaml` 和 `yime_*.dict.yaml`。
2. 部署脚本把导出物复制到 Rime user data 目录。
3. 脚本调用 `rime_deployer.exe --build` 编译 Rime 用户数据。
4. Weasel 作为系统级输入法前端消费编译后的 Rime 数据。

下列命令应在 Windows Yime 仓库中运行，路径以实际检出位置为准：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File tools\export_and_deploy_weasel_yime.ps1 `
  -Mode variable
```

本地隔离烟测可指定临时目录，避免覆盖真实 `%AppData%\Rime`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File tools\export_and_deploy_weasel_yime.ps1 `
  -Mode variable `
  -OutputDir .generated\rime-smoke\variable `
  -RimeUserDir .generated\rime-user-smoke\variable `
  -NoBackup
```

## PIME 路线

当前已跑通的路径：

1. Yime 导出 Rime schema/dict。
2. PIME Go backend 中的 Rime 输入法目录消费这些导出物。
3. PIME TSF 外壳通过 Go backend 调用 Rime 数据。
4. 本地实测已经达到“能输字”的状态。

PIME 侧源码和构建产物不纳入原型或 Windows Yime 数据仓库。

当前 PIME 路线仍是集成原型状态，重点风险包括：

- TSF DLL 运行在宿主进程内，异常会影响 Notepad、IDE 等宿主。
- Go backend 返回给 C++ TSF 的 JSON 字段类型必须严格匹配。
- 真实输入体验还需要继续覆盖候选、翻页、提交、退格、中英文切换和长时间稳定性。

## 当前验收基线

- 原型交接包的拼音映射、音节分解和显示资产必须具有相同的规范音节键集；
- `yime_handoff_manifest.json` 必须记录条目数、来源和 SHA-256；
- Windows Yime 导入器必须从唯一等长输入成功派生三模式词典；
- 三种模式都应在隔离 Rime 用户目录中完成导出和编译烟测；
- 隔离烟测不得覆盖真实 `%AppData%\Rime`；
- 只有显式部署步骤可以写用户目录。

条目数会随统一来源库和候选发布政策变化，不在本文固定为长期常量。每次交接以生成的 manifest
和当次烟测报告为准。

## 下一步

优先级建议：

1. 固定原型到 Windows Yime 的唯一等长输入和 manifest 协议。
2. 每次改来源、运行时数据、编码模式或布局后，跑三模式 Rime 隔离烟测。
3. 在 PIME 和 Weasel 的消费者侧分别记录构建、安装、崩溃排查和 UI 体验问题。
4. 补齐候选、翻页、提交、退格、中英文切换和长时间运行回归。
5. 稳定性足够后，再把版本化交接资产制作成可复现试用包。

**最后更新：2026-07-24**
