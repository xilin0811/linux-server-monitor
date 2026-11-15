
import sqlite3
import time
from pathlib import Path

# 取得目前專案的絕對路徑
BASE_DIR = Path(__file__).resolve().parent

# SQLite 資料庫路徑
DB_PATH = BASE_DIR / "data" / "metrics.db"


def init_database():
    """建立 SQLite 資料庫及資料表。"""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=10)

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY,
                collected_at INTEGER NOT NULL,
                cpu_percent REAL NOT NULL,
                memory_percent REAL NOT NULL,
                disk_percent REAL NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_metrics_collected_at
            ON system_metrics (collected_at)
        """)

        conn.commit()

    finally:
        conn.close()


def save_metric(metrics):
    """將一筆系統監控數據寫入資料庫。"""

    collected_at = int(time.time())

    conn = sqlite3.connect(DB_PATH, timeout=10)

    try:
        cursor = conn.execute("""
            INSERT INTO system_metrics (
                collected_at,
                cpu_percent,
                memory_percent,
                disk_percent
            )
            VALUES (?, ?, ?, ?)
        """, (
            collected_at,
            metrics["cpu_percent"],
            metrics["memory_percent"],
            metrics["disk_percent"]
        ))

        conn.commit()
        return cursor.lastrowid

    finally:
        conn.close()

def get_recent_metrics(limit=60):
    """
    讀取最近 limit 筆監控紀錄。
    回傳順序：最舊到最新，方便前端畫折線圖。
    """

    conn = sqlite3.connect(DB_PATH, timeout=10)

    # 將查詢結果轉換為可使用欄位名稱的 Row
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute("""
            SELECT
                id,
                collected_at,
                cpu_percent,
                memory_percent,
                disk_percent
            FROM system_metrics
            ORDER BY collected_at DESC, id DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()

        # SQL 先取得最新的 N 筆，
        # 再反轉成最舊到最新，方便繪製時間軸
        records = [dict(row) for row in reversed(rows)]

        return records

    finally:
        conn.close()


def is_database_healthy():
    """
    檢查 SQLite 是否存在，以及 system_metrics 資料表能否正常查詢。
    回傳 True 或 False。
    """

    conn = None

    try:
        # 避免健康檢查意外建立全新的空資料庫
        if not DB_PATH.is_file():
            return False

        conn = sqlite3.connect(DB_PATH, timeout=5)

        # 確認監控資料表可以讀取
        conn.execute(
            "SELECT id FROM system_metrics LIMIT 1"
        ).fetchone()

        return True

    except (sqlite3.Error, OSError):
        return False

    finally:
        if conn is not None:
            conn.close()


def delete_old_metrics(days=7):
    """
    刪除超過指定天數的監控紀錄。
    預設保留最近 7 天。
    回傳實際刪除的筆數。
    """

    if days < 1:
        raise ValueError("days must be greater than 0")

    # 取得保留期限的時間門檻
    cutoff = int(time.time()) - (days * 24 * 60 * 60)

    conn = sqlite3.connect(DB_PATH, timeout=10)

    try:
        cursor = conn.execute("""
            DELETE FROM system_metrics
            WHERE collected_at < ?
        """, (cutoff,))

        conn.commit()

        return cursor.rowcount

    finally:
        conn.close()
