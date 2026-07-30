# 助词构式系统与核心部件准入

## 结论

助词材料不能因为缺少独立词汇意义、位于词尾或 BCC 频次低就判为无效。它们进入
核心部件层的理论依据是：

1. 具有稳定的语法功能；
2. 对左右成分有可描述的选择要求；
3. 能以有限规则生成大量更大单位；
4. 字形、位置和来源读音可以共同约束同形词误判。

语言分类与运行角色是两条独立轴。`structural_particles` 等类别回答“建立什么语法
关系”；`display_and_component`、`component_only_candidate` 和 `runtime_generated`
回答“运行时如何物化”。构式身份本身不自动批准直接候选。

正式策略目录是
`internal_data/particle_construction_policy.json`，分类实现是
`yime/input_model/particle_constructions.py`。

## 构式层级

```text
助词构式系统
├─ 结构助词 structural_particles
│  ├─ attributive_de：修饰语 + 的 + 可选中心语
│  ├─ adverbial_de：状语 + 地 + 谓词
│  └─ complement_de：谓词 + 得 + 补语
├─ 动态／体貌助词 aspectual_particles
│  ├─ durative_zhe：谓词 + 着
│  ├─ perfective_le：谓词 + 了
│  └─ experiential_guo：谓词 + 过
└─ 语气助词 modal_particles
   ├─ change_of_state_le：小句 + 了
   ├─ interrogative_ma：小句 + 吗
   ├─ continuative_ne：小句／话题 + 呢
   └─ 吧、啊、嘛、呀、呗、哦、哇、呐、麽等句末构式
```

「了」保留体貌和句末语气两种平行分析，不能在缺少句法上下文时武断二选一。这类
多功能材料标为 `polyfunctional_particle_candidate`，留给上下文证据和运行回放。

## 有类型的组合接口

| 构式 | 左侧要求 | 右侧要求 | 核心价值 |
| --- | --- | --- | --- |
| 的 | 修饰语或比拟材料 | 可选名词中心语 | 形成定中或名词化右边界 |
| 地 | 状语性修饰语 | 必须有谓词 | 形成等待谓词的桥接部件 |
| 得 | 谓词 | 必须有补语 | 形成等待补语的桥接部件 |
| 着／了／过 | 谓词 | 可接论元或后续材料 | 形成带体貌的谓词部件 |
| 句末助词 | 小句或话题 | 无 | 形成完整语气单位，通常不再要求右接 |

这些接口是进入核心审查的正面证据，但不是完整句法分析器。现阶段分类器只证明某个
来源读音存在一种构式分析；固定词汇、专名和同形项裁决始终优先。

## 同形词和读音门禁

规则必须同时匹配字形、来源数字标调读音和位置：

- `目的 mu4 di4`、`土地 tu3 di4`不属于“地”结构助词；
- `取得 qu3 de2`不属于轻声“得”补语构式；
- `着火 zhao2 huo3`不属于持续体“着”；
- `终了 zhong1 liao3`不属于“了”助词。

即使读音相同也只产生“构式可能性”，不覆盖已有词汇裁决。例如“经过”仍可能是
词汇动词；它不能仅凭末字 `过 guo4`自动改成体貌部件。

## 核心准入门槛

构式候选进入核心缓存必须依次满足：

1. 完整读音和组成材料都通过来源门禁；
2. 具有策略目录登记的有类型接口；
3. 固定词汇或专名裁决没有排除该分析；
4. 能服务于多个来源已有的更大单位；
5. A/B 显示预制能降低组合成本，且结构竞争处于可控范围；
6. 运行回放没有引入错误候选、异常排序或不可接受的搜索开销。

未通过缓存门槛不等于无效，而是落到 `runtime_generated`。超过核心长度上限的材料落到
`dynamic_sentence_candidate`，作为动态恢复和回放证据。

## 审阅方法

运行：

```powershell
.\venv312\Scripts\python.exe tools\export_lexicon_quality_review.py
```

输出队列除频次和当前裁决外，还记录：

- `construction_systems`：结构、体貌或语气系统；
- `construction_ids`：具体构式分析；
- `construction_interfaces`：对左右成分的选择接口；
- `theoretical_basis`：为何进入构式角色审查而不是无效材料隔离。

工具只读运行词库和输入模型，只在 `.generated/lexicon_quality_review` 创建报告，不写
来源词库或正式运行词典。

尾部队列适合安排现有疑似切片审查，但不能枚举助词位于内部的完整构式。全位置证据
使用：

```powershell
.\venv312\Scripts\python.exe tools\evaluate_particle_construction_system.py
```

该工具只读静态容量模型，在所有字符位置检查助词及其对齐读音，输出到
`.generated/particle_construction_evaluation`。因此“慢慢地走”“跑得快”等完整构式也能
进入统计，而不是再次退化成单纯尾字规则。

当前真实容量模型基线：

| 指标 | 数量 |
| --- | ---: |
| 含登记助词字形而被扫描的主读音 | 191,421 |
| 通过位置与读音门禁的构式读音 | 154,698 |
| 助词位于字串内部的构式读音 | 59,606 |
| 结构助词系统命中 | 65,829 |
| 动态／体貌助词系统命中 | 61,020 |
| 语气助词系统命中 | 68,121 |

一个读音可以同时命中多个系统，尤其是「了」，所以系统计数不能相加当作不同字串总数。
这些数据证明助词材料具有大规模、可复用的结构生产力；它们仍只是构式可能性证据，不能
替代词汇身份和上下文的人工裁决。

## 与“似的／般的”和“所字结构”的关系

「似的／般的」属于 `structural_particles.attributive_de` 下的比拟子构式。两者共享
语法族，但依据实际组合收益分别采取预制与现场生成策略。

“所字结构”是名词化构式，与结构助词系统关系密切，但“所”本身不属于助词，因此继续
作为平级构式保留在 `construction_component_policy.json`，不为了形式统一而错误归类。
