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

- BCC 的 `freq` 是语料计数，保持原值；没有命中时为 `0`，不改写成 `1`。
- 万象的权重经过其自身语料和排序流程处理，只保存在 `wanxiang_weight`，不得冒充 BCC count。
- 同一字词允许保留多个读音。Unihan 是单字首选来源，pypinyin 是词语首选来源，万象用于补充、交叉
  验证及冲突发现。
- 拼音必须通过 `dictionary_pinyin_compliance_policy.json`，音节数必须与全汉字词条的字数相同，且
  每个规范数字拼音都必须存在于当前 `pinyin_normalized.json`，才可进入 `entries.tsv`。
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
| `entries.tsv` | 一行一个“字词—合规读音”，带 BCC count、万象权重和来源 |
| `source_lexicon.sqlite3` | 支撑百万级来源合并和后续查询的工作库 |
| `rejected_readings.tsv` | 结构、拼音或当前解码清单门禁拒绝的来源记录 |
| `unresolved_bcc.tsv` | 有 BCC 频次、尚无合规读音来源的字词 |
| `reading_conflicts.tsv` | 同一字词有多个合规读音的审查表 |
| `manifest.json` | 输入文件摘要、口径、数量和输出文件清单 |

`.generated/` 不纳入 Git。以后生成 Windows 码表时应读取完整语料包及 `manifest.json`，不得手工复制
其中一列或绕开本仓库的“标准拼音 → 音元分解 → Yinyuan ID”正式链。

## 来源与再发布

生成器只读取使用者本地准备的上游数据，不把上游大文件提交进本仓库。公开或再分发生成结果前，
必须分别核对 Unihan、phrase-pinyin-data、BCC 和 RIME-LMDG 的许可、署名与引用要求；BCC 的研究引用
见 `external_data/word_freq_README.md`，万象仓库当前许可证见其本地 `LICENSE`。
