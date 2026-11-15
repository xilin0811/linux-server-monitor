from flask import Flask, jsonify, render_template, request
from monitor import get_system_info
from database import get_recent_metrics, is_database_healthy

app = Flask(__name__)

# 預設的route
@app.route("/")
def home():
    return render_template("index.html")

# /api/system是自己建立的名稱，這個路徑是用來提供系統資訊的API端點。也可以自己命名為/server-info
@app.route("/api/system", methods=["GET"])
def system_info():
    data = get_system_info()
    return jsonify(data)

@app.route("/api/history", methods=["GET"])
def system_history():

    # 從 URL 取得 limit，例如 ?limit=5
    # 若使用者沒提供，就預設為 60
    raw_limit = request.args.get("limit", "60")

    # 確認 limit 可以轉換為整數
    try:
        limit = int(raw_limit)
    except (ValueError, TypeError):
        return jsonify({
            "error": "limit must be an integer between 1 and 300"
        }), 400

    # 避免使用者要求 0 筆、負數或過多資料
    if limit < 1 or limit > 300:
        return jsonify({
            "error": "limit must be between 1 and 300"
        }), 400

    # 從 SQLite 讀取歷史資料
    records = get_recent_metrics(limit)

    # 轉換為 JSON 回傳
    return jsonify({
        "count": len(records),
        "metrics": records
    })

@app.route("/api/health", methods=["GET"])
def health_check():

    if is_database_healthy():
        return jsonify({
            "status": "healthy",
            "database": "ok"
        }), 200

    return jsonify({
        "status": "unhealthy",
        "database": "unavailable"
    }), 503

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
    # host="127.0.0.1"	只監聽 Ubuntu 本機回送位址
    # 5000 是 Flask 開發伺服器常用的預設連接埠，也可以自己指定其他可用的 Port，例如8000