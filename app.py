
from flask import Flask, jsonify
from monitor import get_system_info

app = Flask(__name__)

# 預設的route
@app.route("/")
def home():
    return {
        "message": "Ubuntu Server Monitoring API",
        "status": "running"
    }

# /api/system是自己建立的名稱，這個路徑是用來提供系統資訊的API端點。也可以自己命名為/server-info
@app.route("/api/system", methods=["GET"])
def system_info():
    data = get_system_info()
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
    # host="127.0.0.1"	只監聽 Ubuntu 本機回送位址
    # 5000 是 Flask 開發伺服器常用的預設連接埠，也可以自己指定其他可用的 Port，例如8000