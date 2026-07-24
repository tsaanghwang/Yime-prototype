# 输入法实现方案

## 文档定位

本文说明当前仓库与 Windows 输入前端之间的实现分工。工程事实和真源优先级见
[当前实现总览](../CURRENT_ARCHITECTURE.md)，文件归属见
[真源文件与生成产物清单](../SOURCE_AND_ARTIFACTS.md)，下一阶段优先级见
[项目路线图](ROADMAP.md)。

当前不再用“Python 桌面钩子原型是否等于正式 IME”概括整个项目。需要区分：

1. 本仓库维护的拼音来源、音节语义、三模式编码、布局投影、运行候选和 Python 交互原型；
2. 外部 Windows Yime 仓库维护的正式词典导入、Rime 适配和 Windows 消费实现；
3. Weasel、PIME 等承载系统输入体验的前端。

## 当前结论

当前核心不是从零证明输入法可行，而是维护一条可重复的数据生产与消费链：

```text
source_lexicon.sqlite3
  -> 规范带调音节
  -> 四个 Yinyuan ID
  -> 等长 / 变长 / 省键三模式
  -> manual_key_layout.json 布局投影
  -> Python 运行库与 Windows Yime 交接包
  -> Windows Yime 导入器
  -> Weasel / PIME 等系统前端
```

Python 桌面应用仍是可运行的交互原型，但不是 TSF/IMM32 系统级 IME。与此同时，系统级前端消费路径
已经存在：Weasel/Rime 和 PIME 已能消费 Yime 导出的数据。二者并不矛盾。

## 真源和消费者边界

### 本仓库负责

- 校验字词拼音来源并保存审计证据；
- 维护 1732 项现行规范带调音节清单；
- 由 `SyllableEncodingPipeline`、`ShouyinEncoder`、`GanyinEncoder` 和
  `YinjieEncoder` 生成四个 Yinyuan ID；
- 从同一音元序列派生等长、变长和省键编码；
- 从 `internal_data/manual_key_layout.json` 生成唯一键位投影；
- 构建 `yime/pinyin_hanzi.db` 和候选质量报告；
- 准备 Windows Yime 所需的等长系统词典与拼音审查资产。

### Windows 消费仓库负责

- 接收原型导出的 `yime_full.dict.yaml`；
- 用正式导入器确定性派生三模式词典；
- 生成或部署 Rime schema/dict；
- 处理 Windows 前端构建、安装、候选 UI、崩溃和系统集成；
- 在用户环境中管理部署与回滚。

消费者不得另建拼音到 Yinyuan ID、四音元码或键位的平行真源。发现数据问题时应回到本仓库的来源、
规则、语义注册表或唯一布局真源修复。

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

## Windows Yime 交接

原型侧入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File tools\prepare_windows_yime_lexicon.ps1
```

默认生成 `.generated/windows_yime_import/`。其中 `yime_full.dict.yaml` 是跨仓库唯一系统词典输入；
Windows Yime 再从它派生等长、变长和省键词典。manifest、拼音显示映射和音节分解审计用于核对键集、
条目数、来源与 SHA-256。

准备脚本不写入外部仓库，也不部署用户的 PIME/Rime 目录。真实部署必须在消费者仓库中显式执行。
完整边界见 [新版词库交接到 Windows Yime](WINDOWS_YIME_LEXICON_HANDOFF.md)。

## 当前质量重点

来源合规和音节编码已经闭合，不代表 245 万级静态候选都具有同等发布价值。当前质量工作的主线是：

- 用只读 `lexicon_lint` 报告识别可疑候选；
- 在独立 `input_model.sqlite3` 中保存建议、批准、拒绝和暂缓决策；
- 优先审查高频未解码字串和多读音冲突；
- 通过上下文证据和动态组合回放验证候选价值；
- 在有对照报告前不直接清洗生产真源或整体削减运行词库。

具体路线见 [候选语料库整理路线图](../CANDIDATE_CORPUS_ROADMAP.md)。

## 修改与验证原则

1. 拼音问题从来源、合规策略、规范化或正式切分器修复；
2. 音元身份从语义注册表和正式编码器修复；
3. 布局只修改 `internal_data/manual_key_layout.json`；
4. 运行库、Rime/KLC、交接包和 Windows 派生词典全部重新生成；
5. 不直接改 SQLite 个别行、`yinjie_code.json`、四个 Yinyuan ID 或消费者键位。

常用语义与布局检查：

```powershell
.\venv312\Scripts\python.exe tools\export_syllable_decomposition.py
.\venv312\Scripts\python.exe tools\check_layout_change_lock.py
```

## 下一步

近期工作不再是“新增 N/M 真源”或“证明系统前端可消费”，而是：

1. 完成候选质检只读工作流并开始高频候选审查；
2. 固定原型到 Windows Yime 的版本化交接协议；
3. 补齐三模式跨仓库烟测和真实应用稳定性回归；
4. 继续清理仍以 4 月 Python 原型状态概括全项目的入口文档。

**最后更新：2026-07-24**
