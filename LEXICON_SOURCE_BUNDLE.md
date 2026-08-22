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
- 词语拼音来源与排序证据是两件事：万象词库直接提供进入统一来源库和运行候选选择的字词、带调拼音
  与原始权重；BCC 提供独立语料频次。运行候选在有 BCC 直接证据时使用 BCC，在缺少 BCC 时使用
  RIME-LMDG 权重的分桶百分位，最后才使用结构保底；原值永不相加，详见
  [候选排序证据与长尾结构](CANDIDATE_RANKING_EVIDENCE.md)。
- 万象来源同时保留 `jichu`、`lianxiang`、`diming`、`shici`、`yixue` 等原始文件分类。统一来源库
  已实际导入这些分类；当前运行词库选择也明确纳入其中若干类别，分类字段继续用于基础、联想、地名、
  诗词和专业词库的审查与分层。
- 同一字词允许保留多个读音。Unihan 是主要的单字读音生产来源；pypinyin 与万象都是词语读音生产
  来源。pypinyin 在两者重合或冲突时暂时具有来源顺序优先权，但这不是对质量或规范地位的最终裁决；
  万象承担大规模词语覆盖、带调拼音、来源分类和缺少 BCC 时的排序证据，同时也与 pypinyin 互相提供
  重合验证及冲突发现。不得把万象描述成只读参考资料。
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
- 包含暂无可信普通话读音来源码点的任意字串进入 `unencoded_pending_strings.tsv`，暂不进入正式
  编码链，但保留为可逆的专家或未来来源复核项目，不判为无效或永久拒绝。
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
| `unencoded_pending_strings.tsv` | 包含暂无可信普通话读音来源码点的全量来源字串、命中码点、BCC 频次、规则和暂缓理由 |
| `unresolved_bcc.tsv` | 有 BCC 频次、尚无合规读音来源的字词 |
| `reading_conflicts.tsv` | 同一字词有多个合规读音的审查表 |
| `character_tiers.tsv` | 九级互斥汉字分级、来源、BCC频次及门禁/编码状态审计表 |
| `manifest.json` | 输入文件摘要、口径、数量和输出文件清单 |

重建后可单独运行万象词语拼音顺序审计：

```powershell
.\venv312\Scripts\python.exe tools\audit_wanxiang_pinyin_order.py
```

该工具以只读方式逐条比较 `accepted_readings.source_marked` 和按原位置规范化后应得的数字拼音，既
覆盖内部轻声音节，也统计音节数异常和纯粹的音节排列变化；审计报告写入
`.generated/wanxiang_pinyin_order_audit/summary.json`。

需要提交小型审查快照而不是整个本地语料包时，运行：

```powershell
.\venv312\Scripts\python.exe tools\export_lexicon_review_summary.py
```

该命令生成 `internal_data/lexicon_source_review_summary.md`：按 BCC 汇总频次列出前100项未解码
字词和前100项多读音冲突，并单列所有“存在读音记录但全部被门禁拒绝”的 BCC 字词。摘要只复述
SQLite 中的来源和拒绝原因，不补写读音或编码；可用 `--limit` 调整两个高频表的行数。

`.generated/` 不纳入 Git。以后生成 Windows 码表时应读取完整语料包及 `manifest.json`，不得手工复制
其中一列或绕开本仓库的“标准拼音 → 音元分解 → Yinyuan ID”正式链。

统一库同时保存：

- `unihan_character_inventory`：项目 Unihan 字符全集及不可分级结构符号标记；
- `unihan_mandarin_evidence`：`kTGH`、`kXHC1983`、`kHanyuPinyin`、`kMandarin` 证据；
- `character_tiers`：按首次命中形成的九级互斥成员表；
- `v_character_tier_summary`：逐级数量和BCC范围摘要。

`yime/refresh_runtime_yime_codes.py` 只复制这张分级表中已有正式音元编码的字符，
不再从旧Unihan数据库、外部XHC文本或运行库频率临时重算成员。

当前规模、BCC 未解码分层、多读音现状以及从静态大词库转向动态组合的整理阶段，统一记录在
[候选语料库整理路线图](CANDIDATE_CORPUS_ROADMAP.md)。

要在不改动来源库的前提下估算适当的静态词库容量，可运行：

```powershell
.\venv312\Scripts\python.exe tools\plan_static_lexicon_capacity.py
```

该工具读取 `canonical_readings`，按完整数字调拼音验证更短组件的递归可达性，并输出静态硬底座、
可调容量前沿和动态迁移候选。它不会把字面可切分当成词汇判决，也不会直接改写运行词库；实际迁移
还必须通过真实输入回放、候选排序、歧义和延迟验证。

要使用现有合格短串为未编码长串建立递归输入证据，可运行：

```powershell
.\venv312\Scripts\python.exe tools\build_recursive_composition_model.py
```

该模型优先复用已有多字编码组件；连续未覆盖区默认作为二字动态块，必要时扩大到三字或四字以避免
顶层单字兜底。单字读音只在块内验证，缺失时形成显式例外，不会被提前选成顶层组件。

该模型只读取 `canonical_readings` 作为已编码组件事实，把结果写入候选模型的独立证据表；较短组件
无需先作人工词汇分类。组件读音的串接结果不写回本来源包，也不构成目标长串的新词音来源。

SQLite 中的 `bcc_frequency_evidence` 保留每个 BCC 分域原始文件及 `word/char` 来源类型，
`v_bcc_frequency_by_category` 提供分域查询，`v_reading_source_conflicts` 提供多来源读音冲突查询。
排序策略只能读取这些派生字段，不得反向覆盖原始频次或来源分类。

## 来源与再发布

生成器只读取使用者本地准备的上游数据，不把上游大文件提交进本仓库。公开或再分发生成结果前，
必须分别核对 Unihan、phrase-pinyin-data、BCC 和 RIME-LMDG 的许可、署名与引用要求；BCC 的研究引用
见 `external_data/word_freq_README.md`，万象仓库当前许可证见其本地 `LICENSE`。

### RIME-LMDG（万象）归属

本项目实际使用 [RIME-LMDG（万象语法模型与词库）](https://github.com/amzxyz/RIME-LMDG) 提供的
字词、带声调拼音、词库分类和权重数据；这些数据经过 Yime 的来源合规、音节编码、候选筛选和分层
排序流程形成派生产物。万象不是只供人工查阅的参考来源，而是当前统一来源库和运行候选的重要生产
来源。

本机同步的 RIME-LMDG 上游仓库以 CC BY 4.0 发布。公开或再分发含其派生数据的词库或安装产物时，
应按该许可证保留适当署名、许可证链接并说明所作修改；Yime 自身的筛选、转码和重新排序不得抹去
万象的来源身份。具体义务以发布时采用的上游版本及其 `LICENSE` 为准。
