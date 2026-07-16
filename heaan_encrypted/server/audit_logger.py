"""
Audit Logger Module
GDPR/KVKK uyumlu audit logging (IP anonymization, hash salting, JSONL format)
"""

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# =============================================================================
# AUDIT LOGGER CLASS
# =============================================================================

class AuditLogger:
    """GDPR/KVKK uyumlu audit logger (IP anonymization + hash salting)"""
    
    # Kullanım Sırası: 1 (Server başlatılırken oluşturulur)
    # Açıklama: Audit logger'ı başlatır ve günlük log dosyası oluşturur
    def __init__(self, log_dir: str = "logs/audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.log_file = self.log_dir / f"audit_{today}.jsonl"
    
    # Kullanım Sırası: 3 (log_request içinde çağrılır)
    # Açıklama: IP adresini GDPR uyumlu maskeler (127.0.0.1 → 127.0.0.xxx)
    def _anonymize_ip(self, ip: str) -> str:
        try:
            if ':' in ip:  # IPv6
                parts = ip.split(':')
                return ':'.join(parts[:-1]) + ':xxx'
            else:  # IPv4
                parts = ip.split('.')
                return '.'.join(parts[:3]) + '.xxx' if len(parts) == 4 else 'xxx.xxx.xxx.xxx'
        except Exception:
            return 'xxx.xxx.xxx.xxx'
    
    # Kullanım Sırası: 4 (log_request içinde çağrılır)
    # Açıklama: User agent'ı maskeler (curl/7.81.0 → curl/x.x.x)
    def _anonymize_user_agent(self, user_agent: str) -> str:
        try:
            if '/' in user_agent:
                tool = user_agent.split('/')[0]
                return f"{tool}/x.x.x"
            return user_agent.split(' ')[0] + "/x.x.x"
        except Exception:
            return "unknown/x.x.x"
    
    # Kullanım Sırası: 5 (log_request içinde çağrılır)
    # Açıklama: PII'ı salted hash'ler (rainbow table attack önleme)
    def _hash_pii(self, text: str) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        salt = secrets.token_hex(8)
        data = f"{text}{timestamp}{salt}".encode()
        return hashlib.sha256(data).hexdigest()[:16]
    
    # Kullanım Sırası: 2 (Her request sonunda çağrılır)
    # Açıklama: Request/response'u GDPR uyumlu şekilde loglar
    def log_request(self,
                   username: str,
                   endpoint: str,
                   request_data: Dict[str, Any],
                   response_data: Dict[str, Any],
                   client_ip: str,
                   user_agent: str,
                   processing_time_ms: float,
                   success: bool,
                   pii_detected: bool = False,
                   pii_count: int = 0,
                   error_message: Optional[str] = None,
                   security_warnings: list = None):
        
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "request",
            "username": username,
            "endpoint": endpoint,
            "success": success,
            "processing_time_ms": round(processing_time_ms, 2),
            "ip_address": self._anonymize_ip(client_ip),  # GDPR: anonymized
            "user_agent": self._anonymize_user_agent(user_agent),  # Fingerprinting önleme
            "query_hash": self._hash_pii(request_data.get("query", "")),  # Salted hash
            "pii_detected": pii_count,
            "model_encrypted": response_data.get("model_encrypted_in_memory", False),
            "error": error_message
        }
        
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    # Kullanım Sırası: 6 (Login endpoint'inde çağrılır)
    # Açıklama: Başarılı/başarısız login denemelerini loglar
    def log_authentication(self,
                          username: str,
                          client_ip: str,
                          success: bool,
                          failure_reason: Optional[str] = None):
        
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "authentication",
            "username": username,
            "success": success,
            "ip_address": self._anonymize_ip(client_ip),
            "failure_reason": failure_reason
        }
        
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    # Kullanım Sırası: 7 (Güvenlik olaylarında çağrılır)
    # Açıklama: Güvenlik olaylarını (rate limit, invalid input) loglar
    def log_security_event(self,
                          event_type: str,
                          severity: str,
                          description: str,
                          client_ip: str,
                          user_agent: str,
                          username: Optional[str] = None):
        
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "security",
            "severity": severity,
            "description": description,
            "username": username,
            "ip_address": self._anonymize_ip(client_ip),
            "user_agent": self._anonymize_user_agent(user_agent)
        }
        
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

audit_logger = AuditLogger()
