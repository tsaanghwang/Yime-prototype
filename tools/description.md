# Tools Directory Notes

`tools/` 顶层现在主要保留三类脚本：

- 当前研究和恢复文档直接引用的维护入口，例如布局检查、编码资产重建、用户词库维护与诊断脚本。
- 与当前数据面直接耦合的生成/校验脚本，例如布局投影、runtime 映射、频率基线、词语优先级和一致性检查。
- 为历史核对保留实现、但命令行入口已阻断的旧打包、安装、部署和 Windows Yime 交接脚本。

产品构建、发布和 Windows 集成只在 `C:\dev\Yime` 进行。完整范围和阻断入口见
[`docs/DETACHED_MAINTENANCE_BOUNDARY.md`](../docs/DETACHED_MAINTENANCE_BOUNDARY.md)。

与音节分析实验、旧切片实现、历史兼容入口相关的脚本，优先放在 `tools/syllable_analysis/`。根目录 `legacy/` 归档树已删除；如需对照旧实现，请查 git 历史。

## 归档与兼容入口

权威目录为 `internal_data/archived_entrypoints.json`；替代入口和原型验收排除项见 `docs/archive/HISTORICAL_ENTRYPOINTS.md`。
