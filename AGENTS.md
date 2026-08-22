# AI 协作首要约束

## 仓库职责与 Yime 隔离

- 本仓库已经退出 Yime 产品构建链，只保留为历史现场、数据清理、来源核对和恢复研究工作区。Yime 的编码、词库、布局、评估和 Windows 发布真源全部在 `C:\dev\Yime`，不得从这里自动同步或覆盖。
- 本仓库内的提交、数据库、生成物、虚拟环境和清理结果默认只影响本仓库。不得直接写入 Yime 工作树，不得建立指向 Yime 的符号链接/junction，不得通过共享可变数据库、同级目录搜索或环境变量让 Yime 被动读取这里的数据。
- 若清理结果确需进入 Yime，必须先取得明确授权，按内容哈希导出到不属于任何 Git 工作树的独立归档，再在 Yime 中走来源审查和临时跨仓批准流程。一次性导出不得恢复旧的自动交接关系。
- 不要因为 Yime 的产品门禁或词库发生变化而在本仓库自动追平；两边的改动必须分别审查和提交。

本仓库当前已经具备“由带调拼音字典生成音元编码”的正式工具链：

```text
带调拼音字典
  -> 来源校验与规范音节清单
  -> SyllableEncodingPipeline / YinjieEncoder
  -> 4 个 Yinyuan ID
  -> 三模式编码
  -> 唯一布局投影与词库编码
```

## 必须保持的原则

- 片音不是等长时间窗、平顶音段、原始波形块或声学帧；音元是表示条件片音的抽象变元，
  Yinyuan ID 只是音元的唯一编号。不得从 `M01`、`N01` 或四元编码位置反推固定音值、等长时限或
  已经得到实验验证的自然语音边界。
- 采用实例驱动：来源中实际出现或经过明确审查的带调音节才进入现行清单；不得用早期“五声补齐”
  假设自动生成新音节。
- 新字典中现有规则覆盖的音节应由正式链自动编码；新形式没有依据时必须失败并报告，不能由 AI
  猜测编码。
- 不得为单个拼音直接手写四音元码、Yinyuan ID、`yinjie_code.json` 条目或键位作为修复。
- 拼音语义和布局投影是两层：布局改动只能修改唯一布局真源
  `internal_data/manual_key_layout.json`，不能反向修改音节分解。
- `v` 系列只是历史程序拼音兼容形式；`iu/iou`、`ui/uei`、`un/uen`、`yo/io` 等必须按登记的
  形式族规则处理，不能建立平行编码。

## 开始修改前

先阅读：

- `docs/CURRENT_ARCHITECTURE.md`
- `docs/PIANYIN_ANALYSIS_OVERVIEW.md`
- `docs/ZAOYIN_YUEYIN_CLASSIFICATION.md`
- `docs/SYLLABLE_ENCODING_RULES.md`
- `docs/LAYOUT_CHANGE_LOCK.md`
- `internal_data/syllable_encoding_rule_catalog.json`

修改来源、规范化、切分或编码规则后，运行：

```powershell
.\venv312\Scripts\python.exe tools\export_syllable_decomposition.py
.\venv312\Scripts\python.exe tools\check_layout_change_lock.py
```

规则目录只能解释来源和变换，禁止加入 Yinyuan ID、码元、键位或 `vk_key` 映射，以免形成第二套
中间码表。
