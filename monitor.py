
import time
import psutil
from datetime import timedelta


def get_system_info():
    # 1. Get CPU usage
    cpu_usage = psutil.cpu_percent(interval=1)

    # 2. Get memory information
    memory = psutil.virtual_memory()

    # 3. Get disk information
    disk = psutil.disk_usage("/")

    # 4. Calculate system uptime
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    uptime = timedelta(seconds=int(uptime_seconds))

    return {
        "cpu_percent": cpu_usage,
        "memory_percent": memory.percent,
        "memory_total_gb": round(memory.total / (1024 ** 3), 2),
        "memory_available_gb": round(memory.available / (1024 ** 3), 2),
        "disk_percent": disk.percent,
        "uptime": str(uptime)
    }


if __name__ == "__main__":
    info = get_system_info()

    print("===== Ubuntu Server Monitor =====")
    print(f"CPU Usage: {info['cpu_percent']}%")
    print(f"Memory Usage: {info['memory_percent']}%")
    print(f"Memory Total: {info['memory_total_gb']} GB")
    print(f"Memory Available: {info['memory_available_gb']} GB")
    print(f"Disk Usage: {info['disk_percent']}%")
    print(f"System Uptime: {info['uptime']}")
