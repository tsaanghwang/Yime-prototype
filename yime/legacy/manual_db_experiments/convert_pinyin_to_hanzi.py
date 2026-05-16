"""旧版数据库驱动的音元转拼音/汉字实验脚本。"""

import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple


class YinYuanInputConverter:
    def __init__(self, db_path=None):
        """初始化转换器，完全基于数据库"""
        base_dir = Path(__file__).resolve().parent.parent
        self.db_path = Path(db_path) if db_path else base_dir / "pinyin_hanzi.db"

        if not self.db_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")

        self.db_conn: Optional[sqlite3.Connection] = None
        self._initialize_database_tables()

    def _get_db_connection(self) -> sqlite3.Connection:
        """获取数据库连接(单例模式)"""
        if self.db_conn is None:
            self.db_conn = sqlite3.connect(self.db_path)
            self.db_conn.row_factory = sqlite3.Row
        return self.db_conn

    def _initialize_database_tables(self):
        """确保所有必要的数据库表存在"""
        conn = self._get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS yinyuan_map (
            yinjie TEXT PRIMARY KEY,
            number_tones TEXT,
            tone_marks TEXT,
            zhuyin TEXT
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS pinyin_hanzi (
            pinyin TEXT PRIMARY KEY,
            hanzi TEXT
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS yinjie_mapping (
            symbol TEXT PRIMARY KEY,
            num_tone TEXT,
            mark_tone TEXT,
            zhuyin TEXT
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS universal_map (
            pinyin TEXT PRIMARY KEY,
            hanzi TEXT,
            yinjie TEXT,
            variants TEXT
        )
        """
        )

        conn.commit()

    def _pua_to_pinyin(self, pua_text: str) -> Optional[str]:
        """改进的 PUA 字符转换方法"""
        if not pua_text or not isinstance(pua_text, str):
            return None

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT mark_tone FROM yinjie_mapping WHERE symbol=?", (pua_text,))
            row = cursor.fetchone()
            if row:
                return row[0]

            pinyin_parts = []
            valid_chars = []

            for char in pua_text:
                if 0xE000 <= ord(char) <= 0xF8FF:
                    valid_chars.append(char)

            for i in range(0, len(valid_chars), 4):
                quad = "".join(valid_chars[i:i + 4])
                if len(quad) < 4:
                    continue

                cursor.execute("SELECT mark_tone FROM yinjie_mapping WHERE symbol=?", (quad,))
                quad_row = cursor.fetchone()
                if quad_row:
                    pinyin_parts.append(quad_row[0])

            return "".join(pinyin_parts) if pinyin_parts else None

        except Exception:
            return None

    def convert(self, input_text: str) -> Tuple[Optional[str], List[str]]:
        try:
            pinyin = self._pua_to_pinyin(input_text)

            if not pinyin:
                return None, []

            conn = self._get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT hanzi
                FROM pinyin_hanzi
                WHERE pinyin=?""",
                (pinyin,),
            )
            row = cursor.fetchone()

            if not row:
                base_pinyin = "".join([c for c in pinyin if c.isalpha()])
                if base_pinyin != pinyin:
                    cursor.execute(
                        """
                        SELECT hanzi
                        FROM pinyin_hanzi
                        WHERE pinyin=?""",
                        (base_pinyin,),
                    )
                    row = cursor.fetchone()
                    if row:
                        return pinyin, list(row[0])

            if row:
                return pinyin, list(row[0])

            return pinyin, []

        except Exception:
            return None, []

    def close(self) -> None:
        """关闭内部数据库连接。"""
        if self.db_conn is not None:
            self.db_conn.close()
            self.db_conn = None

    def __del__(self):
        """析构时关闭数据库连接"""
        try:
            self.close()
        except Exception:
            pass