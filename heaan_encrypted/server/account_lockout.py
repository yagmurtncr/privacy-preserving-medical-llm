#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Account Lockout Module - Brute Force Protection
5 yanlış denemeden sonra hesap kilitleme
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Tuple


class AccountLockout:
    """
    Brute force saldırılarına karşı hesap kilitleme
    
    Özellikler:
    - 5 yanlış denemeden sonra 15 dakika kilitleme
    - IP bazlı ve kullanıcı bazlı takip
    - Otomatik temizleme (1 saat sonra eski kayıtlar silinir)
    """
    
    def __init__(self, max_attempts: int = 5, lockout_duration: int = 15):
        """
        Args:
            max_attempts: Maksimum yanlış deneme sayısı (default: 5)
            lockout_duration: Kilitleme süresi (dakika, default: 15)
        """
        self.max_attempts = max_attempts
        self.lockout_duration = lockout_duration
        self.failed_attempts = defaultdict(list)  # username: [timestamp1, timestamp2, ...]
        self.locked_accounts = {}  # username: lock_until_timestamp
        self.ip_attempts = defaultdict(list)  # ip: [timestamp1, timestamp2, ...]
        
        print(f"✅ Account Lockout initialized (max_attempts: {max_attempts}, lockout: {lockout_duration}min)")
    
    def record_failed_attempt(self, username: str, ip: str = None) -> Tuple[bool, str]:
        """
        Başarısız giriş denemesi kaydet
        
        Args:
            username: Kullanıcı adı
            ip: IP adresi (opsiyonel)
        
        Returns:
            (is_locked, message)
        """
        _now = datetime.now()
        
        # Kullanıcı bazlı takip
        self.failed_attempts[username].append(now)
        
        # IP bazlı takip (opsiyonel)
        if ip:
            self.ip_attempts[ip].append(now)
        
        # Eski kayıtları temizle (1 saat öncesinden)
        cutoff = now - timedelta(hours=1)
        self.failed_attempts[username] = [
            ts for ts in self.failed_attempts[username] if ts > cutoff
        ]
        
        # Max attempt kontrolü
        attempt_count = len(self.failed_attempts[username])
        
        if attempt_count >= self.max_attempts:
            # Hesabı kilitle
            lock_until = now + timedelta(minutes=self.lockout_duration)
            self.locked_accounts[username] = lock_until
            
            message = (
                f"Çok fazla başarısız deneme! "
                f"Hesap {self.lockout_duration} dakika kilitlendi. "
                f"(Deneme: {attempt_count}/{self.max_attempts})"
            )
            
            print(f"🔒 Account locked: {username} (attempts: {attempt_count}, until: {lock_until})")
            return True, message
        
        remaining = self.max_attempts - attempt_count
        message = f"Geçersiz kimlik bilgileri. Kalan deneme: {remaining}/{self.max_attempts}"
        return False, message
    
    def is_locked(self, username: str) -> Tuple[bool, int]:
        """
        Hesap kilitli mi kontrol et
        
        Args:
            username: Kullanıcı adı
        
        Returns:
            (is_locked, remaining_seconds)
        """
        if username not in self.locked_accounts:
            return False, 0
        
        lock_until = self.locked_accounts[username]
        now = datetime.now()
        
        if now < lock_until:
            # Hala kilitli
            remaining = int((lock_until - now).total_seconds())
            return True, remaining
        else:
            # Kilit süresi doldu - temizle
            del self.locked_accounts[username]
            if username in self.failed_attempts:
                del self.failed_attempts[username]
            return False, 0
    
    def reset_attempts(self, username: str):
        """
        Başarılı giriş sonrası sayacı sıfırla
        
        Args:
            username: Kullanıcı adı
        """
        if username in self.failed_attempts:
            del self.failed_attempts[username]
        
        if username in self.locked_accounts:
            del self.locked_accounts[username]
        
        print(f"✅ Login attempts reset: {username}")
    
    def unlock_account(self, username: str):
        """
        Hesabı manuel olarak kilidi aç (admin için)
        
        Args:
            username: Kullanıcı adı
        """
        if username in self.locked_accounts:
            del self.locked_accounts[username]
        
        if username in self.failed_attempts:
            del self.failed_attempts[username]
        
        print(f"🔓 Account manually unlocked: {username}")
    
    def get_stats(self) -> dict:
        """
        Kilitleme istatistiklerini döndür
        
        Returns:
            dict: İstatistikler
        """
        now = datetime.now()
        
        return {
            "locked_accounts": len(self.locked_accounts),
            "locked_users": list(self.locked_accounts.keys()),
            "total_failed_attempts": sum(len(attempts) for attempts in self.failed_attempts.values()),
            "users_with_failed_attempts": len(self.failed_attempts),
            "config": {
                "max_attempts": self.max_attempts,
                "lockout_duration_minutes": self.lockout_duration
            }
        }
    
    def cleanup_old_records(self):
        """
        Eski kayıtları temizle (periyodik olarak çağrılmalı)
        """
        now = datetime.now()
        cutoff = now - timedelta(hours=1)
        
        # Süresi dolmuş kilitleri temizle
        expired_locks = [
            username for username, lock_until in self.locked_accounts.items()
            if now >= lock_until
        ]
        
        for username in expired_locks:
            del self.locked_accounts[username]
        
        # Eski failed attempt'leri temizle
        for username in list(self.failed_attempts.keys()):
            self.failed_attempts[username] = [
                ts for ts in self.failed_attempts[username] if ts > cutoff
            ]
            
            # Boş liste varsa sil
            if not self.failed_attempts[username]:
                del self.failed_attempts[username]
        
        if expired_locks:
            print(f"🧹 Cleanup: {len(expired_locks)} expired locks removed")


# Global instance
account_lockout = AccountLockout(max_attempts=5, lockout_duration=15)

