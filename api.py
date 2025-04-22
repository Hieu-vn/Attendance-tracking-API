from flask import Flask, jsonify
import json

app = Flask(__name__)

# Đọc file JSON khi server khởi động
with open("chamcongthat.json", "r", encoding="utf-8") as f:
    attendance_data = json.load(f)

@app.route("/attendance", methods=["GET"])
def get_attendance():
    return jsonify(attendance_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

