# 字词拼音与频次统一语料包

本工具把 Unihan 单字读音、pypinyin 词语读音、万象字词读音与 BCC 字词频次汇集成一份可追溯、
可重复生成的音元解码输入。它是来源与编码器之间的交付边界，不是第二套拼音分解规则或音元码表。

## 数据关系

```text
Unihan 单字拼音 ───────┐
pypinyin 词语拼音 ─────┼─ 第一轮拼音合规审查 ─ 当前可解码音节门禁 ─┐
万象字词拼音 ──────────┘                                           ├─ entries.tsv
BCC 字频与词频 ─────────── 保留原始整数 count ─────────────────────┘
```

- BCC 的 `freq` 是语料计数，保持原值；没有命中时为 `0`，不改写成 `1`。现代汉语、新闻、对话、
  文学、古代汉语和综合语料的分域计数分别保存，`bcc_frequency` 只是各域最大值的兼容汇总。
- BCC 只读取各分域原始下载：词频频道只贡献多字词，字频频道只贡献单字。
  `merged_word_freq.txt`、`merged_char_freq.txt` 和 `word_freq_merged_single_char_freq.txt` 都是本仓库
  生成的二手数据，禁止作为统一语料包的来源证据；配置误用时构建会直接失败。
- 万象的权重经过其自身语料和排序流程处理，只保存在 `wanxiang_weight`，不得冒充 BCC count。
- 万象来源同时保留 `jichu`、`lianxiang`、`diming`、`shici`、`yixue` 等原始文件分类，供以后构建
  基础、联想、地名、诗词和专业分类词库。
- 同一字词允许保留多个读音。Unihan 是单字首选来源，pypinyin 是词语首选来源，万象用于补充、交叉
  验证及冲突发现。
- 拼音必须通过 `dictionary_pinyin_compliance_policy.json`，音节数必须与全汉字词条的字数相同。规范
  数字拼音须存在于当前 `pinyin_normalized.json`；唯一例外是已有真实来源且在
  `syllable_admission_reviews.json` 明确批准的循环门禁项目，重建后仍须由正式编码器生成。
- 轻声音节不要求按 `-5` 逐项枚举审查：标调制度完整的来源在多字完整词音中给出的无调音节，按
  GB/T 16159-2012 的轻声标写规则准入，不要求虚构本调；不得反过来把所有词末字自动改读轻声。
- `pronunciation_scope` 区分独立候选与词境证据；`neutral_tone_positions` 保存完整词音中的轻声位置，
  `neutral_tone_status` 区分确认轻声与未定无调。词境证据不得反向生成单字轻声候选。
- 各来源的无调解释制度由 `neutral_tone_source_policy.json` 单独登记；未知来源默认是
  `unmarked_ambiguous`，不能因为拼式合法就直接认定为轻声。
- 来源标调原写法保存在 SQLite 的 `accepted_readings.source_marked`；生产读音按现行解码清单统一
  标调位置。例如来源 `aì` 可保留为证据，但 `ai4` 的生产形式只能是规范 `ài`，不形成平行读音。
- BCC 有频次但没有合规读音来源的词条进入 `unresolved_bcc.tsv`；不得用逐字常用音猜测多音词读音。
- 万象的 `cuoyin.dict.yaml` 是有意维护的错音错字资料，`mixed.dict.yaml` 含非纯汉字输入，两者默认
  不作为音元解码读音来源。

## 构建

先同步本地 `C:\dev\RIME-LMDG`，再运行：

```powershell
.\venv312\Scripts\python.exe tools\build_lexicon_source_bundle.py
```

默认产物位于 `.generated/lexicon_source_bundle/`：

| 文件 | 用途 |
|---|---|
| `entries.tsv` | 一行一个“字词—合规读音”，带 BCC 分域 count、万象权重、分类和来源 |
| `source_lexicon.sqlite3` | 字词、读音、来源证据、分类频次与编码输入的唯一生产真源 |
| `rejected_readings.tsv` | 结构、拼音或当前解码清单门禁拒绝的来源记录 |
| `unresolved_bcc.tsv` | 有 BCC 频次、尚无合规读音来源的字词 |
| `reading_conflicts.tsv` | 同一字词有多个合规读音的审查表 |
| `manifest.json` | 输入文件摘要、口径、数量和输出文件清单 |

需要提交小型审查快照而不是整个本地语料包时，运行：

```powershell
.\venv312\Scripts\python.exe tools\export_lexicon_review_summary.py
```

该命令生成 `internal_data/lexicon_source_review_summary.md`：按 BCC 汇总频次列出前100项未解码
字词和前100项多读音冲突，并单列所有“存在读音记录但全部被门禁拒绝”的 BCC 字词。摘要只复述
SQLite 中的来源和拒绝原因，不补写读音或编码；可用 `--limit` 调整两个高频表的行数。

`.generated/` 不纳入 Git。以后生成 Windows 码表时应读取完整语料包及 `manifest.json`，不得手工复制
其中一列或绕开本仓库的“标准拼音 → 音元分解 → Yinyuan ID”正式链。

当前规模、BCC 未解码分层、多读音现状以及从静态大词库转向动态组合的整理阶段，统一记录在
[候选语料库整理路线图](CANDIDATE_CORPUS_ROADMAP.md)。

SQLite 中的 `bcc_frequency_evidence` 保留每个 BCC 分域原始文件及 `word/char` 来源类型，
`v_bcc_frequency_by_category` 提供分域查询，`v_reading_source_conflicts` 提供多来源读音冲突查询。
排序策略只能读取这些派生字段，不得反向覆盖原始频次或来源分类。

## 来源与再发布

生成器只读取使用者本地准备的上游数据，不把上游大文件提交进本仓库。公开或再分发生成结果前，
必须分别核对 Unihan、phrase-pinyin-data、BCC 和 RIME-LMDG 的许可、署名与引用要求；BCC 的研究引用
见 `external_data/word_freq_README.md`，万象仓库当前许可证见其本地 `LICENSE`。
