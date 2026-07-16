#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Security Logger - Güvenlik olaylarını logla
"""

import datetime
import json
from pathlib import Path


class SecurityLogger:
    """
    Kullanım Sırası: Her güvenlik olayında çağrılır
    Açıklama: Güvenlik olaylarını (blocked IP, injection attempt, etc.) loglar
    """
    
    def __init__(self, log_file: str = "logs/security.log"):
        """
        Kullanım Sırası: 0 (Server startup'ta)
        Açıklama: Security logger'ı başlatır
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        print(f"✅ Security Logger initialized: {self.log_file}")
    
    def log_event(self, event_type: str, details: dict):
        """
        Kullanım Sırası: Her güvenlik olayında
        Açıklama: Güvenlik olayını dosyaya yazar
        
        Args:
            event_type: "blocked_ip", "injection_attempt", "rate_limit", etc.
            details: Olay detayları (dict)
        """
        event = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "type": event_type,
            "details": details
        }
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    
    def log_validation_error(self, **kwargs):
        """
        Kullanım Sırası: Validation hatası olduğunda
        Açıklama: Validation hatasını loglar
        """
        self.log_event("validation_error", kwargs)
    
    def log_server_error(self, **kwargs):
        """
        Kullanım Sırası: Server error olduğunda
        Açıklama: Server hatasını loglar
        """
        self.log_event("server_error", kwargs)
    
    def log_authentication(self, **kwargs):
        """
        Kullanım Sırası: Auth event olduğunda
        Açıklama: Authentication olayını loglar
        """
        self.log_event("authentication", kwargs)
    
    def log_security_event(self, **kwargs):
        """
        Kullanım Sırası: Güvenlik olayı olduğunda
        Açıklama: Güvenlik olayını loglar
        """
        self.log_event("security_event", kwargs)
    
    def log_request(self, **kwargs):
        """
        Kullanım Sırası: API request olayında
        Açıklama: API request'i loglar (başarılı veya başarısız)
        """
        self.log_event("api_request", kwargs)
    
    def get_stats(self):
        """
        Kullanım Sırası: İsteğe bağlı (/stats endpoint'ten)
        Açıklama: Güvenlik istatistiklerini döner
        """
        return {
            "log_file": str(self.log_file),
            "exists": self.log_file.exists()
        }


# Global instance
security_logger = SecurityLogger()

