# Linux Server Monitoring Dashboard

A lightweight real-time Linux system monitoring web application built with **Python, Flask, psutil, HTML, CSS, and JavaScript**.

Developed and tested on Ubuntu 24.04 LTS running in VMware, with remote development through VS Code and SSH.

## Project Overview

This project provides a browser-based dashboard for monitoring the resource usage of an Ubuntu Linux server.

The goal is to gain practical experience in Linux system administration, backend development, REST APIs, networking, and web application deployment.

## Features

- Real-time CPU usage monitoring
- Memory utilization monitoring
- Disk usage monitoring
- System uptime tracking
- REST API with JSON responses
- Automatic data refresh every 5 seconds
- Connection status and error handling
- Responsive web dashboard

## Dashboard Preview

![Ubuntu Server Monitoring Dashboard](screenshots/dashboard.png)

## Technology Stack

| Component | Technology |
|---|---|
| Operating System | Ubuntu 24.04 LTS |
| Virtualization | VMware Workstation |
| Backend | Python, Flask |
| System Monitoring | psutil |
| Frontend | HTML, CSS, JavaScript |
| Remote Development | SSH, VS Code |
| Version Control | Git, GitHub |

## Architecture

```text
Windows Browser
      |
      | HTTP Request
      v
SSH Port Forwarding
      |
      v
Flask Web Application
      |
      +-- /            -> Dashboard HTML
      |
      +-- /api/system  -> JSON Response
                              |
                              v
                         monitor.py
                              |
                              v
                       psutil / Linux OS
```

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/xilin0811/linux-server-monitor.git
cd linux-server-monitor
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Start the application

```bash
python app.py
```

### 5. Open the dashboard

On the machine running Flask:

`http://127.0.0.1:5000/`

API endpoint:

`http://127.0.0.1:5000/api/system`

For access from another computer, use SSH port forwarding.

## Project Structure

```text
linux-server-monitor/
├── app.py
├── monitor.py
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── dashboard.js
└── screenshots/
    └── dashboard.png
```

## Development Progress

### v0.1 — Initial Monitoring Dashboard
- Implemented system resource monitoring using psutil
- Developed Flask REST API
- Created responsive monitoring dashboard
- Added automatic refresh and connection status
- Tested remote access through SSH port forwarding

### Planned Improvements
- Gunicorn and Nginx reverse proxy
- systemd service management
- Monitoring history and charts
- Logging and health checks
- Docker containerization
- CI/CD with GitHub Actions

## Security

This project currently uses Flask's development server and is intended for local development or trusted environments.

The monitoring API should not be exposed directly to the public internet without appropriate authentication and access controls.