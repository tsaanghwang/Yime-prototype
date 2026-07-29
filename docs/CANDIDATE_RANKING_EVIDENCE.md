# 候选排序证据与长尾结构

本项已经由程序实现。排序不再把“没有 BCC 计数”误写成最低频次，也不把不同量纲的
BCC 原始 count 与 RIME-LMDG（万象）权重相加。

## 四层决策

| 层 | 条件 | 有效权重 | 证据状态 |
|---|---|---:|---|
| BCC 直接证据 | `bcc_frequency > 0` | `2000 + BCC count` | `verified_corpus` |
| RIME-LMDG 补充 | BCC 为 0，万象权重大于 0 | 按字长桶计算百分位，映射到 1000–1999 | `provisional_external_ranking` |
| 结构保底 | 两种语料都缺失，静态容量模型有 `utility_score` | 按字长桶计算百分位，映射到 1–999 | `provisional_non_frequency_tiebreak` |
| 待补语料 | 以上三项都没有 | 0 | `no_quantified_ranking_evidence` |

三条边界是强制的：BCC 始终高于万象补充，万象补充始终高于结构保底；结构保底不是
词频，只用于打破“所有无语料条目同权”的长尾坍缩。所有补充层都保留原始字段、来源、
百分位、临时状态和 `requires_independent_corpus` 标记，未来取得新的独立语料后可以逐项
替换，不需要反写 BCC。

`utility_score` 来自静态容量模型已存在的动态可恢复性、组件复用和构式价值等信号。
它回答“这个部件对生成系统是否有用”，不回答“它在自然语料中出现了多少次”。因此，
它只在 BCC 和 RIME-LMDG 都没有证据时参与同层排序。

## 构建与审计

策略文件为 `internal_data/candidate_ranking_evidence_policy.json`。全量两级运行词库构建会
自动执行排序证据门禁，并把每个入选条目的证据列写入 `selection.tsv`。也可单独重跑：

```powershell
python tools/evaluate_candidate_ranking_evidence.py
```

报告写入 `.generated/candidate_ranking_evidence/report.json`。门禁要求：

- 每个运行候选都能关联到来源记录；
- 导出表包含 BCC、万象、两种百分位和临时状态；
- 不相加 BCC 与万象原值；
- `structural < RIME-LMDG < BCC` 的权重区间严格分离。

2026-07-28 全量重建结果：

| 范围 | BCC 直接证据 | RIME-LMDG 补充 | 结构保底 |
|---|---:|---:|---:|
| 来源全集 | 433,978 | 1,815,902 | 192,028 |
| 一级运行候选 | 374,123 | 585,244 | 184,912 |
| 二级运行候选 | 5,034 | 1,862 | 982 |

运行候选共1,152,157个，全部分类，来源缺失为0。实测结构保底最高权重999、
RIME-LMDG 最高 1999、BCC 最低 2006，区间隔离门禁通过。

候选池动态覆盖解决“能不能生成”，本机制解决“生成后怎样稳定排序”。两者都完成后，
无 BCC 长尾不再因为缺少同量纲频次而整体并列，也不需要通过虚构最低频次来掩盖缺口。
