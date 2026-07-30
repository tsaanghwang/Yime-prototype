#!/usr/bin/env python3
"""Launch the local mouse-oriented review workbench."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.input_model.review_server import create_server  # noqa: E402


DEFAULT_INPUT_MODEL = (
    ROOT / ".generated" / "input_candidate_model" / "input_model.sqlite3"
)
DEFAULT_SOURCE = (
    ROOT / ".generated" / "lexicon_source_bundle" / "source_lexicon.sqlite3"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="启动未编码候选与规则族审查工作台；只写候选决策覆盖层。",
    )
    parser.add_argument("--input-model", type=Path, default=DEFAULT_INPUT_MODEL)
    parser.add_argument("--source-database", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        server = create_server(
            host=args.host,
            port=args.port,
            input_model_database=args.input_model,
            source_database=args.source_database,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    url = f"http://{args.host}:{server.server_port}/"
    print(f"审查工作台：{url}")
    print("判决只写 input_model.sqlite3；不会写来源库或运行词库。")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n审查工作台已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
