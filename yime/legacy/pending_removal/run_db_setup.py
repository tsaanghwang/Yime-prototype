"""Legacy-compatible bootstrap for db_manager schema checks.

This script remains in the legacy area because it only ensures the
legacy-compatible schema layer is present. It does not rebuild the current
source_pinyin.db -> prototype -> runtime mainline.
"""

from pathlib import Path
import sqlite3
import logging
import sys

PROJECT = Path(__file__).resolve().parents[2]
DB = PROJECT / "pinyin_hanzi.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    from yime.legacy.pending_removal.db_manager import run_schema_migrations

    args = argv if argv is not None else sys.argv[1:]
    db_path = Path(args[0]).resolve() if args else DB.resolve()
    logger.info("使用数据库文件: %s", db_path)

    try:
        run_schema_migrations(db_path)
        logger.info("schema/索引 已确保")
    except Exception as exc:
        logger.exception("执行 schema 创建/迁移 失败: %s", exc)
        return 2

    try:
        con = sqlite3.connect(str(db_path))
        ok = con.execute("PRAGMA integrity_check;").fetchone()
        con.close()
        logger.info("PRAGMA integrity_check -> %s", ok[0] if ok else None)
    except Exception as exc:
        logger.exception("完整性检查失败: %s", exc)
        return 3

    logger.info(
        "数据库建立/检查完成。当前主线下一步：导入 prototype tables 后执行 refresh_runtime_yime_codes.py --apply；"
        "该脚本只用于 legacy-compatible schema 维护。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
