import base64
import getpass
import hashlib
import secrets


iterations = 600_000
password = getpass.getpass("AutoTorrent login password: ")
salt = secrets.token_bytes(16)
digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
print(f"AUTOTORRENT_PASSWORD_HASH=pbkdf2_sha256${iterations}${encode(salt)}${encode(digest)}")
print("AUTOTORRENT_SESSION_SECRET=" + secrets.token_urlsafe(32))
