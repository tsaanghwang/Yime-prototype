# 汉语输入候选整理与动态组合系统

本系统位于统一字词来源库与运行时词库之间，负责整理语言材料、记录审查决策，并验证长候选能否由
来源门禁合格的较短材料动态恢复。自动可达性证据不要求短材料先经人工分类；真正进入发布运行规则
仍须另经回放验证。系统不重新定义汉语“词”，也不是第二套拼音、音元或键位码表。

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

语言的能产组合不能靠逐条静态收录解决。BCC 频次无论多高，都只决定审查优先级；如果字串能由已有
基本单位按照稳定构式和语境需求生成，就应先归为 `productive_phrase` 或
`semi_fixed_construction + model_only`，以规则族、代表样例和反例为审查单位。组合规则及其组件读音
通过回放验证后，同族实例批量标记为 `dynamic_recoverable` 并退出逐条人工队列。只有不能由通用规则
可靠恢复的词汇化单位、固定表达、专名和领域术语才进入 `static_keep`。这样人工工作量取决于有限的
规则和例外，而不是 BCC 表面字串的总数。

当前分类包括单字、词汇候选、固定表达、人名、地名、机构名、领域词、半固定构式、能产短语、句法
片段、确定性无效材料、依赖语境和未知材料。当前整合政策包括：

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

## 未编码字串人工准入工作台

运行：

```powershell
.\venv312\Scripts\python.exe tools\review_unencoded_candidates.py
```

会在本机浏览器打开鼠标操作为主的审查界面。工作台只列出
`candidate_universe.has_gated_reading = 0` 的字串，也就是尚无通过来源门禁的完整注音（拼音）、不能进入
当前编码候选的材料。其中既包括只有汉字字串和 BCC 频次、完全没有注音来源的项目，也可能包括来源
注音已被门禁拒绝的项目。队列默认按 BCC 频次排序，并显示各项实际出现的 BCC 分域；支持搜索、频次
过滤、按精确字数分组查询，以及待审、已准入、已拒绝、暂缓四种状态视图。

`candidate_universe.text_length` 是字数分组的唯一真值。工作台摘要按实际存在的字数生成 `1字`、
`2字`、`3字` 等分组，并分别保留各判决状态的数量；队列项和详情使用同一字段标记所属组。选择某一
字数组后，`/api/queue?text_length=N` 只返回长度恰为 `N` 的未编码字串，仍可与状态、搜索文本、
最低 BCC 频次和游标分页组合使用。字数是候选整理维度，不参与拼音推断或音元编码。

两字未编码候选另有一条内建可达性规则：如果左右两个单字分别都在候选全集中具有来源门禁合格
注音，整体又没有合格词条读音，则记录
`dynamic_reachable + two_character_dynamic_reachability`。这只证明字串在技术上可由两个已知单字
连续输入，不证明它不是词、专名或固定组合，也不改变 `candidate_class`、`integration_policy` 和
`decision_status`。因此这类候选仍留在待审队列，不能仅凭可达性退出静态待编码系列。暂无可信普通话
读音来源的字串不适用此规则；人工 assessment 继续独立决定去留。当前模型在
`metadata.two_character_dynamic_reachability_count` 和工作台摘要中记录覆盖数量。

统一来源包还提供 `unencoded_pending_strings` 表和同名 TSV。其真源是
`dictionary_pinyin_compliance_policy.json.unencoded_pending_codepoints`：只要来源字串包含任一登记
码点，未经核实的读音记录就不会进入正式编码链；纯 BCC 字串也会进入该表，并从
`unresolved_bcc.tsv` 排除。输入候选模型把这些字串标为
`unknown + needs_review + deferred + missing_trusted_mandarin_reading`，在工作台中显示为“暂无可信
普通话读音来源，未予编码”。它们不参加普通自动筛查，但保留原始频次、来源和审计证据，等待专家或
未来可信来源复核；该状态不等同于无效、永久拒绝或最终不予编码。候选模型仍兼容读取旧版
`nonencoding_strings` 表，但按新的暂缓语义迁移，不再恢复为旧式 `noise + reject`。

页面顶部先提供三类判决口径选项卡：国家/国际分词基本规范、学界语料标注准则和审查者自定标准。
前两类用于提示边界可复现、材料类型、粒度一致性和证据不足时暂缓等通用原则；自定标准保存在当前
浏览器，并随判决写入审计证据。选择任何口径都不会自动准入，也不能绕过真实读音来源或正式编码
门禁。

能产材料的主入口是“规则族登记”，不是把每个表面字串逐条准入。每个规则族必须登记稳定的 ASCII
标识、结构规则、适用/排除范围、一个代表例、可选的同族正例和至少一个反例。代表例与正例必须来自
候选全集，登记后按所选的能产短语、半固定构式、专名或领域分类写入 `model_only`，并带有
`rule_family_id`，从逐条待审队列退出；反例只约束规则边界，不会被自动拒绝或改分类。规则族、正反例
及历次修订分别保存在 `rule_families`、`rule_family_examples` 和
`rule_family_audit_events`，不会写入拼音、Yinyuan ID、码元或键位。

“已登记”只表示形成了可审计的有限规则假设，`runtime_eligible` 仍为 `false`，验证状态仍为
`unvalidated`。只有组件已经具有真实来源读音，并完成旧词库/真实输入回放、误吞反例检查和歧义评估
之后，才允许由后续独立流程把同族实例标记为 `dynamic_recoverable`。当前工作台不提供这一步提升，
因此不会把结构描述当成可执行分词器或运行时组合规则。

## 未编码长串的递归动态组合

运行：

```powershell
.\venv312\Scripts\python.exe tools\build_recursive_composition_model.py
```

会对整体尚无来源门禁合格读音的候选，按字数从长到短建立分层组合证据。模型先尽量用统一来源库
中已有合格读音、因而可由正式链编码的多字串覆盖目标；这些组件不要求先被标成人名、词、专名或
动态组合，也不要求人工批准。未被多字组件覆盖的连续余段不立即摊成顶层单字，而是默认封装成二字
动态残余块；余段为奇数或边界会暴露一个孤字时，允许用三字或四字块吸收。单字读音只在残余块内部
验证输入根基，不与多字组件和残余块竞争顶层切分；块内仍缺来源门禁合格单字时才记录单字根基例外。
超过单步组件上限的首选路径会组织成递归树。

证据保存在 `input_model.sqlite3.recursive_composition_evidence`，并导出到
`.generated/recursive_composition/`。每项记录：

- 首选分层组件、有限个等优覆盖方案及其动态残余块；
- 已编码多字覆盖量、组件数、动态残余字符数和单字根基例外数；
- 有界等优方案数、结构多解标记和顶层组件数；
- 首选输入序列、组件读音组合数和可重建组件读音的索引；
- 递归深度；单步最多六组件的递归组合树在查看单项时从首选切分和来源读音即时重建；
- 无法覆盖时的最远可达前缀、可达后缀及缺少已编码单字的码点。

`primary_marked_input` 和 `primary_numeric_input` 只是组件依次输入时的组合序列，不写回
`canonical_readings`，不冒充目标长串的来源词音。模型也不修改 `candidate_class`、
`integration_policy` 或 `decision_status`。统一来源包或候选全集重建时会清空旧递归证据，防止用
过期组件证明新候选。

## 静态词库容量规划

`tools/plan_static_lexicon_capacity.py` 面向已经具有合规完整读音的字串，寻找“必须静态保留的底座”和
“可在验证后迁往动态组合的候选”，不尝试实现普适分词。运行：

```powershell
.\venv312\Scripts\python.exe tools\plan_static_lexicon_capacity.py
```

规划器按完整的 `text + numeric_pinyin` 判断可达性，而不是只按字面切分：

1. 单字始终属于静态底座；
2. 某个读音若不能由更短、已经登记且读音逐音节完全匹配的字串递归覆盖，则该字串必须静态保留；
3. 只有全部登记读音均可由更短组件重建的字串，才进入动态迁移候选；
4. 可恢复字串再按自身 BCC 频次、作为其他字串组件的复用次数与复用频次形成透明效用排序；
5. 默认选择能达到 98% 直接 BCC 频次覆盖的容量，也可用 `--target-capacity` 明确指定容量。

产物位于 `.generated/static_lexicon_capacity/`：SQLite 保存逐读音分解证据和逐字串去向，
`capacity_frontier.tsv` 对比不同容量的直接频次覆盖，`static_capacity_items.tsv` 给出完整排序，
`manifest.json` 和 `summary.md` 记录推荐值。该推荐是容量代理，不是发布判决；“可动态重建”只证明
读音路径存在，真正删减静态词条前仍须进行候选排序、歧义、延迟和真实输入回放。规划器不修改来源
库、当前运行词库、拼音或音元编码。

### 正序与逆序层级筛选

工作台的“构式发现”区支持两种完全对称的只读筛选：

- **逆序/后缀**：先筛出以根后缀结尾的候选，例如 `路`；再用 `马路、铁路、公路` 等细分项逐层
  收窄。一个候选同时命中多个层级时使用最长细分项拆分，例如 `高速公路` 拆为
  `高速 + 公路`，而不是 `高速公 + 路`；
- **正序/前缀**：先筛出以根前缀开头的候选，再按更长前缀细分；同样使用最长细分项，将候选拆成
  `前缀 + 后续部分`。

根项和细分项必须保持方向兼容：正序细分项必须以根项开头，逆序细分项必须以根项结尾。筛选默认只
查看整体没有合规读音的候选，并逐项回查 `candidate_universe.has_gated_reading`，确认拆分后的左右
两部分是否各自具有来源门禁合格读音；页面同时显示来源库中的主读音供核对。它不进行逐字猜读音，
也不把字面可切分等同于语义上成立。

两侧都已有合规读音时，结果只获得“动态组合候选”或所选人名、地名、机构名、领域规则候选建议；
登记时仍写为 `model_only + unvalidated`。至少一侧缺少合规读音时标记
`reading_evidence_required`，不能作为规则族正例直接提升。筛选方向、根项和细分层级会随规则族写入
`evidence.discovery_model`，从而使正序/逆序发现过程可以重放和审计。

### 后段模板的语义分类与程序去留

正序/逆序结果还允许逐项保存语义分类，尤其用于“前段 + 后段”的逆序集合，例如所有以“元”结尾的
候选。现行分类包括人名、商号/企业字号、品名、货币计量、其他专名、固定词项、确定性无效材料和
无法判定。数据字段 `noise` 仅为兼容旧决策格式，语义限定为 R0 明确无效/隔离，不能用于低频、
古旧、构式部件或动态残差。
分类写入 `tail_classifications`，以候选、方向和根锚点为联合边界，同时保存实际命中的最长锚点、
审查者和时间。保存分类本身不写去留 assessment，也不修改来源库或运行词库。

点击“运行分类去留”后，程序重新读取已保存分类并执行确定性门禁：

```text
人名 / 商号 / 品名 / 其他专名
  + 前后组件均为 atomic_gated 或唯一 composition_covered
  -> approved + model_only，移出静态待编码系列

货币计量
  + 逆序后段成立
  + 前段为受控汉字/阿拉伯数字金额
  + 每个有读音字符及货币后段均通过来源门禁
  -> approved + model_only，移出静态待编码系列

固定词项
  -> deferred + static_keep，保留待编码审查

确定性无效材料（兼容值 `noise`）
  -> rejected + reject

分类不明、组件缺读音、缺音两字例外或递归多解
  -> deferred + needs_review
```

因此，分类是人工提供的语义证据，去留是程序依据分类与结构证据共同计算的结果；二者不会混成一次
无条件删除操作。程序还会保护已有的非本流程人工判决，只允许同一后段分类流程重跑自己先前生成的
assessment。所有动态排除项仍明确标记 `runtime_eligible = false`，不能绕过正式读音来源和音节编码
链进入运行词库。

### 框式模板与槽位递归

前缀和后缀之外，工作台还支持含可替换中间字串的框式模板。模板语法只有三种受控单元：

- `{槽位}`：至少一个字符的必填槽位；
- `{槽位?}`：允许为空的可选槽位；
- `(中|上|下)`：从登记项中选择一个固定字串。

其余文字均为固定锚点。例如 `以{依据}为{目标}`、`在{处所}(中|上|下){后续?}`。模板必须至少含
一个槽位和一个固定/选择锚点，槽位名不得重复，不支持任意正则表达式或嵌套执行代码。必填槽位为空的
`以为`不会命中第一项模板；`在中国发展`也不会仅因“中”字出现而被强行解释为
`在{处所}中{后续}`。

每个命中槽位和固定组件按以下顺序检查：

```text
整体已有来源门禁合格注音
  -> atomic_gated，作为原子停止
整体未注音且长度为两字
  -> 两个单字均有合格注音：composition_covered
  -> 至少一个单字缺合格注音：short_form_exception
整体未注音且长度大于两字
  -> 最长已注音子串优先的递归分解
     -> 唯一最少组件解：composition_covered
     -> 多个同等最优解：ambiguous_split
     -> 最终无法覆盖：reading_evidence_required
```

递归结果按子串缓存并限制备选数量，页面只展开当前命中的拆分，不一次生成完整组合全集。只有模板匹配
唯一，且所有非空组件均为 `atomic_gated` 或唯一 `composition_covered` 的项目才能批量带入规则族
正例。缺音两字例外、多解和缺读音项目必须分别人工处理。

框式发现模型以 `kind = frame_template`、原始模板和解析后的受控片段写入
`evidence.discovery_model`。登记 API 会重新解析模板并重跑每个正例的递归门禁，不能依靠前端提交的
显示结果绕过检查。框式材料默认仍是 `model_only + unvalidated`；真实上下文、误吞反例、固定词例外
和输入回放通过后，才可能成为 `dynamic_recoverable`。

### 规则优先的自动筛查

“自动筛查”只处理整体没有来源门禁合格读音、且尚无任何人工或机器 assessment 的候选。已有准入、
拒绝、暂缓和人工改判始终优先，不会被自动流程覆盖。系统加载所有含 `discovery_model` 的已登记规则
族，按以下顺序处理：

```text
已有 assessment：跳过
规则族精确反例：negative_example_excluded
登记框式 / 正序 / 逆序规则匹配
  -> 槽位或两侧递归覆盖
  -> 唯一分类、唯一最高优先级命中：auto_covered
  -> 不同分类同时命中：rule_conflict
  -> 同等最高优先级规则同时命中：rule_conflict
  -> 两字且两个单字均有合格注音：记录内建可达证据，不改变筛查去留
  -> 两字但至少一个单字缺合格注音：short_form_exception
  -> 多个同等递归解：ambiguous_split
  -> 缺来源读音：reading_evidence_required
没有规则命中但可递归覆盖：unclassified_composition
```

框式规则的固定锚点优先级高于一般前后缀；前后缀按最长实际命中锚点提高具体度。同一分类存在多个
命中时，只有一个规则具有严格更高具体度才可自动选择；跨分类命中一律视为冲突。规则负例只排除
对应精确字串，不会被批量改判。

预览 API 计算完整频次范围内的各状态数量和自动覆盖率，但只向页面返回限定数量的明细。对于尚未
解释的项目，系统按首字正序和末字逆序聚类，列出数量、汇总频次和代表样例，帮助审查者添加有限的新
规则族；聚类本身不会自动创建规则。

“应用安全命中”会重新计算当前数据库状态，只写唯一、无冲突的 `auto_covered` 项。写入结果为：

```text
decision_status = approved
integration_policy = model_only
admission_stage = rule_auto_screened_unvalidated
runtime_eligible = false
runtime_blocking_reason = missing_gated_source_reading
```

assessment 同时记录规则族、匹配结构和自动筛查审查者；运行词库、来源库和音节编码真源均不连接
写入。每次最多应用 5000 项，规则冲突、负例、短组合、多解、缺读音和缺规则项目仍留在相应人工或
规则补充队列。只有另行完成真实输入回放与误吞率验证后，才允许把规则族和命中实例提升为
`dynamic_recoverable`。

推荐通过上述命令启动页面。若直接双击 `review_ui/index.html`，静态界面也能正常显示，并会尝试连接
本机 `127.0.0.1:8765` 的审查服务；服务尚未启动时，页面会明确显示启动命令。浏览器不能直接把
SQLite 文件当作审查 API，因此“载入数据”仍由本机服务按命令行指定的候选覆盖库和统一来源库完成，
不接受页面随意导入另一份中间码表。

三个主判决按钮的语义是：

- **准入**：人工确认该字串值得进入候选生产流程；状态写为 `approved`，但同时明确记录
  `runtime_eligible = false` 和 `missing_gated_source_reading`。它仍须补充真实读音来源并通过正式音节
  编码链，界面不会填写拼音、Yinyuan ID、码元或键位；
- **拒绝**：写入 `rejected + reject`，表示不应进入候选生产链；
- **暂缓**：写入 `deferred + needs_review`，等待 KWIC 或其他可追溯上下文。

这三个按钮用于固定词、例外、确定性无效材料及证据不足材料的逐条处理；判断为能产组合时应优先
使用规则族
登记区。个体 `model_only` 仍可用于孤立评测材料，但不等价于已经登记或验证的规则族。

判决写入 `.generated/input_candidate_model/input_model.sqlite3` 的 `assessments`，每次新增或改判同时
写入 `audit_events`。来源库以只读方式打开，运行词库完全不连接写入。服务只允许绑定
`127.0.0.1/localhost`，写请求还要求同源 JSON 和本地审查标记。

## 尚未接入的部分

当前骨架尚不自动修改运行时词库，也不声称已经完成汉语分词。现有 BCC 输入只是分域频次表，不能
反向重建 KWIC 原句。进入生产前仍需补齐：真实上下文导入、功能词和框式构式规则、
Gram/排序器接口、旧词库回放指标，以及只有在动态恢复稳定后才执行的精简发布步骤。当前审查界面
已经能够记录未编码字串的人工准入，但不会替代真实读音来源核验。
