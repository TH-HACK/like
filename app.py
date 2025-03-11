from flask import Flask, request, jsonify
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import data_pb2  # ملف data_pb2.py الذي تم إنشاؤه بواسطة protoc
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# إعداد logging لعرض التحديثات
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # عرض الرسائل في الـ console
    ]
)

# دالة لقراءة الحسابات من ملف acc.txt
def read_accounts(file_path):
    with open(file_path, "r") as file:
        content = file.read()
        accounts = json.loads(content)
    return accounts

# دالة لتشفير البيانات باستخدام AES
def encrypt_data(data, key, iv):
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = pad(data, AES.block_size)
    encrypted_data = cipher.encrypt(padded_data)
    return encrypted_data.hex()

# دالة لجلب JWT Token من الـ API
def get_jwt_token(uid, password):
    url = f"https://l7aj-jwt-1.vercel.app/get?uid={uid}&password={password}"
    try:
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            logging.info(f"تم جلب JWT Token بنجاح للحساب {uid}.")
            return uid, response.json().get("token")
        else:
            logging.warning(f"فشل في جلب JWT Token للحساب {uid}. حالة الاستجابة: {response.status_code}")
            return uid, None
    except requests.Timeout:
        logging.warning(f"انتهت مهلة الطلب لجلب JWT Token للحساب {uid}.")
        return uid, None
    except Exception as e:
        logging.error(f"حدث خطأ أثناء جلب JWT Token للحساب {uid}: {e}")
        return uid, None

# دالة لإرسال الطلب إلى السيرفر
def send_request(url, encrypted_data, jwt_token):
    headers = {
        "Expect": "100-continue",
        "Authorization": f"Bearer {jwt_token}",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB48",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 11; SM-A305F Build/RP1A.200720.012)",
        "Host": "clientbp.ggblueshark.com",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }
    try:
        response = requests.post(url, headers=headers, data=bytes.fromhex(encrypted_data))
        logging.info(f"تم إرسال الطلب بنجاح باستخدام JWT Token.")
        return response
    except Exception as e:
        logging.error(f"حدث خطأ أثناء إرسال الطلب: {e}")
        return None

# الدالة الرئيسية لإرسال اللايكات
def send_likes(request_id, request_code):
    # قراءة الحسابات من ملف acc.txt
    accounts = read_accounts("acc.txt")
    logging.info(f"تم تحميل {len(accounts)} حسابًا من ملف acc.txt.")
    
    # Key and IV للتشفير
    key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
    iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
    
    # عنوان السيرفر
    url = "https://clientbp.ggblueshark.com/LikeProfile"
    
    # إنشاء كائن RequestData
    request_data = data_pb2.RequestData()
    request_data.id = request_id
    request_data.code = request_code
    
    # تسلسل الكائن إلى بايتات
    data_bytes = request_data.SerializeToString()
    
    # تشفير البيانات
    encrypted_data = encrypt_data(data_bytes, key, iv)
    logging.info("تم تشفير البيانات بنجاح.")
    
    # جلب جميع JWT Tokens بشكل غير متزامن
    jwt_tokens = {}
    with ThreadPoolExecutor(max_workers=100) as executor:
        future_to_uid = {
            executor.submit(get_jwt_token, uid, password): uid
            for uid, password in accounts.items()
        }
        
        # معالجة النتائج
        for future in as_completed(future_to_uid):
            uid, jwt_token = future.result()
            if jwt_token:
                jwt_tokens[uid] = jwt_token
    
    # إرسال 100 طلب في نفس الوقت باستخدام JWT Tokens
    success_count = 0
    with ThreadPoolExecutor(max_workers=100) as executor:
        future_to_uid = {
            executor.submit(send_request, url, encrypted_data, jwt_token): uid
            for uid, jwt_token in jwt_tokens.items()
        }
        
        # معالجة النتائج
        for future in as_completed(future_to_uid):
            response = future.result()
            if response and response.status_code == 200:
                success_count += 1
    
    # التحقق من النتائج
    if success_count == len(jwt_tokens):
        return {"status": "success", "message": "تم إرسال 100 لايك"}
    else:
        return {"status": "error", "message": "تحقق من ID والمنطقة"}

# إعداد Flask API
app = Flask(__name__)

@app.route('/like', methods=['GET'])
def like():
    try:
        # استخراج البيانات من الطلب كمعلمات استعلام
        request_id = request.args.get("id")
        request_code = request.args.get("code")
        
        if not request_id or not request_code:
            return jsonify({"error": "Missing 'id' or 'code' in query parameters."}), 400
        
        # تحويل الـ ID إلى عدد صحيح
        try:
            request_id = int(request_id)
        except ValueError:
            return jsonify({"error": "'id' must be a valid integer."}), 400
        
        # إرسال اللايكات
        result = send_likes(request_id, request_code)
        
        # إرجاع الاستجابة
        if result["status"] == "success":
            return jsonify({"message": result["message"]}), 200
        else:
            return jsonify({"error": result["message"]}), 400
    except Exception as e:
        logging.error(f"حدث خطأ أثناء معالجة الطلب: {e}")
        return jsonify({"error": str(e)}), 500

# تشغيل التطبيق
if __name__ == "__main__":
    app.run()  # لن يتم تحديد بورت هنا، Vercel سيحدد البورت تلقائيًا
