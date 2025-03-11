from flask import Flask, request, jsonify
import aiohttp
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import data_pb2  # ملف data_pb2.py الذي تم إنشاؤه بواسطة protoc
import json
import asyncio
import logging

# إعداد logging لعرض التحديثات
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# إعداد Flask app مع دعم async
app = Flask(__name__)

# قراءة الحسابات من ملف acc.txt بشكل غير متزامن
async def read_accounts_async(file_path):
    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(None, lambda: open(file_path, "r").read())
    return json.loads(content)

# تشفير البيانات باستخدام AES
def encrypt_data(data, key, iv):
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = pad(data, AES.block_size)
    encrypted_data = cipher.encrypt(padded_data)
    return encrypted_data.hex()

# جلب JWT Token من الـ API بشكل غير متزامن باستخدام aiohttp
async def get_jwt_token_async(uid, password):
    url = f"https://l7aj-jwt-1.vercel.app/get?uid={uid}&password={password}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=3) as response:
                if response.status == 200:
                    data = await response.json()
                    logging.info(f"تم جلب JWT Token بنجاح للحساب {uid}.")
                    return uid, data.get("token")
                else:
                    logging.warning(f"فشل في جلب JWT Token للحساب {uid}. حالة الاستجابة: {response.status}")
                    return uid, None
    except Exception as e:
        logging.error(f"حدث خطأ أثناء جلب JWT Token للحساب {uid}: {e}")
        return uid, None

# إرسال الطلب إلى السيرفر بشكل غير متزامن باستخدام aiohttp
async def send_request_async(url, encrypted_data, jwt_token):
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
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=bytes.fromhex(encrypted_data)) as response:
                logging.info(f"تم إرسال الطلب بنجاح باستخدام JWT Token.")
                return response
    except Exception as e:
        logging.error(f"حدث خطأ أثناء إرسال الطلب: {e}")
        return None

# الدالة الرئيسية لإرسال اللايكات بشكل غير متزامن
async def send_likes_async(request_id, request_code):
    # قراءة الحسابات من ملف acc.txt
    accounts = await read_accounts_async("acc.txt")
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
    tasks = [get_jwt_token_async(uid, password) for uid, password in accounts.items()]
    results = await asyncio.gather(*tasks)
    jwt_tokens = {uid: token for uid, token in results if token}
    
    # إرسال الطلبات بشكل غير متزامن
    success_count = 0
    tasks = [send_request_async(url, encrypted_data, jwt_token) for jwt_token in jwt_tokens.values()]
    responses = await asyncio.gather(*tasks)
    for response in responses:
        if response and response.status == 200:
            success_count += 1
    
    # التحقق من النتائج
    if success_count == len(jwt_tokens):
        return {"status": "success", "message": "BY  ╭L7╯  L 7 A J ¹‎ ‎ ‎ ‎ ‎ TIKTOK : @l7aj..1m تم إرسال 100 لايك"}
    else:
        return {"status": "error", "message": "تحقق من ID والمنطقة"}

# نقطة النهاية (GET)
@app.route('/like', methods=['GET'])
async def like():
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
        result = await send_likes_async(request_id, request_code)
        
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
    app.run()  # لن يتم تحديد بورت هنا، Vercel سيحدد البورت تلقائ
