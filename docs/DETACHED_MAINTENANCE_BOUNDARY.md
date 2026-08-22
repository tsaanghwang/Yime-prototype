# 脱离产品维护边界

本仓库已经退出 Yime 产品构建链。它只保留为历史现场、数据清理、来源核对、可重复审计和恢复研究
工作区；`C:\dev\Yime` 是现行 Yime 编码、词库、布局、Windows 构建和发布工作的唯一产品仓库。

## 本仓库仍支持的工作

- 核对来源、许可证、历史决策和派生关系；
- 在本仓库内运行字典合规、音节分解、编码审计、候选分析和布局锁检查；
- 在隔离输出目录中进行恢复研究、历史结果复现和 Python 原型实验；
- 修复只影响本仓库的维护脚本、文档和测试。

开发用 Python 环境安装（包括无管理员权限的便携 Python）仍可用于上述工作。它只是本仓库的研究
环境准备，不是 Yime 便携产品包或安装包发布流程。

## 本仓库不再支持的工作

- 用 PyInstaller 构建 Yime 便携产品目录；
- 用 Inno Setup 构建 `Setup.exe` 或朋友试装包；
- 生成、安装、重置或发布 MSKLC 产品包；
- 准备、复制或校验面向 Windows Yime 的跨仓交接包；
- 部署 Weasel/PIME、写入真实用户目录，或运行安装包验收；
- 通过脚本、同级目录探测、环境变量、共享可变数据库、符号链接或 junction 让
  `C:\dev\Yime` 读取本仓库内容；
- 从本仓库发布 Python 包或其他产品发布物。

现存相关脚本和规范文件只用于历史核对。它们的可执行入口会立即以非零状态退出，并把产品工作指向
`C:\dev\Yime`；脚本内部的纯校验函数可继续用于不写外部仓库的来源核对或恢复研究。

当前明确阻断的入口包括：

- `scripts/build_portable_release.bat`
- `scripts/build_setup_release.bat`
- `scripts/build_friend_trial_package.bat`
- `yime_portable.spec`
- `yime_setup.iss`
- `.github/workflows/release.yml`
- `tools/prepare_windows_yime_lexicon.ps1`
- `tools/prepare_windows_yime_auxiliary_assets.py`
- `tools/verify_default_runtime_handoff.py`
- `tools/export_and_deploy_weasel_yime.ps1`
- `tools/run_msklc_packaging_pipeline.py`
- `tools/run_msklc_install_pipeline.py`
- `tools/reset_msklc_install_state.py`
- `tools/verify_seed_install_flow.py`

## 受控恢复出口

如果某项清理或来源核对结果确需进入 Yime，必须先取得明确授权。随后按内容哈希导出到不属于任何
Git 工作树的独立归档，再在 `C:\dev\Yime` 中单独完成来源审查和临时跨仓批准。不得把一次性导出
改造成自动同步，也不得直接从本仓库覆盖 Yime 文件。

旧发布、安装和交接文档继续保留历史命令、产物结构和故障证据，但均不是现行操作手册。看到这些
命令时应在此止步；产品实现、构建、安装、发布和 Windows 集成一律转到 `C:\dev\Yime`。
