# 音元输入法理论文档索引（以 Yime-wiki 为准）

## 实现约束入口

以下文档不是理论正文，但和理论落地到实现时的边界条件直接相关，建议在阅读实现或修改编码链前先看：

### 术语入口

- **[术语总入口（请先读）](TERMINOLOGY_INDEX.md)** — 索引、速查、AI 提醒；链到下列专题
- [音元系统术语说明](YINYUAN_TERMINOLOGY.md)
- [Terminology of the Yinyuan System](YINYUAN_TERMINOLOGY_EN.md)
- [syllable 代码命名约定](../syllable/NAMING.md)

### 技术衔接入口

- [片音与语音技术单位的对应关系](PIANYIN_TECH_BRIDGE.md)
- [Correspondence Between Pianyin and Speech-Technology Units](PIANYIN_TECH_BRIDGE_EN.md)

### 实现边界入口

- [码点与中间层策略](CODEPOINT_POLICY.md)
- [真源文件与生成产物清单](SOURCE_AND_ARTIFACTS.md)

所有理论内容请以 [`Yime-wiki`](https://github.com/tsaanghwang/Yime-wiki) 的
`main` 分支为唯一维护源。下列条目直接链接到该分支中的正文。

本仓库不再嵌入 `Yime.wiki` Git 子模块。Yime 与 Yime-prototype 的原生 GitHub Wiki 是从
`Yime-wiki/main` 发布的阅读镜像，不应在各镜像中分别维护正文。

---

## 目录

- [绪论](https://github.com/tsaanghwang/Yime-wiki/blob/main/绪论.md)
- [已有析音法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md)
  - [已有各式析音法的分类](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#已有各式析音法的分类)
  - [各类各式二分法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#各类各式二分法)
  - [两段二分法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#两段二分法)
  - [声韵二分法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#声韵二分法)
  - [首干二分法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#首干二分法)
  - [质调二分法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#质调二分法)
  - [一调二质分析法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#一调二质分析法)
  - [节调声质韵质分析法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#节调声质韵质分析法)
  - [节调声母韵母分析法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#节调声母韵母分析法)
  - [一调三质分析法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#一调三质分析法)
  - [已有各式析音法的分代](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#已有各式析音法的分代)
  - [第一代析音法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#第一代析音法)
  - [第二代析音法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#第二代析音法)
  - [第三代析音法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#第三代析音法)
  - [第四代析音法](https://github.com/tsaanghwang/Yime-wiki/blob/main/已有析音法.md#第四代析音法)
- [现行析音法](https://github.com/tsaanghwang/Yime-wiki/blob/main/现行析音法.md)
  - [节调](https://github.com/tsaanghwang/Yime-wiki/blob/main/现行析音法.md#节调)
  - [节调与声调](https://github.com/tsaanghwang/Yime-wiki/blob/main/现行析音法.md#节调与声调)
  - [调值与调类](https://github.com/tsaanghwang/Yime-wiki/blob/main/现行析音法.md#调值与调类)
  - [节调的对立](https://github.com/tsaanghwang/Yime-wiki/blob/main/现行析音法.md#节调的对立)
  - [节质](https://github.com/tsaanghwang/Yime-wiki/blob/main/现行析音法.md#节质)
  - [声母](https://github.com/tsaanghwang/Yime-wiki/blob/main/现行析音法.md#声母)
  - [韵母](https://github.com/tsaanghwang/Yime-wiki/blob/main/现行析音法.md#韵母)
  - [干音](https://github.com/tsaanghwang/Yime-wiki/blob/main/现行析音法.md#干音)
- [唱音分析法](https://github.com/tsaanghwang/Yime-wiki/blob/main/唱音分析法.md)
  - [唱音分析的内容](https://github.com/tsaanghwang/Yime-wiki/blob/main/唱音分析法.md#唱音分析的内容)
  - [唱音的划分](https://github.com/tsaanghwang/Yime-wiki/blob/main/唱音分析法.md#唱音的划分)
  - [唱音的音值](https://github.com/tsaanghwang/Yime-wiki/blob/main/唱音分析法.md#唱音的音值)
  - [唱音拼音法](https://github.com/tsaanghwang/Yime-wiki/blob/main/唱音分析法.md#唱音拼音法)
- [音元分析法](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元分析法.md)
  - [划分首音和干音](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元分析法.md#划分首音和干音)
  - [充当首音的音元](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元分析法.md#充当首音的音元)
  - [构成干音的音元](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元分析法.md#构成干音的音元)
  - [干音的分析过程](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元分析法.md#干音的分析过程)
  - [音节的分析模型](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元分析法.md#音节的分析模型)
- [音元拼音法](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元拼音法.md)
  - [音元和音符](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元拼音法.md#音元和音符)
  - [音元的分类](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元拼音法.md#音元的分类)
  - [音元的音符](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元拼音法.md#音元的音符)
  - [音元的发音](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元拼音法.md#音元的发音)
  - [首音和干音](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元拼音法.md#首音和干音)
  - [音节与拼音](https://github.com/tsaanghwang/Yime-wiki/blob/main/音元拼音法.md#音节与拼音)
- [结论](https://github.com/tsaanghwang/Yime-wiki/blob/main/结论.md)
- [附录](https://github.com/tsaanghwang/Yime-wiki/blob/main/附录.md)
- [注释](https://github.com/tsaanghwang/Yime-wiki/blob/main/注释.md)
- [文献](https://github.com/tsaanghwang/Yime-wiki/blob/main/文献.md)
- [摘要](https://github.com/tsaanghwang/Yime-wiki/blob/main/摘要.md)
