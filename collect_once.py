
import logging

from monitor import get_system_info
from database import (
    DB_PATH,
    init_database,
    save_metric,
    delete_old_metrics
)


# 設定日誌格式與最低記錄等級
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


def main():
    try:
        # 1. 初始化資料庫
        init_database()

        # 2. 收集當下的 Linux 系統數據
        metrics = get_system_info()

        # 3. 寫入 SQLite
        record_id = save_metric(metrics)
        # 刪除超過 7 天的歷史資料
        deleted_count = delete_old_metrics(days=7)

        if deleted_count > 0:
            logger.info(
                "Retention cleanup: removed %s old records",
                deleted_count
            )

        # 4. 記錄成功訊息
        logger.info(
            "Metric saved: id=%s cpu=%s%% memory=%s%% disk=%s%%",
            record_id,
            metrics["cpu_percent"],
            metrics["memory_percent"],
            metrics["disk_percent"]
        )

        logger.info("Database: %s", DB_PATH)

    except Exception:
        # 記錄錯誤及完整的 Exception Traceback
        logger.exception("Metrics collection failed")

        # 將錯誤繼續往上傳，讓 systemd 知道任務失敗
        raise


if __name__ == "__main__":
    main()
