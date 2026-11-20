# Linux Deployment Guide / Linux 部署教學

> **Version / 版本：** v0.4 — Monitoring & Reliability (**Completed / 已完成**)  
> **Audience / 適用對象：** Ubuntu / Linux 初學者、系統部署學習者

## Overview / 文件目的

This guide documents deployment and verification of the Linux Server Monitoring Dashboard on Ubuntu: **Gunicorn + Nginx + systemd** (v0.3), extended with **SQLite history, a systemd Timer, Chart.js, health checks, logging, data retention, and pytest** (v0.4).

本文完整保留 v0.3 的 Gunicorn、Nginx、systemd 部署流程，並補充 v0.4 的 SQLite 歷史監控、自動收集、歷史 API、折線圖、健康檢查、Logging、資料保留策略及 pytest 自動化測試。各節提供**指令、用途、預期結果與故障排除方法**，以便在 Ubuntu 上重建與驗證專案。

### Tested Environment / 使用環境

- Ubuntu 24.04 LTS
- Python 3.12
- VMware Workstation
- Gunicorn and Nginx
- systemd / journalctl
- VS Code Remote SSH
- SQLite (Python `sqlite3` standard library)
- Python `logging` and pytest (development/testing)
- Chart.js for historical charts (loaded via CDN in the current frontend)

> **Environment note / 環境提醒：** Example paths use Linux user `xilin` and `/home/xilin/projects/linux-server-monitor`. These values belong to the original learning VM and must be adjusted on other machines. The author reports that the v0.3 deployment and v0.4 functionality/tests were verified in the original Ubuntu VMware environment; this document is not an independent verification of a live machine. / 以下指令中的帳號與絕對路徑為原始測試環境設定，移植時須調整。v0.3 與 v0.4 完成狀態依專案作者回報的測試結果記錄，非本文件重新遠端實測。

### Deployment Architecture / 部署架構

```text
Windows Browser (Dashboard + CPU / RAM history charts)
      |
      | HTTP :80
      v
Ubuntu / Nginx (Reverse Proxy)
      |
      | HTTP 127.0.0.1:5000
      v
Gunicorn (managed by linux-server-monitor.service)
      |
      v
Flask (app.py)
      |-- GET /api/system  -> monitor.py -> psutil (real-time metrics)
      |-- GET /api/history -> database.py -> SQLite history
      |-- GET /api/health  -> SQLite availability check
      `-- GET /           -> HTML + JavaScript + Chart.js

systemd metrics-collector.timer (approximately every 30 seconds)
      |
      v
metrics-collector.service (Type=oneshot)
      |
      v
collect_once.py -> monitor.py -> database.py -> data/metrics.db
                                     `-> 7-day retention cleanup

journalctl <- Gunicorn service logs / collector Python logging
```

**中文解說：** Nginx 是對外的 HTTP 入口，Gunicorn 執行 Flask；`linux-server-monitor.service` 管理長時間運作的 Web 服務。另一條獨立路徑由 `metrics-collector.timer` 定時觸發一次性的資料收集服務，把 psutil 數據寫入 SQLite。`/api/history` 從 SQLite 讀取歷史紀錄，Chart.js 在瀏覽器畫圖；`journalctl` 用來查詢服務日誌。**systemd 不會取代 Nginx 或 Gunicorn；Collector 也不需要在每個 Gunicorn Worker 裡執行。**

---

## 1. Prepare the Python Environment / 準備 Python 環境

Clone the project / 下載專案：

```bash
git clone https://github.com/xilin0811/linux-server-monitor.git
cd linux-server-monitor
```

Install virtual environment support if necessary / 如尚未安裝 venv 支援：

```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

Create and activate the virtual environment / 建立並啟用虛擬環境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install runtime dependencies / 安裝執行環境依賴套件：

```bash
python -m pip install -r requirements.txt
```

For v0.4 development and automated tests / 如要執行 v0.4 自動化測試，另外安裝：

```bash
python -m pip install -r requirements-dev.txt
```

`sqlite3` and `logging` belong to the Python standard library, so no separate `pip install sqlite3` is required. / `sqlite3` 和 `logging` 是 Python 標準函式庫，不需要額外以 pip 安裝。

Verify Gunicorn / 確認已安裝：

```bash
gunicorn --version
```

**Why / 原理：** `.venv` 將這個專案需要的 Python 套件與 Ubuntu 系統環境隔離。`source .venv/bin/activate` 會調整目前 Shell 的 `PATH`，讓 `python` 和 `gunicorn` 優先使用虛擬環境內的版本；**systemd 不會繼承這個互動式啟用狀態**，因此之後必須使用 Gunicorn 的絕對路徑。

**Expected / 預期結果：** `gunicorn --version` 應顯示安裝版本；如果找不到指令，請確認 `.venv` 已啟用且 `requirements.txt` 包含 Gunicorn。

---

## 2. Test Gunicorn Manually / 手動測試 Gunicorn

Start Gunicorn only when the systemd-managed instance is stopped; otherwise both processes compete for port 5000. / **僅在 systemd 管理的 Gunicorn 已停止時，才手動啟動下列指令**，否則可能佔用同一個 Port 5000：

```bash
gunicorn --workers 2 --bind 127.0.0.1:5000 app:app
```

| Parameter / 參數 | Description / 解釋 |
|---|---|
| `gunicorn` | 執行 WSGI Application Server |
| `--workers 2` | 建立兩個 Worker Process 處理請求 |
| `--bind` | 指定監聽的 IP 和 Port |
| `127.0.0.1:5000` | 只接受 Ubuntu 本機的 Port 5000 連線 |
| `app:app` | 從 `app.py` 模組載入 `app` Flask 物件 |

In a second Ubuntu terminal / 另開一個 Ubuntu Terminal：

```bash
curl -i http://127.0.0.1:5000/api/system
```

**Expected / 預期結果：** `HTTP/1.1 200 OK`，並回傳 CPU、Memory、Disk 和 Uptime 的 JSON。

**Why / 原理：** 這次 `curl` 直接呼叫 Gunicorn，**還沒有經過 Nginx**。這有助於把「後端問題」與「反向代理問題」區分開。

**After testing / 測試結束：** 回到執行 Gunicorn 的 Terminal，按 `Ctrl + C` 停止。若之後仍佔用 Port 5000，systemd 啟動新 Gunicorn 時可能發生 `Address already in use`。

---

## 3. Install and Configure Nginx / 安裝與設定 Nginx

Install Nginx / 安裝：

```bash
sudo apt install nginx
```

Check service status / 查看服務：

```bash
systemctl status nginx --no-pager
```

**Expected / 預期結果：** `Active: active (running)`。

Review the repository example / 確認專案設定檔：

`deployment/nginx.conf`

Ensure the listener, hostname, and upstream address match the target VM. For the current architecture, Nginx listens on **Port 80**, and forwards requests to **127.0.0.1:5000**.

**注意：** 以下 `cp` 會覆蓋同名的 `/etc/nginx/sites-available/linux-server-monitor`。如果你已經在 Ubuntu 調整過可運作的 Nginx 設定，請先比較或備份，不要直接覆蓋。

```bash
sudo cp deployment/nginx.conf /etc/nginx/sites-available/linux-server-monitor
```

Enable the website if it has not already been enabled / 首次部署才建立符號連結：

```bash
sudo ln -s /etc/nginx/sites-available/linux-server-monitor /etc/nginx/sites-enabled/linux-server-monitor
```

`ln -s` 建立 Symbolic Link（符號連結），讓 Nginx 載入 `sites-available` 裡的網站設定。若同名連結已存在，不需要再次執行。

**Port conflict / Port 衝突：** 如果預設網站同樣監聽 Port 80，請先檢查 `/etc/nginx/sites-enabled/` 與其他 Server Block，不要直接刪除不熟悉的設定。

Validate before reloading / 先測試，再重新載入：

```bash
sudo nginx -t && sudo systemctl reload nginx
```

`&&` 表示前一個指令成功才執行下一個，避免錯誤設定直接被載入。

### Reverse Proxy Configuration / 反向代理重點

```nginx
location / {
    proxy_pass http://127.0.0.1:5000;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

- `location /`：匹配根路徑以及 `/api/system`、`/static/...` 等路徑。
- `proxy_pass`：將請求轉發至 Gunicorn。
- `proxy_set_header`：向後端傳遞原始 Host、來源 IP 與協定資訊。

**Important / 注意：** Nginx 能正常啟動不代表 Flask 一定正常；後端停止時，Nginx 可能回傳 **502 Bad Gateway**。

---

## 4. Configure systemd for Gunicorn / 使用 systemd 管理 Gunicorn

The repository includes / 專案已包含：

`deployment/linux-server-monitor.service`

### Example Unit File / 服務設定範例

```ini
[Unit]
Description=Linux Server Monitoring Dashboard
After=network.target

[Service]
Type=simple
User=xilin
Group=xilin
WorkingDirectory=/home/xilin/projects/linux-server-monitor
ExecStart=/home/xilin/projects/linux-server-monitor/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:5000 app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Unit File Explanation / 設定逐項解釋

| Setting / 欄位 | Purpose / 用途 |
|---|---|
| `[Unit]` | 服務描述與啟動順序設定 |
| `Description` | 服務描述文字 |
| `After=network.target` | 排列啟動順序；**不保證已能連上網際網路** |
| `[Service]` | 主要執行與程序管理設定 |
| `Type=simple` | systemd 追蹤所啟動的主要程序 |
| `User=xilin` | 使用一般使用者身分執行，而不是 root |
| `Group=xilin` | 指定執行群組 |
| `WorkingDirectory` | 指定 Python 專案工作目錄 |
| `ExecStart` | 使用虛擬環境內的 Gunicorn 絕對路徑 |
| `Restart=on-failure` | 服務異常退出時嘗試自動重啟 |
| `RestartSec=5` | 每次重新啟動前等待約 5 秒 |
| `[Install]` / `WantedBy=multi-user.target` | 提供開機啟用時的依附目標 |

**為什麼要寫絕對路徑？** systemd 不是由已經執行 `source .venv/bin/activate` 的 Terminal 來啟動，因此 `ExecStart` 必須能直接找到正確的 Gunicorn。

### Install the Service / 安裝服務

Stop any manually started Gunicorn process before continuing. / 先停止手動啟動的 Gunicorn。

Check Port 5000 / 檢查是否被佔用：

```bash
sudo ss -lntp | grep ':5000 '
```

沒有輸出通常表示沒有符合條件的 TCP 監聽程序；若有輸出，先確認程序身分。**不要直接使用 `kill -9` 強制結束不明程序。**

Copy the unit file / 複製設定：

```bash
sudo cp deployment/linux-server-monitor.service /etc/systemd/system/linux-server-monitor.service
```

> 如果這台 VM 已經完成 systemd 設定，再次執行 `cp` 前請先確認兩邊內容，避免覆蓋正在使用的服務設定。

Validate the unit / 靜態檢查：

```bash
sudo systemd-analyze verify /etc/systemd/system/linux-server-monitor.service
```

Reload systemd definitions / 讓 systemd 讀取新設定：

```bash
sudo systemctl daemon-reload
```

Enable on boot **and** start now / 設定開機啟動並立即啟動：

```bash
sudo systemctl enable --now linux-server-monitor
```

Check current running state / 確認目前執行中：

```bash
systemctl status linux-server-monitor --no-pager
```

Expected / 預期：`Active: active (running)`。

Check boot-time activation / 確認開機啟用設定：

```bash
systemctl is-enabled linux-server-monitor
```

Expected / 預期：`enabled`。

**Important difference / 重要差別：** `active (running)` 表示**現在**有在運作；`enabled` 表示**下次開機**會嘗試啟動。兩者需要分別檢查。

---

## 5. Test the Complete Deployment / 完整部署驗收

### Test Gunicorn Directly / 直接測試後端

```bash
curl -i http://127.0.0.1:5000/api/system
```

**Expected / 預期：** HTTP 200 + JSON。這只測試 Gunicorn / Flask，不經過 Nginx。

### Test Nginx Reverse Proxy / 測試反向代理

```bash
curl -i http://127.0.0.1/api/system
```

**Expected / 預期：** HTTP 200 + JSON。這次先進入 Nginx，再轉到 Gunicorn。

### Test from Windows / Windows 端測試

Check the Ubuntu IP / 查看 Ubuntu IP：

```bash
hostname -I
```

From Chrome on the trusted VM network / 在可信任的 Windows 網路中開啟：

`http://<UBUNTU_IP>/`

**Expected / 預期：** Dashboard 顯示 CPU、Memory、Disk、Uptime，並持續更新。

### Test SSH Independence / 驗證不依賴 SSH

Disconnect VS Code Remote SSH, then refresh the Dashboard from Windows.

**目的：** 證明 Gunicorn 是由 systemd 管理，而不是依賴前景 Terminal。請確認沒有透過 VS Code Port Forwarding 使用 `localhost:5000`。

### Test Automatic Startup / 驗證重開機自動啟動

Save your work first. / 先儲存目前尚未保存的檔案。

```bash
sudo reboot
```

After Ubuntu boots again / Ubuntu 重新開機後：

```bash
systemctl status linux-server-monitor --no-pager
systemctl is-enabled linux-server-monitor
```

Reopen the Dashboard from Windows. If VMware assigned a new IP, use the updated address.

**注意：** systemd 可以讓服務隨 Ubuntu 啟動，但**不會自動開啟已關機的 VMware VM**。

### Test Restart on Failure / 驗證失敗重啟

Review the current systemd configuration and logs before deliberately testing failure recovery. In an isolated learning VM, a controlled worker/master failure can be simulated after identifying the correct Gunicorn process, then you can confirm whether systemd restarts it.

**中文提醒：** 這是可選的進階驗收。不要用 `kill -9` 隨意終止其他程序；若尚未熟悉 PID、訊號與 systemd Restart Policy，可以先完成服務啟動及重開機驗收，再進行故障模擬。

---

## 6. Manage the systemd Service / 常用服務管理指令

| Command / 指令 | Meaning / 用途 |
|---|---|
| `sudo systemctl start linux-server-monitor` | 立即啟動服務 |
| `sudo systemctl stop linux-server-monitor` | 停止服務（管理員主動停止通常不觸發 on-failure 重啟） |
| `sudo systemctl restart linux-server-monitor` | 停止後重新啟動服務 |
| `systemctl status linux-server-monitor --no-pager` | 查看目前狀態，避免進入 less 分頁 |
| `sudo systemctl enable linux-server-monitor` | 設定開機自動啟動，不一定立即啟動 |
| `sudo systemctl disable linux-server-monitor` | 取消開機啟用，不代表現在立刻停止 |
| `sudo systemctl daemon-reload` | 重新讀取修改過的 Unit File |

**`start` vs `enable`：** `start` 是讓服務**現在執行**；`enable` 是讓服務**開機後自動啟動**。`enable --now` 可以一次執行兩件事。

After changing a `.service` file / 修改 Unit File 後：

```bash
sudo systemctl daemon-reload
sudo systemctl restart linux-server-monitor
```

---

## 7. View Logs with journalctl / 使用 journalctl 查看日誌

Last 30 log entries / 最近 30 筆：

```bash
sudo journalctl -u linux-server-monitor -n 30 --no-pager
```

Logs from the current boot / 本次開機的日誌：

```bash
sudo journalctl -u linux-server-monitor -b --no-pager
```

Follow logs in real time / 即時追蹤日誌：

```bash
sudo journalctl -u linux-server-monitor -f
```

Press `Ctrl + C` to stop following logs. / 按 `Ctrl + C` 離開持續追蹤。

| Option / 參數 | Purpose / 用途 |
|---|---|
| `-u` | 指定要查詢的 systemd Unit |
| `-n 30` | 顯示最後 30 筆日誌 |
| `-b` | 只查看目前這次開機的日誌 |
| `-f` | 持續輸出新日誌（Follow） |
| `--no-pager` | 不開啟 less，直接顯示在 Terminal |

**Why / 原理：** `journalctl` 不是「啟動服務」的指令，而是用來查閱 systemd Journal。Gunicorn 的標準輸出、標準錯誤與相關服務訊息，通常能在此查到；具體內容取決於服務的日誌設定。

---

## 8. Troubleshooting / 故障排除

### A. Service Fails to Start / systemd 服務啟動失敗

```bash
systemctl status linux-server-monitor --no-pager
sudo journalctl -u linux-server-monitor -n 50 --no-pager
ls -l /home/xilin/projects/linux-server-monitor/.venv/bin/gunicorn
```

**排查順序：** 先看 `status` 的錯誤，再看 Journal 詳細記錄，最後確認 `ExecStart` 路徑、權限、Python 套件和工作目錄。

### B. Port 5000 Already in Use / Port 5000 被佔用

```bash
sudo ss -lntp | grep ':5000 '
```

`ss -lntp` 用來顯示正在監聽的 TCP Port 及所屬程序。常見原因是手動執行的 Gunicorn 還沒停止。

### C. Nginx Returns 502 Bad Gateway / Nginx 無法連後端

```bash
systemctl status linux-server-monitor --no-pager
curl -i http://127.0.0.1:5000/api/system
sudo tail -n 30 /var/log/nginx/error.log
```

**原理：** 502 通常表示 Nginx 無法正常取得上游（Gunicorn）的回應。先確定 5000 Port 的 API 是否正常，再查 Nginx 日誌；不要一看到 502 就直接重裝 Nginx。

### D. Nginx Configuration Error / Nginx 設定語法錯誤

```bash
sudo nginx -t
```

Only reload after validation succeeds. / 設定檢查通過後才執行 `sudo systemctl reload nginx`。

### E. Windows Cannot Access Dashboard / Windows 無法存取

```bash
hostname -I
systemctl status nginx --no-pager
sudo ufw status
```

**排查方向：** 檢查 Ubuntu IP 是否改變、VMware NAT/Bridged 網路設定、Windows 與 VM 的連通性、Nginx 是否監聽 Port 80，以及 UFW 是否限制來源。

### F. Dashboard Not Available After Reboot / 開機後網站無法使用

```bash
systemctl is-enabled linux-server-monitor
systemctl status linux-server-monitor --no-pager
sudo journalctl -u linux-server-monitor -b --no-pager
```

如果顯示 `enabled` 但沒有 `active (running)`，表示服務有設定開機啟用，但**實際啟動時可能失敗**；請根據 Journal 判斷原因。

---

## 9. Security Considerations / 安全注意事項

- Gunicorn listens on `127.0.0.1:5000`.（Gunicorn 僅接受 Ubuntu 本機連線。）
- Nginx listens on the HTTP entry port.（Nginx 接收區域網路上的 HTTP 請求。）
- Gunicorn runs as a non-root user.（避免不必要的 root 權限。）
- The monitoring API does not require authentication.（目前 API 未加登入驗證。）
- HTTP traffic is not protected by TLS.（目前是 HTTP，不是 HTTPS。）
- **Do not expose this test deployment to the public internet.**（請勿將目前無驗證的監控網站直接對外公開。）
- Review file paths, permissions, and firewall rules before deploying elsewhere.（搬移到其他機器前需檢查路徑、權限與防火牆。）
- SQLite records contain local system usage history. Keep `data/` ignored by Git and restrict filesystem access.（資料庫包含主機資源使用歷史；請勿提交到 GitHub，並控制檔案權限。）
- `/api/history` and `/api/health` are also unauthenticated in v0.4.（v0.4 新增的 API 亦未加入登入驗證。）
- Chart.js is loaded via a third-party CDN in this implementation; offline operation needs a local copy.（目前圖表依賴外部 CDN；若需要離線執行，應改用本地靜態檔案。）

---

## 10. v0.3 Deployment Verification Record / v0.3 部署驗收紀錄

The following checks were completed in the original Ubuntu VMware learning environment and are recorded here as the v0.3 milestone results. / 以下為專案作者在原始 Ubuntu VMware 環境中完成的 v0.3 驗收紀錄，不是待辦清單。

| Test / 測試項目 | Verification / 驗證方式 | Result / 結果 |
|---|---|---|
| Python environment / Python 環境 | `.venv` created and dependencies installed / 建立虛擬環境與安裝套件 | Passed / 通過 |
| Gunicorn backend / 後端 API | `curl -i http://127.0.0.1:5000/api/system` returned HTTP 200 / API 回傳正常 | Passed / 通過 |
| Nginx configuration / Nginx 設定 | `sudo nginx -t` succeeded / 設定測試通過 | Passed / 通過 |
| Reverse proxy / 反向代理 | `curl -i http://127.0.0.1/api/system` returned HTTP 200 / 代理可取得 API 資料 | Passed / 通過 |
| systemd installation / 服務設定 | Unit File installed and loaded / Unit File 已安裝並載入 | Passed / 通過 |
| Service state / 服務狀態 | `active (running)` / 執行中 | Passed / 通過 |
| Boot enablement / 開機啟用 | `systemctl is-enabled` reported `enabled` / 已設定開機啟動 | Passed / 通過 |
| Windows access / 跨主機存取 | Dashboard accessible using the Ubuntu VM IP / Windows 透過 Ubuntu IP 存取 | Passed / 通過 |
| SSH independence / SSH 獨立性 | Dashboard available after Remote SSH disconnect / 中斷 SSH 後仍可使用 | Passed / 通過 |
| Reboot persistence / 重開機驗證 | Dashboard and service restored after Ubuntu reboot / 開機後自動恢復 | Passed / 通過 |
| Log inspection / 日誌檢視 | `journalctl -u linux-server-monitor` inspected / 已檢視服務日誌 | Passed / 通過 |
| Failure recovery / 異常恢復 | Restart-on-failure behavior verified / 已驗證失敗後自動重啟 | Passed / 通過 |

**Result / 結論：** All v0.3 verification items passed as reported by the project author. / 依專案作者完成的實機測試紀錄，v0.3 驗收項目均已通過。

## 11. v0.4 Historical Data Storage / SQLite 歷史資料儲存

### Purpose / 功能目的

v0.4 adds persistent resource-usage history. Unlike `/api/system`, which reads current values directly through psutil, the historical data is stored as rows in SQLite and remains available after the Flask service is restarted.

v0.4 新增 SQLite 歷史監控資料庫：即時監控仍由 `/api/system` 呼叫 psutil，而歷史監控資料則由獨立 Collector 寫入 SQLite。重啟 Flask 或重新整理網頁，不會清除已保存的資料。

| File / 檔案 | Responsibility / 功能 |
|---|---|
| `monitor.py` | Collects live CPU, memory, and disk metrics / 取得即時 Linux 系統數值 |
| `database.py` | Initializes SQLite; writes, queries, checks and cleans up metrics / 建表、寫入、查詢、健康檢查與刪除過期資料 |
| `collect_once.py` | Collects and saves one record per execution / 每次執行保存一筆監控紀錄 |
| `data/metrics.db` | Runtime SQLite database; excluded from Git / 執行時資料庫，不上傳 GitHub |
| `.gitignore` | Ignores `data/`, virtual environment and Python caches / 忽略執行時資料 |

**Storage path / 路徑：** `/home/xilin/projects/linux-server-monitor/data/metrics.db`. The program constructs the path from its source location, so the collector does not depend on the Terminal's current directory. / 程式使用專案來源檔案位置組合資料庫絕對路徑，降低工作目錄不同造成找錯資料庫的問題。

### Database Schema / 資料表結構

The `init_database()` function in `database.py` creates `system_metrics` when needed. / `database.py` 使用 `init_database()` 建立資料表。

```sql
CREATE TABLE IF NOT EXISTS system_metrics (
    id INTEGER PRIMARY KEY,
    collected_at INTEGER NOT NULL,
    cpu_percent REAL NOT NULL,
    memory_percent REAL NOT NULL,
    disk_percent REAL NOT NULL
);
```

`collected_at` is a Unix timestamp in seconds, and the other metric values are percentages. / `collected_at` 使用以秒為單位的 Unix Timestamp，其他欄位保存百分比。

The project also creates an index on `collected_at` to support time-based queries. / 專案在時間欄位建立索引，方便後續歷史資料查詢。

### Manual Collection / 手動收集一筆資料

Run these commands from the repository root / 在專案根目錄執行：

```bash
cd ~/projects/linux-server-monitor
source .venv/bin/activate
python collect_once.py
```

**Expected / 預期：** An INFO log reports the newly saved record and usage values; running the collector once creates one new sample and then exits. / 一次執行新增一筆資料後結束，並顯示 INFO 日誌。正常情況下不會持續佔用 Terminal。

Verify that SQLite exists and query the latest records / 確認資料庫及最新紀錄：

```bash
ls -lh data/metrics.db
python -m sqlite3 data/metrics.db "SELECT COUNT(*) FROM system_metrics;"
python -m sqlite3 data/metrics.db "SELECT id, datetime(collected_at, 'unixepoch', 'localtime'), cpu_percent, memory_percent, disk_percent FROM system_metrics ORDER BY id DESC LIMIT 5;"
```

**Command notes / 指令說明：** `python -m sqlite3` runs the SQLite CLI module available with the Ubuntu Python 3.12 environment. `COUNT(*)` counts rows; `ORDER BY id DESC LIMIT 5` displays the five latest inserted samples; the `datetime(..., 'localtime')` expression renders the timestamp using the Ubuntu machine's local timezone. / 上述指令分別用於查總筆數、最新五筆以及將時間戳轉換為本機時間。

> **Version-control note / 版本控制提醒：** Keep `database.py` and `collect_once.py` in Git; do not commit `data/metrics.db` or its backups. Running `git check-ignore -v data/metrics.db` should identify the ignore rule. / Git 需追蹤程式碼，不需追蹤每隔一段時間就改變的監控資料庫。

---

## 12. Automated Metrics Collection / 使用 systemd Timer 自動收集

### Separate Service and Timer / 獨立的收集服務與排程

The Gunicorn service is a long-running `Type=simple` process. The collector is different: it executes once, saves a record, and exits, so it uses `Type=oneshot`. The timer triggers this oneshot service periodically.

Gunicorn 是持續運作的 Web Service；Collector 只需要執行一次並結束，所以採用 `Type=oneshot`。**Timer 負責排程，Service 負責實際執行 Python。** 將收集工作與兩個 Gunicorn Workers 分離，也能避免重複啟動收集迴圈。

The repository contains / 專案中包含：

- `deployment/metrics-collector.service`
- `deployment/metrics-collector.timer`

### Collector Service Unit / 收集服務設定

```ini
[Unit]
Description=Collect Linux system metrics into SQLite

[Service]
Type=oneshot
User=xilin
Group=xilin
WorkingDirectory=/home/xilin/projects/linux-server-monitor
ExecStart=/home/xilin/projects/linux-server-monitor/.venv/bin/python /home/xilin/projects/linux-server-monitor/collect_once.py
```

| Setting / 欄位 | Explanation / 解釋 |
|---|---|
| `Type=oneshot` | Run one collection and exit / 執行單次收集後結束 |
| `User` and `Group` | Run as a non-root user / 使用一般帳號執行 |
| `WorkingDirectory` | Set the project directory / 設定工作目錄 |
| `ExecStart` | Use the Python interpreter inside `.venv` / 使用虛擬環境的 Python 絕對路徑 |

**Expected behavior / 預期狀態：** After a successful run, `metrics-collector.service` may display `inactive (dead)`; unlike Gunicorn, this is normal for a oneshot service. Confirm `Result=success` and `ExecMainStatus=0` instead. / 單次執行成功後顯示 `inactive (dead)` 不代表出錯。

### Timer Unit / 排程設定

```ini
[Unit]
Description=Collect Linux system metrics periodically

[Timer]
OnBootSec=1min
OnUnitInactiveSec=30s
AccuracySec=1s
Unit=metrics-collector.service

[Install]
WantedBy=timers.target
```

| Setting / 欄位 | Explanation / 解釋 |
|---|---|
| `OnBootSec=1min` | First trigger is based on system boot time / 依開機時間安排首次執行 |
| `OnUnitInactiveSec=30s` | Trigger about 30 seconds after the previous service finishes / 前次任務結束約 30 秒後再次觸發 |
| `AccuracySec=1s` | Timer accuracy window; not a hard real-time guarantee / 設定排程精度視窗，不保證完全準時 |
| `Unit=metrics-collector.service` | Service triggered by this timer / 指定被觸發的服務 |
| `WantedBy=timers.target` | Allow the timer to be enabled at boot / 讓 Timer 可設定開機啟用 |

**Interval clarification / 間隔提醒：** 30 seconds here is counted after a service run becomes inactive, not necessarily exactly 30 seconds between sample timestamps. The timer runs only while the VM is running; it does not power on VMware. / 本設定不是嚴格固定每 30 秒採樣，也不會在 VM 關機時補齊每一筆遺漏資料。

### Install and Enable / 安裝及啟用

Check the paths and account in the Unit Files before running `sudo cp`. Existing files at the destination will be overwritten. / 複製前先檢查帳號與路徑，並注意 `cp` 會覆蓋同名設定檔。

```bash
cd ~/projects/linux-server-monitor
ls -l deployment/metrics-collector.service deployment/metrics-collector.timer
sudo cp deployment/metrics-collector.service /etc/systemd/system/
sudo cp deployment/metrics-collector.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/metrics-collector.service
sudo systemd-analyze verify /etc/systemd/system/metrics-collector.timer
sudo systemctl daemon-reload
```

**First validate the oneshot service / 先手動驗證一次性收集服務：**

```bash
sudo systemctl start metrics-collector.service
systemctl status metrics-collector.service --no-pager
systemctl show metrics-collector.service -p Result -p ExecMainStatus
```

**Expected / 預期：** `Result=success`, `ExecMainStatus=0`; SQLite gains one row. / 服務上次執行成功，且資料庫新增一筆監控紀錄。

**Then enable the timer / 再啟用排程：**

```bash
sudo systemctl enable --now metrics-collector.timer
systemctl status metrics-collector.timer --no-pager
systemctl list-timers --all | grep metrics-collector
```

**Expected / 預期：** Timer displays `active (waiting)` and a scheduled NEXT time. / Timer 顯示 `active (waiting)`，並可查到下一次預定觸發時間。

After a few collection cycles, run the SQL count query again; the row count should increase. / 經過數個週期再查詢 SQLite 筆數，應能看到紀錄數量增加。

---

## 13. REST APIs and Historical Charts / API 與歷史折線圖

### API Reference / API 一覽

| Endpoint | Data source / 資料來源 | Purpose / 功能 |
|---|---|---|
| `GET /` | Flask templates and static files | Dashboard 網頁 |
| `GET /api/system` | `monitor.py` / psutil | 即時 CPU、RAM、Disk、Uptime |
| `GET /api/history` | SQLite / `database.py` | 歷史監控資料，預設最多 60 筆 |
| `GET /api/history?limit=5` | SQLite / `database.py` | 讀取最近五筆，按時間由舊到新排列 |
| `GET /api/health` | Flask + SQLite query | 基本健康檢查（資料表可讀性） |

### History API / 歷史資料 API

```bash
curl -i "http://127.0.0.1/api/history?limit=5"
curl -sS "http://127.0.0.1/api/history?limit=5" | python -m json.tool
```

**Expected / 預期：** HTTP 200 and JSON containing `count` and a `metrics` array. Each record includes `id`, `collected_at`, `cpu_percent`, `memory_percent`, and `disk_percent`. Records are sorted oldest to newest within the requested latest N samples. / 回傳本次查詢的筆數與時間升序的歷史紀錄，方便繪製折線圖。

The Flask route validates `limit` as an integer from **1 to 300**. An invalid value returns HTTP 400. / `limit` 僅接受 1～300 的整數；不合法時回傳 HTTP 400。

```bash
curl -i "http://127.0.0.1/api/history?limit=abc"
curl -i "http://127.0.0.1/api/history?limit=0"
```

**Expected / 預期：** Both return `400 Bad Request`. / 兩者皆應回傳 HTTP 400。

### Health API / 健康檢查 API

```bash
curl -i http://127.0.0.1/api/health
```

Successful example / 成功的回傳範例：

```json
{
  "status": "healthy",
  "database": "ok"
}
```

**Expected / 預期：** HTTP 200 when the expected SQLite database file and table can be queried. A database-check failure returns HTTP 503 with `status: unhealthy`. / 資料庫檔案存在且指定資料表可讀時回傳 HTTP 200；檢查失敗則回傳 HTTP 503。

**Limitation / 限制：** This is a basic availability/readability check, **not** a writeability check, full database integrity check, or guarantee that the systemd Timer has recently collected new samples. / 此 API 僅檢查基本可讀性，**不代表資料庫一定可寫入，也不代表 Collector 最近有成功執行**。若要驗證收集新鮮度，仍須查看 SQLite 時間戳與 Timer 日誌。

### Browser Charts / 前端歷史折線圖

The existing real-time cards remain on the Dashboard and update approximately every **5 seconds**. v0.4 additionally uses `static/history.js` and Chart.js to fetch `/api/history` approximately every **30 seconds**, rendering historical CPU and memory charts below the live cards.

原本四張即時卡片維持約每 5 秒更新；新增的 Chart.js CPU／Memory 折線圖約每 30 秒向 `/api/history` 重新查詢資料。頁面可選擇最近 30、60、120、300 筆。這些代表**筆數**，不是保證固定時間長度。

Chart.js is currently loaded from a CDN; if the browser has no internet access, live cards and APIs can still work while the history charts may not render. / Chart.js 目前透過 CDN 載入；若瀏覽器無法存取外部 CDN，圖表可能無法顯示，但即時監控與 API 不一定受到影響。

**Browser validation / 網頁驗證：** Open `http://<UBUNTU_IP>/` on Windows, hard refresh (`Ctrl + Shift + R`), verify both charts, change the sample-count selector, and confirm the live cards still update. / 從 Windows 進入網頁、強制重新整理、切換顯示筆數並確認原本即時監控正常。

---

## 14. Logging, Retention, and Backup / 日誌、資料保留與備份

### Collector Logging / 收集程式日誌

`collect_once.py` uses Python `logging` (INFO for successful collection and ERROR/traceback on failure). Its output is captured by the oneshot systemd service and can be inspected with `journalctl`.

Collector 使用 Python `logging` 記錄收集成功的 ID 與資源數值；如發生例外則記錄 Traceback，並將錯誤重新拋出，使 systemd 能辨認任務失敗。

```bash
sudo journalctl -u metrics-collector.service -n 30 --no-pager
sudo journalctl -u metrics-collector.service -b --no-pager
sudo journalctl -u metrics-collector.service -f
```

`-u` selects the Unit, `-n` limits the recent entries, `-b` limits logs to the current boot, and `-f` follows new entries (quit with `Ctrl + C`). / `-u` 指定服務、`-n` 查最近日誌、`-b` 限本次開機、`-f` 即時追蹤。

### Seven-Day Retention / 七天保留策略

v0.4 calls `delete_old_metrics(days=7)` after saving a sample. Its SQL deletion condition is based on timestamps older than the last seven days. / Collector 每次成功寫入後，呼叫 `delete_old_metrics(days=7)` 清理超過七天的歷史紀錄。

```sql
DELETE FROM system_metrics
WHERE collected_at < ?;
```

The placeholder is populated with `current Unix time - (7 * 24 * 60 * 60)`. / 以目前 Unix 時間減去七天的秒數計算刪除門檻，使用 SQL 參數避免拼接字串。

**Important / 注意：** The deletion affects the actual database, so back up before testing retention against meaningful real records. The deletion may not immediately reduce the physical `.db` file size because SQLite may reuse freed pages. / SQL 刪除會真的移除紀錄，測試前先備份；刪除後 `.db` 檔案大小不一定立即縮小，這是 SQLite 頁面重用機制造成的正常現象。

### SQLite Backup / 備份資料庫

Use SQLite's backup API to obtain a consistent copy while the Collector may be writing. / Collector 運作期間，使用 SQLite Backup API 備份，避免直接複製資料庫檔案造成不一致。

```bash
cd ~/projects/linux-server-monitor
source .venv/bin/activate
python - <<'PYBACKUP'
import sqlite3
from pathlib import Path

source = Path('data/metrics.db')
target = Path('data/metrics-backup.db')

src = sqlite3.connect(source)
dst = sqlite3.connect(target)
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()

print(f'Backup completed: {target}')
PYBACKUP
```

**Expected / 預期：** `Backup completed: data/metrics-backup.db`. Both the original database and backup remain inside the Git-ignored `data/` directory. / 原始與備份資料庫均留在被 Git 忽略的資料夾內。

---

## 15. Automated Tests / pytest 自動化測試

### Install Development Dependencies / 安裝測試套件

The repository provides `requirements-dev.txt`, which includes the runtime requirements plus pytest. / 專案的 `requirements-dev.txt` 包含正式執行環境依賴及 pytest 測試套件。

```bash
cd ~/projects/linux-server-monitor
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest --version
```

### Run Tests / 執行測試

```bash
python -m pytest -v
python -m pytest -q
```

`-v` shows detailed test case names, while `-q` summarizes results more compactly. A zero exit code and all tests marked PASSED indicate that the tested functions met their assertions. / `-v` 查看每個案例的測試結果，`-q` 精簡輸出；所有測試通過代表本次涵蓋的功能符合斷言條件。

The v0.4 suite in `tests/test_monitoring.py` covers these cases / 測試涵蓋：

| Test area / 測試範圍 | Expected result / 預期結果 |
|---|---|
| Health endpoint (database available) / 資料庫正常 | HTTP 200, `healthy` |
| Health endpoint (database missing) / 資料庫不存在 | HTTP 503, `unhealthy` |
| History limit / 歷史筆數限制 | Latest N records returned correctly / 回傳最新 N 筆 |
| Invalid history limits / 錯誤參數（0、負數、過大、非數字） | HTTP 400 |
| Seven-day retention / 七天資料保留 | Old sample deleted; recent sample preserved / 舊資料刪除、新資料保留 |
| Dashboard home / 首頁 | HTTP 200 |

The tests use pytest's `tmp_path` and `monkeypatch` to create an isolated database and redirect `database.DB_PATH`. **They should not use or delete your actual `data/metrics.db`.** / pytest 測試透過 `tmp_path` 和 `monkeypatch` 指向獨立的暫存資料庫，不應操作正式監控資料。

**Testing note / 測試說明：** This suite focuses on database and Flask behavior. It does not by itself verify a real reboot, CDN access, end-to-end Windows networking, or that a systemd Timer is running; those require separate operational checks. / 自動化測試不能取代實機重開機、跨主機連線與 Timer 維運驗證。

---

## 16. v0.4 Verification Record / v0.4 驗收紀錄

The project author reported completing and successfully checking the v0.4 implementation. The following is a **record of reported results**, not a claim that this document independently ran tests on the VM. / 依專案作者回報，v0.4 功能與操作測試均已完成。此表為**已完成紀錄**，不使用待勾選項目，也不宣稱重新遠端驗證。

| Test / 驗證項目 | Verification method / 驗證方式 | Recorded result / 紀錄 |
|---|---|---|
| SQLite storage / 資料庫儲存 | `python collect_once.py` and SQL `COUNT(*)` / 手動收集與 SQL 統計 | Passed / 通過 |
| Automatic collection / 自動收集 | `metrics-collector.timer` active, records increase / Timer 運作、筆數增加 | Passed / 通過 |
| Collector logs / 收集日誌 | `journalctl -u metrics-collector.service` / 查看日誌 | Passed / 通過 |
| History API / 歷史資料 | `GET /api/history?limit=5` returns JSON / API 查詢正常 | Passed / 通過 |
| API validation / 參數驗證 | Invalid `limit` returns HTTP 400 / 錯誤參數被拒絕 | Passed / 通過 |
| CPU/RAM charts / 歷史圖表 | Browser chart display and sample selector / 瀏覽器折線圖及選單 | Passed / 通過 |
| Health API / 健康檢查 | `GET /api/health` returns expected healthy result / 基本健康狀態 | Passed / 通過 |
| Python logging / 日誌功能 | Collector INFO logs inspected / 收集成功日誌 | Passed / 通過 |
| Data retention / 資料清理 | Seven-day retention tested with isolated old/new sample data / 測試資料新舊紀錄處理 | Passed / 通過 |
| Automated tests / 自動化測試 | `python -m pytest -q` / 執行測試套件 | Passed / 通過 |
| Existing endpoints / 原功能 | Dashboard and `/api/system` continue working / 原有功能正常 | Passed / 通過 |

**Final local release checks / 發布前最後確認：**

```bash
systemctl status linux-server-monitor --no-pager
systemctl status metrics-collector.timer --no-pager
systemctl show metrics-collector.service -p Result -p ExecMainStatus
curl -i http://127.0.0.1/api/health
curl -i "http://127.0.0.1/api/history?limit=5"
python -m pytest -q
```

Use the outputs on **your own Ubuntu VM** as the authoritative evidence when releasing. / 正式發布時，以上指令在你 Ubuntu 上的實際輸出才是最終驗證依據。

---

## 17. v0.4 Troubleshooting / v0.4 故障排除

| Symptom / 現象 | First check / 優先檢查 |
|---|---|
| Timer does not run / Timer 沒啟動 | `systemctl status metrics-collector.timer --no-pager` and `systemctl list-timers --all` |
| Collector exits with error / 收集程式失敗 | `systemctl show metrics-collector.service -p Result -p ExecMainStatus`, then `sudo journalctl -u metrics-collector.service -n 50 --no-pager` |
| No SQLite history / 沒有歷史資料 | Run `python collect_once.py` and query `SELECT COUNT(*) FROM system_metrics;` |
| SQLite permission error / 資料庫權限錯誤 | Verify `User=xilin`, project path and ownership of `data/`; avoid running collectors as different users |
| `/api/history` returns 500 / API 發生伺服器錯誤 | Inspect `sudo journalctl -u linux-server-monitor -n 50 --no-pager`; verify DB path and table |
| `/api/health` returns 503 / 健康檢查失敗 | Confirm `data/metrics.db` and `system_metrics` table exist and are readable |
| Charts missing / 圖表不顯示 | Browser F12 Console/Network; check CDN access, `/static/history.js`, and History API response |
| Charts show old data / 歷史數據不更新 | Check Timer status, collection timestamps, chart selector, and browser caching |
| pytest fails / 測試失敗 | Activate `.venv`; install `requirements-dev.txt`; inspect specific assertion and ensure test DB isolation |

**Important / 注意：** A successful Health API response is not proof that sampling is fresh. Query the last `collected_at` and check Timer logs when diagnosing stale metrics. / `/api/health` 成功不代表歷史資料一定有持續更新；需查看最後收集時間及 Timer 日誌。

---

## 18. v0.5 — Docker Containerization / Docker 容器化部署

### Deployment Architecture / 部署架構

The monitoring dashboard is containerized using Docker Compose.
The host metrics collector remains managed by Ubuntu systemd.

Ubuntu Host:
- systemd Timer runs `collect_once.py`.
- SQLite stores historical data in `data/metrics.db`.
- The latest complete metrics are saved in `data/latest.json`.

Docker Container:
- Gunicorn serves the Flask application.
- The Dashboard is available on Ubuntu loopback Port 5003.
- The host `data/` directory is mounted read-only to `/app/data`.
- The container does not perform host resource sampling directly.

### Prerequisites / 部署前置條件

- Ubuntu 24.04 LTS
- Docker Engine
- Docker Compose Plugin
- Working v0.4 host metrics collector
- Existing SQLite database and latest.json
- Read permissions for Container UID 10001

### Build and Run / 建置與啟動

```bash
cd ~/projects/linux-server-monitor
python collect_once.py
sudo docker compose config
sudo docker compose up -d --build
```

### Verify / 驗證

```bash
sudo docker compose ps
curl -i http://127.0.0.1:5003/api/health
curl -i http://127.0.0.1:5003/api/system
curl -i "http://127.0.0.1:5003/api/history?limit=5"
```

### Logs / 日誌

Docker Dashboard:

```bash
sudo docker compose logs --tail=30 dashboard
```

Ubuntu Host Collector:

```bash
sudo journalctl -u metrics-collector.service -n 30 --no-pager
```

### Stop and Restart / 停止與重啟

Stop the Docker application:

```bash
sudo docker compose down
```

Rebuild and restart:

```bash
sudo docker compose up -d --build
```

The host SQLite data is not deleted by these commands.

### Troubleshooting / 故障排除

- HTTP 503: verify the host collector and Snapshot freshness.
- SQLite unavailable: verify the Bind Mount and read permissions.
- Container unhealthy: inspect Docker Health Check and logs.
- Port conflict: check whether Port 5003 is already occupied.
- Host metrics not updating: inspect the Ubuntu systemd Timer.

### Security and Limitations / 安全性與限制

- Port 5003 is bound to Ubuntu 127.0.0.1.
- The SQLite data directory is mounted read-only.
- The application runs as a non-root user.
- No authentication or HTTPS is configured.
- The containerized Dashboard depends on the Ubuntu host collector.
- Monitoring updates approximately every 30 seconds.
- The current deployment is intended for a trusted learning VM.
- Do not expose the application directly to the public internet.

---

## 19. v0.6 — GitHub Actions CI/CD & GHCR Deployment

### 1. CI/CD Workflow / 自動化流程

This project uses GitHub Actions to automate testing and Docker image publishing.

本專案使用 GitHub Actions 建立 CI/CD 自動化流程：

1. Push code to a feature branch.
2. Run Python syntax checks and pytest.
3. Build the Docker image and run Flask API smoke tests.
4. Create a Pull Request and pass required CI checks.
5. Merge the Pull Request into `main`.
6. Push a version tag (e.g., `v0.6.0`) to publish the Docker image to GHCR.

**Note:** GitHub Actions runs on a separate GitHub-hosted runner, not on the local VMware Ubuntu server. CI/CD does not automatically modify the local Ubuntu deployment.

### 2. Pull Docker Image / 下載映像檔

After the release image has been published to GHCR:

```bash
sudo docker pull ghcr.io/xilin0811/linux-server-monitor:v0.6.0
```

If the GHCR package is private, registry authentication with appropriate permissions is required.

### 3. Run the Container / 啟動容器

Start a standalone test container:

```bash
sudo docker run -d \
  --name monitor-v06-registry-test \
  -p 127.0.0.1:5006:5000 \
  ghcr.io/xilin0811/linux-server-monitor:v0.6.0
```

Verify the Flask API:

```bash
curl -i http://127.0.0.1:5006/api/health
curl -i http://127.0.0.1:5006/api/system
curl -i "http://127.0.0.1:5006/api/history?limit=5"
```

Stop and remove the test container:

```bash
sudo docker stop monitor-v06-registry-test
sudo docker rm monitor-v06-registry-test
```

### 4. Deployment Notes / 部署注意事項

- The GHCR image can be downloaded without rebuilding the Dockerfile locally.
- The standalone test container uses its own SQLite database.
- The production-style Ubuntu host monitoring setup still requires the host systemd collector and read-only bind mount.
- GitHub Actions does not automatically deploy to the local VMware VM.
- Published images should be verified before updating an existing deployment.
- Port 5006 is bound to Ubuntu's loopback interface and is not directly exposed to the external network.

## 20. Future Work / 後續規劃

The historical database, charts, health check, logging, retention policy and pytest testing belong to **v0.4 Completed**, not Future Work. / SQLite、歷史圖表、健康檢查、Logging、資料保留及 pytest 已列為 v0.4 完成項目，不再放入未來規劃。


### v1.0 — Production-Oriented Improvements / 正式環境強化

- Introduce authentication, HTTPS/TLS, and access controls. / 加入身分驗證、HTTPS 和權限控管。
- Improve metrics freshness checks, alerting and long-term retention strategies. / 增加資料新鮮度檢查、告警及長期保留設計。
- Extend test coverage and improve portability beyond the original VMware environment. / 擴充測試並提升跨環境部署能力。

---

