# Tools Directory Notes

`tools/` 顶层现在主要保留三类脚本：

- 当前文档直接引用的工作流入口，例如布局流水线、MSKLC 打包安装、编码资产重建、用户词库维护与诊断脚本。
- 与当前数据面直接耦合的生成/校验脚本，例如布局投影、runtime 映射、频率基线、词语优先级和一致性检查。
- 仍有活动消费者的查询或诊断辅助脚本。

与音节分析实验、旧切片实现、历史兼容入口相关的脚本，优先放到：

- `tools/syllable_analysis/`：仍可能用于重建分析资产、但不应继续占据 `tools/` 顶层的音节分析工具。
- `legacy/syllable_analysis_tools/`：已经没有活动消费者、只保留作历史对照或旧入口兼容语义的脚本。

本轮已把一组无活动引用的旧音节分析脚本从 `tools/` 顶层下沉到 `legacy/syllable_analysis_tools/`，以降低顶层目录噪音。
另外，一条已失配的早期 orchestrator 分析链也已从 `tools/` 顶层归档到 `legacy/syllable_analysis_tools/`，避免继续把历史流水线误当成当前入口。
这轮又继续归档了一组更早的表示法类和一次性补丁脚本，进一步收紧 `tools/` 顶层只保留当前工作流入口与活动工具。
第四轮又把几份无活动引用的旧拼音侧小工具下沉到 `legacy/pinyin_analysis/`，避免顶层继续混入一次性复制、查重和格式转换脚本。
第五轮又把一个没有消费者的通用占位 JSON 资产移到 `legacy/syllable_prototypes/`，继续避免 `tools/` 顶层混入非现行工具输入。
