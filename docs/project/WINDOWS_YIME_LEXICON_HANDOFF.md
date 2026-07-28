# 默认核心词库交接到 Windows Yime

原型负责完整来源、拼音审查、正式音节编码、候选筛选和评测；Windows Yime 负责安装运行、动态组句
和用户学习。完整大词库是离线真源，不是 Windows 默认运行词库。

## 当前交接物

| 交接物 | 职责 |
| --- | --- |
| `internal_data/runtime_lexicon_filter_policy.json` | 前五级单字、一级组件、二级预组合及门禁策略 |
| `yime_core_trial.dict.yaml` | 1,124,631 条已编码运行记录 |
| `yime_core_trial_manifest.json` | 来源、布局、转换版本、条目数和输出 SHA-256 |
| `yime_runtime_profile.json` | Windows 默认 schema、离线文件边界和验收摘要 |
| 拼音显示与音节分解资产 | 反查、显示和正式编码审计 |

历史 `yime_full.dict.yaml` 及其变长、省键派生产物继续可重建，用于离线筛选、差异诊断和回归；不得
作为安装回退。

## 构建与校验

```powershell
.\venv312\Scripts\python.exe tools\build_two_level_runtime_trial.py

.\venv312\Scripts\python.exe tools\verify_default_runtime_handoff.py `
  --windows-repo C:\dev\Yime `
  --output .generated\default_runtime_handoff.json
```

验证器必须确认：

1. 原型策略与 Windows 默认 schema 均为 `yime_core_trial`；
2. Windows 核心词典 SHA-256 与 manifest 一致；
3. 固定回放的95% Wilson 下界不低于99%；
4. 旧三套大词库均声明为 offline-only。

Windows `build.bat` 复制共享数据后删除旧 dict、schema 和 manifest；发现任何残留即失败。安装后用
`tools/verify-installed-runtime.ps1` 检查源码/安装哈希、核心 profile 和 `runtime-leak`。

## 发布语义

- “完整长词未预装”不表示“未编码”：只要组件已有正式编码，就由动态组句恢复；
- 来源库允许保留未决、古旧和动态残差材料，运行库只接受通过来源与 R0–R5 覆盖门禁的组件；
- 用户实际选择进入个人学习库，不自动反写公共系统库；
- 高频晋升扫描只产生待审建议，不能绕过拼音和编码门禁；
- 字符或实际读音本身缺少可信来源时仍须失败并报告，不允许 AI 猜码。

当前证据包括2,449条固定回放、540,000次加速学习漂移，以及
`experiments/default_runtime_clean_cold_start_20260727.json` 的纯净用户态人工闭环。人工小样本验证
机制，不替代总体统计。
