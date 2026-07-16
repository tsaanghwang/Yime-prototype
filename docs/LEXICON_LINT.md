# 系统词库质检与清洗（占位）

本文档说明如何在 **Yime-python-prototype** 仓库中对系统词库做**只读质检**。
当前阶段**不自动清理词库**；`lexicon_clean --apply` 尚未启用。

## 目的

在发版或大规模改词库后，用统一规则找出可能需要人工审阅的词条，例如：

- 词语以常见助词 / 语气词结尾（的、了、吗、呢、吧…）
- 词语仍使用占位编码（`yime_code == pinyin_tone`）

这些规则产生的是 **warning**，不是自动删除指令。是否剔除、如何改规则，应经人工确认后再进入清洗实现。

## 工具

| 脚本 | 作用 | 是否改数据 |
|------|------|------------|
| `tools/lexicon_lint.py` | 扫描并输出 JSON 报告 | 否（只读） |
| `tools/lexicon_clean.py` | 根据同类规则生成 dry-run 计划 | 否（默认；`--apply` 未启用） |

共享逻辑：`yime/utils/lexicon_quality.py`

## 何时运行

建议在以下时机之一执行 **lint**（不必每次日常开发都跑）：

1. 修改 `source_pinyin.db` 构建脚本或源 TSV 之后
2. 执行 `runtime_codes_refresh.py --apply` 之后
3. 执行 `yime/export_runtime_candidates_json.py` 之后
4. 准备把 `runtime_candidates` 导出为 Rime `dict.yaml` 并合入 **Yime** 运行时仓库之前

## 快速用法

在仓库根目录（已激活 `venv312` 或 `.venv`）：

```powershell
# 自动寻找 .generated/runtime_candidates_by_code_true.json、
# yime/pinyin_hanzi.db、.generated/source_pinyin.db（存在则扫描）
python tools/lexicon_lint.py

# 显式指定 runtime JSON
python tools/lexicon_lint.py --runtime-json .generated/runtime_candidates_by_code_true.json

# 输出到自定义路径
python tools/lexicon_lint.py --output .generated/my_lint_report.json

# 仅当存在 error 时失败（默认）
echo $LASTEXITCODE

# warning 也视为失败（可选，用于严格 CI）
python tools/lexicon_lint.py --fail-on-warnings
```

生成 **dry-run 清洗计划**（仍不写回）：

```powershell
python tools/lexicon_clean.py
# 计划默认写入 .generated/lexicon_clean_plan.json
```

尝试 `--apply` 会报错退出（故意未实现）：

```powershell
python tools/lexicon_clean.py --apply
# 退出码 2，提示先完成 lint 与人工确认
```

## 报告格式

`lexicon_lint` 输出 JSON，结构对齐仓库内其它校验脚本（如 `validate_source_pinyin_db.py`）：

```json
{
  "tool": "lexicon_lint",
  "inputs": { "runtime_json": "..." },
  "summary": {
    "candidate_rows": 0,
    "source_phrase_rows": 0,
    "error_count": 0,
    "warning_count": 0,
    "suffix_particle_count": 0,
    "placeholder_phrase_count": 0
  },
  "errors": {},
  "warnings": {
    "suffix_particle": [ { "text": "...", "suffix_char": "的" } ]
  },
  "sample_limit": 20
}
```

每个 warning/error 类别默认最多保留 `--sample-limit` 条样例（全量计数在 `summary`）。

## 当前规则说明

### `suffix_particle`（warning）

- 适用范围：`entry_type == phrase` 且长度 ≥ 2
- 条件：末字属于助词/语气词集合（见 `lexicon_quality.PARTICLE_SUFFIX_CHARS`）
- 白名单：`PARTICLE_SUFFIX_WHITELIST`（如「你的」「好的」）不报警
- **含义**：供人工判断是否为「残片词 / 不宜上屏」；不是自动删除

### `source_suffix_particle`（warning）

- 在 `source_pinyin.db` 的 `phrase_readings` 表上应用相同尾字规则

### `placeholder_phrase_code`（warning）

- 与 `runtime_candidates_export.py` 一致：`yime_code == pinyin_tone` 的词语

### `json_code_key_mismatch` / `missing_required_fields`（error）

- JSON 结构或字段完整性问题

## 与构建管线的关系

```
source_pinyin.db  ──validate──►  (已有 validate_source_pinyin_db.py)
        │
        ▼
runtime refresh / export
        │
        ▼
tools/lexicon_lint.py  ──►  .generated/lexicon_lint_report.json
        │
        ▼
（人工审阅、调整规则与白名单）
        │
        ▼
tools/lexicon_clean.py --apply   ← 尚未启用
        │
        ▼
导出 dict.yaml → 拷贝至 Yime 运行时仓库
```

**注意**：`lexicon_lint` / `lexicon_clean` **未**接入 `rebuild_pinyin_assets.py` 或 `integrate_lexicon_trial.ps1` 的默认步骤，避免在规则未稳定前阻断现有构建。发版前可手动执行。

## 调整规则

编辑 `yime/utils/lexicon_quality.py`：

- `PARTICLE_SUFFIX_CHARS`：尾字集合
- `PARTICLE_SUFFIX_WHITELIST`：不报警的固定短语

修改后运行 `tests/yime/test_lexicon_quality.py`。

## 后续（尚未做）

- [ ] 在 lint 报告稳定后，实现 `lexicon_clean --apply`（写回 source 或 runtime 层）
- [ ] 可选：接入 `integrate_lexicon_trial.ps1` 的 export 之后一步
- [ ] 可选：把报告摘要同步到 Yime 运行时仓库文档

## 相关文档

- [拼音数据迁移与运行时查词](project/PINYIN_DATA_MIGRATION.md)
- [数据文件结构说明](DATAFILES.md)
- [真源文件与生成产物清单](SOURCE_AND_ARTIFACTS.md)
