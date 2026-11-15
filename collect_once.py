
from monitor import get_system_info
from database import DB_PATH, init_database, save_metric


def main():
    # 1. 初始化 SQLite 資料庫
    init_database()

    # 2. 取得當下的 Linux 系統數據
    metrics = get_system_info()

    # 3. 儲存數據並取得紀錄 ID
    record_id = save_metric(metrics)

    # 4. 在 Terminal 顯示結果
    print("===== Monitoring Data Collector =====")
    print(f"Record ID: {record_id}")
    print(f"CPU Usage: {metrics['cpu_percent']}%")
    print(f"Memory Usage: {metrics['memory_percent']}%")
    print(f"Disk Usage: {metrics['disk_percent']}%")
    print(f"Database: {DB_PATH}")
    print("Data saved successfully.")


if __name__ == "__main__":
    main()
