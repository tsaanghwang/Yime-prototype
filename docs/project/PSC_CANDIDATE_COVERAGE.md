# 审音表读音覆盖补全

## 目的和边界

本流程只处理一件事：审音表已有明确证据、而原型候选库尚不能按该读音输入的单字或词语，经过门禁与复核后增加为候选输入路径。

它不执行以下操作：

- 不据此判定或改写现有主要读音、高频读音和候选频率；
- 不删除、覆盖或重新排序原有读音；
- 不把 2016 年征求意见稿自动当作正式规范；
- 不把未经复核的 OCR 或转录结果直接写入规范读音真源；
- 不修改外部 PSC 对照数据库。

补充读音在规范源库中保留 psc_orthoepy_1985 或
psc_orthoepy_2016_draft 来源。对已有词形，它们保持非主读；对运行时候选而言，
同一词形可以对应多条拼音和多套编码，但频率、学习与提交仍回指同一词条。

## 生成覆盖审计

在原型根目录运行：

    .\venv312\Scripts\python.exe tools\audit_orthoepy_coverage.py

默认只读：

- C:\dev\PSC-Outline\psc_outline_ocr.sqlite3；
- .generated\lexicon_source_bundle\source_lexicon.sqlite3。

审计产物写入 .generated\orthoepy_coverage。输入数据库的哈希也会写入审计库，
复核决定与候选指纹绑定；来源记录变化后，旧决定会变成待重新复核，而不会静默套用。

## 可视复核

双击或运行：

    .\Review-Orthoepy-Coverage.cmd

界面可按正式表、征求意见稿、直接单字、例词、缺词、缺读音和门禁状态筛选。
可执行“批准”“校正后批准”“暂缓”“拒绝”和“清除决定”，并显示来源条目、页码、
原型现有读音、建议读音、门禁结果和解释。

正式表中满足严格自动条件的例词可以直接导出；无调单字、多个占位符、来源歧义、
2016 年征求意见稿以及门禁失败项一律留给界面复核。

## 导出已批准目录

    .\venv312\Scripts\python.exe tools\audit_orthoepy_coverage.py --apply

输出：

    internal_data/pinyin_source_db/orthoepy_coverage_readings.json

该文件只保存已批准的结构化读音记录和来源，不包含外部 PDF 或外部数据库内容。

## 全量 PSC 复核差集

来源转录校核完成后，可将“机器精确核合、人工确认、人工校正”三种状态与当前
运行时候选逐对比较：

    .\venv312\Scripts\python.exe tools\export_psc_candidate_coverage.py

输出：

    internal_data/pinyin_source_db/psc_candidate_readings.json

目录中的 `records` 是当前候选没有的字词—读音对，保持非主读、仅补覆盖；
`pending_records` 保存无法在现行“一字一音节”门禁下安全接入的全部记录，不静默
丢弃。儿化来源保留原拼音证据，只有词形明确写出“儿”时才派生分写 `er` 输入槽；
不得根据拼音中的 `r` 自动给候选增删“儿”。外部 PSC 数据库、PDF 和转录决定库
均不复制入仓库。

## 接入候选

依次运行：

    .\venv312\Scripts\python.exe internal_data\pinyin_source_db\rebuild_pinyin_assets.py
    .\venv312\Scripts\python.exe -m yime.import_duozi_into_prototype_tables
    .\venv312\Scripts\python.exe -m yime.refresh_runtime_yime_codes --apply --skip-runtime-export

源库中的 phrase_readings 兼容视图仍只包含主读；新增的
phrase_candidate_readings 只在主读之外额外纳入已批准的
psc_orthoepy_* 读音和 `psc_candidate_coverage` 差集读音。这样不会顺带把所有
普通次读放进运行时候选。

运行库按“词条类型 + 词条 ID + 拼音”唯一保存物化候选。每条读音分别生成完整、
变长和省键编码；同词多读不会复制词形主体，也不会改变原有主读标记。

## 验证

    .\venv312\Scripts\python.exe -m pytest -q tests\lexicon_bundle\test_orthoepy_coverage.py tests\lexicon_bundle\test_psc_candidate_coverage.py tests\lexicon_bundle\test_builder.py tests\yime\test_runtime_candidates_export.py

验收条件：

1. 外部 PSC 数据库和原型源数据库在审计前后哈希不变；
2. 已批准记录进入 canonical_readings，但已有词形的 is_primary 不改变；
3. 只有 psc_orthoepy_* 与 psc_candidate_coverage 补充读音进入候选扩展视图；
4. 同一词形的多条读音映射都能物化，且三种模式编码均非空；
5. 运行时候选编码一致性检查的“不匹配”为 0。
