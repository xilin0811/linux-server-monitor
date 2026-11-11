# Linux Deployment Guide / Linux 部署教學

> **Version / 版本：** v0.3 — Gunicorn + Nginx + systemd (**Completed / 已完成**)  
> **Audience / 適用對象：** Ubuntu / Linux 初學者、系統部署學習者

## Overview / 文件目的

This guide explains how to deploy the Linux Server Monitoring Dashboard using **Gunicorn**, **Nginx**, and **systemd** on Ubuntu.

本文記錄從安裝 Python 套件、測試 Gunicorn、設定 Nginx Reverse Proxy，到使用 systemd 管理背景服務的完整流程。每一步提供**指令、用途、預期結果及常見錯誤**，方便重建環境與排除問題。

### Tested Environment / 使用環境

- Ubuntu 24.04 LTS
- Python 3.12
- VMware Workstation
- Gunicorn and Nginx
- systemd / journalctl
- VS Code Remote SSH

> **Environment note / 環境提醒：** Example paths use Linux user `xilin` and `/home/xilin/projects/linux-server-monitor`. These values belong to the original learning VM and must be adjusted on other machines. Deployment and reboot/recovery tests were completed in the original Ubuntu VMware environment. / 以下指令中的使用者與絕對路徑為原始測試環境設定，移植時須調整；本版已完成原始 VM 的部署與恢復驗證。

### Deployment Architecture / 部署架構

```text
Windows Browser
      |
      | HTTP :80
      v
Ubuntu / Nginx (Reverse Proxy)
      |
      | HTTP 127.0.0.1:5000
      v
Gunicorn (WSGI Server) <--- systemd manages this process
      |
      v
Flask Application (app.py)
      |
      v
monitor.py -> psutil -> Linux system metrics

journalctl -> reads logs from the systemd journal
```

**中文解說：** Nginx 是對外的 HTTP 入口，Gunicorn 負責執行 Python Flask，Flask 提供畫面和 API。systemd 負責管理 Gunicorn 的生命週期，`journalctl` 用來查詢服務日誌。**systemd 不會取代 Nginx 或 Gunicorn。**

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

Install dependencies / 安裝依賴套件：

```bash
python -m pip install -r requirements.txt
```

Verify Gunicorn / 確認已安裝：

```bash
gunicorn --version
```

**Why / 原理：** `.venv` 將這個專案需要的 Python 套件與 Ubuntu 系統環境隔離。`source .venv/bin/activate` 會調整目前 Shell 的 `PATH`，讓 `python` 和 `gunicorn` 優先使用虛擬環境內的版本；**systemd 不會繼承這個互動式啟用狀態**，因此之後必須使用 Gunicorn 的絕對路徑。

**Expected / 預期結果：** `gunicorn --version` 應顯示安裝版本；如果找不到指令，請確認 `.venv` 已啟用且 `requirements.txt` 包含 Gunicorn。

---

## 2. Test Gunicorn Manually / 手動測試 Gunicorn

Start Gunicorn / 啟動：

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
sudo nginx -t
sudo systemctl reload nginx
```

只有在 `nginx -t` 成功時才執行 `reload`。

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

---

## 10. Deployment Verification Record / 部署驗收紀錄

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

## 11. Future Work / 後續規劃

This deployment guide documents the completed v0.3 configuration. Future versions may add historical metric storage and charts, automated health checks and tests, Docker deployment, GitHub Actions CI/CD, and improved authentication and HTTPS support.

本文件記錄已完成的 v0.3 部署流程；後續規劃包括監控歷史數據、健康檢查與自動化測試、Docker 容器化、GitHub Actions CI/CD，以及身分驗證與 HTTPS 安全機制。這些項目尚未包含在 v0.3 版本中。

## Current Status / 目前狀態

**v0.3 — systemd Service Management (Completed / 已完成)**

Gunicorn, Nginx, and systemd deployment are documented and have passed the project author's verification, including startup, SSH independence, reboot recovery, logging, and failure recovery.

已完成 Gunicorn、Nginx 與 systemd 的整合部署及驗收，並保留可重現的操作指令、故障排除方法和測試紀錄。
