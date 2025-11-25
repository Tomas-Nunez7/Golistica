import os
import bcrypt
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import socket
import json

load_dotenv()

APP_SECRET = os.getenv('APP_SECRET_KEY', 'change-me')
MASTER_KEY = os.getenv('MASTER_KEY', None)  # should be a base64 32-byte for Fernet or generated via Fernet.generate_key()
ALERT_HOST = os.getenv('ALERT_HOST', '127.0.0.1')
ALERT_PORT = int(os.getenv('ALERT_PORT', '9001'))

def hash_password(plain: str) -> str:
    ph = bcrypt.hashpw(plain.encode(), bcrypt.gensalt())
    return ph.decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def get_fernet():
    if not MASTER_KEY:
        # generate a key for dev (not for production)
        return Fernet(Fernet.generate_key())
    return Fernet(MASTER_KEY.encode() if isinstance(MASTER_KEY, str) else MASTER_KEY)

def encrypt_value(plaintext: str) -> bytes:
    f = get_fernet()
    return f.encrypt(plaintext.encode())

def decrypt_value(token: bytes) -> str:
    f = get_fernet()
    return f.decrypt(token).decode()

def send_tcp_alert(obj: dict):
    payload = json.dumps(obj).encode()
    try:
        with socket.create_connection((ALERT_HOST, ALERT_PORT), timeout=2) as s:
            s.sendall(payload + b"\n")
            return True
    except Exception as e:
        # best-effort: return False if can't send
        print('TCP alert send failed:', e)
        return False
