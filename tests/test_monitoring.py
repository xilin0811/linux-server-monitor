
import sqlite3
import time

import pytest

import database
from app import app as flask_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    每個測試都建立獨立的 SQLite 資料庫。
    不使用正式的 data/metrics.db。
    """

    test_db_path = tmp_path / "test_metrics.db"

    # 暫時替換 database.py 使用的 DB_PATH
    monkeypatch.setattr(database, "DB_PATH", test_db_path)

    # 建立測試用資料表
    database.init_database()

    # 啟用 Flask 測試模式
    flask_app.config["TESTING"] = True

    # 回傳 Flask 測試用 Client
    return flask_app.test_client()


def sample_metric(cpu=12.5):
    """產生一筆測試用監控數據。"""

    return {
        "cpu_percent": cpu,
        "memory_percent": 65.0,
        "disk_percent": 40.0
    }


def test_health_success(client):
    """資料庫正常時，Health API 應回傳 HTTP 200。"""

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json["status"] == "healthy"
    assert response.json["database"] == "ok"


def test_health_database_unavailable(client, tmp_path, monkeypatch):
    """資料庫不存在時，Health API 應回傳 HTTP 503。"""

    missing_db = tmp_path / "missing.db"

    monkeypatch.setattr(database, "DB_PATH", missing_db)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json["status"] == "unhealthy"


def test_history_limit(client):
    """History API 應依照 limit 回傳最新資料。"""

    database.save_metric(sample_metric(cpu=10.0))
    database.save_metric(sample_metric(cpu=20.0))

    response = client.get("/api/history?limit=1")

    assert response.status_code == 200
    assert response.json["count"] == 1
    assert len(response.json["metrics"]) == 1

    latest = response.json["metrics"][0]

    assert latest["cpu_percent"] == 20.0


@pytest.mark.parametrize(
    "limit",
    ["0", "-1", "301", "abc"]
)
def test_history_invalid_limit(client, limit):
    """無效的 limit 應回傳 HTTP 400。"""

    response = client.get(f"/api/history?limit={limit}")

    assert response.status_code == 400


def test_retention_removes_old_records(client):
    """超過七天的資料應被刪除，近期資料應保留。"""

    old_timestamp = int(time.time()) - (8 * 24 * 60 * 60)

    # 在測試資料庫新增一筆八天前的紀錄
    conn = sqlite3.connect(database.DB_PATH)

    try:
        conn.execute("""
            INSERT INTO system_metrics (
                collected_at,
                cpu_percent,
                memory_percent,
                disk_percent
            )
            VALUES (?, ?, ?, ?)
        """, (old_timestamp, 10.0, 50.0, 30.0))

        conn.commit()

    finally:
        conn.close()

    # 再新增一筆現在的紀錄
    database.save_metric(sample_metric(cpu=30.0))

    # 執行資料保留政策
    deleted = database.delete_old_metrics(days=7)

    assert deleted == 1

    # 確認最後只剩近期資料
    records = database.get_recent_metrics(limit=10)

    assert len(records) == 1
    assert records[0]["cpu_percent"] == 30.0


def test_home_page(client):
    """原本的 Dashboard 首頁必須仍然正常。"""

    response = client.get("/")

    assert response.status_code == 200
    assert b"html" in response.data.lower()
