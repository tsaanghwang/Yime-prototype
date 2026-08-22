# 输入法实现方案

## 文档定位

本文说明当前仓库内仍可用于研究和恢复的输入原型。Windows 消费和交接内容只保留为历史证据；
产品实现、构建与发布均在 `C:\dev\Yime`。工程事实和真源优先级见
[当前实现总览](../CURRENT_ARCHITECTURE.md)，文件归属见
[真源文件与生成产物清单](../SOURCE_AND_ARTIFACTS.md)，下一阶段优先级见
[项目路线图](ROADMAP.md)。

当前不再用“Python 桌面钩子原型是否等于正式 IME”概括整个项目。需要区分：

1. 本仓库保留的拼音来源、音节语义、三模式编码、布局投影、候选和 Python 交互原型；
2. `C:\dev\Yime` 独立维护的现行产品真源、正式词典、Windows 实现及发布；
3. 仅供核对的历史 Weasel、PIME 和跨仓交接材料。

## 当前结论

当前核心是复现和审计一条历史数据链，不再维持到产品消费者的自动链路：

```text
source_lexicon.sqlite3
  -> 规范带调音节
  -> 四个 Yinyuan ID
  -> 等长 / 变长 / 省键三模式
  -> manual_key_layout.json 布局投影
  -> 完整离线真源
  -> runtime_lexicon_filter_policy.json
  -> yime_core_trial 历史核心运行词典快照
  -X-> Windows Yime / PIME / Rime（本仓库不再交接）
```

Python 桌面应用仍可作为研究交互原型运行，但不是 TSF/IMM32 系统级 IME。历史前端消费结果只用于
来源核对，不能解释为本仓库仍支持产品集成。

## 真源和消费者边界

### 本仓库负责

- 校验字词拼音来源并保存审计证据；
- 维护 1732 项现行规范带调音节清单；
- 由 `SyllableEncodingPipeline`、`ShouyinEncoder`、`GanyinEncoder` 和
  `YinjieEncoder` 生成四个 Yinyuan ID；
- 从同一音元序列派生等长、变长和省键编码；
- 从 `internal_data/manual_key_layout.json` 生成唯一键位投影；
- 构建 `yime/pinyin_hanzi.db` 和候选质量报告；
- 保存历史核心词典、manifest、runtime profile 与拼音审查资产，供来源核对和恢复研究。

### 产品仓库独立负责

- `C:\dev\Yime` 独立维护现行编码、词库、布局、Rime/PIME/Windows 实现和发布真源；
- 产品侧自行审查和生成安装输入、manifest、runtime profile、部署与回滚；
- 不通过环境变量、同级目录、共享数据库或自动脚本读取本仓库。

本仓库不得把自身历史语义或布局结果覆盖到产品仓库。确需转移的清理结果必须先取得明确授权，按内容
哈希导出到独立非 Git 归档，再由产品仓库单独审查。

## 本仓库的 Python 输入原型

主入口：

```powershell
.\venv312\Scripts\python.exe -m yime.input_method.app
```

核心职责：

1. 监听全局按键并管理组合态；
2. 按当前编码模式查询 SQLite 运行候选；
3. 显示非激活浮动候选框；
4. 处理分页、选词、待上屏文本和回贴；
5. 为数据链和交互变化提供轻量本地回归入口。

运行时优先查询 `yime/pinyin_hanzi.db` 的 `runtime_candidates_materialized`，并按模式使用：

- `full_yime_code`：等长模式；
- `variable_yinyuan_code`：变长模式；
- `input_shorthand_code`：省键模式。

旧 `yime_code`、`primary_yime_code` 只承担兼容职责。JSON 候选导出主要用于人工检查和备用，不是生产
真源。

### 原型已实现

- Win32 低层键盘钩子及必要回退；
- 组合输入、候选分页和数字选词；
- 待上屏文本累积、撤销与整段提交；
- SQLite 三模式候选查询；
- 非激活候选框、手工编辑和跨窗口回贴；
- 隐藏待命、退出清理及基础状态诊断。

### 原型仍需打磨

- 不同应用、DPI、多显示器和焦点切换下的稳定性；
- 单项选择与整段提交的交互一致性；
- 长时间运行、异常退出和剪贴板/回贴失败恢复；
- 用户自适应排序和更完整的用户词库体验。

这些限制描述的是 Python 原型，不应再推导成“Yime 没有系统级前端消费路径”。

## 三模式派生

三种模式必须来自同一四音元序列：

1. 等长模式保留首音和三个干音音元；
2. 变长模式固定保留首音，只合并干音中相邻相同音元；
3. 省键模式以变长结果为输入，只省略符合规则的中调音元；
4. 虚首音承担连续输入边界，不作为省键项删除；
5. 最后才将 Yinyuan ID 投影到当前键位。

不得为某个拼音在 Python 原型、Rime schema 或 Windows 导入器中单独手写另一套三模式结果。

## Windows Yime 交接（历史，已阻断）

以下命令只为说明旧入口名称，不得执行：

```powershell
.\venv312\Scripts\python.exe tools\build_two_level_runtime_trial.py

.\venv312\Scripts\python.exe tools\verify_default_runtime_handoff.py `
  --windows-repo C:\dev\Yime `
  --output .generated\default_runtime_handoff.json
```

`tools/verify_default_runtime_handoff.py` 等交接入口现在立即返回非零状态，且不会读取或写入
`C:\dev\Yime`。旧资产结构与摘要规则见
[Windows Yime 交接历史记录](WINDOWS_YIME_LEXICON_HANDOFF.md)；现行产品导入和校验只能在产品仓库
内部实现。

## 当前质量重点

来源合规和音节编码已经闭合，不代表 245 万级静态候选都具有同等发布价值。当前质量工作的主线是：

- 用只读 `lexicon_lint` 报告识别可疑候选；
- 在独立 `input_model.sqlite3` 中保存建议、批准、拒绝和暂缓决策；
- 优先审查高频未解码字串和多读音冲突；
- 通过上下文证据和动态组合回放验证候选价值；
- 保持历史核心运行词库作为离线对照，不把安装泄漏门禁冒充本仓库当前发布职责；
- 用纯净用户态回放和高频晋升扫描发现真实缺口，不把个人误选直接提升为系统词。

具体路线见 [候选语料库整理路线图](../CANDIDATE_CORPUS_ROADMAP.md)。

## 修改与验证原则

1. 拼音问题从来源、合规策略、规范化或正式切分器修复；
2. 音元身份从语义注册表和正式编码器修复；
3. 布局只修改 `internal_data/manual_key_layout.json`；
4. 只在本仓库内重建研究运行库和审计产物，不生成交接包或 Windows 发布物；
5. 不直接改 SQLite 个别行、`yinjie_code.json`、四个 Yinyuan ID，也不写入 `C:\dev\Yime`。

常用语义与布局检查：

```powershell
.\venv312\Scripts\python.exe tools\export_syllable_decomposition.py
.\venv312\Scripts\python.exe tools\check_layout_change_lock.py
```

## 下一步

近期工作不再是“新增 N/M 真源”或“证明系统前端可消费”，而是：

1. 继续来源核对、数据清理和可撤销的审音研究；
2. 审核高频候选与恢复实验结果，不把它们自动提升到产品；
3. 扩充专业、专名、古籍及罕见字硬失败回归；
4. 保持历史结果可复现，并防止旧产品入口重新启用。

**最后更新：2026-07-27**
