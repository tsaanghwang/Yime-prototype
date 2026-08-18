# 儿化标注草稿规则审计

- 范围：研究草稿、表层类规则和校对显示；未修改正式音元源、布局或运行时。
- 规则类：22。
- 表层音质变更：无。
- 仅分类元数据变更：无。
- 已清除过期分类：无。
- 未变化成员：['_i', 'ei', 'en', 'e', 'i', 'in', 'ia', 'ua', 'uei', 'uen', 'ü', 'ün', 'ang', 'eng', 'iang', 'uang', 'ueng', 'ing', 'ong', 'iong', 'o', 'uo', 'ie', 'üe', 'ian', 'üan']。
- 人工例外（规则不覆盖）：['a', 'ai', 'an', 'uai', 'uan', 'iao', 'iou', 'u', 'ao', 'ou']。
- 合流类不一致：无。

## 表层类

PSC 儿化结果拼写用于来源对齐；基础音质或卷舌范围不同的成员拆分为不同三段模板。技术拼音别名不进入音系草稿。
`᷊`（U+1DCA）仅为 Yime 下方卷舌显示附标，标准 IPA 仍由同一结构渲染为 `˞/ɚ`；上方可继续附加音高符号。

| 表层类 | 成员 | 标准 IPA | Yime 显示 |
|---|---|---|---|
| `ERHUA-ORAL-AR-A` | `a` | `ää˞ɐ˞` | `ää᷊ɐ᷊` |
| `ERHUA-ORAL-AR-AI-N` | `ai, an` | `aa˞ɐ˞` | `aa᷊ɐ᷊` |
| `ERHUA-ORAL-ER` | `_i, ei, en` | `ɚɚɚ` | `ə᷊ə᷊ə᷊` |
| `ERHUA-ORAL-ER-E` | `e` | `ɤɤ˞ɤ˞` | `ɤɤ᷊ɤ᷊` |
| `ERHUA-ORAL-I-ER` | `i, in` | `iɚɚ` | `iə᷊ə᷊` |
| `ERHUA-ORAL-IAR` | `ia` | `iä˞ɐ˞` | `iä᷊ɐ᷊` |
| `ERHUA-ORAL-UAR-A` | `ua` | `uä˞ɐ˞` | `uä᷊ɐ᷊` |
| `ERHUA-ORAL-UAR-AI-N` | `uai, uan` | `ua˞ɐ˞` | `ua᷊ɐ᷊` |
| `ERHUA-ORAL-UER` | `uei, uen` | `uɚɚ` | `uə᷊ə᷊` |
| `ERHUA-ORAL-UMLAUT-I-ER` | `ü, ün` | `ʏɚɚ` | `ʏə᷊ə᷊` |
| `ERHUA-NASAL-NG` | `ang, eng, iang, uang, ueng, ing, ong, iong` | `按成员基础主音派生` | `按成员基础主音派生` |
| `ERHUA-ORAL-IAOR` | `iao` | `iɑʊ˞` | `iɑʊ᷊` |
| `ERHUA-ORAL-IOUR` | `iou` | `iɤʊ˞` | `iɤʊ᷊` |
| `ERHUA-ORAL-UR` | `u` | `ʊ˞ʊ˞ʊ˞` | `ʊ᷊ʊ᷊ʊ᷊` |
| `ERHUA-ORAL-OR` | `o` | `oo˞o˞` | `oo᷊o᷊` |
| `ERHUA-ORAL-AOR` | `ao` | `ɑɑʊ˞` | `ɑɑʊ᷊` |
| `ERHUA-ORAL-OUR` | `ou` | `ɤɤʊ˞` | `ɤɤʊ᷊` |
| `ERHUA-ORAL-UOR` | `uo` | `uo˞o˞` | `uo᷊o᷊` |
| `ERHUA-ORAL-IER` | `ie` | `ie̞˞ɚ` | `ie̞᷊ə᷊` |
| `ERHUA-ORAL-UMLAUT-ER` | `üe` | `ʏe̞˞ɚ` | `ʏe̞᷊ə᷊` |
| `ERHUA-ORAL-IAR-IAN` | `ian` | `iɛ̞˞ɐ˞` | `iɛ̞᷊ɐ᷊` |
| `ERHUA-ORAL-UMLAUT-AR` | `üan` | `ʏɛ̞˞ɐ˞` | `ʏɛ̞᷊ɐ᷊` |

## 参数化分类

- `ERHUA-NASAL-NG`：保留各成员呼音，基础主音同时加鼻化和卷舌特征，并复制到主音、末音两段；`ong/ueng` 与其余 `-ng` 韵母遵循同一结构规则。
- 独立占位项 `ng` 不是本规则中的规范韵母，不自动生成儿化表层。
- 其余单成员类：没有合流遗漏时维持已有人工标注。
