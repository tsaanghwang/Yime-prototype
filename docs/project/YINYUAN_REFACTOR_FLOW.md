# 片音 / 音元重构流程

本文档说明 2026-06 至 2026-07 “噪音 / 乐音共享类别轴、片音到音元归并、
稳定 Yinyuan ID 与规则审计”重构后的主线。全仓库总览见
[当前架构与数据真源](../CURRENT_ARCHITECTURE.md)。

## 目标

- 把 **噪音类 (`zaoyin`) / 乐音类 (`yueyin`)** 明确为跨层共享的类别轴，而不是普通声学术语或某一层专有对象名。分类定义以 [噪音类与乐音类：分类说明](../ZAOYIN_YUEYIN_CLASSIFICATION.md) 为准。
- 把 **片音对象**、**音元对象**、**片音到音元的归并规则**、**编码表示** 四层拆开。
- 让正式编码器统一产出稳定的四个 Yinyuan ID，再由布局层单独投影到物理键。
- 避免 `YueyinYinyuan` / `ZaoyinYinyuan` 同时兼任“领域对象 + 归并器 + 配置加载器 + 工具函数”。

## 重构后主线

```mermaid
flowchart TD
    A[音节字符串] --> B[SyllableEncodingPipeline\n首音段 / 干音段切分]

    B --> C[ShouyinEncoder\n首音结构编码]
    B --> D[GanyinEncoder\n干音结构编码]

    C --> C1[zaoyin_yinyuan_enhanced.json\n显式首音语义与稳定 Nxx]
    C1 --> C2[首音 Yinyuan ID / 字符投影]

    D --> D1[ganyin_to_pianyin_sequence.json\n干音片音序列]
    D1 --> D2[YueyinMapper\n片音归并到乐音音元]
    D2 --> D3[yueyin_yinyuan_enhanced.json\n乐音语义与稳定 Mxx]
    D3 --> D4[呼音 / 主音 / 末音三个 Yinyuan ID]

    C2 --> H[YinjieEncoder\n四个 Yinyuan ID]
    D4 --> H
    H --> I[manual_key_layout.json\n唯一物理键投影]

    E[syllable.pianyin.*\n片音对象] --> F[YinyuanCategory\n共享类别轴]
    G[syllable.analysis.yinyuan.*\n音元对象] --> F
```

## 分层约束

1. `syllable.pianyin.*`
负责片音对象。回答“这个实现值是什么”。

2. `syllable.analysis.yinyuan.*`
负责音元对象。回答“这个抽象单位是什么”。

3. `syllable.analysis.yueyin_mapper.YueyinMapper`
负责乐音片音到乐音音元的归并，以及数字/调号风格转换。回答“怎么从实现值归并到抽象单位”。

4. `syllable.analysis.ganyin_encoder.GanyinEncoder`
负责干音结构编码。它消费 mapper 与运行时映射，但不再把归并规则塞进 `YueyinYinyuan`。

5. `syllable.analysis.shouyin_encoder.ShouyinEncoder`
负责首音结构编码。当前主线从真源 JSON 直接读取显式映射，不再构造未参与主流程的 `ZaoyinYinyuan` 实例。

6. `internal_data/syllable_encoding_rule_catalog.json`
负责解释 1732 个规范带调音节的来源、拼写变换和编码路径。它不保存四 ID
结果或键位，避免成为第二套编码真源。

7. `internal_data/manual_key_layout.json`
只负责 Yinyuan ID 到 Base/Shift 物理键的投影。布局变化不得回写前六层。

## 模块职责

- `syllable.analysis.yinyuan_categories`
  - 共享 `zaoyin / yueyin` 类别轴
- `syllable.pianyin.pianyin`
  - 片音对象与共享 `category` 接口
- `syllable.analysis.yinyuan`
  - 音元对象与共享 `category` 接口
- `syllable.analysis.yueyin_yinyuan`
  - 乐音音元对象；仅保留对象语义与受控桥接
- `syllable.analysis.yueyin_mapper`
  - 乐音片音归并、双模型归并、调号样式转换
- `syllable.analysis.ganyin_encoder`
  - 干音结构编码主链
- `tools/syllable_analysis/*`
  - 统一复用 `YueyinMapper`，不再直接调用
    `YueyinYinyuan` 私有方法

## 不再推荐的旧模式

- 在 `YueyinYinyuan` 上继续添加 `_process_mid_high_model`、`_change_pitch_style` 之类的流程方法。
- 让 `ZaoyinYinyuan` / `YueyinYinyuan` 同时兼任“领域对象”和“编码流程服务”。
- 把“噪音 / 乐音”写成只属于音元层、或只属于片音层的分类。
- 让 `ZaoyinPianyin` 默认投射成 `YueyinYinyuan`。
- 在 `yinjie_code.json`、数据库或消费者键表中直接补某个拼音的编码。
- 为布局试验建立平行的拼音到键位或 Yinyuan ID 到键位映射。

## 兼容性说明

- `type` 等历史字段保持兼容；新代码优先使用共享 `category` 轴。
- `UnpitchedPianyin`、`PitchedPianyin`、`NoiseYinyuan` 和 `MusicalYinyuan` 只保留为旧调用别名；新代码使用 `Zaoyin*` / `Yueyin*`。
- `YueyinYinyuan.from_pianyin()` 现在只接受乐音片音；噪音片音不再默认补成“中性调乐音音元”。
- 工具脚本已切到 `YueyinMapper`，主链与脚本链的归并规则保持同源。
- 1732 条规范音节编码及语义注册表摘要由布局改动锁固定；键盘重构只允许
  改动 `manual_key_layout.json` 的最后一层投影。
