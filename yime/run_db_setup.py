"""Compatibility bootstrap for db_manager schema checks.

This script only ensures the legacy-compatible schema layer is present. It does
not rebuild the current source_pinyin.db -> prototype -> runtime mainline.
"""

from pathlib import Path
import sqlite3
import logging
import sys

PROJECT = Path(__file__).parent
# 默认使用与本脚本同目录下的数据库文件
DB = PROJECT / "pinyin_hanzi.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _import_run_schema_migrations():
    try:
        from yime.legacy.pending_removal.db_manager import run_schema_migrations
        return run_schema_migrations
    except Exception as e:
        logger.error("无法导入 pending_removal.db_manager.run_schema_migrations: %s", e)
        sys.exit(1)

def main():
    # 允许通过命令行覆盖 DB 路径： python run_db_setup.py C:\path\to\db
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1]).resolve()
    else:
        db_path = DB.resolve()
    logger.info("使用数据库文件: %s", db_path)

    run_schema_migrations = _import_run_schema_migrations()

    try:
        run_schema_migrations(db_path)
        logger.info("schema/索引 已确保")
    except Exception as e:
        logger.exception("执行 schema 创建/迁移 失败: %s", e)
        sys.exit(2)

    try:
        con = sqlite3.connect(str(db_path))
        ok = con.execute("PRAGMA integrity_check;").fetchone()
        con.close()
        logger.info("PRAGMA integrity_check -> %s", ok[0] if ok else None)
    except Exception as e:
        logger.exception("完整性检查失败: %s", e)
        sys.exit(3)

    logger.info(
        "数据库建立/检查完成。当前主线下一步：导入 prototype tables 后执行 refresh_runtime_yime_codes.py --apply；"
        "旧 schema 维护脚本已隔离到 yime/legacy/pending_removal/；run_db_setup 只是兼容脚本入口。"
    )

if __name__ == "__main__":
    main()
