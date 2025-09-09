# server/crypto_utils.py
from argon2 import PasswordHasher, Type
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import constant_time
from cryptography.hazmat.backends import default_backend
from nacl.secret import SecretBox
from nacl.utils import random as nacl_random
from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt, crypto_aead_xchacha20poly1305_ietf_decrypt

ph = PasswordHasher(time_cost=4, memory_cost=2**18, parallelism=2, hash_len=32, type=Type.ID)

def hash_passphrase(passphrase: str) -> str:
    return ph.hash(passphrase)

def verify_passphrase(stored_hash: str, candidate: str) -> bool:
    try:
        return ph.verify(stored_hash, candidate)
    except Exception:
        return False

def derive_master_key_from_passphrase(passphrase: bytes, salt: bytes, length: int = 32) -> bytes:
    """
    Use Argon2id externally (you can run Argon2 to get a raw key) or use HKDF on a pre-derived secret.
    Here we assume passphrase byte string + salt and produce master key via HKDF for simplicity.
    """
    hk = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=b"secure-chat-master-key",
        backend=default_backend()
    )
    return hk.derive(passphrase)

def hkdf_split(master_key: bytes) -> dict:
    # produce two separate keys: encryption_key and mac_key
    hk = HKDF(algorithm=hashes.SHA256(), length=64, salt=None, info=b"chat-key-split", backend=default_backend())
    out = hk.derive(master_key)
    return {"enc": out[:32], "mac": out[32:]}

# PyNaCl XChaCha20-Poly1305 helpers (server-side decrypt example)
def xchacha20_encrypt(key: bytes, plaintext: bytes, aad: bytes = b""):
    nonce = nacl_random(24)  # 24 bytes for XChaCha
    ct = crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, key)
    return nonce + ct  # return nonce || ciphertext

def xchacha20_decrypt(key: bytes, nonce_and_ct: bytes, aad: bytes = b""):
    nonce = nonce_and_ct[:24]
    ct = nonce_and_ct[24:]
    return crypto_aead_xchacha20poly1305_ietf_decrypt(ct, aad, nonce, key)
# crypto_utils.py

# 32-byte static master key (base64 for demo purposes)
STATIC_MASTER_KEY = b'\x01' * 32  # You can generate a proper random key for production

def get_static_key() -> bytes:
    return STATIC_MASTER_KEY
