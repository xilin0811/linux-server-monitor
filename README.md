# Linux Server Monitoring Dashboard

> **Final learning release / 最終學習版本：v0.6.0 — Completed**  
> **Platform：** Ubuntu 24.04 LTS (VMware) · Python 3.12 · Docker  
> **Documentation：** English overview + 繁體中文學習說明

A browser-based Linux monitoring dashboard built incrementally from a Flask REST API to a Linux service, historical metrics storage, Docker containerization, and GitHub Actions CI/CD.

這是一個從零開始的 **Linux／Backend／DevOps 實作學習專案**。從 Python 蒐集 CPU、記憶體、磁碟與 Uptime，到透過 Gunicorn、Nginx 和 systemd 部署，再加入 SQLite 歷史資料、Docker Compose、GitHub Actions 自動測試及 GHCR 版本化映像發布。**學習範圍已於 v0.6.0 完成**；不以「正式商業環境可直接使用」為目標。

![Dashboard preview / 儀表板畫面](screenshots/dashboard.png)

## Contents / 快速導覽

- [What this project demonstrates / 專案成果](#what-this-project-demonstrates--專案成果)
- [Architecture / 系統架構](#architecture--系統架構)
- [Version journey / 版本學習歷程](#version-journey--版本學習歷程)
- [Technology stack / 技術](#technology-stack--技術)
- [Getting started / 快速開始](#getting-started--快速開始)
- [API reference / API](#api-reference--api)
- [Project structure / 專案結構](#project-structure--專案結構)
- [CI/CD and image publishing / 自動化交付](#cicd-and-image-publishing--自動化交付)
- [Troubleshooting / 排錯入口](#troubleshooting--排錯入口)
- [Scope and limitations / 專案定位](#scope-and-limitations--專案定位)

> **Learning notes / 詳細學習筆記：** [docs/deployment.md](docs/deployment.md) 收錄每階段的部署步驟、指令解釋、預期輸出與故障排除。README 是成果總覽；需要重新操作時，請閱讀部署指南。

## What this project demonstrates / 專案成果

| Area | Implemented result / 已實作成果 |
| --- | --- |
| Monitoring | CPU、Memory、Disk、Uptime；`/api/system` REST API |
| Frontend | HTML/CSS/JavaScript Dashboard；約每 5 秒更新卡片 |
| Historical data | SQLite `system_metrics`、CPU/RAM Chart.js 歷史折線圖 |
| Collection | systemd Timer 約每 30 秒觸發一次 Host Collector；保留最近 7 天資料 |
| Reliability | Gunicorn 由 systemd 管理、Logging、基本 Health API、pytest |
| Containerization | Dockerfile、非 root `appuser`、Docker Network、Volume、Docker Compose |
| Host monitoring in Docker | Ubuntu Collector 儲存 `latest.json` + SQLite；Docker Dashboard 使用唯讀 Bind Mount 讀取 |
| CI | GitHub Actions 自動執行 Python 測試、Docker Image Build 和 Flask API Smoke Test |
| Delivery | Git Tag 觸發 GHCR 發布，可在其他 Docker Host 使用 `docker pull` 取得 Image |

### Why build it? / 為什麼做這個專案？

The goal is to understand the complete path from **source code → running application → HTTP request → persistent data → automated testing → versioned image**, rather than learning isolated commands.

學習重點包含：Linux 指令與權限、SSH／Port Forwarding、Git 分支與 PR、HTTP 與 Reverse Proxy、systemd／journalctl、Python 虛擬環境、SQLite、Docker Image／Container／Volume／Network、YAML、CI/CD。

## Architecture / 系統架構

本專案保留兩種部署方式。**兩者是在同一台 Ubuntu VM 上的不同服務，不要混淆它們的 IP 和 Port。**

### A. Native Ubuntu deployment / Ubuntu 原生部署（v0.3–v0.4）

```text
Windows browser -- http://<UBUNTU_VM_IP>:80 --> Ubuntu Nginx :80
                                                  |
                                                  v
                                        Gunicorn 127.0.0.1:5000
                                                  |
                                                  v
                                              Flask app.py
                                              |    |      |
                                          /api/system  /api/history  /api/health
                                              |           |              |
                                         monitor.py    SQLite       SQLite check

Ubuntu systemd Timer --> metrics-collector.service --> collect_once.py
                                                         |
                                                         v
                                                   data/metrics.db
```

- **Nginx**：處理 Port 80 的 HTTP 請求，轉交 Gunicorn。
- **Gunicorn**：執行 Flask WSGI 應用，監聽 Ubuntu 的 `127.0.0.1:5000`。
- **systemd**：管理 Gunicorn，以及定時執行的一次性資料收集服務。
- **SQLite**：保存歷史數據；即時 API 在此模式直接呼叫 psutil。

### B. Docker Compose deployment / 容器化儀表板（v0.5）

```text
Ubuntu Host (VMware)
  metrics-collector.timer --> collect_once.py --> data/metrics.db
                                         \-------> data/latest.json
                                                    | (read-only bind mount)
                                                    v
  curl 127.0.0.1:5003 --> Docker Port Mapping --> Container :5000
                                                    |
                                                 Gunicorn
                                                    |
                                                  Flask
                                    /api/system: reads latest.json
                                    /api/history: reads SQLite
                                    /api/health: checks DB + snapshot freshness
```

- Ubuntu Host **仍負責收集 Host Metrics**；Container 負責 Flask API / Dashboard。
- `compose.yaml` 掛載 Host 的 `./data` 到 Container 的 `/app/data`，設定為 **read-only**。
- 在 `MONITOR_SOURCE=host_snapshot` 模式，`/api/system` 讀取最近一次 Host Snapshot；超過約 120 秒未更新會回傳 503。
- Docker 的 `127.0.0.1:5003` 是 **Ubuntu Host 的本機位址**。Windows 若要透過自己的 `localhost:5003` 開啟網站，需另外設定 SSH Port Forwarding。
- 你在 v0.5 練習的 **Named Volume** 是另一種獨立儲存方式；最終 Compose 的 Host 監控模式改用 **Bind Mount**，兩者不是同一份資料。

> **Important / 注意：** v0.6 的新增重點是 CI/CD 與 Image 發布；正式 Image 已可從 GHCR 取得，但 `compose.yaml` 仍以本地 Dockerfile 建置 `linux-server-monitor:v0.5-compose`。GHCR Pull 範例是**另一個獨立測試容器**，不是自動更新目前的 Compose 服務。

## Version journey / 版本學習歷程

| Version | Milestone | Key learning / 重點 |
| --- | --- | --- |
| **v0.1** | Initial Dashboard | Flask、psutil、REST API、HTML/CSS/JS、每 5 秒更新、SSH Port Forwarding |
| **v0.2** | Gunicorn + Nginx | WSGI Server、Reverse Proxy、Ubuntu VM IP、HTTP Port |
| **v0.3** | systemd | Unit File、開機啟動、`Restart=on-failure`、`systemctl`、`journalctl` |
| **v0.4** | Monitoring & Reliability | SQLite、Collector Timer、歷史 API、Chart.js、7 天保留、pytest |
| **v0.5** | Docker Containerization | Dockerfile、Image／Container、Networking、Volume、Bind Mount、Compose |
| **v0.6** | **CI/CD & GHCR — Final** | GitHub Actions、PR Checks、Python／Docker CI、Smoke Test、Tag-based Image Publishing |

All milestones above were completed in the learning environment. / 以上各階段已依本專案學習過程完成；詳細操作與驗收方法見 [部署教學](docs/deployment.md)。

### v0.6 CI/CD flow / 最終交付流程

```text
VS Code (Ubuntu) -> Git Commit / Push -> GitHub Feature Branch
                                         |
                                         v
                                   Pull Request -> main
                                         |
                                         v
                                   Python pytest CI
                                         |
                                         v
                                Docker Build + Smoke Test
                                         |
                                         v
                                     PR Merge
                                         |
                                         v
                                 Git Tag v0.6.0
                                         |
                                         v
                                  GHCR Image Publish
                                         |
                                         v
                               docker pull on Ubuntu
```

**CI** 驗證程式和容器；**GHCR** 保存已建置 Image；**CD** 在此專案實作的是版本化 Image 發布，**不包含**自動部署至 VMware Ubuntu。

## Technology stack / 技術

| Layer | Tools |
| --- | --- |
| Environment | Ubuntu 24.04 LTS、VMware Workstation、VS Code Remote SSH |
| Backend | Python 3.12、Flask、psutil、Gunicorn |
| Frontend | HTML、CSS、JavaScript、Chart.js |
| Storage | SQLite (`sqlite3`)、JSON Snapshot |
| Linux deployment | Nginx、systemd Service/Timer、journalctl |
| Containers | Docker Engine、Dockerfile、Compose、Bridge Network、Volume、Bind Mount |
| Automation | Git、GitHub、Pull Requests、GitHub Actions、pytest、GHCR |

## Getting started / 快速開始

### Option A — Python / Native Ubuntu

適合第一次閱讀程式碼或在沒有既有 Port 5000 服務的環境中測試。

```bash
# First-time setup: place the repository in ~/projects
mkdir -p ~/projects
cd ~/projects

# On an Ubuntu terminal (not Windows PowerShell)
git clone https://github.com/xilin0811/linux-server-monitor.git
cd linux-server-monitor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt

# Initialize/sample SQLite once for /api/health and history
python collect_once.py

# Development server (only when Port 5000 is free)
python app.py
```

Open in the **Ubuntu** environment: `http://127.0.0.1:5000/`. From Windows, use VS Code SSH Port Forwarding for Port 5000. If the systemd-managed Gunicorn is already bound to 5000, **do not start another server on the same Port**.

正式原生部署（Nginx、systemd、Timer）請遵循 [Deployment Guide](docs/deployment.md)，不要對既有服務直接覆蓋 Unit File。

### Option B — Docker Compose / Host Monitoring

此模式要求 Ubuntu 已設定好 `metrics-collector.timer`，並已產生 `data/metrics.db`、`data/latest.json`；Docker Container UID 10001 需要對資料具有讀取權限。

```bash
cd ~/projects/linux-server-monitor
source .venv/bin/activate
python collect_once.py
systemctl status metrics-collector.timer --no-pager
sudo docker compose config
sudo docker compose up -d --build
sudo docker compose ps
curl -i http://127.0.0.1:5003/api/health
```

- Dashboard：`http://127.0.0.1:5003/`（Ubuntu Host）
- Host Snapshot API：`http://127.0.0.1:5003/api/system`
- History API：`http://127.0.0.1:5003/api/history?limit=5`
- Windows：透過 Remote SSH 將 Ubuntu Port **5003** 轉發至 Windows，再開 `http://localhost:5003/`。

> `docker compose up -d --build` 建置與啟動 Compose 的服務，不等於從 GHCR 更新到 v0.6 Image。參閱 [Docker 模式與 GHCR 操作](docs/deployment.md)。

### Option C — Published image / 從 GHCR 下載

```bash
sudo docker pull ghcr.io/xilin0811/linux-server-monitor:v0.6.0
sudo docker run -d --name monitor-v06-registry-test \
  -p 127.0.0.1:5006:5000 \
  ghcr.io/xilin0811/linux-server-monitor:v0.6.0
curl -i http://127.0.0.1:5006/api/health
```

此為**獨立測試用容器**：它會自行初始化一份 SQLite；如果沒有指定 Volume，刪除容器時可能失去測試資料。它不會自動連接 Ubuntu 的 Host Collector。若 GHCR Package 為 Private，需先取得適當下載權限。

## API reference / API

| Method | Endpoint | Meaning / 功能 |
| --- | --- | --- |
| `GET` | `/` | Dashboard 網頁 |
| `GET` | `/api/system` | CPU、Memory、Disk、Uptime；Host Snapshot 模式額外含 `collected_at` |
| `GET` | `/api/history?limit=60` | 最近 N 筆 SQLite 紀錄；`limit` 為 1～300，預設 60 |
| `GET` | `/api/health` | SQLite 基本可讀性；Host Snapshot 模式另檢查資料是否過期 |

History JSON example / 歷史資料範例：

```json
{
  "count": 1,
  "metrics": [
    {
      "id": 1,
      "collected_at": 1795000000,
      "cpu_percent": 12.5,
      "memory_percent": 65.7,
      "disk_percent": 42.0
    }
  ]
}
```

上述為**示意數值**；不代表實際監控結果。`/api/history` 對不合法的 `limit` 回傳 HTTP 400；`/api/health` 資料不可用時回傳 HTTP 503。Live Cards 約每 5 秒向 API 查詢，但 Host Snapshot 本身約每 30 秒更新，因此連續數次查詢可能得到相同數值。

## Project structure / 專案結構

```text
linux-server-monitor/
├── .github/workflows/
│   ├── ci.yml                 # Python pytest + Docker Build / Smoke Test
│   └── publish.yml            # Publish tagged image to GHCR
├── Dockerfile                 # Build Python application image
├── .dockerignore              # Exclude unnecessary build inputs
├── docker-entrypoint.sh       # Initialize standalone DB / start Gunicorn
├── compose.yaml               # Host Snapshot dashboard mode
├── app.py                     # Flask routes and API
├── monitor.py                 # psutil metrics collection
├── database.py                # SQLite storage and queries
├── collect_once.py            # systemd-triggered collector + snapshot
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt       # pytest + runtime dependencies
├── templates/index.html       # Dashboard HTML
├── static/
│   ├── dashboard.js            # Live cards
│   ├── history.js              # Chart.js history
│   └── style.css
├── deployment/
│   ├── nginx.conf
│   ├── linux-server-monitor.service
│   ├── metrics-collector.service
│   └── metrics-collector.timer
├── docs/deployment.md         # Detailed tutorial and troubleshooting
├── screenshots/dashboard.png
└── data/                      # Runtime only; ignored by Git
    ├── metrics.db
    └── latest.json
```

## CI/CD and image publishing / 自動化交付

- **[Python + Docker CI](.github/workflows/ci.yml)：** `push` 到 `main` / `feature/**` 或 PR 到 `main` 時，測試 Python 並建置、啟動測試容器。
- **[GHCR publishing](.github/workflows/publish.yml)：** Push `v*` Git Tag 時，建置、Smoke Test，再發布 `ghcr.io/xilin0811/linux-server-monitor:<tag>`。
- **Branch protections / Rulesets：** 學習透過 PR 和 Required Status Checks 保護 `main`；實際是否啟用請以 GitHub Repository Settings 為準。
- **No remote auto-deployment：** Workflow 不會 SSH 進你的 VMware 或替換正在執行的 Compose 服務。

## Troubleshooting / 排錯入口

| Symptom / 現象 | First check / 第一個檢查 |
| --- | --- |
| Nginx 502 | `systemctl status linux-server-monitor --no-pager`、`curl -i http://127.0.0.1:5000/api/health` |
| No historical data | `systemctl status metrics-collector.timer --no-pager`、`python -m sqlite3 data/metrics.db "SELECT COUNT(*) FROM system_metrics;"` |
| Docker Compose unhealthy | `sudo docker compose logs --tail=50 dashboard`、`ls -l data/latest.json data/metrics.db` |
| Docker API returns 503 | 查看 SQLite、Host Snapshot 是否超過 120 秒、Collector 日誌 |
| Windows cannot connect | 分清 `127.0.0.1` 屬於 Windows 或 Ubuntu、VM IP、SSH Port Forwarding |
| CI failed | GitHub Actions → 失敗的 Job → 第一個失敗的 Step |
| GHCR pull denied | 確認 Package Visibility 或適當 Registry 登入權限 |

完整指令說明與故障排除流程：**[Linux Deployment & Learning Guide](docs/deployment.md)**。

## Scope and limitations / 專案定位

**Final learning milestone: v0.6.0 / 學習成果至 v0.6.0 完成。** This is a demonstrative project for Linux, backend, containerization, and CI/CD learning—not an internet-facing production monitoring service.

- 未實作帳密驗證、HTTPS/TLS 與正式的網際網路公開服務；請只在可信任的練習環境使用。
- 目前沒有 Kubernetes、多節點部署、自動遠端部署或 Rollback；不將其宣稱為已完成能力。
- Chart.js 由 CDN 載入；離線環境可能影響歷史圖表顯示。
- CI Smoke Test 驗證的是獨立測試容器，不代表 GitHub Runner 已驗證你的 VMware Host Collector。
- 監控資料存放在 Ubuntu VM，未包含跨機備份與高可用部署。

**Potential extensions（非本次待辦）：** Authentication、HTTPS、Alerting、Advanced Observability、Deployment Rollback、Kubernetes。這些是可能的未來學習題目，不是本專案尚未完成的 v1.0 承諾。

---

**Project completed at v0.6.0.** For commands, expected results, design decisions, and verification steps, see [docs/deployment.md](docs/deployment.md).
