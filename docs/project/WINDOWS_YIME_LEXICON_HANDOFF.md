# 新版词库交接到 Windows Yime

原型是拼音来源审查、音节编码和候选整合的事实来源；Windows Yime 只接收原型导出的
等长 `yime_full.dict.yaml`，再由自身的正式导入器确定性派生变长和省键词典。不得分别手工
维护或导入三套系统词典。

## 准备交接包

在原型已经完成单字、多字导入和运行码刷新后执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File tools\prepare_windows_yime_lexicon.ps1
```

默认输出目录是 `.generated/windows_yime_import/`，其中：

- `yime_full.dict.yaml`：交给 Windows Yime 的唯一系统词库真源；
- `yime_pinyin_codes.tsv`：数字标调拼音到当前等长布局码的映射；
- `yime_syllable_decomposition.tsv`：正式编码器生成的音节分解、Yinyuan ID 和布局投影；
- `pinyin_normalized.json`：数字标调拼音到规范带调拼音的显示映射；
- `yime_pua_pinyin.json`：由原型 `yime/code_pinyin.json` 复制并按 Windows 运行时命名的 PUA 注释映射；
- `yime_handoff_manifest.json`：上述拼音资产的条目数、来源路径和 SHA-256；
- `yime_full.metadata.json`：原型导出统计、布局摘要和输入数据库信息；
- `windows_derived/`：由当前 `C:\dev\Yime` 正式导入器试派生的三模式词典及哈希清单。

该脚本只准备和验证文件，不写入 Windows Yime 仓库，也不部署到用户的 PIME/Rime 目录。
若只需原型侧导出，可加 `-SkipWindowsDerivation`；Windows Yime 仓库不在默认位置时使用
`-WindowsYimeRoot` 指定。

## 验收边界

交接前必须满足：

1. 来源数据库校验无错误、无警告；
2. 原型单字和多字行全部生成唯一运行码，缺码及多码冲突为零；
3. 当前布局锁和音元真源一致性检查通过；
4. Windows Yime 导入器成功生成等长、变长、省键三份词典；
5. 三份拼音审查及显示资产具有完全相同的规范音节键集；
6. `yime_handoff_manifest.json` 与 `windows_derived/yime_lexicon_manifest.json` 中的条目数和各文件 SHA-256 可复核。

真正部署时，应在 Windows Yime 仓库中使用其
`tools/deploy-yime-rime-data.ps1 -Input <yime_full.dict.yaml>` 入口；部署属于下一步显式操作，
不包含在本准备脚本内。
