# 汉语输入候选整理与动态组合系统

本系统位于统一字词来源库与运行时词库之间，负责整理语言材料、记录审查决策，并验证长候选能否由
已经批准的短材料动态恢复。它不重新定义汉语“词”，也不是第二套拼音、音元或键位码表。

当前候选规模、BCC 未解码分层、多读音冲突和分阶段整理计划见
[候选语料库整理路线图](CANDIDATE_CORPUS_ROADMAP.md)。

## 主体边界

```text
source_lexicon.sqlite3（只读来源真源）
  -> 完整候选全集（合规读音、BCC、拒绝记录的字串并集）
  -> 按 BCC 频次安排审查顺序
  -> 保守规则 / 统计模型 / LLM 分类适配器
  -> input_model.sqlite3（决策覆盖层）
       -> proposed：机器建议，不能进入生产
       -> approved：人工或明确审查流程批准
       -> rejected：明确拒绝
       -> deferred：证据不足，暂缓
  -> 动态组合器（只使用 approved 组件及已有读音）
  -> 回放评测
  -> 正式词库与 Gram/运行时候选消费者
```

来源真源继续保存字词、读音、BCC 分域频次、万象权重和拒绝证据。`candidate_universe` 为来源库中的
每个不同字串保存紧凑的全集目录和基础状态；`assessments` 只保存人工或模型作出实质判断后的稀疏覆盖
记录，避免为四百多万项重复保存大段证据。`context_evidence` 另外保存可追溯的 KWIC 前后文，供边界
判断和模型审查使用。整个覆盖层不得向来源库写入数据。

## 分类轴与整合轴

分类和处理政策是两个独立维度。例如，“张大千”的分类可以是 `person_name`，处理政策可以是
`static_keep`；一个普通高频短语可以是 `productive_phrase`，处理政策可以是 `model_only` 或经过
回放验证后的 `dynamic_recoverable`。

当前分类包括单字、词汇候选、固定表达、人名、地名、机构名、领域词、半固定构式、能产短语、句法
片段、噪声、依赖语境和未知材料。当前整合政策包括：

- `static_keep`：静态保留；
- `dynamic_component`：允许作为动态组合组件；
- `dynamic_recoverable`：已经验证可由组件恢复的长材料；
- `model_only`：只用于组合模型或评测，不作为静态词条；
- `reject`：拒绝进入候选链；
- `needs_review`：证据不足。

## 首版分类器的限制

`PolicyClassifier` 只依据来源显式提供的分类形成建议，例如万象的 `mingren`、`renming`、`diming`
和 `lianxiang` 文件类别。来源没有明确分类时，即使已有合规拼音，也只标为 `lexical_candidate +
needs_review`。所有自动结果一律是 `proposed`，不会自动批准。

以后可以增加以下分类适配器，但必须输出相同的审计结构：

1. 功能词、边界和字符形式规则；
2. 词频、左右熵、互信息和 n-gram 统计；
3. 带真实上下文的 LLM 分类；
4. 由人工标注集训练的小型本地分类器。

LLM 可以判断语义、构式和边界，不得填写拼音、音元 ID、编码或键位。模型证据不足时必须允许输出
`context_dependent` 或 `unknown`。

代码以 `CandidateClassifier` 和 `CompositionScorer` 两个协议隔离模型实现。规则、统计分类器、LLM、
Gram 或小型神经模型可以替换具体实现，但不得绕过统一的建议状态、来源读音和审计字段。

## 动态组合的安全条件

`DynamicComposer` 当前实现的是“动态恢复验证”，不是自由造句器。给定目标文本后，它只枚举已经
批准为 `static_keep` 或 `dynamic_component` 的连续组件，并从统一来源库读取这些组件的合规读音。

- 没有来源读音的组件不能参加组合；
- 未批准的机器建议不能参加组合；
- 多音组件默认保留全部有来源的组合，不擅自选择一个读音；
- 审查者可以用 `allowed_reading_ids` 明确限制某个组件允许参与组合的来源读音；
- 首版分数只是组件 BCC 频次与组件数量惩罚，不能冒充语言学词汇性判断。

后续 Gram 或小型神经模型应实现独立的排序接口。任何排序器都只能排列已有读音和候选，不得反向
覆盖来源事实。

## 构建入口

统一语料包构建完成后运行：

```powershell
.\venv312\Scripts\python.exe tools\build_input_candidate_model.py
```

默认读取 `.generated/lexicon_source_bundle/source_lexicon.sqlite3`，生成
`.generated/input_candidate_model/input_model.sqlite3`。每次构建都会同步整个候选全集，而不是截取高频
前若干项；`v_review_queue` 再按 BCC 频次分批呈现审查次序。重复运行会更新来源基础状态，但不会覆盖
已经存在的人工或模型决策。

词库尾助词质检信号可以通过：

```powershell
.\venv312\Scripts\python.exe tools\export_lexicon_quality_review.py
```

与 `candidate_universe`、`assessments` 和 `context_evidence` 只读合并，生成
`.generated/lexicon_quality_review/` 下的全量 TSV、Markdown 摘要和 manifest。它只负责安排审查
顺序，不会自动写 assessment；已有 approved/rejected 决策的字串会从待审队列排除。

## 尚未接入的部分

当前骨架尚不自动修改运行时词库，也不声称已经完成汉语分词。现有 BCC 输入只是分域频次表，不能
反向重建 KWIC 原句。进入生产前仍需补齐：真实上下文导入、
功能词和框式构式规则、审查界面、Gram/排序器接口、旧词库回放指标，以及只有在动态恢复稳定后才执行
的精简发布步骤。
