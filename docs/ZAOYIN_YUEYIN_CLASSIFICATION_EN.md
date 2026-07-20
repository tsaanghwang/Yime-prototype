<!-- markdownlint-disable MD013 -->
# Zaoyin and Yueyin: Classification Specification

## Status

This document is the canonical definition of the two project-specific classes called `zaoyin` and `yueyin`. It governs English prose, Python names, Yinyuan ID data, and AI interpretation of the code.

The ordinary English words *noise*, *musical sound*, *unpitched*, and *pitched* are not canonical translations. They may appear only when explaining legacy class names or fields. They must not redefine the two classes.

## Canonical Names

| Context | First class | Second class |
|---|---|---|
| Chinese | 噪音类 | 乐音类 |
| English | `zaoyin` | `yueyin` |
| Python/JSON | `zaoyin` / `ZAOYIN` | `yueyin` / `YUEYIN` |
| Yinyuan ID prefix | `N` | `M` |

Use `zaoyin class` and `yueyin class` at first mention in English prose. Use `zaoyin` and `yueyin` thereafter.

## Definitions

**Zaoyin** is the class of pianyin and yinyuan whose contrastive identity is carried by quality, while pitch is zero, indeterminate, unstable, or non-contrastive for that unit.

**Yueyin** is the class of pianyin and yinyuan whose contrastive identity is jointly carried by quality and specified pitch.

The decisive question is not whether a physical fundamental frequency exists. It is whether pitch participates as a specified contrastive property in classifying the unit.

Consequently, a voiced initial may have an actual pitch and still belong to the zaoyin class when that pitch does not distinguish the initial yinyuan. A yueyin unit, by contrast, is classified jointly by its quality portion and its linked, specified pitch target.

## Derived Result and Shared Top-Level Axis

The dichotomy is first derived by analysis:

```text
quality, pitch, and their contrastive roles in a pianyin
  -> contrastive-feature analysis
  -> zaoyin or yueyin
```

Once established, the result becomes a shared top-level category axis:

```text
classification result
  -> Pianyin.category
  -> Yinyuan.category
  -> N/M Yinyuan ID class
  -> encoding validation
```

There is no contradiction between deriving the classes from analysis and using the resulting classes as top-level program types. The first statement explains provenance; the second explains downstream representation.

## Category Axis Versus Structural Axis

Keep the two axes separate:

```text
structural axis: shouyin / ganyin / huyin / main / final positions
category axis:   zaoyin / yueyin
```

In the current Modern Standard Chinese model, zaoyin yinyuan fill the shouyin position and yueyin yinyuan fill the three internal ganyin positions. This is a stable filling relation, not synonymy. Shouyin is not another name for zaoyin, and ganyin is not another name for yueyin.

## Current Engineering Boundary

The production encoder does not classify recorded speech acoustically. It applies an already reviewed classification embodied in the semantic registries:

```text
toned Pinyin
  -> shouyin/ganyin structural analysis
  -> N-class Yinyuan ID for shouyin
  -> three M-class Yinyuan IDs for ganyin
```

`YinyuanCategory` therefore represents a classification result. A compatibility helper that recovers a category from a legacy `pitch` marker is not the theoretical classifier.

## Code Rules

1. New code uses `ZaoyinPianyin`, `YueyinPianyin`, `ZaoyinYinyuan`, `YueyinYinyuan`, and `YinyuanCategory`.
2. `UnpitchedPianyin`, `PitchedPianyin`, `NoiseYinyuan`, and `MusicalYinyuan` are compatibility names or legacy internal bases; do not propagate them into new public APIs or explanations.
3. A category is declared by a canonical object type or a reviewed semantic registry. The mere presence of an arbitrary `pitch` value is not sufficient to classify a unit as yueyin.
4. `Nxx` and `Mxx` are identifiers assigned after classification, not the theoretical basis of classification.
5. `zaoyin/yueyin` name a category shared by the pianyin and yinyuan layers; they do not name syllable-structure portions.

For the Chinese specification, see [噪音类与乐音类：分类说明](ZAOYIN_YUEYIN_CLASSIFICATION.md). For the pianyin/yinyuan/ID boundary, see [Pianyin Analysis and Yinyuan Representation](PIANYIN_ANALYSIS_OVERVIEW.md).
