"""
E2E Client Module
Server ile end-to-end şifreli iletişim için Python client library
"""

import requests

from heaan_encrypted.server.e2e_encryption import E2EEncryptionClient

# =============================================================================
# E2E CLIENT CLASS
# =============================================================================

class E2EClient:
    """Server ile E2E şifreli iletişim kuran client"""
    
    #1 Kullanım Sırası: İlk (Client oluşturulurken çağrılır)
    # Açıklama: Client başlatır ve server'ın public key'ini alır
    def __init__(self, server_url: str = "http://localhost:9200"):
        self.server_url = server_url.rstrip("/")
        self.encryption_client = None
        self._initialize_encryption()
    
    #2 Kullanım Sırası: __init__ içinde çağrılır
    # Açıklama: Server'ın public key'ini alır ve E2EEncryptionClient oluşturur
    def _initialize_encryption(self):
        try:
            response = requests.get(f"{self.server_url}/public_key")
            response.raise_for_status()
            
            data = response.json()
            server_public_key_pem = data["public_key_pem"]
            self.encryption_client = E2EEncryptionClient(server_public_key_pem)
        except Exception as e:
            raise Exception(f"Şifreleme başlatma hatası: {e}")
    
    #3 Kullanım Sırası: Encrypted request gönderirken çağrılır
    # Açıklama: Query'yi şifreler, server'a gönderir, response'u decrypt eder
    def generate_encrypted(
        self,
        query: str,
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        enable_pii_protection: bool = True,
        enable_dp: bool = False
    ) -> dict:
        if not self.encryption_client:
            raise Exception("Şifreleme başlatılmamış")
        
        # Query'yi şifrele
        encrypted_request = self.encryption_client.encrypt_query(query)
        
        # Şifreli isteği gönder
        payload = {
            **encrypted_request,
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "enable_pii_protection": enable_pii_protection,
            "enable_dp": enable_dp
        }
        
        try:
            response = requests.post(
                f"{self.server_url}/generate_encrypted",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise Exception(f"Server hatası: {response.status_code} - {response.text}")
        except Exception as e:
            raise Exception(f"İstek başarısız: {e}")
        
        encrypted_response = response.json()
        
        # Response'u decrypt et
        decrypted_response = self.encryption_client.decrypt_response({
            "encrypted_response": encrypted_response["encrypted_response"],
            "nonce": encrypted_response["nonce"]
        })
        
        return {
            "response": decrypted_response,
            "processing_time_ms": encrypted_response["processing_time_ms"],
            "model": encrypted_response["model"],
            "timing_breakdown": encrypted_response.get("timing_breakdown", {}),
            "pii_protection_applied": encrypted_response.get("pii_protection_applied", False),
            "dp_applied": encrypted_response.get("dp_applied", False),
            "security_warnings": encrypted_response.get("security_warnings", [])
        }
    
    #4 Kullanım Sırası: Plaintext request gönderirken çağrılır
    # Açıklama: Query'yi plaintext olarak gönderir (şifreleme yok)
    def generate_plaintext(
        self,
        query: str,
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        enable_pii_protection: bool = True,
        enable_dp: bool = False
    ) -> dict:
        payload = {
            "query": query,
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "enable_pii_protection": enable_pii_protection,
            "enable_dp": enable_dp
        }
        
        try:
            response = requests.post(
                f"{self.server_url}/generate",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise Exception(f"Server hatası: {response.status_code} - {response.text}")
        except Exception as e:
            raise Exception(f"İstek başarısız: {e}")
        
        return response.json()
