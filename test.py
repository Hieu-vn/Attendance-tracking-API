import os
import json

# Đường dẫn tới thư mục chứa các file JSON
DATA_DIR = "data"  # 🔁 Bạn có thể sửa lại đường dẫn thực tế

records = []

# Duyệt qua tất cả các file trong thư mục
for file_name in os.listdir(DATA_DIR):
    if file_name.endswith(".json"):
        file_path = os.path.join(DATA_DIR, file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("operator") == "RecPush":
                    info = data.get("info", {})
                    record = {
                        "idCard": int(info.get("idCard", 0)),
                        "persionName": info.get("persionName", ""),
                        "personId": info.get("personId", ""),
                        "RecordID": info.get("RecordID", ""),
                        "time": info.get("time", ""),
                        "VerifyStatus": info.get("VerifyStatus", ""),
                        "direction": info.get("direction", ""),
                        "facesluiceName": info.get("facesluiceName", ""),
                        "PushType": info.get("PushType", ""),
                        "OpendoorWay": info.get("OpendoorWay", ""),
                        "mqtt": info  # ⭐ Thêm toàn bộ thông tin gốc vào trường "mqtt"
                    }
                    records.append(record)
        except Exception as e:
            print(f"❌ Lỗi đọc file {file_name}: {e}")

# Sắp xếp danh sách bản ghi theo idCard
records_sorted = sorted(records, key=lambda x: x["idCard"])

# Xuất ra file JSON
output_path = "all_recpush_sorted_by_idcard.json"
with open(output_path, "w", encoding="utf-8") as out_file:
    json.dump(records_sorted, out_file, ensure_ascii=False, indent=4)

print(f"✅ Đã xuất file JSON: {output_path}")
