"""Audit the research-only conditional sound-value model and its source chain."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from syllable.analysis.conditional_sound_values import (  # noqa: E402
    DEFAULT_MODEL_PATH,
    audit_conditional_sound_value_model,
)


def _report_markdown(payload: dict[str, object]) -> str:
    verdict = "通过" if payload["passed"] else "未通过"
    issues = payload["issues"]
    issue_lines = "\n".join(f"- {issue}" for issue in issues) if issues else "- 无"
    return f"""# 条件音值结构化来源审计

- 结论：{verdict}
- 模型：`{payload['model_id']}`
- 上游来源层：{payload['source_layer_count']}
- 噪音片音真源：{payload['zaoyin_count']}；现行稳定登记：{payload['zaoyin_registered_count']}；已登记实现值：{payload['zaoyin_realization_count']}
- 乐音音元：{payload['yueyin_count']}；已登记实现值：{payload['yueyin_realization_count']}
- 条件规则：{payload['conditional_rule_count']}
- 运行时启用：`{str(payload['runtime_enabled']).lower()}`

## 问题

{issue_lines}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    result = audit_conditional_sound_value_model(args.model, PROJECT_ROOT)
    payload = result.as_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.output_dir:
        output_dir = args.output_dir.resolve()
        generated_root = (PROJECT_ROOT / ".generated").resolve()
        if generated_root not in output_dir.parents:
            raise SystemExit("--output-dir 必须位于仓库 .generated 目录内")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "summary.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output_dir / "REPORT.md").write_text(
            _report_markdown(payload),
            encoding="utf-8",
        )

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
