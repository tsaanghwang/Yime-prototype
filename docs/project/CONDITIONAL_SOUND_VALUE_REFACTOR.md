# 条件音值结构化重构

## 1. 结论先行

条件音值不能从两个 `*_enhanced.json` 才开始建模。它们是稳定 Yinyuan ID、语义码和运行时字符的
生产登记表，适合回答“这个抽象音元是哪一个”，不适合单独回答“它在什么条件下取哪个实际音值”。

本轮重构把数据链重新分成三层：

1. **片音实现值与归并规则**：保存已经登记的 IPA 实现值、音质归并和音高归并；
2. **抽象音元稳定登记**：继续由 `M01-M33`、`N01-N24` 唯一标识，不因条件音值增加而重排；
3. **条件选择与替换规则**：记录来源、适用条件、位置和操作，最后才决定表层实现或音元替换。

第一版只建立来源关系、规则契约和审计，不生成语流音变候选，不修改规范拼音、四音元分解、三模式
编码或键盘布局。

## 2. 历史来源追踪

### 2.1 噪音链

当前文件的历史可追到：

```text
yinyuan/unpitched_yinyuan.json（初始提交）
  -> noise_yinyuan.json
  -> zaoyin_yinyuan.json
  -> zaoyin_yinyuan_enhanced.json（2025-08）
  -> 2026-04 增加稳定语义登记
  -> 2026-05 两次只移动目录
```

当前可重建链的真正上游是：

```text
syllable/yinyuan/pianyin_initial.json
  -> tools/syllable_analysis/generate_zaoyin_yinyuan.py
  -> syllable/yinyuan/zaoyin_yinyuan_enhanced.json
```

`pianyin_initial.json` 保存首音标签及其已登记的实际 IPA 值；增强表负责保存稳定 ID 和运行时字符。

### 2.2 乐音链

`yueyin_yinyuan_enhanced.json` 于 2026-04 新增，但其中 33 组别名原样接管了 2025-08 已存在的
`yueyin_yinyuan.json`。后者来自下面的归并链，而不是增强表自身：

```text
规范干音分析
  -> internal_data/yinyuan_derived/ganyin_to_pianyin_sequence.json
  -> syllable/yinyuan/pitched_pianyin.json
  +  syllable/yinyuan/variables_of_attributes.json
  -> YueyinMapper（音质组与三档调级归并）
  -> yueyin_yinyuan_enhanced.json 的 aliases
```

因此乐音条件音值的两个上游维度是“具体片音清单”和“音质/音高归并规则”；增强表仍只承担稳定登记。

## 3. 新的数据契约

入口是 `syllable/pianyin/conditional_sound_value_model.json`。放在 `pianyin` 层，是因为条件音值首先
描述片音实现，而不是重新定义音元或键位。

每条未来规则必须显式包含：

- 唯一 `rule_id`；
- `research_only` 或 `deferred` 状态；
- 可追溯的 `source_refs`；
- 从模型已登记维度中选择的 `conditions`；
- 一个或多个 `operations`。

操作只有两类：

- `select_realization`：选择同一抽象音元的条件片音，不改变编码 ID；
- `substitute_yinyuan`：实际读音落入另一既有音元时，在原固定位置替换目标 ID。

任何操作都不得插入或删除音元位置。儿化、虚首音、语气词“啊”和跨音节同化若以后需要改变
候选文字，仍必须另有明确的词条或构式记录，不能由本表仅凭邻音自动改字。

## 4. 第一版门禁

运行：

```powershell
.\venv312\Scripts\python.exe tools\audit_conditional_sound_values.py `
  --output-dir .generated\conditional_sound_value_audit
```

审计器检查：

- 四个上游来源文件和两个稳定登记表均存在且可读；
- `pianyin_initial.json` 的首音标签、IPA 实现值与 N 系登记表一致；
- `pitched_pianyin.json` 的 107 个已见乐音片音与 M 系别名一致；
- 每个乐音别名按 `variables_of_attributes.json` 均归并回其登记音元；
- 57 个稳定 Yinyuan ID 唯一且 N/M 类别正确；
- 条件规则只引用已登记 ID、已声明条件维度和两类合法操作；
- `runtime_enabled=false`。

报告只写入 `.generated/conditional_sound_value_audit/`。审计通过不等于允许接入运行时。

## 5. 后续顺序

1. 先逐现象补来源记录和条件规则，优先处理虚首音与语气词“啊”所需的首音实现；
2. 再补儿化韵类、附着位置及表层音质证据；
3. 对每条规则生成“规范四 ID -> 表层四 ID”对照和碰撞报告；
4. 只有规则、冲突、三模式码长与候选碰撞全部审定后，才建立可移除的离线别名试验包；
5. 正式候选接入另行批准。
