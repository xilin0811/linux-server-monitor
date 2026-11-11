
async function updateDashboard() {
    const status = document.getElementById("status");
    const lastUpdated = document.getElementById("last-updated");

    try {
        // 1. Request system information
        const response = await fetch("/api/system", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error(`HTTP Error: ${response.status}`);
        }

        // 2. Convert the JSON response
        const data = await response.json();

        // 3. Update metric values
        document.getElementById("cpu").textContent =
            `${data.cpu_percent}%`;

        document.getElementById("memory").textContent =
            `${data.memory_percent}%`;

        document.getElementById("disk").textContent =
            `${data.disk_percent}%`;

        document.getElementById("uptime").textContent =
            data.uptime;

        // 4. Update progress bars
        document.getElementById("cpu-bar").value =
            data.cpu_percent;

        document.getElementById("memory-bar").value =
            data.memory_percent;

        document.getElementById("disk-bar").value =
            data.disk_percent;

        // 5. Update connection status
        status.textContent = "● Connected";
        status.classList.remove("disconnected");
        status.classList.add("connected");

        // 6. Update timestamp
        lastUpdated.textContent =
            `Last updated: ${new Date().toLocaleTimeString()}`;

    } catch (error) {
        console.error("Failed to fetch system data:", error);

        status.textContent = "● Connection Error";
        status.classList.remove("connected");
        status.classList.add("disconnected");
    }
}

// Run the first update immediately
updateDashboard();

// Update every 5 seconds
setInterval(updateDashboard, 5000);
