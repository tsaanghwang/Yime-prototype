# 两级默认运行词典筛选链路

## 目标

完整来源、读音证据和原型 inventory 继续保留；输入法只把经过筛选的候选物化到
`runtime_candidates_materialized`。因此这不是删除来源数据，也不是宣布被筛出的长串
“没有读音”，而是把它们从公共冷启动候选移到动态组合和用户学习路径。

正式策略位于：

```text
internal_data/runtime_lexicon_filter_policy.json
```

当前策略：

- 单字边界：前五级、14,000 个已编码汉字；
- 一级组件：经过来源门禁和生产运行库交集检查的 1–4 字候选；
- 二级预组合：既有长桥接项，加生产运行库中最高权重的 5,000 条长候选；
- 所有保留项必须已经存在于当前生产运行库，筛选器不推测拼音、不生成新读音；
- 完整 `source_lexicon.sqlite3`、`phrase_inventory` 和 `runtime_candidates`
  均不删除。

## 单一构建入口

```powershell
.\venv312\Scripts\python.exe tools\build_two_level_runtime_trial.py
```

第一次运行会：

1. 从统一来源库和静态容量模型重建 B-lite 选择；
2. 生成前五级 1–4 字一级组件；
3. 导出当前完整生产运行词典；
4. 对一级组件和长桥接项执行生产运行库交集门禁；
5. 加入限定容量的二级长候选；
6. 输出带选择层级和原因的 `selection.tsv`；
7. 使用 SQLite backup API 克隆完整原型运行库；
8. 写入 `runtime_lexicon_selection` 并只重建物化候选表。

已有筛选运行库需要重新应用同一策略时使用：

```powershell
.\venv312\Scripts\python.exe tools\build_two_level_runtime_trial.py `
  --reuse-runtime-database
```

命令不会自动覆盖既有筛选运行库。未通过生产交集检查的选择项会使构建失败，不能用
“忽略错误”代替正式门禁。

## 原型与 Windows 的运行边界

Python 桌面原型默认仍加载 `yime/pinyin_hanzi.db`；需要复现筛选数据库时显式设置：

```powershell
$env:YIME_RUNTIME_DB_PATH = `
  "C:\dev\Yime-python-prototype\.generated\two_level_runtime_trial\runtime\pinyin_hanzi.db"
```

候选解码和反查共用该路径。未设置环境变量时行为保持不变。

Windows Yime 不依赖这个环境变量；它默认打包 `yime_core_trial.dict.yaml`，并由
`yime_runtime_profile.json` 固定运行边界。跨仓库一致性由
`tools/verify_default_runtime_handoff.py` 校验。

如果需要在筛选数据库中关闭覆盖层并重新物化全量候选：

```powershell
.\venv312\Scripts\python.exe tools\apply_runtime_lexicon_selection.py `
  --output-db .generated\two_level_runtime_trial\runtime\pinyin_hanzi.db `
  --disable
```

## 当前规模与回放

生产交集后的筛选结果：

- 1,116,892 个不同字串；
- 1,124,631 条选择 TSV 读音；
- 运行库匹配 1,124,631/1,124,631，未匹配为 0；
- 物化候选 1,124,632 行；多出的一行来自一个同字同码的已登记拼音映射；
- 完整来源和约 239.6 万条 phrase inventory 仍保留。

真实 librime 扩大回放的预定正常文本口径：

- 2,440/2,449 冷启动保持生产首选；
- 首选率 99.6325%；
- 95% Wilson 下界 99.3030%；
- 已超过 99% 目标。

未进入二级缓存的长句仍可由一级组件分段输入。完整提交后，原型的整句自动学习把
经过用户实际确认的选择序列写入用户词库，重启后继续生效。

## 已落地的 Windows 结论

- 默认运行方案已经由历史大词库切换为 `yime_core_trial`；
- 旧大词库不进入安装包，也不作为默认或反查回退；
- “完整长词未预装”不再等同于“词条未编码”，动态组合只消费已经编码的组件；
- 来源全集允许保留噪声和未决材料，运行层必须通过门禁；
- 开发期真实缺词由高频晋升扫描汇总，审核通过后才进入公共系统库。

纯净用户态人工闭环记录位于
`experiments/default_runtime_clean_cold_start_20260727.json`。该小样本验证机制，不替代扩大回放的
总体99%统计。
