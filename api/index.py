from flask import Flask, request, jsonify
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import data_pb2  # ملف dat_pb2.py الذي تم إنشاؤه بواسطة protoc
import json
import asyncio
import aiohttp
import logging

# إعداد logging لعرض التحديثات
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # عرض الرسائل في الـ console
    ]
)

app = Flask(__name__)

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

# دالة لجلب JWT Token من الـ API بشكل غير متزامن
async def get_jwt_token(session, uid, password):
    url = f"https://l7aj-jwt-1.vercel.app/get?uid={uid}&password={password}"
    try:
        async with session.get(url, timeout=3) as response:
            if response.status == 200:
                token = await response.json()
                logging.info(f"تم جلب JWT Token بنجاح للحساب {uid}.")
                return uid, token.get("token")
            else:
                logging.warning(f"فشل في جلب JWT Token للحساب {uid}. حالة الاستجابة: {response.status}")
                return uid, None
    except asyncio.TimeoutError:
        logging.warning(f"انتهت مهلة الطلب لجلب JWT Token للحساب {uid}.")
        return uid, None
    except Exception as e:
        logging.error(f"حدث خطأ أثناء جلب JWT Token للحساب {uid}: {e}")
        return uid, None

# دالة لإرسال الطلب إلى السيرفر بشكل غير متزامن
async def send_request(session, url, encrypted_data, jwt_token):
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
        async with session.post(url, headers=headers, data=bytes.fromhex(encrypted_data)) as response:
            logging.info(f"تم إرسال الطلب بنجاح باستخدام JWT Token.")
            return response
    except Exception as e:
        logging.error(f"حدث خطأ أثناء إرسال الطلب: {e}")
        return None

# الدالة الرئيسية لتنفيذ العملية
@app.route('/process', methods=['GET'])
async def process():
    # قراءة الحسابات من ملف acc.txt
    accounts = read_accounts("acc.txt")
    logging.info(f"تم تحميل {len(accounts)} حسابًا من ملف acc.txt.")
    
    # Key and IV للتشفير
    key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
    iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
    
    # عنوان السيرفر
    url = "https://clientbp.ggblueshark.com/LikeProfile"
    
    # طلب إدخال ID و Code من المستخدم عبر query parameters
    request_id = int(request.args.get('id'))
    request_code = request.args.get('code')
    
    # إنشاء كائن RequestData
    request_data = data_pb2.RequestData()
    request_data.id = request_id  # تعيين الـ ID
    request_data.code = request_code  # تعيين الـ Code
    
    # تسلسل الكائن إلى بايتات
    data_bytes = request_data.SerializeToString()
    
    # تشفير البيانات
    encrypted_data = encrypt_data(data_bytes, key, iv)
    logging.info("تم تشفير البيانات بنجاح.")
    
    # جلب جميع JWT Tokens بشكل غير متزامن
    jwt_tokens = {}
    async with aiohttp.ClientSession() as session:
        tasks = [get_jwt_token(session, uid, password) for uid, password in accounts.items()]
        results = await asyncio.gather(*tasks)
        for uid, token in results:
            if token:
                jwt_tokens[uid] = token
    
    # إرسال الطلبات بشكل غير متزامن
    responses = []
    async with aiohttp.ClientSession() as session:
        tasks = [send_request(session, url, encrypted_data, jwt_token) for jwt_token in jwt_tokens.values()]
        results = await asyncio.gather(*tasks)
        for result in results:
            if result:
                responses.append({
                    "status_code": result.status,
                    "response_text": await result.text()
                })
            else:
                responses.append({"error": "Failed to send request"})
    
    return jsonify(responses)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
