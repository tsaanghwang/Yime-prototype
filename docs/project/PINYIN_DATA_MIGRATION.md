# 拼音数据迁移说明

本文档说明当前主线的数据重建入口、运行时查词消费面，以及
2026-06 已删除的旧脚本。当前总览见
[当前架构与数据真源](../CURRENT_ARCHITECTURE.md)，音节规则依据见
[音节编码规则与来源](../SYLLABLE_ENCODING_RULES.md)。

## 1. 当前主线 rebuild 链

当前推荐的数据主线是：

1. 外部上游文本导入到 `source_pinyin.db`
2. 从 `source_pinyin.db` 重建 prototype tables
3. 用 canonical 码面刷新 runtime 资产

默认把大型生成产物放在当前仓库的 `.generated/` 目录，而不是继续改动
已跟踪的大文件：

- `.generated/source_pinyin.db`
- `.generated/runtime_candidates_by_code_true.json`

兼容策略：

- 运行时读取优先级：`YIME_RUNTIME_CANDIDATES_JSON` ->
  `.generated/runtime_candidates_by_code_true.json` -> 旧仓库路径
- source DB 读取优先级：`YIME_SOURCE_PINYIN_DB` -> `.generated/source_pinyin.db` -> 旧仓库路径

对应入口：

- [build_source_pinyin_db.py](../../internal_data/pinyin_source_db/build_source_pinyin_db.py)
- [validate_source_pinyin_db.py](../../internal_data/pinyin_source_db/validate_source_pinyin_db.py)
- [import_danzi_into_prototype_tables.py](../../yime/import_danzi_into_prototype_tables.py)
  （兼容入口；真实实现位于 `yime/utils/prototype_single_char_import.py`）
- [import_duozi_into_prototype_tables.py](../../yime/import_duozi_into_prototype_tables.py)
  （兼容入口；真实实现位于 `yime/utils/prototype_phrase_import.py`）
- [refresh_runtime_yime_codes.py](../../yime/refresh_runtime_yime_codes.py)
  （兼容入口；真实实现位于 `yime/utils/runtime_codes_refresh.py`）

这条链的关键点是：

- runtime 主线已经改为 `pinyin_tone -> yime_code`，不再依赖旧 `音元拼音.全拼 UNIQUE`。
- 单字和词语 prototype 导入不再从旧 `汉字 / 数字标调拼音 / 词汇` 表借字段或主键。
- `numeric_pinyin_patch.csv` 只补上游缺失的数字标调拼音事实；直接指定
  “拼音 → 四音元码”的 canonical 补丁已退役，编码缺口必须回到正式音节编码链修复。

推荐执行顺序：

```powershell
.\venv312\Scripts\python.exe internal_data\pinyin_source_db\build_source_pinyin_db.py
.\venv312\Scripts\python.exe internal_data\pinyin_source_db\validate_source_pinyin_db.py
.\venv312\Scripts\python.exe yime\import_danzi_into_prototype_tables.py
.\venv312\Scripts\python.exe yime\import_duozi_into_prototype_tables.py
.\venv312\Scripts\python.exe yime\refresh_runtime_yime_codes.py --apply
.\venv312\Scripts\python.exe yime\export_runtime_candidates_json.py
```

其中：

- `build_source_pinyin_db.py` 默认会把 SQLite 产物写到 `.generated/source_pinyin.db`
- `rebuild_pinyin_assets.py` 在导出后会同步 `yime/pinyin_normalized.json`（码元→拼音显示层）
- `export_runtime_candidates_json.py`（兼容入口；真实实现位于
  `yime/utils/runtime_candidates_export.py`）默认把 runtime true JSON 写到
  `.generated/runtime_candidates_by_code_true.json`（**可选**，人工 diff /
  备用）

本地验证：

```bash
scripts/run_tests.cmd
```

若本次还改变了音节分解或编码规则，必须另外执行：

```powershell
.\venv312\Scripts\python.exe tools\export_syllable_decomposition.py
.\venv312\Scripts\python.exe tools\run_locked_layout_pipeline.py
```

前一命令会同时刷新分解、规则来源和遗漏审计表；后一命令验证 1727 条
“拼音 → 四个 Yinyuan ID”摘要没有被布局改动越界修改。

## 2. 运行时查词（IME 消费面）

自用与当前 Windows 原型默认以 **SQLite 为主**。

`CompositeCandidateDecoder` 优先级：

1. **`yime/pinyin_hanzi.db`** → `runtime_candidates_materialized` 物化表 —
  **默认运行时主路径（按 UI 当前编码模式查词；默认变长模式）**
2. **`.generated/runtime_candidates_by_code_true.json`** — 仅 SQLite 不可用时
3. **静态层** — 仍无候选时：`pinyin_normalized.json` 解码拼音；可选 `pinyin_hanzi.json` 汉字兜底（已 gitignore）

启动成功时常见日志：

```text
[Decoder] 运行时候选来源: SQLite 运行时候选主链（优先 runtime_candidates_materialized，回退 runtime_candidates）
```

诊断面板：SQLite 为主标 **正常**；未生成 JSON 导出仅为 **提示**。

环境变量：`YIME_RUNTIME_CANDIDATES_JSON`、
`YIME_SOURCE_PINYIN_DB`（见 §1 兼容策略）。

## 3. 已退役的 legacy-compatible 区域（2026-06）

以下对象已从仓库删除；恢复请查 git 历史：

- `yime/run_db_setup.py` 与
  `yime/legacy/pending_removal/db_manager.py`（旧中文 schema 维护链）
- `yime/utils/legacy_pinyin_tables/`（`多式拼音映射关系` / `数字标调拼音` /
  `音元拼音` 三表生成链）
- `yime/syllable_structure.py` 与 `yime/utils/syllable_compat/`
  （音节结构已收编至 `syllable/codec/yinjie.py`）
- 本地 DB 旧中文表：`数字标调拼音`、`多式拼音映射关系`、`音元拼音`（见
  `tools/drop_legacy_chinese_pinyin_tables.py`）

**仍保留的旧 import 路径：** `yime/syllable_decoder.py`
（``SyllableDecoder`` 直接继承 ``syllable.codec.YinjieDecoder``）。
音节结构真源为 ``syllable.codec.yinjie.Yinjie``；四元模型到变长音元模型的转换见
``syllable.codec.variable_length_yinyuan``。

当前主线如果需要真正刷新可消费数据，仍应回到本文第 1 节的
`source_pinyin.db -> prototype tables -> runtime` 链。

## 4. 已归档的旧脚本

根目录 `legacy/`（旧 YAML 比较链、早期音节分析试验、`pinyin` helper
快照等）与 `yime/legacy/`（含 `windows_candidate_box`）已于 2026-06
删除；恢复请查 git 历史。

这一步的目的是把主目录中的误用面降下来，避免把旧表检查脚本误认为当前 rebuild 入口。
