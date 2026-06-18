-- 原型查询模板
-- 说明：本文件只放“便于找数据记录”的查询，不修改数据。

-- 1. 看看单字词库视图目前有多少行。
SELECT COUNT(*) AS row_count FROM char_lexicon;

-- 2. 看看词语词库视图目前有多少行。
SELECT COUNT(*) AS row_count FROM phrase_lexicon_view;

-- 3. 按数字标调拼音找单字候选。
-- 把 yi4 改成你要查的拼音。
SELECT *
FROM char_lexicon
WHERE pinyin_tone = 'yi4'
ORDER BY sort_weight DESC;

-- 4. 按 yime 四码找候选（见 yinjie_slot_decomposition 查看各槽分解）。
-- 把这里的四码替换成你的一键转码脚本生成的编码。
SELECT *
FROM runtime_candidates
WHERE yime_code = '􀀕􀀩􀀩􀀩'
ORDER BY entry_type, sort_weight DESC, text;

-- 5. 看看哪些汉字已有 pinyin_tone 但还没有 yime_code。
SELECT *
FROM char_lexicon
WHERE pinyin_tone IS NOT NULL
  AND yime_code IS NULL
ORDER BY hanzi, pinyin_tone;

-- 6. 看看哪些词语已有 prototype 词条，但还没有 phrase_pinyin_map 读音行。
SELECT
  pi.id,
  pi.phrase,
  pi.yime_code,
  pi.phrase_frequency,
  pi.phrase_length
FROM phrase_inventory pi
LEFT JOIN phrase_pinyin_map ppm
  ON pi.id = ppm.phrase_id
WHERE ppm.id IS NULL
ORDER BY pi.phrase;

-- 7. 看看哪些单字还没有写入频率（导入后应全部为 NULL 以外）。
SELECT hanzi, char_frequency_abs, frequency_source
FROM char_lexicon
WHERE char_frequency_abs IS NULL
ORDER BY hanzi;

-- 8. 统一看候选，按编码或拼音都可以筛选。
SELECT *
FROM runtime_candidates
WHERE pinyin_tone = 'yi4'
   OR yime_code = '􀀕􀀩􀀩􀀩'
ORDER BY entry_type, sort_weight DESC, text;
