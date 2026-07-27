from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from yime.input_model import (
    CandidateAssessment,
    CandidateClass,
    DecisionStatus,
    InputModelStore,
    IntegrationPolicy,
    UnencodedCandidateReview,
    build_input_model,
)
from yime.input_model.review_server import ASSETS, create_server


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "internal_data" / "input_candidate_model_policy.json"


def _source_database(path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE accepted_readings (
                text TEXT NOT NULL,
                source TEXT NOT NULL,
                source_category TEXT NOT NULL
            );
            CREATE TABLE canonical_readings (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                marked_pinyin TEXT NOT NULL,
                numeric_pinyin TEXT NOT NULL,
                reading_rank INTEGER NOT NULL,
                is_primary INTEGER NOT NULL,
                bcc_frequency INTEGER NOT NULL,
                pinyin_sources TEXT NOT NULL,
                reading_source_categories TEXT NOT NULL
            );
            CREATE TABLE bcc_frequency (
                text TEXT PRIMARY KEY,
                frequency INTEGER NOT NULL
            );
            CREATE TABLE bcc_frequency_evidence (
                text TEXT NOT NULL,
                source_category TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                frequency INTEGER NOT NULL,
                source_file TEXT NOT NULL
            );
            CREATE TABLE rejections (
                text TEXT NOT NULL,
                reason TEXT NOT NULL
            );
            INSERT INTO accepted_readings VALUES
                ('已有编码', 'pypinyin', 'phrase');
            INSERT INTO canonical_readings VALUES
                (1, '已有编码', 'yǐ yǒu biān mǎ', 'yi3 you3 bian1 ma3',
                 1, 1, 2000, 'pypinyin', 'pypinyin:phrase');
            INSERT INTO bcc_frequency VALUES
                ('高频未编码', 12000),
                ('低频未编码', 8),
                ('已有编码', 2000);
            INSERT INTO bcc_frequency_evidence VALUES
                ('高频未编码', 'modern_chinese', 'word', 12000, 'modern.txt'),
                ('高频未编码', 'literature', 'word', 300, 'literature.txt'),
                ('低频未编码', 'multi_domain', 'word', 8, 'multi.txt'),
                ('已有编码', 'news', 'word', 2000, 'news.txt');
            INSERT INTO rejections VALUES
                ('低频未编码', '没有可安全进入解码的读音');
            """
        )
    return path


@pytest.fixture
def review(tmp_path: Path) -> UnencodedCandidateReview:
    source = _source_database(tmp_path / "source.sqlite3")
    model = tmp_path / "input_model.sqlite3"
    build_input_model(
        source_database=source,
        output_database=model,
        policy_path=POLICY,
    )
    return UnencodedCandidateReview(
        input_model_database=model,
        source_database=source,
    )


def _add_bidirectional_analysis_candidates(
    review: UnencodedCandidateReview,
) -> None:
    with sqlite3.connect(review.source_database) as connection:
        connection.executemany(
            """
            INSERT INTO canonical_readings VALUES
                (?, ?, ?, ?, 1, 1, ?, 'review-test', 'review-test:component')
            """,
            [
                (2, "高速", "gāo sù", "gao1 su4", 9000),
                (3, "公路", "gōng lù", "gong1 lu4", 8000),
                (4, "旧", "jiù", "jiu4", 7000),
                (5, "铁路", "tiě lù", "tie3 lu4", 6000),
                (6, "新", "xīn", "xin1", 5000),
                (7, "城区", "chéng qū", "cheng2 qu1", 4000),
                (8, "以", "yǐ", "yi3", 3900),
                (9, "为", "wéi", "wei2", 3800),
                (10, "人", "rén", "ren2", 3700),
                (11, "本", "běn", "ben3", 3600),
                (12, "人工", "rén gōng", "ren2 gong1", 3500),
                (13, "智能", "zhì néng", "zhi4 neng2", 3400),
                (14, "基础", "jī chǔ", "ji1 chu3", 3300),
                (15, "甲", "jiǎ", "jia3", 3200),
                (16, "乙", "yǐ", "yi3", 3100),
                (17, "在", "zài", "zai4", 3000),
                (18, "水", "shuǐ", "shui3", 2900),
                (19, "中", "zhōng", "zhong1", 2800),
                (20, "游泳", "yóu yǒng", "you2 yong3", 2700),
                (21, "家", "jiā", "jia1", 2600),
                (22, "上", "shàng", "shang4", 2500),
                (23, "下", "xià", "xia4", 2400),
                (24, "康藏", "kāng zàng", "kang1 zang4", 2300),
                (25, "科技", "kē jì", "ke1 ji4", 2200),
                (26, "张", "zhāng", "zhang1", 2100),
                (27, "元", "yuán", "yuan2", 2000),
                (28, "一", "yī", "yi1", 1900),
                (29, "千", "qiān", "qian1", 1800),
            ],
        )
        connection.executemany(
            "INSERT INTO bcc_frequency VALUES (?, ?)",
            [
                ("高速公路", 5000),
                ("旧铁路", 3000),
                ("神秘公路", 2000),
                ("新城区", 1800),
                ("新未知", 900),
                ("以人为本", 4800),
                ("以人工智能为基础", 4600),
                ("以甲乙为本", 4400),
                ("以为", 4200),
                ("在水中游泳", 4000),
                ("在家中", 3800),
                ("在中国发展", 3600),
                ("康藏公路", 3400),
                ("以科技为基础", 3200),
                ("张元", 3000),
                ("一千元", 2800),
                ("固定元", 2600),
                ("乱码元", 2400),
                ("未知元", 2200),
            ],
        )
    build_input_model(
        source_database=review.source_database,
        output_database=review.input_model_database,
        policy_path=POLICY,
    )


def test_queue_only_contains_strings_without_gated_readings(
    review: UnencodedCandidateReview,
) -> None:
    page = review.queue(minimum_frequency=0)
    assert [item.text for item in page.items] == ["高频未编码", "低频未编码"]
    assert page.items[0].bcc_categories == ("modern_chinese", "literature")
    assert page.items[1].bcc_categories == ("multi_domain",)
    assert review.summary()["unencoded_total"] == 2
    with pytest.raises(KeyError):
        review.detail("已有编码")


def test_queue_groups_and_filters_unencoded_candidates_by_exact_text_length(
    review: UnencodedCandidateReview,
) -> None:
    with sqlite3.connect(review.source_database) as connection:
        connection.executemany(
            "INSERT INTO bcc_frequency VALUES (?, ?)",
            [("字", 100), ("双字", 90), ("三个字", 80)],
        )
    build_input_model(
        source_database=review.source_database,
        output_database=review.input_model_database,
        policy_path=POLICY,
    )

    groups = {
        item["text_length"]: item for item in review.summary()["length_groups"]
    }
    assert groups[1]["label"] == "1字"
    assert groups[1]["count"] == 1
    assert groups[2]["status_counts"]["proposed"] == 1
    assert groups[3]["count"] == 1

    page = review.queue(text_length=2, minimum_frequency=0)
    assert [item.text for item in page.items] == ["双字"]
    assert page.items[0].text_length == 2
    assert page.items[0].text_length_label == "2字"
    assert review.detail("双字")["text_length_label"] == "2字"

    with pytest.raises(ValueError, match="positive integer"):
        review.queue(text_length=0)


def test_source_unencoded_pending_strings_are_deferred_and_skip_automatic_screening(
    review: UnencodedCandidateReview,
) -> None:
    with sqlite3.connect(review.source_database) as connection:
        connection.execute(
            """
            CREATE TABLE unencoded_pending_strings (
                text TEXT PRIMARY KEY,
                text_length INTEGER NOT NULL,
                matched_codepoints TEXT NOT NULL,
                rule_ids TEXT NOT NULL,
                reason TEXT NOT NULL,
                bcc_frequency INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO unencoded_pending_strings
            VALUES (
                '高频未编码', 5, 'U+FA11',
                'SRC-DEFER-MISSING-TRUSTED-MANDARIN-READING',
                '测试暂无可信普通话读音来源规则', 12000
            )
            """
        )
    build_input_model(
        source_database=review.source_database,
        output_database=review.input_model_database,
        policy_path=POLICY,
    )

    assert [item.text for item in review.queue(status="proposed").items] == [
        "低频未编码"
    ]
    deferred = review.queue(status="deferred")
    assert [item.text for item in deferred.items] == ["高频未编码"]
    assert deferred.items[0].candidate_class == "unknown"
    assert deferred.items[0].integration_policy == "needs_review"
    assert review.detail("高频未编码")["blocking_reason"] == (
        "missing_trusted_mandarin_reading"
    )
    assert review.automatic_screening()["pending_total"] == 1


def test_two_character_unencoded_strings_use_gated_single_character_components(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)

    summary = review.summary()
    assert summary["two_character_dynamic_reachability"] == 2
    proposed = {
        item.text
        for item in review.queue(
            status="proposed", text_length=2, minimum_frequency=0
        ).items
    }
    assert {"以为", "张元"} <= proposed
    assert not review.queue(
        status="approved", text_length=2, minimum_frequency=0
    ).items
    reachable = review.detail("张元")
    assert reachable["decision_status"] == "proposed"
    assert reachable["candidate_class"] == "unknown"
    assert reachable["integration_policy"] == "needs_review"
    assert reachable["dynamic_reachable"] is True
    assert reachable["dynamic_reachability_rule"] == (
        "two_character_dynamic_reachability"
    )
    assert reachable["blocking_reason"] == "missing_gated_source_reading"
    assert reachable["evidence"]["components"] == ("张", "元")
    assert reachable["evidence"]["changes_candidate_disposition"] is False

    overridden = review.decide(
        text="张元",
        action="defer",
        candidate_class="context_dependent",
        integration_policy=None,
        rationale="人工确认需要作为特殊两字例外继续审查。",
        assessor="human:test",
    )
    assert overridden["decision_status"] == "deferred"
    assert overridden["integration_policy"] == "needs_review"


def test_reverse_affix_analysis_uses_longest_suffix_and_gated_parts(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)
    result = review.analyze_affix_family(
        direction="suffix",
        root_anchor="路",
        refinements=["公路", "铁路"],
        intended_class="place_name",
    )

    assert result["total_matches"] == 4
    assert result["both_parts_gated"] == 3
    assert result["anchor_counts"] == [
        {"anchor": "路", "matched": 4, "both_parts_gated": 0},
        {"anchor": "公路", "matched": 3, "both_parts_gated": 2},
        {"anchor": "铁路", "matched": 1, "both_parts_gated": 1},
    ]
    highway = result["items"][0]
    assert highway["text"] == "高速公路"
    assert highway["left_part"] == "高速"
    assert highway["right_part"] == "公路"
    assert highway["both_parts_gated"] is True
    assert highway["left_reading"]["numeric"] == "gao1 su4"
    assert highway["right_reading"]["numeric"] == "gong1 lu4"
    assert highway["suggestion"] == "proper_name_rule_candidate"
    assert highway["registration_policy"] == "model_only"
    assert highway["eventual_policy_after_replay"] == "dynamic_recoverable"

    unknown = next(item for item in result["items"] if item["text"] == "神秘公路")
    assert unknown["left_part"] == "神秘"
    assert unknown["left_has_gated_reading"] is False
    assert unknown["suggestion"] == "reading_evidence_required"


def test_forward_affix_analysis_mirrors_component_check(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)
    result = review.analyze_affix_family(
        direction="prefix",
        root_anchor="新",
        refinements=[],
        intended_class="productive_phrase",
    )

    assert result["total_matches"] == 2
    assert result["both_parts_gated"] == 1
    city = result["items"][0]
    assert city["text"] == "新城区"
    assert city["left_part"] == "新"
    assert city["right_part"] == "城区"
    assert city["both_parts_gated"] is True
    assert city["suggestion"] == "dynamic_composition_candidate"
    assert city["whole_has_gated_reading"] is False

    with pytest.raises(ValueError, match="must start with"):
        review.analyze_affix_family(
            direction="prefix",
            root_anchor="新",
            refinements=["老城"],
        )


def test_tail_semantic_classification_is_saved_then_programmatically_applied(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)
    with sqlite3.connect(review.input_model_database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "yime-input-candidate-model-v11"
        assert connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'tail_classifications'
            """
        ).fetchone() == (1,)
    analysis = review.analyze_affix_family(
        direction="suffix",
        root_anchor="元",
        refinements=[],
        minimum_frequency=0,
    )
    by_text = {item["text"]: item for item in analysis["items"]}
    assert by_text["一千元"]["both_parts_gated"] is False

    saved = review.save_tail_classifications(
        direction="suffix",
        root_anchor="元",
        classifications=[
            {
                "text": "张元",
                "matched_anchor": "元",
                "semantic_class": "person_name",
            },
            {
                "text": "一千元",
                "matched_anchor": "元",
                "semantic_class": "currency_measurement",
            },
            {
                "text": "固定元",
                "matched_anchor": "元",
                "semantic_class": "fixed_lexical_item",
            },
            {
                "text": "乱码元",
                "matched_anchor": "元",
                "semantic_class": "noise",
            },
            {
                "text": "未知元",
                "matched_anchor": "元",
                "semantic_class": "product_name",
            },
        ],
        assessor="human:test-classifier",
    )
    assert saved["saved_count"] == 5
    builtin = review.detail("张元")
    assert builtin["decision_status"] == "proposed"
    assert builtin["rationale"] == "bcc_without_gated_reading"
    assert builtin["blocking_reason"] == "missing_gated_source_reading"
    assert builtin["dynamic_reachable"] is True
    assert builtin["dynamic_reachability_rule"] == (
        "two_character_dynamic_reachability"
    )
    assert builtin["evidence"]["components"] == ("张", "元")
    rerun = review.analyze_affix_family(
        direction="suffix",
        root_anchor="元",
        refinements=[],
        minimum_frequency=0,
    )
    rerun_by_text = {item["text"]: item for item in rerun["items"]}
    assert rerun_by_text["张元"]["tail_classification"]["semantic_class"] == (
        "person_name"
    )

    applied = review.apply_tail_classifications(
        direction="suffix",
        root_anchor="元",
        assessor="program:test-tail-disposition",
    )
    assert applied["applied_count"] == 5
    assert applied["disposition_counts"] == {
        "exclude_from_static_encoding": 2,
        "keep_for_encoding_review": 1,
        "reject": 1,
        "reading_or_structure_review": 1,
    }

    person = review.detail("张元")
    assert person["candidate_class"] == "person_name"
    assert person["integration_policy"] == "model_only"
    assert person["decision_status"] == "approved"
    assert person["evidence"]["tail_classification"]["components_covered"] is True

    currency = review.detail("一千元")
    assert currency["candidate_class"] == "productive_phrase"
    assert currency["decision_status"] == "approved"
    assert currency["evidence"]["tail_classification"]["components_covered"] is True

    fixed = review.detail("固定元")
    assert fixed["integration_policy"] == "static_keep"
    assert fixed["decision_status"] == "deferred"
    assert review.detail("乱码元")["decision_status"] == "rejected"
    product = review.detail("未知元")
    assert product["candidate_class"] == "domain_term"
    assert product["integration_policy"] == "needs_review"
    assert product["decision_status"] == "deferred"


def test_discovered_affix_family_only_registers_two_gated_parts(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)
    family = review.register_rule_family(
        family_id="road-suffix",
        title="道路名称后缀",
        pattern_description="已注音前部 + 公路/铁路",
        applicability_notes="作为地名规则候选，仍需真实回放验证。",
        representative="高速公路",
        positive_examples=["旧铁路"],
        negative_examples=["神秘公路"],
        candidate_class="place_name",
        rationale="正例拆分两侧都有来源门禁合格读音。",
        assessor="human:test",
        discovery_model={
            "direction": "suffix",
            "root_anchor": "路",
            "refinements": ["公路", "铁路"],
        },
    )

    assert family["evidence"]["discovery_model"] == {
        "kind": "affix_hierarchy",
        "direction": "suffix",
        "root_anchor": "路",
        "refinements": ["公路", "铁路"],
    }
    assert review.detail("高速公路")["candidate_class"] == "place_name"
    with pytest.raises(ValueError, match="both split parts"):
        review.register_rule_family(
            family_id="unsafe-road-suffix",
            title="不安全道路后缀",
            pattern_description="缺注音前部 + 公路",
            applicability_notes="",
            representative="神秘公路",
            positive_examples=[],
            negative_examples=["高速公路"],
            candidate_class="place_name",
            rationale="应被两侧注音门禁阻止。",
            assessor="human:test",
            discovery_model={
                "direction": "suffix",
                "root_anchor": "路",
                "refinements": ["公路"],
            },
        )


def test_frame_template_recurses_two_character_slots_when_both_chars_are_gated(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)
    result = review.analyze_construction_family(
        template="以{依据}为{目标}",
        intended_class="productive_phrase",
    )

    assert result["total_matches"] == 4
    assert result["composition_covered"] == 4
    assert result["short_form_exceptions"] == 0
    fixed = next(item for item in result["items"] if item["text"] == "以人为本")
    assert fixed["suggestion"] == "frame_composition_candidate"
    recursive = next(
        item for item in result["items"] if item["text"] == "以人工智能为基础"
    )
    basis_slot = next(
        item for item in recursive["components"] if item.get("name") == "依据"
    )
    assert basis_slot["coverage_status"] == "composition_covered"
    assert basis_slot["parts"] == ("人工", "智能")
    short = next(item for item in result["items"] if item["text"] == "以甲乙为本")
    assert short["suggestion"] == "frame_composition_candidate"
    short_slot = next(
        item for item in short["components"] if item.get("name") == "依据"
    )
    assert short_slot["coverage_status"] == "composition_covered"
    assert short_slot["parts"] == ("甲", "乙")
    assert all(item["text"] != "以为" for item in result["items"])


def test_frame_template_supports_choices_and_optional_trailing_slot(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)
    result = review.analyze_construction_family(
        template="在{处所}(中|上|下){后续?}",
        intended_class="productive_phrase",
    )

    assert result["total_matches"] == 2
    assert {item["text"] for item in result["items"]} == {
        "在水中游泳",
        "在家中",
    }
    home = next(item for item in result["items"] if item["text"] == "在家中")
    trailing = next(
        item for item in home["components"] if item.get("name") == "后续"
    )
    assert trailing["coverage_status"] == "empty_optional"
    with pytest.raises(ValueError, match="requires at least one slot"):
        review.analyze_construction_family(template="从头到尾")


def test_frame_discovery_model_is_rechecked_during_registration(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)
    family = review.register_rule_family(
        family_id="yi-x-wei-y",
        title="以 X 为 Y",
        pattern_description="以{依据}为{目标}",
        applicability_notes="槽位递归覆盖后仍需上下文回放。",
        representative="以人为本",
        positive_examples=["以人工智能为基础"],
        negative_examples=["以甲乙为本"],
        candidate_class="productive_phrase",
        rationale="两个正例都有唯一递归注音覆盖。",
        assessor="human:test",
        discovery_model={
            "kind": "frame_template",
            "template": "以{依据}为{目标}",
        },
    )

    assert family["evidence"]["discovery_model"]["kind"] == "frame_template"
    assert family["evidence"]["discovery_model"]["template"] == "以{依据}为{目标}"
    two_character_family = review.register_rule_family(
        family_id="two-char-frame",
        title="两字槽位框式",
        pattern_description="以{依据}为{目标}",
        applicability_notes="两字槽位的两个单字均已有合格注音。",
        representative="以甲乙为本",
        positive_examples=[],
        negative_examples=["以为"],
        candidate_class="productive_phrase",
        rationale="两字槽位按内建动态组合规则覆盖。",
        assessor="human:test",
        discovery_model={
            "kind": "frame_template",
            "template": "以{依据}为{目标}",
        },
    )
    assert two_character_family["evidence"]["discovery_model"]["kind"] == (
        "frame_template"
    )


def _register_road_rule(
    review: UnencodedCandidateReview,
    *,
    family_id: str,
    candidate_class: str,
) -> None:
    review.register_rule_family(
        family_id=family_id,
        title=f"道路后缀 {family_id}",
        pattern_description="已注音前部 + 公路/铁路",
        applicability_notes="自动筛查测试规则。",
        representative="高速公路",
        positive_examples=["旧铁路"],
        negative_examples=["神秘公路"],
        candidate_class=candidate_class,
        rationale="正例两侧均有来源门禁合格注音。",
        assessor="human:test",
        discovery_model={
            "kind": "affix_hierarchy",
            "direction": "suffix",
            "root_anchor": "路",
            "refinements": ["公路", "铁路"],
        },
    )


def test_automatic_screening_applies_only_unique_conflict_free_rule_matches(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)
    _register_road_rule(
        review,
        family_id="automatic-road",
        candidate_class="place_name",
    )

    preview = review.automatic_screening()
    covered = next(item for item in preview["items"] if item["text"] == "康藏公路")
    assert covered["category"] == "auto_covered"
    assert covered["selected_family_id"] == "automatic-road"
    excluded = next(item for item in preview["items"] if item["text"] == "神秘公路")
    assert excluded["category"] == "negative_example_excluded"

    applied = review.apply_automatic_screening(
        assessor="human:auto-test",
        maximum_items=10,
    )
    assert "康藏公路" in applied["applied_texts"]
    detail = review.detail("康藏公路")
    assert detail["decision_status"] == "approved"
    assert detail["integration_policy"] == "model_only"
    assert detail["evidence"]["admission_stage"] == (
        "rule_auto_screened_unvalidated"
    )
    assert detail["evidence"]["rule_family_id"] == "automatic-road"
    assert review.detail("神秘公路")["decision_status"] == "proposed"


def test_automatic_screening_covers_two_character_slots_and_keeps_conflicts(
    review: UnencodedCandidateReview,
) -> None:
    _add_bidirectional_analysis_candidates(review)
    review.register_rule_family(
        family_id="automatic-frame",
        title="以 X 为 Y 自动筛查",
        pattern_description="以{依据}为{目标}",
        applicability_notes="自动筛查测试规则。",
        representative="以人为本",
        positive_examples=["以人工智能为基础"],
        negative_examples=["以为"],
        candidate_class="productive_phrase",
        rationale="正例具有唯一递归覆盖。",
        assessor="human:test",
        discovery_model={
            "kind": "frame_template",
            "template": "以{依据}为{目标}",
        },
    )
    short_preview = review.automatic_screening()
    short = next(
        item for item in short_preview["items"] if item["text"] == "以甲乙为本"
    )
    assert short["category"] == "auto_covered"
    assert short["selected_family_id"] == "automatic-frame"
    technology = next(
        item for item in short_preview["items"] if item["text"] == "以科技为基础"
    )
    assert technology["category"] == "auto_covered"

    _register_road_rule(
        review,
        family_id="road-as-place",
        candidate_class="place_name",
    )
    _register_road_rule(
        review,
        family_id="road-as-domain",
        candidate_class="domain_term",
    )
    conflict_preview = review.automatic_screening()
    conflict = next(
        item for item in conflict_preview["items"] if item["text"] == "康藏公路"
    )
    assert conflict["category"] == "rule_conflict"
    before = review.detail("康藏公路")["decision_status"]
    review.apply_automatic_screening(
        assessor="human:auto-test",
        maximum_items=100,
    )
    assert before == "proposed"
    assert review.detail("康藏公路")["decision_status"] == "proposed"


def test_approval_is_audited_but_remains_blocked_from_runtime(
    review: UnencodedCandidateReview,
) -> None:
    detail = review.decide(
        text="高频未编码",
        action="approve",
        candidate_class="fixed_expression",
        integration_policy="static_keep",
        rationale="边界明确，批准进入读音来源核验队列。",
        assessor="human:test",
    )

    assert detail["decision_status"] == "approved"
    assert detail["runtime_eligible"] is False
    assert detail["evidence"]["admission_stage"] == (
        "lexical_approved_pending_source_reading"
    )
    assert detail["source"]["readings"] == []
    assert detail["audit_events"][0]["payload"]["decision_status"] == "approved"
    assert review.summary()["status_counts"]["approved"] == 1
    with InputModelStore(review.input_model_database) as store:
        assert store.approved_component("高频未编码") is None


def test_reject_and_defer_force_safe_policies(
    review: UnencodedCandidateReview,
) -> None:
    rejected = review.decide(
        text="低频未编码",
        action="reject",
        candidate_class="noise",
        integration_policy="static_keep",
        rationale="低频切分噪声。",
        assessor="human:test",
    )
    assert rejected["integration_policy"] == "reject"
    assert rejected["decision_status"] == "rejected"

    deferred = review.decide(
        text="高频未编码",
        action="defer",
        candidate_class="context_dependent",
        integration_policy="static_keep",
        rationale="等待真实上下文。",
        assessor="human:test",
    )
    assert deferred["integration_policy"] == "needs_review"
    assert deferred["decision_status"] == "deferred"


def test_review_standard_is_preserved_in_audit_evidence(
    review: UnencodedCandidateReview,
) -> None:
    detail = review.decide(
        text="高频未编码",
        action="defer",
        candidate_class="context_dependent",
        integration_policy=None,
        rationale="按本轮双上下文规则，当前证据不足。",
        assessor="human:test",
        review_standard="reviewer",
        custom_criteria={
            "name": "双上下文核验",
            "goal": "discovery",
            "rules": "至少出现于两个相互独立的上下文。",
        },
    )

    assert detail["evidence"]["review_standard"] == "reviewer"
    assert detail["evidence"]["custom_criteria"] == {
        "name": "双上下文核验",
        "goal": "discovery",
        "rules": "至少出现于两个相互独立的上下文。",
    }
    assert detail["audit_events"][0]["payload"]["evidence"]["review_standard"] == (
        "reviewer"
    )


def test_rule_family_registration_uses_examples_and_counterexamples(
    review: UnencodedCandidateReview,
) -> None:
    family = review.register_rule_family(
        family_id="modifier-head",
        title="修饰语加中心语",
        pattern_description="可替换修饰语 + 已登记中心语",
        applicability_notes="只登记结构假设；需回放验证边界与歧义。",
        representative="高频未编码",
        positive_examples=[],
        negative_examples=["低频未编码"],
        candidate_class="productive_phrase",
        rationale="正例表现为能产组合，反例用于约束误吞。",
        assessor="human:test",
    )

    assert family["status"] == "registered"
    assert family["runtime_eligible"] is False
    assert family["validation_state"] == "unvalidated"
    assert family["blocking_reason"] == (
        "requires_replay_and_attested_component_readings"
    )
    assert [(item["text"], item["example_role"]) for item in family["examples"]] == [
        ("高频未编码", "representative"),
        ("低频未编码", "negative"),
    ]
    assert review.rule_families()[0]["family_id"] == "modifier-head"
    assert review.summary()["rule_family_count"] == 1

    detail = review.detail("高频未编码")
    assert detail["decision_status"] == "approved"
    assert detail["integration_policy"] == "model_only"
    assert detail["evidence"]["rule_family_id"] == "modifier-head"
    assert detail["runtime_eligible"] is False
    with InputModelStore(review.input_model_database) as store:
        assert store.approved_component("高频未编码") is None


def test_rule_family_registration_fails_closed(review: UnencodedCandidateReview) -> None:
    values = {
        "family_id": "productive-family",
        "title": "能产构式",
        "pattern_description": "A + B",
        "applicability_notes": "",
        "representative": "高频未编码",
        "positive_examples": [],
        "negative_examples": ["低频未编码"],
        "candidate_class": "productive_phrase",
        "rationale": "用于规则族审查。",
        "assessor": "human:test",
    }
    with pytest.raises(ValueError, match="negative example"):
        review.register_rule_family(**{**values, "negative_examples": []})
    with pytest.raises(ValueError, match="overlap"):
        review.register_rule_family(
            **{**values, "negative_examples": ["高频未编码"]}
        )
    with pytest.raises(ValueError, match="candidate universe"):
        review.register_rule_family(
            **{**values, "negative_examples": ["不在语料库"]}
        )
    with pytest.raises(ValueError, match="rule family class"):
        review.register_rule_family(
            **{**values, "candidate_class": "fixed_expression"}
        )


def test_updating_rule_family_releases_removed_positive_example(
    review: UnencodedCandidateReview,
) -> None:
    values = {
        "family_id": "revisable-family",
        "title": "可修订构式",
        "pattern_description": "结构假设",
        "applicability_notes": "",
        "candidate_class": "semi_fixed_construction",
        "rationale": "先登记后修订。",
        "assessor": "human:test",
    }
    review.register_rule_family(
        **values,
        representative="高频未编码",
        positive_examples=["低频未编码"],
        negative_examples=["已有编码"],
    )

    # A counterexample is mandatory, so use the other item while swapping roles.
    review.register_rule_family(
        **values,
        representative="低频未编码",
        positive_examples=[],
        negative_examples=["高频未编码"],
    )
    assert review.detail("低频未编码")["evidence"]["rule_family_id"] == (
        "revisable-family"
    )
    assert review.detail("高频未编码")["decision_status"] == "proposed"


def test_invalid_decisions_fail_closed(review: UnencodedCandidateReview) -> None:
    with pytest.raises(ValueError, match="rationale"):
        review.decide(
            text="高频未编码",
            action="approve",
            candidate_class="lexical_candidate",
            integration_policy="static_keep",
            rationale="",
            assessor="human:test",
        )
    with pytest.raises(ValueError, match="static_keep or model_only"):
        review.decide(
            text="高频未编码",
            action="approve",
            candidate_class="lexical_candidate",
            integration_policy="dynamic_component",
            rationale="来源不足时不能直接成为动态组件。",
            assessor="human:test",
        )
    with InputModelStore(review.input_model_database) as store:
        with pytest.raises(ValueError, match="lexical-only"):
            store.put(
                CandidateAssessment(
                    text="高频未编码",
                    candidate_class=CandidateClass.LEXICAL_CANDIDATE,
                    integration_policy=IntegrationPolicy.STATIC_KEEP,
                    status=DecisionStatus.APPROVED,
                    rationale="不能绕过来源门禁。",
                    assessor="test:unsafe",
                )
            )
    with pytest.raises(ValueError, match="custom criteria"):
        review.decide(
            text="高频未编码",
            action="defer",
            candidate_class="context_dependent",
            integration_policy=None,
            rationale="自定标准不完整。",
            assessor="human:test",
            review_standard="reviewer",
        )


def test_local_server_and_packaged_assets_are_restricted(
    review: UnencodedCandidateReview,
) -> None:
    assert all(path.is_file() for path in ASSETS.values())
    with pytest.raises(ValueError, match="local machine"):
        create_server(
            host="0.0.0.0",
            port=0,
            input_model_database=review.input_model_database,
            source_database=review.source_database,
        )
    server = create_server(
        host="127.0.0.1",
        port=0,
        input_model_database=review.input_model_database,
        source_database=review.source_database,
    )
    server.server_close()
    assert ASSETS["/app.js"] == ASSETS["/assets/app.js"]
    assert ASSETS["/styles.css"] == ASSETS["/assets/styles.css"]


def test_direct_file_page_may_connect_to_local_api(
    review: UnencodedCandidateReview,
) -> None:
    server = create_server(
        host="127.0.0.1",
        port=0,
        input_model_database=review.input_model_database,
        source_database=review.source_database,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(
            Request(f"{base_url}/api/summary", headers={"Origin": "null"}),
            timeout=5,
        ) as response:
            assert response.status == 200
            assert response.headers["Access-Control-Allow-Origin"] == "null"
            payload = json.load(response)
            assert payload["length_groups"][0]["label"].endswith("字")

        with urlopen(f"{base_url}/api/config", timeout=5) as response:
            payload = json.load(response)
            assert "currency_measurement" in payload["tail_semantic_classes"]

        with urlopen(
            f"{base_url}/api/queue?text_length=5&minimum_frequency=0",
            timeout=5,
        ) as response:
            payload = json.load(response)
            assert payload["items"]
            assert all(item["text_length"] == 5 for item in payload["items"])
            assert all(item["text_length_label"] == "5字" for item in payload["items"])

        preflight = Request(
            f"{base_url}/api/decision",
            method="OPTIONS",
            headers={
                "Origin": "null",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "content-type,x-yime-review"
                ),
            },
        )
        with urlopen(preflight, timeout=5) as response:
            assert response.status == 204
            assert response.headers["Access-Control-Allow-Origin"] == "null"
            assert "POST" in response.headers["Access-Control-Allow-Methods"]

        with urlopen(
            f"{base_url}/api/affix-analysis?direction=suffix&root_anchor=%E7%A0%81",
            timeout=5,
        ) as response:
            payload = json.load(response)
            assert payload["direction"] == "suffix"
            assert payload["runtime_writes"] is False

        construction_query = urlencode({"template": "以{依据}为{目标}"})
        with urlopen(
            f"{base_url}/api/construction-analysis?{construction_query}",
            timeout=5,
        ) as response:
            payload = json.load(response)
            assert payload["kind"] == "frame_template"
            assert payload["runtime_writes"] is False

        with urlopen(f"{base_url}/api/automatic-screening", timeout=5) as response:
            payload = json.load(response)
            assert payload["registered_rule_count"] == 0
            assert payload["runtime_writes"] is False

        apply_request = Request(
            f"{base_url}/api/automatic-screening/apply",
            method="POST",
            data=json.dumps(
                {
                    "assessor": "human:http-auto-test",
                    "maximum_items": 10,
                }
            ).encode("utf-8"),
            headers={
                "Origin": "null",
                "Content-Type": "application/json",
                "X-Yime-Review": "1",
            },
        )
        with urlopen(apply_request, timeout=5) as response:
            payload = json.load(response)
            assert payload["applied_count"] == 0
            assert payload["integration_policy"] == "model_only"

        family_request = Request(
            f"{base_url}/api/rule-family",
            method="POST",
            data=json.dumps(
                {
                    "family_id": "http-family",
                    "title": "HTTP 规则族",
                    "pattern_description": "A + B",
                    "applicability_notes": "接口回归测试",
                    "representative": "高频未编码",
                    "positive_examples": [],
                    "negative_examples": ["低频未编码"],
                    "candidate_class": "productive_phrase",
                    "rationale": "验证规则族登记接口。",
                    "assessor": "human:http-test",
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Origin": "null",
                "Content-Type": "application/json",
                "X-Yime-Review": "1",
            },
        )
        with urlopen(family_request, timeout=5) as response:
            payload = json.load(response)
            assert payload["family_id"] == "http-family"
            assert payload["runtime_eligible"] is False

        with urlopen(f"{base_url}/api/rule-families", timeout=5) as response:
            payload = json.load(response)
            assert payload["items"][0]["family_id"] == "http-family"

        save_classification = Request(
            f"{base_url}/api/tail-classifications",
            method="POST",
            data=json.dumps(
                {
                    "direction": "suffix",
                    "root_anchor": "码",
                    "classifications": [
                        {
                            "text": "低频未编码",
                            "matched_anchor": "码",
                            "semantic_class": "noise",
                        }
                    ],
                    "assessor": "human:http-tail-test",
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Origin": "null",
                "Content-Type": "application/json",
                "X-Yime-Review": "1",
            },
        )
        with urlopen(save_classification, timeout=5) as response:
            payload = json.load(response)
            assert payload["saved_count"] == 1
            assert payload["decisions_written"] is False

        apply_classification = Request(
            f"{base_url}/api/tail-classifications/apply",
            method="POST",
            data=json.dumps(
                {
                    "direction": "suffix",
                    "root_anchor": "码",
                    "assessor": "program:http-tail-test",
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Origin": "null",
                "Content-Type": "application/json",
                "X-Yime-Review": "1",
            },
        )
        with urlopen(apply_classification, timeout=5) as response:
            payload = json.load(response)
            assert payload["disposition_counts"]["reject"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
