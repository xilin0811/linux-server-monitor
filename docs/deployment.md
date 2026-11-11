
# Linux Deployment Guide

## Overview

This guide documents the deployment of the Linux
Server Monitoring Dashboard using Gunicorn and Nginx.

Tested environment:
- Ubuntu 24.04 LTS
- Python 3.12
- Gunicorn
- Nginx
- VMware Workstation

## 1. Prepare the Python Environment

```bash
cd ~/projects/linux-server-monitor

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
```

## 2. Start Gunicorn

```bash
gunicorn --workers 2 \
  --bind 127.0.0.1:5000 app:app
```

Explanation:
- `--workers 2`: Start two worker processes
- `--bind`: Define the listening address and port
- `app:app`: Load the Flask app from app.py

## 3. Test Gunicorn

```bash
curl -i http://127.0.0.1:5000/api/system
```

Expected result: HTTP 200 with JSON system metrics.

## 4. Install and Configure Nginx

```bash
sudo apt install nginx
```

Review `deployment/nginx.conf` and adjust the
server name, listening port, and proxy settings
for the target environment.

Copy the configuration:

```bash
sudo cp deployment/nginx.conf \
  /etc/nginx/sites-available/linux-server-monitor
```

Enable the site if it has not already been enabled:

```bash
sudo ln -s \
  /etc/nginx/sites-available/linux-server-monitor \
  /etc/nginx/sites-enabled/linux-server-monitor
```

Check for conflicts with other Nginx sites,
including the default site on port 80.

## 5. Validate Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 6. Test Reverse Proxy

On Ubuntu:

```bash
curl -i http://127.0.0.1/api/system
```

From a Windows machine on the trusted VM network:

```text
http://<UBUNTU_IP>/
```

## 7. Troubleshooting

Check listening ports:

```bash
sudo ss -lntp
```

Check Nginx service:

```bash
systemctl status nginx
```

Check Nginx errors:

```bash
sudo tail -n 30 /var/log/nginx/error.log
```

## Current Limitations

- Gunicorn is started manually.
- Closing the Gunicorn terminal stops the app.
- Automatic startup with systemd is planned.
- The dashboard has no user authentication.
- Deployment is intended for trusted local networks.
