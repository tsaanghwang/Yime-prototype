# 字典拼音第一轮合规审查

本机制位于外部字典与音节分解器之间。两个来源共用一个审查核心和一份策略，只保留各自的文件格式
适配与独立报告：

```text
external_data/hanzi_pinyin.txt ─┐
                                ├─ 字符/声调/结构审查
external_data/phrase_pinyin.txt ─┘   ├─ 具体来源记录校勘
                                    ├─ 已知非规范读音隔离
                                    ├─ 方案允许的省写还原
                                    └─ 合规拼音 → staging → 音节解码
```

共用实现是 `yime/utils/dictionary_pinyin_compliance.py`，策略真源是
`internal_data/pinyin_source_db/dictionary_pinyin_compliance_policy.json`。单字和词语构建入口都调用它；
`tools/build_lexicon_source_bundle.py` 再执行一次同样的边界检查，防止维护人员绕过前置构建步骤直接把旧中间文件
送进解码链。

## 第一轮检查什么

- 单个音节只能使用登记的拼音字母、音质字母和声调符号；数字、大写、标点直接拒绝。
- 来源字典不得使用 `v` 或 `u:` 代替 `ü`。技术拼音只能留在输入兼容边界。
- 一个音节不得同时带多个声调标记；无标记形式按来源中的轻声形式处理。
- 拼式必须命中策略中已准入的声母—韵母结构；即使只含拼音字母，`abc`、`fiong` 一类未经审查的
  新拼式仍会失败并报告，不能仅凭“字典里出现了”直接进入解码。
- 单字表检查常用读音是否属于候选集合，以及 `is_single` 是否与候选数一致。
- 词语表检查冒号格式和词长—音节数是否一致。
- `ong` 必须符合现行声韵分布和零声母拼写：唇音声母 `b/p/m/f` 不与 `ong` 相拼；零声母
  `ueng` 写作 `weng`，不写作 `wong`。
- `wong` 不是通用别名。只有 U+25948、U+259B7 两条经过字典旁证的来源记录校正为 `wèng`；其他
  `wong` 必须失败并重新校勘。
- U+31FC5 `𱿅` 的 `bòng` 有来源记录，但不符合普通话声韵拼合限制。原始证据保留，状态为
  `excluded_nonstandard_orthography`，不进入音节分解，也不猜改成 `cí` 或 `bèng`。
- 《汉语拼音方案》允许韵母ㄦ用作韵尾时省写为 `r`。Unihan/BCC 按字位带来的独立 `r` 在完整音节
  编码入口还原为 `er5`，同时保留来源形式和儿化韵尾角色；附着在前一音节后的 `r` 仍须按上下文分析。

`dictionary_attested` 的含义刻意较窄：字典实例通过了第一轮来源合规检查。它不等于“已由国家规范
逐项认证”，也不等于“理论上所有声母韵母组合都存在”。新的特殊形式如果需要例外转换或解释，必须
先改策略和规则目录；不得从 Yinyuan ID、码表或键位倒推处理方式。

## 运行与产物

```powershell
.\venv312\Scripts\python.exe tools\audit_dictionary_pinyin.py
```

报告写入 `.generated/pinyin_compliance/`：

- `summary.json`：两个来源的计数和审查状态汇总；
- `hanzi_pinyin_review.tsv`：单字表错误、规范别名和特殊读音；
- `phrase_pinyin_review.tsv`：词语表错误、规范别名和特殊读音。

存在 `error` 时命令返回非零。`canonical_alias`、`source_correction` 和
`excluded_nonstandard_orthography` 是必须让维护者看见但不阻断整个构建的 `notice`。排除针对的是
具体读音，不是字形：字及其码点继续进入字符清单和单字 staging；如果该字没有其它合规读音，内部
读音字段留空，因此不会进入音节分解、编码清单或候选码表。原始 `external_data` 文件不被改写，只有
合规或有据校正后的读音进入后续音节派生数据。

## 局限与下一轮

第一轮解决的是“来源数据能否安全、可解释地进入工程链”，不是替代语言文字规范机构。后续可以在同一
策略层增加来源等级、逐条证据链接和待审音节队列，但不能重新用现有码表充当拼音合法性标准。
