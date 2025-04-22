from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import datetime
from dateutil.parser import parse
from functools import wraps
import sqlite3
import pandas as pd

app = Flask(__name__)
CORS(app)

# Cấu hình cơ sở dữ liệu
DB_FILE = "attendance.db"

# Khởi tạo cơ sở dữ liệu nếu chưa tồn tại
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Tạo bảng employees nếu chưa tồn tại
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY,
        person_id TEXT UNIQUE,
        id_card INTEGER UNIQUE,
        name TEXT,
        department TEXT,
        position TEXT,
        active INTEGER DEFAULT 1
    )
    ''')
    
    # Tạo bảng attendance nếu chưa tồn tại
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER,
        person_id TEXT,
        record_id TEXT,
        timestamp TEXT,
        direction TEXT,
        verify_status TEXT,
        device_name TEXT,
        open_door_way TEXT,
        push_type TEXT,
        raw_data TEXT,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    )
    ''')
    
    # Tạo bảng devices
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT UNIQUE,
        name TEXT,
        location TEXT,
        status TEXT,
        last_active TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

# Middleware để xử lý lỗi cơ sở dữ liệu
def db_handler(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {str(e)}"}), 500
        except Exception as e:
            return jsonify({"error": f"Server error: {str(e)}"}), 500
    return decorated_function

# Utility để kết nối và trả về connection và cursor
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Để kết quả trả về dạng dictionary
    return conn

# Hàm nhập dữ liệu từ JSON vào DB
def import_data_from_json():
    if os.path.exists("all_recpush_sorted_by_idcard.json"):
        with open("all_recpush_sorted_by_idcard.json", "r", encoding="utf-8") as f:
            records = json.load(f)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Import nhân viên
        unique_employees = {}
        for record in records:
            person_id = record.get("personId")
            if person_id and person_id not in unique_employees:
                unique_employees[person_id] = {
                    "id_card": record.get("idCard"),
                    "name": record.get("persionName"),
                    "person_id": person_id
                }
        
        # Thêm nhân viên vào DB
        for person_id, emp_data in unique_employees.items():
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO employees (person_id, id_card, name) VALUES (?, ?, ?)",
                    (emp_data["person_id"], emp_data["id_card"], emp_data["name"])
                )
            except sqlite3.IntegrityError:
                pass  # Ignore if employee already exists
        
        # Import dữ liệu chấm công
        for record in records:
            employee_id = None
            person_id = record.get("personId")
            
            if person_id:
                cursor.execute("SELECT id FROM employees WHERE person_id = ?", (person_id,))
                result = cursor.fetchone()
                if result:
                    employee_id = result["id"]
            
            cursor.execute(
                """
                INSERT OR IGNORE INTO attendance 
                (employee_id, person_id, record_id, timestamp, direction, verify_status, device_name, open_door_way, push_type, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    person_id,
                    record.get("RecordID"),
                    record.get("time"),
                    record.get("direction"),
                    record.get("VerifyStatus"),
                    record.get("facesluiceName"),
                    record.get("OpendoorWay"),
                    record.get("PushType"),
                    json.dumps(record.get("mqtt", {}))
                )
            )
        
        conn.commit()
        conn.close()
        return True
    return False

# API Routes

@app.route("/api/v1/attendance", methods=["GET"])
@db_handler
def get_all_attendance():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    
    # Đếm tổng số bản ghi để phân trang
    total_records = conn.execute("SELECT COUNT(*) as count FROM attendance").fetchone()["count"]
    
    # Query với JOIN để lấy thêm thông tin nhân viên
    query = """
    SELECT 
        a.id, a.employee_id, a.person_id, a.record_id, a.timestamp, 
        a.direction, a.verify_status, a.device_name, a.open_door_way,
        e.name as employee_name, e.id_card
    FROM attendance a
    LEFT JOIN employees e ON a.employee_id = e.id
    ORDER BY a.timestamp DESC
    LIMIT ? OFFSET ?
    """
    
    cursor = conn.execute(query, (per_page, offset))
    attendance_records = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        "data": attendance_records,
        "pagination": {
            "total": total_records,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_records + per_page - 1) // per_page
        }
    })

@app.route("/api/v1/attendance/<int:record_id>", methods=["GET"])
@db_handler
def get_attendance_by_id(record_id):
    conn = get_db_connection()
    
    query = """
    SELECT 
        a.id, a.employee_id, a.person_id, a.record_id, a.timestamp, 
        a.direction, a.verify_status, a.device_name, a.open_door_way, a.raw_data,
        e.name as employee_name, e.id_card, e.department, e.position
    FROM attendance a
    LEFT JOIN employees e ON a.employee_id = e.id
    WHERE a.id = ?
    """
    
    cursor = conn.execute(query, (record_id,))
    record = cursor.fetchone()
    
    conn.close()
    
    if record:
        return jsonify(dict(record))
    else:
        return jsonify({"error": "Record not found"}), 404

@app.route("/api/v1/attendance/employee/<int:employee_id>", methods=["GET"])
@db_handler
def get_attendance_by_employee(employee_id):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    
    # Đếm tổng số bản ghi của nhân viên này
    total_records = conn.execute(
        "SELECT COUNT(*) as count FROM attendance WHERE employee_id = ?", 
        (employee_id,)
    ).fetchone()["count"]
    
    query = """
    SELECT 
        a.id, a.employee_id, a.person_id, a.record_id, a.timestamp, 
        a.direction, a.verify_status, a.device_name, a.open_door_way,
        e.name as employee_name, e.id_card, e.department, e.position
    FROM attendance a
    LEFT JOIN employees e ON a.employee_id = e.id
    WHERE a.employee_id = ?
    ORDER BY a.timestamp DESC
    LIMIT ? OFFSET ?
    """
    
    cursor = conn.execute(query, (employee_id, per_page, offset))
    attendance_records = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        "data": attendance_records,
        "pagination": {
            "total": total_records,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_records + per_page - 1) // per_page
        }
    })

@app.route("/api/v1/attendance/date/<date>", methods=["GET"])
@db_handler
def get_attendance_by_date(date):
    # Format date to ensure it matches the pattern in DB (YYYY-MM-DD)
    try:
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d")
        date_str = parsed_date.strftime("%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    
    # Đếm tổng số bản ghi của ngày này
    total_records = conn.execute(
        "SELECT COUNT(*) as count FROM attendance WHERE date(timestamp) = ?", 
        (date_str,)
    ).fetchone()["count"]
    
    query = """
    SELECT 
        a.id, a.employee_id, a.person_id, a.record_id, a.timestamp, 
        a.direction, a.verify_status, a.device_name, a.open_door_way,
        e.name as employee_name, e.id_card, e.department, e.position
    FROM attendance a
    LEFT JOIN employees e ON a.employee_id = e.id
    WHERE date(a.timestamp) = ?
    ORDER BY a.timestamp ASC
    LIMIT ? OFFSET ?
    """
    
    cursor = conn.execute(query, (date_str, per_page, offset))
    attendance_records = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        "data": attendance_records,
        "pagination": {
            "total": total_records,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_records + per_page - 1) // per_page
        }
    })

@app.route("/api/v1/attendance/report", methods=["GET"])
@db_handler
def get_attendance_report():
    # Các tham số lọc
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    employee_id = request.args.get('employee_id')
    
    if not start_date:
        # Mặc định là đầu tháng hiện tại
        today = datetime.datetime.now()
        start_date = datetime.datetime(today.year, today.month, 1).strftime("%Y-%m-%d")
    
    if not end_date:
        # Mặc định là ngày hiện tại
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    
    # Xây dựng query động dựa trên các tham số lọc
    query_parts = [
        "SELECT e.id, e.name, e.id_card, e.department, e.position, a.timestamp, a.direction, a.device_name",
        "FROM employees e",
        "LEFT JOIN attendance a ON e.id = a.employee_id",
        "WHERE e.active = 1"
    ]
    query_params = []
    
    if start_date:
        query_parts.append("AND date(a.timestamp) >= ?")
        query_params.append(start_date)
    
    if end_date:
        query_parts.append("AND date(a.timestamp) <= ?")
        query_params.append(end_date)
    
    if department:
        query_parts.append("AND e.department = ?")
        query_params.append(department)
    
    if employee_id:
        query_parts.append("AND e.id = ?")
        query_params.append(employee_id)
    
    query_parts.append("ORDER BY e.id, a.timestamp")
    
    query = " ".join(query_parts)
    cursor = conn.execute(query, query_params)
    records = [dict(row) for row in cursor.fetchall()]
    
    # Xử lý dữ liệu thành báo cáo
    report_data = {}
    
    for record in records:
        emp_id = record["id"]
        if emp_id not in report_data:
            report_data[emp_id] = {
                "employee_id": emp_id,
                "name": record["name"],
                "id_card": record["id_card"],
                "department": record["department"],
                "position": record["position"],
                "days": {}
            }
        
        if record["timestamp"]:
            date = record["timestamp"].split(" ")[0]  # Lấy phần ngày từ timestamp
            time = record["timestamp"].split(" ")[1]  # Lấy phần giờ từ timestamp
            direction = record["direction"]
            
            if date not in report_data[emp_id]["days"]:
                report_data[emp_id]["days"][date] = {
                    "in": [],
                    "out": []
                }
            
            if direction == "in":
                report_data[emp_id]["days"][date]["in"].append({
                    "time": time,
                    "device": record["device_name"]
                })
            elif direction == "out":
                report_data[emp_id]["days"][date]["out"].append({
                    "time": time,
                    "device": record["device_name"]
                })
    
    # Chuyển đổi từ dictionary sang danh sách
    report_list = list(report_data.values())
    
    # Tính toán thêm các chỉ số: giờ làm, giờ vào sớm/muộn, giờ ra sớm/muộn
    for employee in report_list:
        total_work_hours = 0
        total_days = 0
        days_with_records = 0
        
        for date, records in employee["days"].items():
            # Sắp xếp theo thời gian
            if records["in"]:
                records["in"].sort(key=lambda x: x["time"])
            if records["out"]:
                records["out"].sort(key=lambda x: x["time"])
            
            # Nếu có cả check-in và check-out
            if records["in"] and records["out"]:
                days_with_records += 1
                first_in = records["in"][0]["time"]
                last_out = records["out"][-1]["time"]
                
                # Tính số giờ làm việc
                try:
                    t_in = datetime.datetime.strptime(first_in, "%H:%M:%S")
                    t_out = datetime.datetime.strptime(last_out, "%H:%M:%S")
                    delta = t_out - t_in
                    hours = delta.total_seconds() / 3600
                    total_work_hours += hours
                    records["work_hours"] = round(hours, 2)
                except Exception as e:
                    records["work_hours"] = None
            
            total_days += 1
        
        employee["summary"] = {
            "total_days": total_days,
            "days_with_records": days_with_records,
            "average_work_hours": round(total_work_hours / days_with_records, 2) if days_with_records > 0 else 0,
            "attendance_rate": round((days_with_records / total_days) * 100, 2) if total_days > 0 else 0
        }
    
    conn.close()
    
    return jsonify({
        "start_date": start_date,
        "end_date": end_date,
        "data": report_list
    })

@app.route("/api/v1/attendance/manual", methods=["POST"])
@db_handler
def add_manual_attendance():
    data = request.json
    
    required_fields = ["employee_id", "timestamp", "direction"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Kiểm tra employee_id có tồn tại không
    conn = get_db_connection()
    cursor = conn.execute("SELECT id, person_id FROM employees WHERE id = ?", (data["employee_id"],))
    employee = cursor.fetchone()
    
    if not employee:
        conn.close()
        return jsonify({"error": "Employee not found with the given ID"}), 404
    
    # Thêm bản ghi chấm công thủ công
    cursor.execute(
        """
        INSERT INTO attendance 
        (employee_id, person_id, timestamp, direction, verify_status, device_name)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            data["employee_id"],
            employee["person_id"],
            data["timestamp"],
            data["direction"],
            data.get("verify_status", "Manual"),
            data.get("device_name", "Manual Input")
        )
    )
    
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    
    return jsonify({
        "id": last_id,
        "message": "Manual attendance record added successfully"
    }), 201

@app.route("/api/v1/employees", methods=["GET"])
@db_handler
def get_all_employees():
    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM employees WHERE active = 1 ORDER BY name")
    employees = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(employees)

@app.route("/api/v1/employees/<int:employee_id>", methods=["GET"])
@db_handler
def get_employee_by_id(employee_id):
    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,))
    employee = cursor.fetchone()
    
    if not employee:
        conn.close()
        return jsonify({"error": "Employee not found"}), 404
    
    # Lấy thông tin chấm công gần đây
    cursor = conn.execute(
        """
        SELECT * FROM attendance 
        WHERE employee_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 10
        """, 
        (employee_id,)
    )
    recent_attendance = [dict(row) for row in cursor.fetchall()]
    
    result = dict(employee)
    result["recent_attendance"] = recent_attendance
    
    conn.close()
    return jsonify(result)

@app.route("/api/v1/employees", methods=["POST"])
@db_handler
def add_employee():
    data = request.json
    
    required_fields = ["name", "id_card", "person_id"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO employees (name, id_card, person_id, department, position, active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                data["name"],
                data["id_card"],
                data["person_id"],
                data.get("department", ""),
                data.get("position", "")
            )
        )
        
        conn.commit()
        last_id = cursor.lastrowid
        
        conn.close()
        return jsonify({
            "id": last_id,
            "message": "Employee added successfully"
        }), 201
    except sqlite3.IntegrityError as e:
        conn.close()
        if "UNIQUE constraint failed" in str(e):
            return jsonify({"error": "Employee with the same ID card or person ID already exists"}), 409
        return jsonify({"error": str(e)}), 400

@app.route("/api/v1/employees/<int:employee_id>", methods=["PUT"])
@db_handler
def update_employee(employee_id):
    data = request.json
    
    conn = get_db_connection()
    cursor = conn.execute("SELECT id FROM employees WHERE id = ?", (employee_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Employee not found"}), 404
    
    # Các trường có thể cập nhật
    valid_fields = ["name", "department", "position", "active"]
    update_fields = {}
    
    for field in valid_fields:
        if field in data:
            update_fields[field] = data[field]
    
    if not update_fields:
        conn.close()
        return jsonify({"error": "No valid fields to update"}), 400
    
    # Xây dựng câu query UPDATE
    query_parts = [f"{field} = ?" for field in update_fields.keys()]
    query = f"UPDATE employees SET {', '.join(query_parts)} WHERE id = ?"
    
    params = list(update_fields.values())
    params.append(employee_id)
    
    conn.execute(query, params)
    conn.commit()
    conn.close()
    
    return jsonify({
        "message": "Employee updated successfully"
    })

@app.route("/api/v1/devices", methods=["GET"])
@db_handler
def get_all_devices():
    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM devices ORDER BY name")
    devices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(devices)

# API để xử lý dữ liệu MQTT
@app.route("/api/v1/mqtt/process", methods=["POST"])
@db_handler
def process_mqtt_data():
    data = request.json
    
    if not data or "operator" not in data or data["operator"] != "RecPush":
        return jsonify({"error": "Invalid MQTT data format"}), 400
    
    info = data.get("info", {})
    person_id = info.get("personId")
    
    conn = get_db_connection()
    
    # Tìm nhân viên theo person_id
    employee_id = None
    if person_id:
        cursor = conn.execute("SELECT id FROM employees WHERE person_id = ?", (person_id,))
        result = cursor.fetchone()
        if result:
            employee_id = result["id"]
    
    # Thêm bản ghi chấm công
    cursor = conn.execute(
        """
        INSERT INTO attendance 
        (employee_id, person_id, record_id, timestamp, direction, verify_status, device_name, open_door_way, push_type, raw_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            employee_id,
            person_id,
            info.get("RecordID"),
            info.get("time"),
            info.get("direction"),
            info.get("VerifyStatus"),
            info.get("facesluiceName"),
            info.get("OpendoorWay"),
            info.get("PushType"),
            json.dumps(info)
        )
    )
    
    # Cập nhật thông tin thiết bị
    device_id = info.get("deviceID")
    if device_id:
        device_name = info.get("facesluiceName", "Unknown Device")
        
        conn.execute(
            """
            INSERT OR REPLACE INTO devices (device_id, name, status, last_active)
            VALUES (?, ?, 'active', datetime('now'))
            """,
            (device_id, device_name)
        )
    
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    
    return jsonify({
        "id": last_id,
        "message": "MQTT data processed successfully"
    }), 201

# Import dữ liệu khi khởi động
@app.before_first_request
def before_first_request():
    init_db()
    import_data_from_json()

if __name__ == "__main__":
    # Khởi tạo DB trước khi chạy server
    init_db()
    import_data_from_json()
    app.run(host="0.0.0.0", port=5000, debug=True)
