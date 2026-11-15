
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
