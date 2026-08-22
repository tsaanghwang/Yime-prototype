# Windows frontends status（历史快照）

> **不再是当前集成状态。** 本页只用于核对脱离维护前的 Windows Yime、Weasel 和 PIME 证据。
> 本仓库不再生成交接包、部署前端或校验产品仓库；现行工作转到 `C:\dev\Yime`。见
> [脱离产品维护边界](../DETACHED_MAINTENANCE_BOUNDARY.md)。

本文记录 Yime 面向 Windows 系统级输入法前端的当前状态。它只说明消费者边界和已经验证的集成路径，
不把某个历史分支名、测试条数或本机绝对路径当作长期接口。

## 定位

Python 原型仓库负责拼音来源、音节语义、三模式编码、布局投影和词库交接资产，不承载 Weasel、
librime 或 PIME 的源码。Windows Yime 仓库负责正式导入和部署；Weasel/PIME 是消费前端。

当前边界如下：

- 原型保留完整等长词典作为离线真源，并向 Windows Yime 交接筛选策略、核心运行词典、manifest 和
  runtime profile。
- Windows Yime 正式安装只携带 `yime_core_trial`；旧等长、变长、省键大词库不作为运行回退。
- Rime 在核心已编码单字和预组合部件上动态组句，并把人工纠正写入独立 userdb。
- Weasel 与旧三模式导出曾作为离线兼容和回归路径；PIME 是当时的 Windows TSF 消费外壳。

历史交接入口和验收条件见
[新版词库交接到 Windows Yime](../project/WINDOWS_YIME_LEXICON_HANDOFF.md)。

## 当前实现状态

- 原型核心构建入口：`tools/build_two_level_runtime_trial.py`
- 跨仓库校验入口：`tools/verify_default_runtime_handoff.py`
- Windows 安装态校验入口：`tools/verify-installed-runtime.ps1`
- 正式默认 schema：`yime_core_trial`
- 离线兼容导出：`full`、`variable`、`shorthand`

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

1. Windows Yime 安装包部署核心 schema/dict 和固定 librime 运行时。
2. PIME Go backend 通过 librime 运行 `yime_core_trial`。
3. PIME TSF 外壳处理组合、候选、翻页、提交和语言栏工具。
4. 纯净用户态人工闭环已验证长句可构造、纠正后首选并能跨重启保持。

PIME 侧源码和构建产物不纳入原型或 Windows Yime 数据仓库。

当前仍处产前开发测试，重点风险包括：

- TSF DLL 运行在宿主进程内，异常会影响 Notepad、IDE 等宿主。
- Go backend 返回给 C++ TSF 的 JSON 字段类型必须严格匹配。
- 真实输入体验还需要继续覆盖候选、翻页、提交、退格、中英文切换和长时间稳定性。

## 当前验收基线

- 原型交接包的拼音映射、音节分解和显示资产必须具有相同的规范音节键集；
- `yime_handoff_manifest.json` 必须记录条目数、来源和 SHA-256；
- 核心词典 SHA-256、条目数和 runtime profile 必须与原型交接物一致；
- 固定回放的95% Wilson 下界不得低于99%；
- 安装包不得出现旧三套大词库、schema 或 manifest；
- 全新用户目录必须验证冷启动、一次纠正、第二次首选和重启保持；
- 三模式离线派生仍应在隔离目录中保留回归；
- 隔离烟测不得覆盖真实 `%AppData%\Rime`；
- 只有显式部署步骤可以写用户目录。

条目数会随统一来源库和候选发布政策变化，不在本文固定为长期常量。每次交接以生成的 manifest
和当次烟测报告为准。

## 下一步

优先级建议：

1. 继续累积纯净用户态长期漂移数据，并控制用户库增长。
2. 审核高频晋升扫描结果，只提升跨周期、可解释且已编码的真实缺词。
3. 扩充专业、专名、古籍和罕见字硬失败样本。
4. 每次改来源、运行策略、编码或布局后，重跑核心交接和安装泄漏门禁。
5. 获得外部试用者数据后，再校准产前99%估计。

**最后更新：2026-07-27**
