import hashlib
import secrets

def generate_api_key():
    return "dg_sk_"+secrets.token_urlsafe(32)

def hash_api_key(api_key:str):
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

def api_key_prefix(api_key:str):
    return api_key[:12]