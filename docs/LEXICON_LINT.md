# 系统候选完整性质检

本文档说明如何对候选资产做确定性、只读完整性检查。候选池的动态覆盖和核心提升由
`evaluate_dynamic_candidate_coverage.py` 负责；lint 不承担低频删除或词汇性判断。

## 目的

在发版或大规模改词库后，用统一规则找出可能需要人工审阅的词条，例如：

- 词语以常见助词 / 语气词结尾（的、了、吗、呢、吧…）
- 词语仍使用占位编码（`yime_code == pinyin_tone`）

这些规则产生的是 **候选角色审阅信号**，不是自动删除指令。系统先依据字形、来源读音和位置，
把命中项映射到结构助词、动态／体貌助词或语气助词构式；1–4 字项再检查有类型的核心部件价值，
更长项检查动态恢复价值。是否直接显示、仅作组件、现场生成或拒绝，仍须经词汇裁决和回放确认。
完整理论模型见[助词构式系统与核心部件准入](PARTICLE_CONSTRUCTION_SYSTEM.md)。

## 工具

| 脚本 | 作用 | 是否改数据 |
|------|------|------------|
| `tools/lexicon_lint.py` | 扫描并输出 JSON 报告 | 否（只读） |
| `tools/evaluate_dynamic_candidate_coverage.py` | 给全部已编码候选分配 R0–R5 并输出残差 | 否（只读） |
| `tools/export_lexicon_quality_review.py` | 结合候选覆盖层导出全量排序 TSV 与摘要 | 否（只读） |
| `tools/evaluate_particle_construction_system.py` | 全位置扫描助词构式及其类型接口 | 否（只读） |
| `tools/audit_long_form_core_migration.py` | 检查零证据普通长串是否已迁出静态核心 | 否（只读） |
| `tools/apply_lexicon_review_decisions.py` | 预检或显式应用版本化人工裁决 | 默认只读；仅 `--apply` 写覆盖层 |

共享逻辑：`yime/utils/lexicon_quality.py`

## 何时运行

建议在以下时机之一执行 **lint**（不必每次日常开发都跑）：

1. 修改统一 `source_lexicon.sqlite3` 构建器、门禁或上游来源之后
2. 执行 `runtime_codes_refresh.py --apply` 之后
3. 执行 `yime/export_runtime_candidates_json.py` 之后
4. 准备把 `runtime_candidates` 导出为 Rime `dict.yaml` 并合入 **Yime** 运行时仓库之前

## 快速用法

在仓库根目录使用可用的 `venv312`：

```powershell
# 默认只流式扫描 yime/pinyin_hanzi.db
.\venv312\Scripts\python.exe tools\lexicon_lint.py

# 只有显式指定或运行库不存在时才扫描巨型 runtime JSON，避免与 SQLite 重复计数
.\venv312\Scripts\python.exe tools\lexicon_lint.py `
  --runtime-json .generated\runtime_candidates_by_code_true.json

# 显式扫描统一来源层；同时给出多个参数才会做跨层对照
.\venv312\Scripts\python.exe tools\lexicon_lint.py `
  --source-db .generated\lexicon_source_bundle\source_lexicon.sqlite3

# 输出到自定义路径
.\venv312\Scripts\python.exe tools\lexicon_lint.py `
  --output .generated\my_lint_report.json

# 仅当存在 error 时失败（默认）
echo $LASTEXITCODE

# warning 也视为失败（可选，用于严格 CI）
.\venv312\Scripts\python.exe tools\lexicon_lint.py --fail-on-warnings
```

生成完整的 R0–R5 动态覆盖报告：

```powershell
.\venv312\Scripts\python.exe tools\evaluate_dynamic_candidate_coverage.py
```

旧命令 `tools/lexicon_clean.py` 只作兼容转发，不再产生删除计划。

生成可逐项审阅的全量派生队列：

```powershell
.\venv312\Scripts\python.exe tools\export_lexicon_quality_review.py
```

默认读取 `yime/pinyin_hanzi.db` 与
`.generated/input_candidate_model/input_model.sqlite3`，生成：

- `.generated/lexicon_quality_review/review_queue.tsv`：按 BCC 频次档、BCC 频次和运行权重排序；
- `.generated/lexicon_quality_review/review_summary.md`：总量、频次分层、尾字分布和高优先级样例；
- `.generated/lexicon_quality_review/manifest.json`：输入路径、数量和“不写 assessments”政策。

队列以不同字串为单位合并同形多读，左连接 `candidate_universe` 和 `assessments`。已有
`approved`/`rejected` 决策的字串从待审队列排除；`proposed`/`deferred` 保留，并显示是否已有
`context_evidence`。工具不会自动新增、修改或批准任何 assessment。

经人工或明确代理审阅后的裁决保存在
`internal_data/lexicon_review_decisions.json`。先运行默认 dry-run，再显式应用：

```powershell
.\venv312\Scripts\python.exe tools\apply_lexicon_review_decisions.py
.\venv312\Scripts\python.exe tools\apply_lexicon_review_decisions.py --apply
```

该工具只写生成型 `input_model.sqlite3` 覆盖层，不改来源词库。动态覆盖定义、真实基线和完成门槛见
[候选池分层与动态覆盖闭环](DYNAMIC_CANDIDATE_COVERAGE.md)。

## 报告格式

`lexicon_lint` 输出 JSON，结构对齐仓库内其它校验脚本（如 `validate_source_pinyin_db.py`）：

```json
{
  "tool": "lexicon_lint",
  "inputs": { "runtime_db": "..." },
  "summary": {
    "candidate_rows": 0,
    "source_phrase_rows": 0,
    "error_count": 0,
    "warning_count": 0,
    "suffix_particle_count": 0,
    "source_suffix_particle_count": 0,
    "suffix_particle_by_char": {},
    "source_suffix_particle_by_char": {},
    "placeholder_phrase_count": 0
  },
  "errors": {},
  "warnings": {
    "suffix_particle": [ { "text": "...", "suffix_char": "的" } ]
  },
  "sample_limit": 20
}
```

不带输入参数时只选择一个权威输入：依次尝试运行 SQLite、runtime JSON、统一来源 SQLite，避免同一
候选跨层重复计数。显式给出多个输入参数时才会同时扫描并把结果视为跨层观察。

每个 warning/error 类别默认最多保留 `--sample-limit` 条样例（全量计数在 `summary`）；运行候选
样例按 `sort_weight` 从高到低保留，优先支持高价值人工审阅。SQLite
逐行扫描，不把数百万行候选或来源记录一次性载入内存。显式扫描 runtime JSON 仍需由标准库解析整个
JSON，因此只用于确实需要检查 JSON 导出结构的场合。

## 当前规则说明

### `suffix_particle`（warning）

- 适用范围：`entry_type == phrase` 且长度 ≥ 2
- 条件：末字属于助词/语气词集合，且末音节命中登记的数字标调读音
  （见 `lexicon_quality.PARTICLE_SUFFIX_PINYIN`）
- 读音约束会排除「目的 `di4`」「终了 `liao3`」「花呢 `ni2`」「爪哇 `wa1`」等确定性误报
- 白名单：`PARTICLE_SUFFIX_WHITELIST`（如「你的」「好的」）不报警
- **角色建议**：1–4 字按构式系统标为 `structural_component_candidate`、
  `aspectual_component_candidate`、`modal_component_candidate` 或
  `polyfunctional_particle_candidate`；更长项标为 `dynamic_sentence_candidate`
- **含义**：优先审查它作为核心组件或动态句子材料的价值；不是自动删除，也不证明整条应直接上屏
- **理论证据**：报告同时给出构式编号、左右选择接口和说明；稳定语法接口而非词汇频次是进入核心
  部件审查的理由

### `source_suffix_particle`（warning）

- 在 `source_lexicon.sqlite3` 的 `phrase_readings` 兼容视图上应用相同尾字规则

### `placeholder_phrase_code`（warning）

- 与 `runtime_candidates_export.py` 一致：`yime_code == pinyin_tone` 的词语

### `json_code_key_mismatch` / `missing_required_fields`（error）

- JSON 结构或字段完整性问题

## 与构建管线的关系

```
source_lexicon.sqlite3 ──validate──►  (validate_source_pinyin_db.py)
        │
        ▼
runtime refresh / export
        │
        ▼
tools/lexicon_lint.py  ──►  .generated/lexicon_lint_report.json
        │
        ▼
evaluate_dynamic_candidate_coverage.py ← R0–R5 全量覆盖与残差
        │
        ▼
export_lexicon_quality_review.py ← 结合 input_model 生成全量排序队列
        │
        ▼
人工决定写入独立候选整理覆盖层
        │
        ▼
apply_lexicon_review_decisions.py ← 版本化裁决，默认 dry-run
```

**注意**：lint 负责数据完整性；动态覆盖报告负责生成能力。两者都不删除来源事实。

## 调整规则

助词类别与组合接口编辑
`internal_data/particle_construction_policy.json`；分类器位于
`yime/input_model/particle_constructions.py`。尾字扫描入口编辑
`yime/utils/lexicon_quality.py`：

- `PARTICLE_SUFFIX_PINYIN`：尾字与允许的末音节读音
- `PARTICLE_SUFFIX_WHITELIST`：不报警的固定短语

修改后运行 `tests/input_model/test_particle_constructions.py` 和
`tests/yime/test_lexicon_quality.py`。
审阅队列导出规则另运行 `tests/yime/test_lexicon_review.py`。

## 相关文档

- [候选池分层与动态覆盖闭环](DYNAMIC_CANDIDATE_COVERAGE.md)
- [拼音数据迁移与运行时查词](project/PINYIN_DATA_MIGRATION.md)
- [数据文件结构说明](DATAFILES.md)
- [真源文件与生成产物清单](SOURCE_AND_ARTIFACTS.md)
