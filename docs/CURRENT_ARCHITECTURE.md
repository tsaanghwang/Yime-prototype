# 当前实现总览

本文是当前分支的工程状态入口。它只描述已经落到代码、数据和锁检查中的主线；理论设想、旧试验和
外部 Windows 前端的实现细节不在这里冒充现状。

阅读 `syllable/analysis/`、片音对象、音元对象或 Yinyuan ID 前，先看
[片音分析与音元表示：工程阅读概要](PIANYIN_ANALYSIS_OVERVIEW.md)。固定四元编码位置不是等长语音
时间窗，当前分析对象也不是程序从波形中切出的平顶音段。

## 一句话状态

当前项目已经基本形成“字典驱动的音元编码生成器”：给定格式合格、带明确声调的拼音字典，工具链
可以提取规范音节，对已登记规则覆盖的音节生成四个 Yinyuan ID，再生成三模式编码、布局投影和运行时
词库。遇到没有来源或没有登记规则的新形式时，流程应失败并报告，不允许临时猜码。

## 当前端到端数据链

```text
Unihan 单字读音 / phrase-pinyin-data 词语读音 / 经审查补丁
  -> source_pinyin.db
  -> 规范数字标调音节清单（当前 1727 项）
  -> SyllableEncodingPipeline
  -> 首音段 + 干音段
  -> ShouyinEncoder + GanyinEncoder
  -> 4 个 Yinyuan ID
  -> 等长 / 变长 / 省键三模式编码
  -> manual_key_layout.json 的唯一键位投影
  -> SQLite 运行时候选、Rime/KLC/Windows 消费产物
```

1727个现行音节均有 Unihan、词语来源或经审查补丁依据，并全部能通过正式编码器。逐项来源、规则和
四个 Yinyuan ID 见 `internal_data/yime_syllable_encoding_provenance.tsv`。

## 当前真源

| 层 | 真源 | 职责 |
|---|---|---|
| 单字读音 | `internal_data/hanzi_pinyin/pinyin.txt` | Unihan 合并后的带调单字读音实例 |
| 词语读音 | `internal_data/phrase_pinyin/phrase_pinyin.txt` | 经校验的词语带调读音实例 |
| 拼音补充 | `internal_data/pinyin_source_db/pinyin_normalized_patch.json` | 明确审查的来源或标调补充；不能写音元码 |
| 拼写规则说明 | `internal_data/syllable_encoding_rule_catalog.json` | 解释来源、规范化和兼容规则；禁止保存编码映射 |
| 首音语义 | `syllable/yinyuan/zaoyin_yinyuan_enhanced.json` | N01–N24 的标签、语义码、Yinyuan ID 与运行时字符 |
| 乐音语义 | `syllable/yinyuan/yueyin_yinyuan_enhanced.json` | M01–M33 的标签、别名、Yinyuan ID 与运行时字符 |
| 音节分解 | `syllable/analysis/syllable_encoding_pipeline.py`、`syllable_splitter.py` | 标准拼音到首音段/干音段 |
| 音节编码 | `ShouyinEncoder`、`GanyinEncoder`、`YinjieEncoder` | 正式生成四音元编码 |
| 键盘布局 | `internal_data/manual_key_layout.json` | 唯一 Yinyuan-ID-to-key 投影 |
| 运行时词库 | `yime/pinyin_hanzi.db` | SQLite 候选主路径；属于可重建消费端数据 |

`key_to_symbol.json`、BMP PUA 投影等文件负责字符承载和平台投影，不得反过来定义拼音分解。数据库、
`yinjie_code.json`、resolved layout、crosswalk、KLC 和审计 TSV 都是派生或审计产物，不应手工作为
单项修复入口。

## 这版键盘布局重构

当前布局状态为 `canonical_yinyuan_vk_layout_v1`，已经写入唯一布局真源并由布局锁闭合。

### 总体分配

- 47个 Base 可分配键中：22个放常用乐音，24个放 N01–N24，反引号 `` ` `` 保留。
- 其余11个乐音放在 Shift 层。
- 所有57个 Yinyuan ID 只使用 Base 或 Shift；保留的 AltGr 槽位全部为空。
- `Shift+1` 至 `Shift+9` 是候选选择操作，不承载 Yinyuan ID。
- 已删除早期“把数字和标点机械搬到其他键位”的输入兜底；数字和标点由宿主/候选功能处理。

### Base 乐音记忆结构

```text
左手：W E R = o 低中高    右手：U I O = u 高中低
      S D F = a 低中高          J K L = i 高中低
      X C V = e 低中高          M , . = ü 高中低

A/Z = n 高/低            ; / = ng 高/低
```

### 首音和特殊首音

- 21个实首音全部在 Base；数字排保留 `x/q/j/s/c/z/zh/ch/sh/r` 的组块。
- `N12` 零首音使用 `'`。
- `N23` 使用 `Y`，`N24` 使用 `=`。
- `N04 m`、`N05 d`、`N07 l` 分别使用 `-`、`]`、`\`。
- `N06 t` 使用 `T`；`N01 b`、`N08 n`、`N09 g`、`N11 h` 使用同字母键，`N10 k` 使用 `Q`。

设计理由见 `internal_data/musical_layout_skeleton.md` 与
`internal_data/shouyin_layout_skeleton.md`；实现事实必须以 `manual_key_layout.json` 为准。

## 三张音节审计表

运行 `tools/export_syllable_decomposition.py` 会同时生成：

1. `yime_syllable_decomposition.tsv`：1727项正式分解、Yinyuan ID 和布局码。
2. `yime_syllable_encoding_provenance.tsv`：每项编码的来源和规则依据。
3. `yime_syllable_omissions.tsv`：旧理论全集与现行实例驱动链的50项差集。

50项差集目前分为：22项方案形式/音节拼写/编码形式差异，20项历史 `v` 技术拼音，3项 `io`
形式族中未实例化的声调，以及5项早期五声穷举遗留（`er1、m3、n1、ng1、ê5`）。它们不是50个
被编码器漏掉的现行音节。

## 修改入口

### 修改拼音来源或音节规则

1. 从单字/词语来源或经审查补丁开始。
2. 修改正式规范化、切分或编码真源。
3. 重建编码和三张审计表。
4. 单独审查语义变化并执行布局锁；不得从 `yinjie_code.json` 中间补入。

### 修改键盘布局

1. 只改 `internal_data/manual_key_layout.json`。
2. 运行 `python tools/run_locked_layout_pipeline.py`。
3. 检查 resolved layout、crosswalk、KLC 和运行时一致性。
4. 不得在布局修改中改变拼音到 Yinyuan ID 的语义链。

### 常用验证

```powershell
.\venv312\Scripts\python.exe tools\export_syllable_decomposition.py
.\venv312\Scripts\python.exe tools\check_layout_change_lock.py
```

## 当前边界

- 这套链能自动处理已登记规则覆盖的字典音节，不承诺对任意新拼音形式自动发明分解规则。
- 词频、默认读音、多音排序和候选质量仍依赖输入字典与频率数据。
- Python 原型是语义、生成和审计主仓库；Windows 输入法、Rime 或 KLC 是消费者，必须从这里的正式
  语义和布局产物同步，不能在消费者仓库另建一套拼音到键位映射。
