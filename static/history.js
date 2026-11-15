
(() => {
    "use strict";

    // 1. Get HTML elements
    const statusEl = document.getElementById("history-status");
    const limitEl = document.getElementById("history-limit");

    const cpuCanvas = document.getElementById("cpu-history-chart");
    const memoryCanvas = document.getElementById("memory-history-chart");

    // Verify required HTML elements exist
    if (!statusEl || !limitEl || !cpuCanvas || !memoryCanvas) {
        console.error("Historical chart HTML elements are missing.");
        return;
    }

    // Verify Chart.js loaded successfully
    if (typeof Chart === "undefined") {
        statusEl.textContent = "Chart.js failed to load.";
        console.error("Chart.js is not available.");
        return;
    }

    // 2. Create one line chart
    function createUsageChart(canvas, label, color, fillColor) {
        return new Chart(canvas, {
            type: "line",

            data: {
                labels: [],

                datasets: [{
                    label: label,
                    data: [],
                    borderColor: color,
                    backgroundColor: fillColor,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.25,
                    pointRadius: 0,
                    pointHoverRadius: 4
                }]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                interaction: {
                    intersect: false,
                    mode: "index"
                },

                plugins: {
                    legend: {
                        display: false
                    },

                    tooltip: {
                        callbacks: {
                            label: (context) =>
                                `${context.dataset.label}: ${context.parsed.y}%`
                        }
                    }
                },

                scales: {
                    x: {
                        ticks: {
                            color: "#94a3b8",
                            maxTicksLimit: 6
                        },
                        grid: {
                            display: false
                        }
                    },

                    y: {
                        min: 0,
                        max: 100,

                        ticks: {
                            color: "#94a3b8",
                            callback: (value) => `${value}%`
                        },

                        grid: {
                            color: "rgba(148, 163, 184, 0.12)"
                        }
                    }
                }
            }
        });
    }

    // 3. Create CPU and Memory charts
    const cpuChart = createUsageChart(
        cpuCanvas,
        "CPU",
        "#38bdf8",
        "rgba(56, 189, 248, 0.12)"
    );

    const memoryChart = createUsageChart(
        memoryCanvas,
        "Memory",
        "#34d399",
        "rgba(52, 211, 153, 0.12)"
    );

    // Avoid overlapping requests
    let isLoading = false;

    // 4. Fetch historical monitoring data
    async function updateHistory() {

        if (isLoading) {
            return;
        }

        isLoading = true;

        try {
            const limit = Number(limitEl.value);

            const response = await fetch(
                `/api/history?limit=${limit}`,
                { cache: "no-store" }
            );

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();

            if (!Array.isArray(result.metrics)) {
                throw new Error("Invalid history API response");
            }

            const records = result.metrics;

            // 5. Convert Unix timestamps to local time labels
            const labels = records.map((row) => {
                const date = new Date(row.collected_at * 1000);

                return date.toLocaleTimeString("zh-TW", {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                    hour12: false
                });
            });

            // 6. Extract CPU and Memory values
            const cpuValues = records.map(
                (row) => Number(row.cpu_percent)
            );

            const memoryValues = records.map(
                (row) => Number(row.memory_percent)
            );

            // 7. Update CPU chart
            cpuChart.data.labels = labels;
            cpuChart.data.datasets[0].data = cpuValues;
            cpuChart.update("none");

            // 8. Update Memory chart
            memoryChart.data.labels = labels;
            memoryChart.data.datasets[0].data = memoryValues;
            memoryChart.update("none");

            // 9. Display current history status
            if (records.length === 0) {
                statusEl.textContent =
                    "No historical metrics available yet.";
            } else {
                const latest = records[records.length - 1];

                const latestTime = new Date(
                    latest.collected_at * 1000
                ).toLocaleString("zh-TW");

                statusEl.textContent =
                    `Loaded ${records.length} samples | ` +
                    `Last sample: ${latestTime}`;
            }

        } catch (error) {
            console.error("Failed to update history:", error);

            statusEl.textContent =
                `History update failed: ${error.message}`;

        } finally {
            isLoading = false;
        }
    }

    // 10. Update when the selected sample count changes
    limitEl.addEventListener("change", updateHistory);

    // 11. Load immediately
    updateHistory();

    // 12. Refresh historical charts every 30 seconds
    setInterval(updateHistory, 30000);

})();
