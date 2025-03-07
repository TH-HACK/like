from flask import Flask, request, jsonify
import aiohttp
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import data_pb2
import json
import logging #اا

app = Flask(__name__)

# Configuration constants
KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
IV = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
URL = "https://clientbp.ggblueshark.com/LikeProfile"
ACCOUNTS_FILE = "acc.txt"
JWT_FILE = "jwt.txt"

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

def read_accounts():
    with open(ACCOUNTS_FILE, "r") as f:
        return json.load(f)

def encrypt_data(data):
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    return cipher.encrypt(pad(data, AES.block_size)).hex()

async def get_jwt_token(session, uid, password):
    url = f"https://l7aj-jwt-1.vercel.app/get?uid={uid}&password={password}"
    try:
        async with session.get(url, timeout=3) as response:
            if response.status == 200:
                return uid, (await response.json()).get("token")
            logging.warning(f"JWT fetch failed for {uid}: {response.status}")
    except Exception as e:
        logging.error(f"Error fetching JWT for {uid}: {str(e)}")
    return uid, None

async def send_request(session, encrypted_data, token):
    headers = {
        "Expect": "100-continue",
        "Authorization": f"Bearer {token}",
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
        async with session.post(
            URL,
            headers=headers,
            data=bytes.fromhex(encrypted_data)
        ) as response:
            return await response.text()
    except Exception as e:
        logging.error(f"Request failed: {str(e)}")
        return None

def save_tokens(tokens):
    with open(JWT_FILE, "w") as f:
        json.dump(tokens, f)
    logging.info(f"Saved {len(tokens)} tokens to {JWT_FILE}")

@app.route('/process', methods=['GET'])
async def process():
    # Get parameters
    req_id = request.args.get('id', type=int)
    req_code = request.args.get('code', type=str)
    if not req_id or not req_code:
        return jsonify({"error": "Missing required parameters"}), 400

    # Prepare request data
    req_data = data_pb2.RequestData()
    req_data.id = req_id
    req_data.code = req_code
    encrypted = encrypt_data(req_data.SerializeToString())

    # Get accounts
    accounts = read_accounts()
    logging.info(f"Loaded {len(accounts)} accounts")

    # Fetch JWT tokens
    async with aiohttp.ClientSession() as session:
        jwt_tasks = [get_jwt_token(session, uid, pwd) for uid, pwd in accounts.items()]
        results = await asyncio.gather(*jwt_tasks)
    
    tokens = {uid: token for uid, token in results if token}
    save_tokens(tokens)
    
    # Send requests
    async with aiohttp.ClientSession() as session:
        send_tasks = [send_request(session, encrypted, token) for token in tokens.values()]
        await asyncio.gather(*send_tasks)
    
    return jsonify({
        "status": "completed",
        "total_accounts": len(accounts),
        "successful_tokens": len(tokens),
        "encrypted_data": encrypted
    })

if __name__ == '__main__':
    app.run()
