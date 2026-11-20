# Linux Deployment & Learning Guide / Linux 部署與學習筆記

> **Final learning version / 最終學習版本：v0.6.0 — Completed**  
> **Environment / 學習環境：** Windows + VMware + Ubuntu 24.04 LTS + Python 3.12  
> **Project：** [Linux Server Monitoring Dashboard](../README.md)  
> **Goal / 目的：** 可重新操作、可理解原理、可快速排錯；不是公開網際網路的正式營運部署指南。

這份文件將原本 v0.3／v0.4 的 Linux 部署記錄，與後續 v0.5 Docker、v0.6 GitHub Actions 整合成**從簡到難、按用途查閱**的學習筆記。每個重要步驟提供指令、**為什麼**、**預期結果**與注意事項。已有服務運作的 VM 不需要從頭重新執行全部安裝指令；建議只做對應章節的**唯讀檢查**。

> **Absolute paths / 路徑注意：** 以下部分範例沿用原學習 VM 的使用者 `xilin` 及 `/home/xilin/projects/linux-server-monitor`。移植到別台電腦必須修改；不要不經確認就覆蓋 `/etc/nginx/` 或 `/etc/systemd/system/` 的既有設定。

## 目錄 / Contents

1. [快速定位：你現在在操作哪個環境？](#1-快速定位你現在在操作哪個環境)
2. [核心概念：整套系統怎麼合作？](#2-核心概念整套系統怎麼合作)
3. [Python 環境與第一次啟動 Flask](#3-python-環境與第一次啟動-flask)
4. [v0.2：Gunicorn + Nginx](#4-v02gunicorn--nginx)
5. [v0.3：systemd 管理 Web Service](#5-v03systemd-管理-web-service)
6. [v0.4：SQLite、Collector、Timer、圖表與 pytest](#6-v04sqlitecollector-timer圖表與-pytest)
7. [v0.5：Docker Image、Container、Network、Volume](#7-v05docker-imagecontainernetworkvolume)
8. [v0.5：Docker Compose + Ubuntu Host Snapshot](#8-v05docker-compose--ubuntu-host-snapshot)
9. [v0.6：GitHub Actions CI/CD、PR、GHCR](#9-v06github-actions-cicdprghcr)
10. [完整驗收與日常維運](#10-完整驗收與日常維運)
11. [故障排除：從症狀找原因](#11-故障排除從症狀找原因)
12. [安全、資料備份、清理與範圍](#12-安全資料備份清理與範圍)
13. [術語速查與常用指令](#13-術語速查與常用指令)

---

## 1. 快速定位：你現在在操作哪個環境？

你有 **Windows 實體電腦、VMware Ubuntu 虛擬機器、Ubuntu 裡的 Docker Container，以及 GitHub Actions Runner** 四種不同環境。**先認環境，再看 IP 與 Port。**

### 1.1 環境層次

```text
Windows host (Chrome / VS Code)
    |
    | VMware virtual network (NAT / Bridged; depends on VM settings)
    v
Ubuntu 24.04 VM (Linux host)
    |-- Nginx :80
    |-- Native Gunicorn 127.0.0.1:5000
    |-- systemd: web service + metrics collector timer
    |-- data/metrics.db and data/latest.json
    |
    `-- Docker Engine
          |-- Image = reusable application template
          `-- Container = running instance of an image
                 `-- Gunicorn 0.0.0.0:5000 (container network)

GitHub Actions Runner = separate GitHub-hosted machine (NOT this VMware VM)
```

### 1.2 IP 與 Port 對照

| 從哪裡連線 | URL／位址 | 實際對象 | 意義 |
| --- | --- | --- | --- |
| Windows Chrome | `http://<UBUNTU_VM_IP>/` | Ubuntu :80 → Nginx → 原生 Gunicorn | 原本 v0.4 Native 站台 |
| Ubuntu Terminal | `http://127.0.0.1:5000/` | Ubuntu 本機 Gunicorn | 不經 Nginx 的原生後端 |
| Ubuntu Terminal | `http://127.0.0.1/` | Ubuntu Nginx :80 | 測試反向代理 |
| Ubuntu Terminal | `http://127.0.0.1:5003/` | Docker Port Mapping → Container :5000 | v0.5 Compose Dashboard |
| Docker Container 內 | `http://127.0.0.1:5000/` | 該容器自己的 Gunicorn | 與 Ubuntu localhost 不同 |
| Windows Chrome（已轉發 Port 5003） | `http://localhost:5003/` | Windows Port Forwarding → Ubuntu 5003 → Container | Windows 自己的 localhost |
| GitHub Runner | `http://127.0.0.1:5004/`（CI） | Runner 上的測試 Container | 不會連到 VMware |

`<UBUNTU_VM_IP>` 不是固定數字。Ubuntu Terminal 執行：

```bash
hostname -I
```

**為什麼：** `127.0.0.1`（Loopback）永遠指「目前網路命名空間中的自己」。Windows、Ubuntu、Container 各有自己的 localhost；VS Code Port Forwarding 是額外建立的通道，不代表它們共用 IP。

### 1.3 如何知道指令在哪裡執行？

| 指令 | 位置／作用 |
| --- | --- |
| `pwd` | 目前 Ubuntu Shell 的工作目錄 |
| `sudo docker ps` | 從 Ubuntu 要求 Docker Engine 列出容器 |
| `sudo docker build -t name:tag .` | Docker 使用目前目錄作 Build Context，預設找 `Dockerfile` |
| `sudo docker run -d ...` | 透過 Image 建立並**背景啟動** Container，執行完仍回到 Ubuntu Shell |
| `sudo docker exec <container> pwd` | 在指定 Container 中執行 `pwd` |
| `sudo docker exec -it <container> sh` | 開啟 Container 互動式 Shell（輸入 `exit` 離開） |
| `sudo docker compose exec dashboard sh` | 在 Compose 的 dashboard Service 容器內開 Shell |
| `curl -i http://127.0.0.1:5003/api/health` | 在 Ubuntu 發 HTTP 請求，透過 Port Mapping 進容器 |

`curl` 是 HTTP 工具，**不是 Docker 專用指令**。`-i` 會顯示 HTTP 標頭及回應內容。`HTTP 200` 表示該請求成功，不代表整台機器所有功能都已經驗證。

---

## 2. 核心概念：整套系統怎麼合作？

### 2.1 Native Ubuntu（v0.4）

```text
Windows Browser
  -> Ubuntu VM IP :80
  -> Nginx Reverse Proxy
  -> Ubuntu 127.0.0.1:5000 (Gunicorn, systemd-managed)
  -> Flask app.py
      |-- GET /api/system  -> monitor.py / psutil
      |-- GET /api/history -> database.py / data/metrics.db
      |-- GET /api/health  -> SQLite readability
      `-- GET /           -> HTML + JS + Chart.js

metrics-collector.timer
  -> metrics-collector.service (oneshot)
  -> collect_once.py
  -> monitor.py -> database.py -> data/metrics.db (retains ~7 days)
```

**各元件責任：**

- **Nginx**：接收 HTTP，Reverse Proxy 到 Gunicorn；不執行你的 Python 程式。
- **Gunicorn**：WSGI Server，使用 Worker Process 執行 Flask。
- **Flask**：處理 Route、API、回傳 JSON 或 HTML。
- **psutil**：讀取 CPU／Memory／Disk／Uptime。
- **systemd**：管理長期運作的 Gunicorn 及定時的一次性 Collector；不處理 HTTP 路由。
- **SQLite**：保存 CPU、RAM、Disk 的歷史資料；不是由 Nginx 儲存。
- **Chart.js**：前端以 API 返回的歷史資料繪製折線圖。

### 2.2 Docker Host Snapshot（v0.5）

```text
Ubuntu VM Host
  metrics-collector.timer -> collect_once.py
                                  |-- data/metrics.db
                                  `-- data/latest.json
                                      |   (read-only bind mount: ./data -> /app/data)
                                      v
                              Docker Compose dashboard
                              Gunicorn :5000 -> Flask
Ubuntu 127.0.0.1:5003 ------^    |-- /api/system: latest.json
                                   |-- /api/history: SQLite read-only
                                   `-- /api/health: DB + Snapshot freshness
```

為什麼要讓 Collector 保留在 Host？因為 `psutil` 在 Container 內看到的部分資源與掛載視圖，未必等於 Ubuntu 主機。**讓 Host 收集主機數據，Container 唯讀顯示**，能避免把 Container 的 `/` 磁碟視圖誤當主機磁碟。

**v0.6 只增加 CI／CD 與版本化 Image 發布**，不改變上述的主要監控邏輯，也不會自動把 GitHub Runner 上的 Image 部署到這台 Ubuntu VM。

---

## 3. Python 環境與第一次啟動 Flask

### 3.1 建立 Python 虛擬環境

首次部署時：

```bash
sudo apt update
sudo apt install python3-venv python3-pip

mkdir -p ~/projects
cd ~/projects
git clone https://github.com/xilin0811/linux-server-monitor.git
cd linux-server-monitor
python3 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install -r requirements-dev.txt
```

| 指令 | 為什麼需要 | 預期結果 |
| --- | --- | --- |
| `apt update` | 更新 APT 套件索引（不是升級所有套件） | 取得最新來源資訊 |
| `python3 -m venv .venv` | 在專案中建立獨立 Python 環境 | 產生 `.venv/` |
| `source .venv/bin/activate` | 讓目前 Shell 優先使用虛擬環境的 Python／pip | Terminal 常出現 `(.venv)` |
| `pip install -r requirements-dev.txt` | 安裝 Runtime Requirements 和 pytest | 依賴安裝成功 |

如果**原本已建立 `.venv`**，不需要再次 Clone 或新建，直接：

```bash
cd ~/projects/linux-server-monitor
source .venv/bin/activate
```

`sqlite3`、`json` 和 `logging` 是 Python 標準函式庫，不需要另外 `pip install sqlite3`。systemd 不會繼承你互動式 Terminal 的 `.venv` 啟用狀態，因此 Unit File 需要指定 Python 或 Gunicorn 的**絕對路徑**。

### 3.2 第一次初始化 SQLite（適用空白環境）

```bash
python collect_once.py
ls -lh data/metrics.db data/latest.json
```

**為什麼：** Collector 會初始化資料表、收集一筆 CPU／RAM／Disk 歷史數據，並保存最新的完整 Host Snapshot。這能讓 `/api/health` 和歷史資料有可查詢的內容。

### 3.3 開發模式啟動 Flask

> 只在 Port 5000 沒有被既有 systemd Gunicorn 使用時執行。正在使用原本 v0.4 部署的 VM，不需要重跑這一步。

```bash
python app.py
```

從 **Ubuntu 本機**：

```bash
curl -i http://127.0.0.1:5000/api/system
```

**預期：** HTTP 200 + JSON。此為 Flask Development Server，僅用於開發與除錯。按 `Ctrl + C` 停止。若從 Windows 連線，請用 VS Code SSH Port Forwarding，不要直接假設 Windows localhost 就是 Ubuntu。

---

## 4. v0.2：Gunicorn + Nginx

### 4.1 Gunicorn 是什麼？

Flask 的 `python app.py` 使用 Development Server；Gunicorn 是部署時使用的 **WSGI Application Server**。手動啟動：

```bash
gunicorn --workers 2 --bind 127.0.0.1:5000 app:app
```

| 語法 | 作用 |
| --- | --- |
| `--workers 2` | 建立兩個 Worker Process |
| `--bind 127.0.0.1:5000` | 只監聽 Ubuntu Host 的 Loopback Port 5000 |
| `app:app` | 從 `app.py` 模組載入名叫 `app` 的 Flask 物件 |

**先停掉同 Port 的其他程序**，否則會看到 `Address already in use`。另開 Ubuntu Terminal：

```bash
curl -i http://127.0.0.1:5000/api/health
```

預期 HTTP 200（SQLite 已初始化時）。這個測試**不經過 Nginx**，有利於將後端問題與 Reverse Proxy 問題區分。測完按 `Ctrl + C` 停掉手動 Gunicorn。

### 4.2 安裝與設定 Nginx

```bash
sudo apt install nginx
systemctl status nginx --no-pager
```

預期 Nginx `active (running)`。專案已提供 `deployment/nginx.conf`；目前的設計是 **Nginx Port 80 → Gunicorn 127.0.0.1:5000**。

```nginx
location / {
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

- `location /`：符合根目錄、API、靜態資源等請求。
- `proxy_pass`：設定上游應用程式的 IP／Port。
- `proxy_set_header`：傳遞原始請求的 Host、IP、Protocol 資訊。

**第一次安裝或已備份現有設定後**，可使用：

```bash
sudo cp deployment/nginx.conf /etc/nginx/sites-available/linux-server-monitor
sudo ln -s /etc/nginx/sites-available/linux-server-monitor /etc/nginx/sites-enabled/linux-server-monitor
sudo nginx -t && sudo systemctl reload nginx
```

`ln -s` 建立 Symbolic Link；已存在同名連結就**不要再建立**。在既有 VM 上，`cp` 會覆蓋目的地，先比較內容、確認其他站台沒有監聽 Port 80 衝突。`nginx -t && reload` 表示**語法正確才重新載入**。

測試：

```bash
curl -i http://127.0.0.1/api/health
hostname -I
```

Windows Chrome：`http://<UBUNTU_VM_IP>/`。若使用 VMware NAT，Windows 通常透過 VMware 虛擬網路連接 Ubuntu；IP 可能因重開機而改變。**Nginx 502** 通常要先檢查 Gunicorn，而不是直接重裝 Nginx。

---

## 5. v0.3：systemd 管理 Web Service

### 5.1 為什麼要使用 systemd？

手動執行的 Gunicorn 依附於你啟動它的 Terminal；希望服務在 SSH 中斷、Ubuntu 重開機或程序異常後持續可用，就需要讓系統管理它。`systemd` 是 Ubuntu 的 Service Manager。

專案範本：`deployment/linux-server-monitor.service`

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

| 欄位 | 為什麼需要 |
| --- | --- |
| `Type=simple` | 讓 systemd 追蹤長時間運作的 Gunicorn 主程序 |
| `User` / `Group` | 使用一般帳號執行，不必把 Web Server 交給 root |
| `WorkingDirectory` | 設定 Python 專案目錄，避免相對路徑錯誤 |
| `ExecStart` | 用 `.venv/bin/gunicorn` 絕對路徑，不仰賴 Terminal `source` |
| `Restart=on-failure` | 異常結束時嘗試自動重啟 |
| `RestartSec=5` | 重啟前等待約五秒 |
| `WantedBy=multi-user.target` | 允許設定開機啟用 |

`After=network.target` 管理啟動順序，**不保證網際網路已連線**。

### 5.2 安裝服務（首次設定）

**先停止手動啟動的 Gunicorn**，並確認這些設定檔符合你的使用者及路徑：

```bash
sudo ss -lntp | grep ':5000 ' || true
sudo cp deployment/linux-server-monitor.service /etc/systemd/system/linux-server-monitor.service
sudo systemd-analyze verify /etc/systemd/system/linux-server-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now linux-server-monitor
```

已完成部署的 VM 不要再次隨意 `cp` 覆蓋設定，先使用以下**唯讀查詢**：

```bash
systemctl status linux-server-monitor --no-pager
systemctl is-enabled linux-server-monitor
```

**預期：** 分別為 `active (running)` 與 `enabled`。

- `start`：現在啟動。
- `enable`：設定開機自動啟動（不等於立刻啟動）。
- `enable --now`：同時做兩件事。
- `daemon-reload`：修改 Unit File 後重新讀取設定。

### 5.3 驗證 SSH 中斷、重開機與故障恢復

驗證原理：

1. 先從 Windows 透過 `http://<UBUNTU_VM_IP>/` 確認 Dashboard 可開啟。
2. 中斷 VS Code Remote SSH，再重新整理 Windows Chrome；若仍可連線，代表服務不依賴 SSH Terminal。
3. 儲存工作後在 Ubuntu 執行 `sudo reboot`；重新開機後確認 `systemctl status` 與 Windows 網頁。
4. 若要練習程序故障恢復，先確認 Gunicorn PID 與 Service 身分，再於隔離 VM 中進行受控測試；**不要對不明程序執行 `kill -9`**。

**重要：** systemd 可以在 **Ubuntu VM 開機之後**啟動服務，但不會自動幫你打開已關閉的 VMware 虛擬機器。上述項目是原始學習環境曾執行的驗收步驟，不代表每次重新部署都自動完成。

### 5.4 管理與日誌

```bash
sudo systemctl start linux-server-monitor
sudo systemctl stop linux-server-monitor
sudo systemctl restart linux-server-monitor
systemctl status linux-server-monitor --no-pager
sudo journalctl -u linux-server-monitor -n 50 --no-pager
sudo journalctl -u linux-server-monitor -b --no-pager
sudo journalctl -u linux-server-monitor -f
```

`journalctl -u` 指定 Unit；`-n 50` 查最近 50 筆；`-b` 只看本次開機；`-f` 持續追蹤（`Ctrl + C` 離開）；`--no-pager` 不進入分頁工具。**主動 stop** 一般不算 `on-failure` 要處理的意外崩潰。

---

## 6. v0.4：SQLite、Collector Timer、圖表與 pytest

### 6.1 兩條不同的數據路徑

- **即時 `/api/system`（Native 模式）**：收到請求時呼叫 `monitor.py` 和 `psutil`，每次重新量測。
- **歷史 `/api/history`**：讀取 `data/metrics.db`，不是每個前端請求都直接寫資料庫。
- **Collector**：systemd Timer 定期執行 `collect_once.py`，收集一次、寫入 SQLite、更新 `latest.json`、清理七天前的資料。

前端 Live Cards 約每 **5 秒** Poll 一次 API；CPU／RAM 歷史圖表約每 **30 秒**查詢一次 History API。Chart.js 目前使用 CDN，沒有網際網路時圖表可能無法載入。

### 6.2 SQLite Schema / 資料表

`database.py` 透過 `init_database()` 初始化：

```sql
CREATE TABLE IF NOT EXISTS system_metrics (
    id INTEGER PRIMARY KEY,
    collected_at INTEGER NOT NULL,
    cpu_percent REAL NOT NULL,
    memory_percent REAL NOT NULL,
    disk_percent REAL NOT NULL
);
```

還有 `collected_at` 的索引，支援時間範圍或最新資料查詢。

| 欄位 | 意義 |
| --- | --- |
| `id` | 自增／唯一的資料列識別碼 |
| `collected_at` | Unix Timestamp（秒） |
| `cpu_percent` | CPU 使用率百分比 |
| `memory_percent` | 記憶體使用率百分比 |
| `disk_percent` | `/` 檔案系統使用率百分比 |

**資料庫位置（Ubuntu Host）：** `/home/xilin/projects/linux-server-monitor/data/metrics.db`。專案以 Python 原始碼路徑來組合資料庫路徑，不依賴你從哪個 Terminal 目錄執行。

### 6.3 手動收集、驗證 SQL

```bash
cd ~/projects/linux-server-monitor
source .venv/bin/activate
python collect_once.py
ls -lh data/metrics.db data/latest.json
python -m sqlite3 data/metrics.db "SELECT COUNT(*) FROM system_metrics;"
python -m sqlite3 data/metrics.db "SELECT id, datetime(collected_at, 'unixepoch', 'localtime'), cpu_percent, memory_percent, disk_percent FROM system_metrics ORDER BY id DESC LIMIT 5;"
```

**預期：** Collector 輸出一筆 `INFO` 日誌、資料庫新增紀錄、SQL 能看到資料。`COUNT(*)` 統計列數；`ORDER BY id DESC LIMIT 5` 顯示最新 5 筆。

如 `python -m sqlite3` 在你實際的 Python 環境無法使用，可改用 Python 標準函式庫：

```bash
python - <<'PY'
import sqlite3
with sqlite3.connect('data/metrics.db') as con:
    print(con.execute('SELECT COUNT(*) FROM system_metrics').fetchone()[0])
PY
```

### 6.4 為什麼用 systemd Timer，而不是無窮迴圈？

因為 Gunicorn 有多個 Workers，若在 Flask 啟動時安排持續收集，可能每個 Worker 都跑一次，造成重複資料。分成兩個獨立 Units：

- `metrics-collector.service`：`Type=oneshot`，執行一次 `collect_once.py` 後結束。
- `metrics-collector.timer`：定期觸發該 Service。

Repository 提供 `deployment/metrics-collector.service` 和 `.timer`。Timer 核心設定：

```ini
[Timer]
OnBootSec=1min
OnUnitInactiveSec=30s
AccuracySec=1s
Unit=metrics-collector.service
```

- `OnBootSec=1min`：依 Ubuntu 開機時間安排首次觸發。
- `OnUnitInactiveSec=30s`：前次 Service 完成後約 30 秒再觸發。
- `AccuracySec=1s`：時間準確度視窗，不是硬即時保證。

所以這不是嚴格**每隔剛好 30 秒**取得一筆資料，也不會在 Ubuntu 關機時自動補齊資料。

首次安裝（請確認路徑、不要覆蓋既有個人化設定）：

```bash
sudo cp deployment/metrics-collector.service /etc/systemd/system/
sudo cp deployment/metrics-collector.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/metrics-collector.service
sudo systemd-analyze verify /etc/systemd/system/metrics-collector.timer
sudo systemctl daemon-reload
sudo systemctl start metrics-collector.service
systemctl show metrics-collector.service -p Result -p ExecMainStatus
sudo systemctl enable --now metrics-collector.timer
```

預期：`Result=success`、`ExecMainStatus=0`；Timer 為 `active (waiting)`。Oneshot Service 執行完可能顯示 `inactive (dead)`，**不代表失敗**。

日常檢查：

```bash
systemctl status metrics-collector.timer --no-pager
systemctl list-timers --all | grep metrics-collector
sudo journalctl -u metrics-collector.service -n 30 --no-pager
```

### 6.5 API 介面與預期回應

| API | 正常用途 | 重要錯誤回應 |
| --- | --- | --- |
| `GET /api/system` | CPU、RAM、Disk、Uptime 的 JSON | Host Snapshot 過期時可回傳 503 |
| `GET /api/history` | 預設最近 60 筆歷史紀錄 | DB 出錯可能 500 |
| `GET /api/history?limit=5` | 最近 5 筆，結果由舊到新 | `limit` 非 1～300 的整數時 400 |
| `GET /api/health` | 檢查 SQLite；Host Snapshot 模式再檢查新鮮度 | 無法讀取／資料過期時 503 |

```bash
# Native Ubuntu through Nginx
curl -i http://127.0.0.1/api/health
curl -sS "http://127.0.0.1/api/history?limit=5" | python -m json.tool

# Invalid query parameter: should return HTTP 400
curl -i "http://127.0.0.1/api/history?limit=abc"
curl -i "http://127.0.0.1/api/history?limit=0"
```

Health 成功回應示例：

```json
{"status":"healthy","database":"ok"}
```

歷史成功回應包含 `count` 和 `metrics` 陣列；每筆包含 `id`、`collected_at`、`cpu_percent`、`memory_percent`、`disk_percent`。讀取成功**不代表**資料庫可寫、Timer 活著、整個主機沒有異常。

### 6.6 七天資料保留與備份

Collector 每次寫入後，呼叫 `delete_old_metrics(days=7)`，刪除比目前 Unix 時間早七天以上的資料：

```sql
DELETE FROM system_metrics WHERE collected_at < ?;
```

其中 `?` 由程式帶入時間門檻，避免自行拼字串。刪除列後 SQLite `.db` 檔案大小未必立即下降，因為頁面可能保留待重用。

**重要：** 刪除是真實變更；不要拿有意義的監控資料隨便做破壞性測試。備份推薦 SQLite Backup API：

```bash
cd ~/projects/linux-server-monitor
source .venv/bin/activate
python - <<'PY'
import sqlite3
from pathlib import Path
src = Path('data/metrics.db')
dst = Path('data/metrics-backup.db')
from contextlib import closing
with closing(sqlite3.connect(src)) as source, closing(sqlite3.connect(dst)) as target:
    source.backup(target)
print(f'Backup completed: {dst}')
PY
```

此方式比 Collector 正在寫入時直接 `cp` 資料庫檔案更適合取得一致的備份。備份仍留在本機 `data/`，**不是異地備份**。

### 6.7 pytest 自動化測試

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -v
python -m pytest -q
```

- `-v`：Verbose，逐個顯示測試名稱。
- `-q`：Quiet，精簡結果。
- 測試透過 pytest `tmp_path` 與 `monkeypatch` 指向隔離的測試資料庫，不應修改真實 `data/metrics.db`。
- 測試內容涵蓋基本 API、錯誤參數、SQLite、七天保留、Host Snapshot 正常及過期情境（以目前測試檔為準）。
- pytest 通過**不能取代** Nginx／VMware／systemd 重開機／真實網路驗收。

---

## 7. v0.5：Docker Image、Container、Network、Volume

### 7.1 Docker Engine / Dockerfile / Image / Container

| 名詞 | 白話理解 | 專案實例 |
| --- | --- | --- |
| Docker Engine | Ubuntu 裡管理 Container 的軟體 | `sudo docker ps` |
| Dockerfile | 建置 Image 的指令配方 | `FROM python:3.12-slim` |
| Image | 包含執行環境、程式、啟動設定的可重用範本 | `linux-server-monitor:v0.5-compose` |
| Container | 由 Image 建立並執行的一個實例 | Compose 的 `dashboard` |
| `.dockerignore` | 排除不應送入 Build Context 的檔案 | `.venv/`、`data/` |
| Docker Compose | 使用 YAML 管理服務、Port、Volume 等 | `compose.yaml` |

### 7.2 Build Image 與路徑觀念

```bash
cd ~/projects/linux-server-monitor
sudo docker build -t linux-server-monitor:learning .
sudo docker image ls
```

`-t` 指定 Image 名稱及 Tag；最後的 `.` 是**目前目錄作為 Build Context**，不是 Linux 的 `/` 根目錄。Docker 預設找該 Context 根目錄的 `Dockerfile`。`COPY` 將必要的 Python 原始碼複製進 Image，`RUN` 在建置時執行（例如 `pip install`），`CMD` 則指定 Container 啟動時的預設命令。

目前 Dockerfile 使用 `python:3.12-slim`、`WORKDIR /app`、安裝 `requirements.txt`、複製程式和靜態資源、建立非 root 的 `appuser`（UID/GID 10001），最後透過 `docker-entrypoint.sh` 啟動 Gunicorn。

**`appuser` 不是 Ubuntu 的 `xilin` 帳號。** 它是 Container 中的低權限使用者。之後掛載外部資料夾時，仍需要考慮 UID/GID 的 Linux 權限。

### 7.3 啟動 Standalone Container（學習實驗）

> 以下 `5006` 只是例子。若正在使用同名 Container 或 Port 5006，先檢查 `docker ps -a`，不要直接重建覆蓋。

```bash
sudo docker run -d \
  --name monitor-learning \
  -p 127.0.0.1:5006:5000 \
  linux-server-monitor:learning

sudo docker ps
curl -i http://127.0.0.1:5006/api/health
sudo docker exec monitor-learning whoami
sudo docker exec monitor-learning pwd
```

預期：`/api/health` HTTP 200，`whoami` 為 `appuser`，`pwd` 為 `/app`。

**網路解釋：** `-p 127.0.0.1:5006:5000` 表示 **Ubuntu Host 5006 → Container 5000**；Container 的 Gunicorn 綁定 `0.0.0.0:5000`，使 Docker 能透過其網路介面轉發請求。Host 的 `127.0.0.1` 與 Container 的 `127.0.0.1` 並不相同。

**`-d`** 是背景執行，返回 Ubuntu Shell；不是進入 Container。需要進入 Container：

```bash
sudo docker exec -it monitor-learning sh
# The following commands now execute inside the container:
pwd
whoami
exit
```

清理本次學習用 Container：

```bash
sudo docker stop monitor-learning
sudo docker rm monitor-learning
```

### 7.4 Docker Network / Container DNS

```bash
sudo docker network ls
sudo docker network inspect bridge
sudo docker port monitor-learning  # only if this container still exists
```

- `bridge`：Docker 的常見網路模式，每個 Container 可以有自己的網路介面及 IP。
- `127.0.0.1`：目前網路命名空間自己。
- **User-defined Bridge**：同網路的 Container 可以用 DNS 名稱彼此找到對方。
- 容器 IP（例如 `172.17.x.x`）可能改變，不應當成永久入口。

Compose 也能建立自己的專用 Network；即使已學過 Network，這個專案最終仍是透過 Port Publishing 提供 Dashboard 測試入口。

### 7.5 Named Volume 與 Bind Mount（不要混淆）

| 項目 | Named Volume | Bind Mount |
| --- | --- | --- |
| 誰決定儲存位置 | Docker 管理 | Ubuntu Host 指定路徑 |
| 典型語法 | `source=monitor-v05-lab-data,target=/app/data` | `source=./data,target=/app/data` |
| 刪掉 Container | Volume 通常仍保留 | Host 資料夾仍保留 |
| 本專案用途 | 學習 SQLite Persistence | 最終 Host Collector 資料共享 |

Named Volume 不會自動等於專案的 `data/metrics.db`；它是由 Docker 管理的**另一份資料**。

若要查看 Docker 已建立的 Volume：

```bash
sudo docker volume ls
sudo docker volume inspect monitor-v05-lab-data
```

`Mountpoint` 是 Volume 在 Ubuntu Docker Host 上的儲存位置（常見為 `/var/lib/docker/volumes/...`，實際以 `inspect` 為準）。一般不應直接修改 Docker 管理目錄的檔案。

**Persistence 的實驗結論：** 建立 Named Volume → 掛載到 `/app/data` → Container 寫入 SQLite → 刪除並重建 Container → 使用同一個 Volume 仍能查到原本紀錄。前提是不要另外刪除 Volume。

---

## 8. v0.5：Docker Compose + Ubuntu Host Snapshot

### 8.1 YAML 是什麼？

YAML 是**結構化設定格式**，不是 Python 程式碼。縮排代表階層、`key: value` 表示設定、`-` 表示清單項目；使用空白而不是 Tab 縮排。

- `Dockerfile`：描述 Image **怎麼建置**。
- `compose.yaml`：描述服務**怎麼啟動**、Port 怎麼轉發、資料怎麼掛載。
- `docker compose config`：檢查 Compose YAML 設定（不會啟動容器）。

### 8.2 最終 Compose 的關鍵設定

Repository 的 `compose.yaml` 含有：

```yaml
services:
  dashboard:
    build:
      context: .
      dockerfile: Dockerfile
    image: linux-server-monitor:v0.5-compose
    ports:
      - "127.0.0.1:5003:5000"
    environment:
      MONITOR_SOURCE: host_snapshot
      MONITOR_SNAPSHOT_PATH: /app/data/latest.json
      DB_READ_ONLY: "1"
    volumes:
      - type: bind
        source: ./data
        target: /app/data
        read_only: true
        bind:
          create_host_path: false
```

| 設定 | 實際意義 |
| --- | --- |
| `build.context: .` | 以 Repository 目錄做 Docker Build Context |
| `image: ...v0.5-compose` | 在本地建置的 Image Tag（不是 GHCR v0.6.0） |
| `ports` | Ubuntu `127.0.0.1:5003` → Container :5000 |
| `MONITOR_SOURCE=host_snapshot` | `/api/system` 讀取 Ubuntu Collector 的 `latest.json` |
| `MONITOR_SNAPSHOT_PATH` | Container 中 Snapshot 的讀取路徑 |
| `DB_READ_ONLY=1` | 使用 SQLite 唯讀連線；啟動時不重新初始化 Host DB |
| `source: ./data` / `target: /app/data` | Ubuntu 專案資料目錄 → 容器資料目錄 |
| `read_only: true` | Container 不能透過此掛載修改 Host 資料 |
| `create_host_path: false` | Host 資料夾不存在時直接報錯，而非默默建立空目錄 |

### 8.3 為什麼要使用 latest.json？

在 Ubuntu 上執行的 Collector 會同時：

1. 使用 `psutil` 取得 Host CPU／Memory／Disk／Uptime。
2. 寫入 `data/metrics.db`（歷史資料）。
3. 將完整最新數據與 `collected_at` 寫入 `data/latest.json`。
4. 執行七天前歷史資料清理。

Container 用唯讀掛載取得 Host 的兩份檔案。`/api/system` 的讀取模式會檢查時間戳，若 Snapshot 超過約 **120 秒**未更新，會回傳 HTTP 503，而不是把陳舊數據當成即時資料。

**重要差異：** 網頁每 5 秒 Poll API，不代表 Host 每 5 秒重新採樣；Host Collector 約每 30 秒執行一次，因此部分卡片數值在連續數次刷新時可能相同。

### 8.4 啟動前檢查（避免破壞既有服務）

```bash
cd ~/projects/linux-server-monitor
source .venv/bin/activate

# Confirm collector and data
systemctl status metrics-collector.timer --no-pager
ls -lh data/metrics.db data/latest.json
stat -c '%A %U:%G %n' data data/metrics.db data/latest.json

# Read the generated configuration before applying it
sudo docker compose config
```

**Expected / 預期：** Timer 顯示 `active (waiting)`，兩個檔案存在，Compose 設定合法。由於 Container 使用 UID 10001，必須能讀取 Host 的資料夾與檔案。若遇到 Permission denied，先確認擁有權與 ACL，**不要使用 `chmod -R 777`**。

若只是更新已運作的同一個 Compose 服務：

```bash
sudo docker compose up -d --build
sudo docker compose ps
```

第一次部署且需要先建立新 Snapshot，可在 Ubuntu Host 執行：

```bash
python collect_once.py
```

**這裡執行的是 Ubuntu 的 Python，不是 Container 裡的 Python**，所以收集的是 Ubuntu Host Metrics。

### 8.5 檢查 Host Snapshot、SQLite 與健康狀態

```bash
# API through Docker Port Publishing
curl -i http://127.0.0.1:5003/api/health
curl -sS http://127.0.0.1:5003/api/system | python -m json.tool
curl -sS "http://127.0.0.1:5003/api/history?limit=5" | python -m json.tool

# Compare host snapshot
python -m json.tool data/latest.json

# Confirm read-only bind mount
sudo docker compose ps -q dashboard
sudo docker inspect "$(sudo docker compose ps -q dashboard)" --format '{{json .Mounts}}'
```

**Expected / 預期：** HTTP 200；`/api/system` 與 Host `latest.json` 對應；`.Mounts` 有 `"Destination":"/app/data"` 及 `"RW":false`。若剛好跨越 Timer 收集時刻，兩次查詢可能差一筆 Snapshot。

### 8.6 查看狀態與日誌

```bash
sudo docker compose ps
sudo docker compose logs --tail=50 dashboard
sudo journalctl -u metrics-collector.service -n 50 --no-pager
```

- Compose `healthy`：Docker Health Check 的結果。
- HTTP 503 / `unhealthy`：可能是 SQLite 不可讀、`latest.json` 不存在或超過 120 秒沒有更新。
- **Docker Health Check 不保證 Container 變成 unhealthy 後會自動重啟。** Restart Policy 是不同功能。

### 8.7 停止、重建與資料安全

```bash
# Stop and remove Compose-managed application/network; host data remains
sudo docker compose down

# Recreate from Dockerfile
sudo docker compose up -d --build
```

因為 Host `data/` 是透過 Bind Mount 掛載，**這兩條命令不會刪除 Host 的 SQLite 和 Snapshot**。但請勿使用未知清理指令刪掉 Host 資料夾。

**目前的 Compose Image 名稱是 `linux-server-monitor:v0.5-compose`；不是 `ghcr.io/...:v0.6.0`。** 如果只在 GHCR 下載 v0.6 Image，並不會讓正在運作的 Compose Container 自動更新。

---

## 9. v0.6：GitHub Actions CI/CD、PR、GHCR

### 9.1 CI 和 CD 各做什麼？

- **CI（Continuous Integration）**：每次 Push／PR，自動安裝依賴、執行 pytest、Build Docker Image，並測試 API。
- **CD（在本專案為 Image Delivery）**：正式版本 Git Tag 觸發建置／測試及 Image Push 到 GHCR。
- **不包含**：SSH 到 VMware 自動拉 Image、替換 Container、正式環境 Rolling Deploy 或 Rollback。

### 9.2 GitHub Actions Runner 是另外一台機器

```text
Ubuntu VM / VS Code
   -> git push
   -> GitHub Repository
        -> GitHub-hosted Runner (separate Ubuntu machine)
             -> Checkout source
             -> Python 3.12 + pytest
             -> docker build
             -> docker run + HTTP Smoke Test
             -> GitHub Actions result
```

Runner 不會繼承你的 VMware `/home/xilin/`、SQLite、systemd Timer 或已安裝的套件。`pytest` 使用隔離資料庫；Docker Smoke Test 啟動**獨立測試容器**，不代表已驗證你的 VMware Host Collector。

### 9.3 Python + Docker CI：`.github/workflows/ci.yml`

| Trigger | Job | Purpose |
| --- | --- | --- |
| Push `main` / `feature/**` | `python-tests` | Python 3.12、Syntax Check、pytest |
| Pull Request targeting `main` | `python-tests` | 檢查提議合併的程式 |
| 上述 Python Job 成功 | `docker-build` | Docker Build、Image Inspect、Container Smoke Test |

重要 YAML 範例：

```yaml
jobs:
  python-tests:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout repository
        uses: actions/checkout@v7
      # Set up Python, install requirements-dev.txt, run pytest

  docker-build:
    runs-on: ubuntu-24.04
    needs: python-tests
    # Build image and verify a temporary container
```

`needs: python-tests` 代表 Docker Job 需先等 Python Job 成功；**不同 Jobs 使用不同 Runner 環境**，第二個 Job 不會繼承前一個 Job 安裝的套件。CI 中的容器測試通常會使用 `127.0.0.1:5004:5000`，那是 **GitHub Runner** 的 Port，不是你 VMware 的 5004。

### 9.4 PR 與保護 main

建議的 GitHub Flow：

```text
feature branch -> git push -> Pull Request (base: main)
              -> Python CI -> Docker CI -> Review -> Merge
              -> local git switch main + git pull --ff-only
```

- **PR（Pull Request）**：提出將分支合併到 `main` 的請求，**不是**自動完成 Merge。
- **Required Status Checks**：可要求 Python 與 Docker Jobs 都通過再合併。
- **Branch Ruleset**：可限制直接推送到 `main` 或 Force Push；是否目前生效以 Repository Settings 為準。
- **Required approvals**：若單人練習，應避免設定無人可 Approve 的條件。

在本專案更新文件時也建議使用新分支 + PR（尤其 `main` 已設定保護規則時），不要直接強推 `main`。

### 9.5 Git Tag 與 Docker Image Tag 不同

| 命令 | 用途 |
| --- | --- |
| `git push origin main` | 更新遠端 `main` 分支指標 |
| `git tag -a v0.6.0 -m "..."` | 在目前 Commit 建立 Git 版本標籤 |
| `git push origin v0.6.0` | 推送 Git Tag；觸發 `publish.yml`（若符合條件） |
| `docker push ghcr.io/...:v0.6.0` | 上傳**已建置的 Docker Image**，不等於推 Git Commit |
| `docker pull ghcr.io/...:v0.6.0` | 從 Registry 下載 Image |

**v0.6.0 已當成固定里程碑。** 文件整理後，請不要刪除或強制改寫既有 `v0.6.0` Tag；文件修改可以透過新的 PR 進 `main`，仍將此專案定位為「v0.6 最終成果」。若需要完全一致的版本快照，再另行評估是否建立文件修訂 Tag，而非覆寫原 Tag。

### 9.6 發布 Workflow：`.github/workflows/publish.yml`

```text
Push Git Tag matching v*
    -> Checkout source at tag
    -> Build release image
    -> Start temporary container + smoke test
    -> Login to ghcr.io (GITHUB_TOKEN)
    -> docker push ghcr.io/xilin0811/linux-server-monitor:<tag>
```

為什麼不直接把 Token 放進 YAML？GitHub Actions 可以用工作期間提供的 `GITHUB_TOKEN`，並將權限限制為：

```yaml
permissions:
  contents: read
  packages: write
```

不需要把私人 SSH Key、Personal Access Token 或帳號密碼提交到 Repository。GitHub Secrets 用於保存不能公開的外部憑證，但**本專案的 GHCR 發布可使用內建 `GITHUB_TOKEN`**。

GHCR 保存 Image，不會幫你開機或執行 Flask，亦不代表 VMware 已自動部署。

### 9.7 在 Ubuntu 下載已發布的 Image（獨立測試）

```bash
sudo docker pull ghcr.io/xilin0811/linux-server-monitor:v0.6.0
sudo docker image ls

sudo docker run -d \
  --name monitor-v06-registry-test \
  -p 127.0.0.1:5006:5000 \
  ghcr.io/xilin0811/linux-server-monitor:v0.6.0

curl -i http://127.0.0.1:5006/api/health
curl -i http://127.0.0.1:5006/api/system
curl -i "http://127.0.0.1:5006/api/history?limit=5"
```

**Expected / 預期：** 拉取成功、容器啟動、API 正常回傳。若 Package 是 Private，需先有適當 Registry 登入權限。

**注意：** 這是 Standalone Container，使用自己的測試 SQLite。若沒有掛載 Volume，刪除它時可能失去容器可寫入層資料；它不會自動讀取 Host `latest.json`。測試後：

```bash
sudo docker stop monitor-v06-registry-test
sudo docker rm monitor-v06-registry-test
```

---

## 10. 完整驗收與日常維運

### 10.1 只讀／低風險檢查（原生部署）

```bash
cd ~/projects/linux-server-monitor
source .venv/bin/activate

# Host-side services and APIs
systemctl status linux-server-monitor --no-pager
systemctl status metrics-collector.timer --no-pager
systemctl show metrics-collector.service -p Result -p ExecMainStatus
sudo nginx -t
curl -i http://127.0.0.1/api/health
curl -sS "http://127.0.0.1/api/history?limit=5" | python -m json.tool

# Test suite
python -m pytest -q
```

### 10.2 Docker Compose 狀態與數據

```bash
sudo docker compose config
sudo docker compose ps
sudo docker compose logs --tail=30 dashboard
curl -i http://127.0.0.1:5003/api/health
curl -sS http://127.0.0.1:5003/api/system | python -m json.tool
python -m json.tool data/latest.json
```

- **預期：** Compose Dashboard `Up (healthy)`；API 回傳；Host Snapshot 內容合理。
- **不要誤判：** `/api/health` 200 不代表完整硬體監測、Nginx、CDN 和跨主機網路全部通過。

### 10.3 GitHub Actions 驗收

打開 [Actions](https://github.com/xilin0811/linux-server-monitor/actions)，查看 `CI - Python Tests and Docker Build` 及 `CD - Publish Docker Image`。檢查 Python pytest、Docker Build／Smoke Test、GHCR Publish 對應 Job 的狀態。**GitHub Actions 的成功是 Runner 的驗收，不是 VM 服務存活證明。**

### 10.4 版本歷程（作為已完成學習記錄）

| 版本 | 實際學習里程碑 | 如何快速複習 |
| --- | --- | --- |
| v0.1 | Flask + psutil + REST API + JS | 第 3、6 節 |
| v0.2 | Gunicorn + Nginx | 第 4 節 |
| v0.3 | systemd + journalctl | 第 5 節 |
| v0.4 | SQLite + Timer + Chart.js + pytest | 第 6 節 |
| v0.5 | Docker + Compose + Host Snapshot | 第 7、8 節 |
| **v0.6** | **Python CI + Docker CI + GHCR Publish** | **第 9 節** |

---

## 11. 故障排除：從症狀找原因

**排錯原則：先定位層次，再看最接近錯誤的日誌，不要一開始就重裝全部環境。**

| 現象 | 優先檢查 | 可能原因 |
| --- | --- | --- |
| `Address already in use: 5000` | `sudo ss -lntp \| grep ':5000 '` | 手動 Flask/Gunicorn 與 systemd 同時佔 Port |
| Nginx `502 Bad Gateway` | `curl -i http://127.0.0.1:5000/api/health` | Gunicorn 沒啟動或 upstream 不可達 |
| Nginx 設定失敗 | `sudo nginx -t` | 設定語法／連結／Port 衝突 |
| Gunicorn Service 失敗 | `systemctl status linux-server-monitor --no-pager` | `ExecStart`、權限或 Python 依賴問題 |
| Windows 無法連 Ubuntu Port 80 | `hostname -I`、`systemctl status nginx --no-pager` | VM IP 改變、NAT/Bridged、Windows 路由、Firewall |
| `python` 找不到套件 | `which python`、`python -m pip list` | `.venv` 未啟用／安裝錯環境 |
| History API 無資料 | `python -m sqlite3 data/metrics.db "SELECT COUNT(*) FROM system_metrics;"` | Collector 未執行／DB 不存在 |
| Timer 看似沒執行 | `systemctl list-timers --all` | Timer 未啟用、前次 Service 失敗 |
| Oneshot Service 顯示 `inactive (dead)` | `systemctl show metrics-collector.service -p Result -p ExecMainStatus` | 可能只是正常執行完畢 |
| Dashboard 歷史圖表沒出現 | Browser F12 Console/Network | Chart.js CDN 不可用、`history.js` 或 API 出錯 |
| Docker Container 直接 Exited | `sudo docker logs <container>` | EntryPoint、套件、資料庫權限 |
| Compose `unhealthy` | `sudo docker compose logs --tail=50 dashboard` | Host Snapshot 過期、SQLite 無法讀取 |
| Compose API 503 | `stat data/latest.json`、`journalctl -u metrics-collector.service` | 超過 120 秒沒更新或讀不到檔案 |
| SQLite Permission denied | `stat -c '%A %u:%g %n' data data/*` | UID10001 對掛載檔案沒有讀取權限 |
| Docker Build `COPY` 找不到檔案 | `pwd`、`.dockerignore`、`Dockerfile` | Build Context 不正確或檔案被排除 |
| CI 失敗 | GitHub Actions → 第一個失敗 Step | Python 依賴、pytest、Docker Build／Smoke Test |
| GHCR Pull `denied` | GitHub Package Visibility、Registry 登入 | Private Package／權限不足 |

### 常用排錯指令與語法

```bash
# TCP listening processes; -l=listening, -n=numeric, -t=TCP, -p=process
sudo ss -lntp

# Recent systemd application logs; -u=unit, -n=number, --no-pager=no pager
sudo journalctl -u linux-server-monitor -n 50 --no-pager

# Latest collector logs
sudo journalctl -u metrics-collector.service -n 50 --no-pager

# Docker Engine containers and images
sudo docker ps -a
sudo docker image ls

# Compose-managed container status and logs
sudo docker compose ps
sudo docker compose logs --tail=50 dashboard
```

當 `curl` 顯示失敗，請先判斷是 **DNS/IP、Port、Nginx、Gunicorn、Flask Route、SQLite、Snapshot** 哪一層出了問題；同一個 HTTP 503 在不同部署模式可能有不同原因。

---

## 12. 安全、資料備份、清理與範圍

### 12.1 目前安全性與限制

- Flask API **沒有 Authentication**；Nginx Port 80 是 HTTP，尚未配置 HTTPS。
- 不要將此練習部署直接暴露到公開網際網路；僅在可信任的 VM／測試網路使用。
- Ubuntu Gunicorn 監聽 `127.0.0.1:5000`；Compose 發布 `127.0.0.1:5003:5000`，限制 Host 上的入口介面。
- Container 使用非 root `appuser`（UID10001），Host `data/` 為唯讀 Bind Mount。
- 測試容器的 `psutil` 數值可能有 Container/Host 視圖差異；它不等同 Host Collector 的權威數據。
- Chart.js 依賴外部 CDN；學習環境不含正式監控告警、備援、遠端自動部署或 Rollback。

### 12.2 `.gitignore` vs `.dockerignore`

- `.gitignore`：避免把 `.venv`、`data/metrics.db`、`data/latest.json`、Cache 等執行資料加入 Git。
- `.dockerignore`：避免 `.venv`、`data/`、Git Metadata 等不需要的檔案進入 Docker Build Context。

確認 `data/` 沒有被 Git 追蹤：

```bash
git ls-files data/
git check-ignore -v data/metrics.db
```

正常情況下 `git ls-files data/` **沒有輸出**；`git check-ignore` 會指出 `.gitignore` 的匹配規則。**`.gitignore` 不會自動取消既有已追蹤的檔案**，因此要同時檢查 Git Tracking 狀態。

### 12.3 安全清理測試 Docker 資源

```bash
sudo docker image ls
sudo docker ps -a
sudo docker volume ls
sudo docker system df
```

先確定誰還在使用哪個 Image/Volume，才能決定是否清理。若已確認測試用 Image 不再被 Container 引用，可使用：

```bash
sudo docker image rm linux-server-monitor:ci-local
sudo docker image prune
```

不要把 `docker image rm` 與 `docker rm` 混淆；刪除 Image 不會替你刪除正在運作的容器。**不要執行 `docker system prune -a --volumes` 進行盲目清理**，可能損失仍有用的測試資料。Named Volume 和 Ubuntu Host `data/` 也不是同一個儲存位置。

### 12.4 本專案為何在 v0.6 結束？

本專案的學習目標已涵蓋 **Linux 管理、Web Service 部署、SQLite 持久化、Docker 容器化、GitHub Actions CI、GHCR 交付**。v0.6.0 是此學習歷程的最終里程碑。

舊文件中的 `v1.0 — Production-Oriented Improvements` 不再是待完成的承諾；Authentication、HTTPS、Alerting、Kubernetes、多節點與 Rollback 等僅是**可選延伸方向**。這也避免把「具有自動測試與 Image 發布」誤寫成「具備正式環境全自動部署」。

---

## 13. 術語速查與常用指令

| Term | 你應該記住的定義 |
| --- | --- |
| **Host** | 執行某個環境的主機；在本專案的 Docker 段落通常是 Ubuntu VM |
| **VM** | VMware 在 Windows 上建立的虛擬電腦，具有自己的 Ubuntu OS |
| **Loopback** | `127.0.0.1`：目前網路環境的自己，並非全世界唯一一台機器 |
| **Port** | 服務的通訊入口；先找對 Host/IP，再找 Port |
| **Reverse Proxy** | Nginx 收請求、轉給 Gunicorn |
| **WSGI / Gunicorn** | 執行 Flask Python Web Application 的 Server 介面與程序 |
| **systemd Unit** | 告訴 Ubuntu 如何管理程序／排程的設定檔 |
| **oneshot** | 執行一次後結束的 Service，結束不一定是錯誤 |
| **SQLite** | 以本機檔案保存結構化資料的資料庫 |
| **Dockerfile** | 定義 Image 建置步驟，`RUN` 在 Build 時執行 |
| **Docker Image** | 可重用的應用程式執行範本；不是正在運作的容器 |
| **Docker Container** | 從 Image 建立並啟動的實例；`docker run -d` 後你仍在 Host Shell |
| **Build Context** | `docker build ... .` 最後的 `.` 指目前專案目錄及可用檔案範圍 |
| **Docker Volume** | Docker 管理的持久化資料儲存空間 |
| **Bind Mount** | 將 Host 指定資料夾或檔案掛載進 Container |
| **Docker Compose** | 讀取 `compose.yaml` 管理服務、Port、Volume；不是新的 Python 框架 |
| **Git Branch** | 持續更新的 Commit 指標，如 `main`、`feature/ci-cd` |
| **Git Tag** | 固定標記某次 Git 版本，如 `v0.6.0` |
| **Pull Request** | 提議合併修改並先經 Review/CI，建立 PR 不等於已 Merge |
| **CI** | Commit／PR 後自動測試、建置與驗證 |
| **CD** | 將通過驗證的成果準備交付或發布；本專案發布 GHCR Image |
| **GitHub Runner** | GitHub Actions Job 使用的獨立機器，不是你的 VMware |
| **GHCR** | GitHub Container Registry，儲存並分發 Docker Images |
| **Health Check** | 回報某些核心依賴是否正常，不代表整套系統完全無故障 |

### 最後重點：三種容易混淆的 Push / Build

```bash
# Update source branch on GitHub
git push origin main

# Push a Git version tag (can trigger publish.yml)
git push origin v0.6.0

# Build local Docker image
sudo docker build -t linux-server-monitor:learning .

# Pull published image from registry
sudo docker pull ghcr.io/xilin0811/linux-server-monitor:v0.6.0
```

**Git Repository 保存程式碼與歷史；GHCR 保存 Image；Docker Engine 執行 Container；Ubuntu systemd 在這個專案負責主機監控。** 若 `main` 啟用 Branch Ruleset，請透過 PR Merge 更新 `main`；表中的 `git push origin main` 是說明語意，不是建議繞過分支保護。

---

**End of learning guide / 學習筆記完結：v0.6.0。**  
回到 [README（成果總覽）](../README.md)。
