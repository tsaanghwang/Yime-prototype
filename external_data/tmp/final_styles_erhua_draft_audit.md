# 儿化标注草稿规则审计

- 范围：研究草稿、表层类规则和校对显示；未修改正式音元源、布局或运行时。
- 规则类：9。
- 本次变更成员：['a', 'ai', 'an', 'e', 'ei', 'en', 'i', 'ia', 'ua', 'uai', 'uan', 'ü']。
- 未变化成员：['_i', 'in', 'uei', 'uen', 'ün', 'iao', 'iou']。
- 合流类不一致：无。

## 表层类

同一 PSC 儿化结果的规范拼音成员引用同一套三段模板；技术拼音别名不进入音系草稿。
`᷊`（U+1DCA）仅为 Yime 下方卷舌显示附标，标准 IPA 仍由同一结构渲染为 `˞/ɚ`；上方可继续附加音高符号。

| 表层类 | 成员 | 标准 IPA | Yime 显示 |
|---|---|---|---|
| `ERHUA-ORAL-AR` | `a, ai, an` | `ää˞ä˞` | `ää᷊ä᷊` |
| `ERHUA-ORAL-ER` | `_i, e, ei, en` | `ɚɚɚ` | `ə᷊ə᷊ə᷊` |
| `ERHUA-ORAL-I-ER` | `i, in` | `iɚɚ` | `iə᷊ə᷊` |
| `ERHUA-ORAL-IAR` | `ia` | `iä˞ä˞` | `iä᷊ä᷊` |
| `ERHUA-ORAL-UAR` | `ua, uai, uan` | `uä˞ä˞` | `uä᷊ä᷊` |
| `ERHUA-ORAL-UER` | `uei, uen` | `uɚɚ` | `uə᷊ə᷊` |
| `ERHUA-ORAL-UMLAUT-I-ER` | `ü, ün` | `ʏɚɚ` | `ʏə᷊ə᷊` |
| `ERHUA-ORAL-IAOR` | `iao` | `iɑ˞ʊ˞` | `iɑ᷊ʊ᷊` |
| `ERHUA-ORAL-IOUR` | `iou` | `iɤ˞ʊ˞` | `iɤ᷊ʊ᷊` |

## 尚未自动统一

- `-ng` 鼻化类：鼻化范围与 rhotic 动程需继续分别审查。
- `ong/ueng`：共用内部编码族但来源表层形式不同，不能压成单一模板。
- 其余单成员类：没有合流遗漏时维持已有人工标注。
