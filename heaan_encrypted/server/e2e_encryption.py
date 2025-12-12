"""
E2E Encryption Module
Client-Server arası end-to-end şifreleme (RSA-2048 + AES-256-GCM hybrid)
"""

import base64
import secrets
from typing import Dict, Tuple, Any, cast

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend

# =============================================================================
# SERVER-SIDE E2E ENCRYPTION
# =============================================================================

class E2EEncryptionManager:
    """Server-side E2E şifreleme yöneticisi (RSA key yükleme + decrypt/encrypt)"""
    
    # Kullanım Sırası: 1 (Server başlatılırken oluşturulur)
    # Açıklama: RSA public/private key'leri yükler
    def __init__(self, private_key_path: str, public_key_path: str):
        # RSA private key yükle
        with open(private_key_path, "rb") as f:
            self.private_key: RSAPrivateKey = cast(
                RSAPrivateKey,
                serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
            )
        
        # RSA public key yükle
        with open(public_key_path, "rb") as f:
            self.public_key: RSAPublicKey = cast(
                RSAPublicKey,
                serialization.load_pem_public_key(f.read(), backend=default_backend())
            )
    
    # Kullanım Sırası: 2 (/public_key endpoint'inde çağrılır)
    # Açıklama: Server'ın public key'ini PEM formatında döndürür
    def get_public_key_pem(self) -> str:
        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode('utf-8')
    
    # Kullanım Sırası: 3 (process_encrypted_request içinde çağrılır)
    # Açıklama: Client'ın RSA ile şifrelenmiş AES key'ini decrypt eder
    def decrypt_client_key(self, encrypted_key_b64: str) -> bytes:
        encrypted_key = base64.b64decode(encrypted_key_b64)
        aes_key = self.private_key.decrypt(
            encrypted_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        return aes_key
    
    # Kullanım Sırası: 4 (process_encrypted_request içinde çağrılır)
    # Açıklama: Client'ın AES ile şifrelenmiş query'sini decrypt eder
    def decrypt_query(self, encrypted_query_b64: str, aes_key: bytes, nonce_b64: str) -> str:
        encrypted_query = base64.b64decode(encrypted_query_b64)
        nonce = base64.b64decode(nonce_b64)
        aesgcm = AESGCM(aes_key)
        plaintext_bytes = aesgcm.decrypt(nonce, encrypted_query, None)
        return plaintext_bytes.decode('utf-8')
    
    # Kullanım Sırası: 5 (create_encrypted_response içinde çağrılır)
    # Açıklama: Server response'unu AES ile şifreler
    def encrypt_response(self, response: str, aes_key: bytes) -> Tuple[str, str]:
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(nonce, response.encode('utf-8'), None)
        encrypted_response_b64 = base64.b64encode(ciphertext).decode('utf-8')
        nonce_b64 = base64.b64encode(nonce).decode('utf-8')
        return encrypted_response_b64, nonce_b64
    
    # Kullanım Sırası: 6 (/generate_encrypted endpoint'inde çağrılır - decrypt aşaması)
    # Açıklama: Client'tan gelen tüm encrypted request'i decrypt eder
    def process_encrypted_request(self, encrypted_request: Dict[str, Any]) -> Tuple[str, bytes]:
        aes_key = self.decrypt_client_key(encrypted_request["encrypted_key"])
        query = self.decrypt_query(encrypted_request["encrypted_query"], aes_key, encrypted_request["nonce"])
        return query, aes_key
    
    # Kullanım Sırası: 7 (/generate_encrypted endpoint'inde çağrılır - encrypt aşaması)
    # Açıklama: Server response'unu şifreli hale getirir
    def create_encrypted_response(self, response: str, aes_key: bytes) -> Dict[str, str]:
        encrypted_response, nonce = self.encrypt_response(response, aes_key)
        return {
            "encrypted_response": encrypted_response,
            "nonce": nonce,
            "encryption_method": "AES-256-GCM"
        }


# =============================================================================
# CLIENT-SIDE E2E ENCRYPTION
# =============================================================================

class E2EEncryptionClient:
    """Client-side şifreleme yardımcısı (Python client library için)"""
    
    # Kullanım Sırası: 1 (Client başlatılırken çağrılır)
    # Açıklama: Server'ın public key'ini yükler
    def __init__(self, server_public_key_pem: str):
        self.public_key: RSAPublicKey = cast(
            RSAPublicKey,
            serialization.load_pem_public_key(server_public_key_pem.encode('utf-8'), backend=default_backend())
        )
        self.aes_key: bytes | None = None
    
    # Kullanım Sırası: 2 (Client query göndermeden önce çağrılır)
    # Açıklama: Query'yi şifreler ve AES key'i RSA ile korur
    def encrypt_query(self, query: str) -> Dict[str, str]:
        # AES key üret (256-bit)
        self.aes_key = secrets.token_bytes(32)
        nonce = secrets.token_bytes(12)
        
        # Query'yi AES-GCM ile şifrele
        aesgcm = AESGCM(self.aes_key)
        encrypted_query = aesgcm.encrypt(nonce, query.encode('utf-8'), None)
        
        # AES key'i RSA ile şifrele
        encrypted_key = self.public_key.encrypt(
            self.aes_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        
        return {
            "encrypted_query": base64.b64encode(encrypted_query).decode('utf-8'),
            "encrypted_key": base64.b64encode(encrypted_key).decode('utf-8'),
            "nonce": base64.b64encode(nonce).decode('utf-8')
        }
    
    # Kullanım Sırası: 3 (Server'dan response alındıktan sonra çağrılır)
    # Açıklama: Server'ın şifreli response'unu decrypt eder
    def decrypt_response(self, encrypted_response: Dict[str, str]) -> str:
        if not self.aes_key:
            raise ValueError("AES key mevcut değil. Önce encrypt_query çağırın!")
        
        encrypted_response_bytes = base64.b64decode(encrypted_response["encrypted_response"])
        nonce = base64.b64decode(encrypted_response["nonce"])
        aesgcm = AESGCM(self.aes_key)
        plaintext = aesgcm.decrypt(nonce, encrypted_response_bytes, None)
        return plaintext.decode('utf-8')
