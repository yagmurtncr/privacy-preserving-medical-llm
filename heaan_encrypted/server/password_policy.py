#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Password Policy Module - Güçlü Şifre Zorunluluğu
Min 12 karakter, büyük/küçük harf, rakam, özel karakter
"""

import re
from typing import Tuple


class PasswordPolicy:
    """
    Şifre güvenlik politikası
    
    Kurallar:
    - Minimum 12 karakter
    - En az 1 büyük harf (A-Z)
    - En az 1 küçük harf (a-z)
    - En az 1 rakam (0-9)
    - En az 1 özel karakter (!@#$%^&*...)
    - Yaygın şifreleri engelleme
    """
    
    # Konfigürasyon
    MIN_LENGTH = 12
    REQUIRE_UPPERCASE = True
    REQUIRE_LOWERCASE = True
    REQUIRE_DIGIT = True
    REQUIRE_SPECIAL = True
    
    # Yaygın zayıf şifreler (blacklist)
    COMMON_PASSWORDS = [
        # Çok yaygın şifreler
        "password", "123456", "12345678", "1234567890", "qwerty", "abc123",
        "password123", "admin", "letmein", "welcome", "monkey", "dragon",
        "master", "sunshine", "princess", "football", "iloveyou", "trustno1",
        
        # Türkçe yaygın şifreler
        "sifre123", "sifre", "parola", "parola123", "admin123",
        
        # Klavye pattern'leri
        "qwertyuiop", "asdfghjkl", "zxcvbnm", "1qaz2wsx", "1q2w3e4r",
        
        # Tarih pattern'leri
        "12345", "123456789", "11111111", "00000000"
    ]
    
    @staticmethod
    def validate(password: str, username: str = None) -> Tuple[bool, str]:
        """
        Şifrenin policy'ye uygun olup olmadığını kontrol et
        
        Args:
            password: Kontrol edilecek şifre
            username: Kullanıcı adı (opsiyonel, şifrede kullanıcı adı olmasın)
        
        Returns:
            (is_valid, error_message)
        """
        
        # 1. Uzunluk kontrolü
        if len(password) < PasswordPolicy.MIN_LENGTH:
            return False, f"Şifre en az {PasswordPolicy.MIN_LENGTH} karakter olmalıdır (mevcut: {len(password)})"
        
        # 2. Büyük harf kontrolü
        if PasswordPolicy.REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            return False, "Şifre en az 1 büyük harf (A-Z) içermelidir"
        
        # 3. Küçük harf kontrolü
        if PasswordPolicy.REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            return False, "Şifre en az 1 küçük harf (a-z) içermelidir"
        
        # 4. Rakam kontrolü
        if PasswordPolicy.REQUIRE_DIGIT and not re.search(r'\d', password):
            return False, "Şifre en az 1 rakam (0-9) içermelidir"
        
        # 5. Özel karakter kontrolü
        if PasswordPolicy.REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/`~]', password):
            return False, "Şifre en az 1 özel karakter (!@#$%^&*...) içermelidir"
        
        # 6. Yaygın şifreler kontrolü (case insensitive)
        password_lower = password.lower()
        for common_pass in PasswordPolicy.COMMON_PASSWORDS:
            if common_pass in password_lower:
                return False, "Bu şifre çok yaygın kullanılıyor. Daha güçlü bir şifre seçin."
        
        # 7. Kullanıcı adı kontrolü (şifrede kullanıcı adı olmasın)
        if username and username.lower() in password_lower:
            return False, "Şifre kullanıcı adınızı içeremez"
        
        # 8. Ardışık karakterler kontrolü (123456, abcdef)
        if PasswordPolicy._has_sequential_chars(password):
            return False, "Şifre çok fazla ardışık karakter içeriyor (örn: 123456, abcdef)"
        
        # 9. Tekrarlanan karakterler kontrolü (aaaaaa, 111111)
        if PasswordPolicy._has_repeated_chars(password):
            return False, "Şifre çok fazla tekrarlanan karakter içeriyor (örn: aaaa, 1111)"
        
        # Tüm kontroller geçti
        return True, "OK"
    
    @staticmethod
    def _has_sequential_chars(password: str, max_sequential: int = 4) -> bool:
        """
        Ardışık karakterleri kontrol et (123456, abcdef)
        
        Args:
            password: Şifre
            max_sequential: Maksimum ardışık karakter sayısı
        
        Returns:
            bool: Çok fazla ardışık karakter var mı?
        """
        sequential_count = 1
        
        for i in range(1, len(password)):
            if ord(password[i]) == ord(password[i-1]) + 1:
                sequential_count += 1
                if sequential_count >= max_sequential:
                    return True
            else:
                sequential_count = 1
        
        return False
    
    @staticmethod
    def _has_repeated_chars(password: str, max_repeated: int = 3) -> bool:
        """
        Tekrarlanan karakterleri kontrol et (aaaa, 1111)
        
        Args:
            password: Şifre
            max_repeated: Maksimum tekrar sayısı
        
        Returns:
            bool: Çok fazla tekrarlanan karakter var mı?
        """
        repeat_count = 1
        
        for i in range(1, len(password)):
            if password[i] == password[i-1]:
                repeat_count += 1
                if repeat_count >= max_repeated:
                    return True
            else:
                repeat_count = 1
        
        return False
    
    @staticmethod
    def get_strength_score(password: str) -> Tuple[int, str]:
        """
        Şifre gücü skoru hesapla (0-100)
        
        Args:
            password: Şifre
        
        Returns:
            (score, description)
        """
        score = 0
        
        # Uzunluk bonusu (max 40 puan)
        length_score = min(len(password) * 2, 40)
        score += length_score
        
        # Karakter çeşitliliği (max 60 puan)
        if re.search(r'[a-z]', password):
            score += 15
        if re.search(r'[A-Z]', password):
            score += 15
        if re.search(r'\d', password):
            score += 15
        if re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/`~]', password):
            score += 15
        
        # Skor açıklaması
        if score < 40:
            description = "Çok Zayıf"
        elif score < 60:
            description = "Zayıf"
        elif score < 75:
            description = "Orta"
        elif score < 90:
            description = "Güçlü"
        else:
            description = "Çok Güçlü"
        
        return score, description
    
    @staticmethod
    def generate_suggestion() -> str:
        """
        Güçlü şifre önerisi mesajı
        
        Returns:
            str: Öneri mesajı
        """
        return (
            f"Güçlü şifre oluşturmak için:\n"
            f"• En az {PasswordPolicy.MIN_LENGTH} karakter kullanın\n"
            f"• Büyük harf (A-Z), küçük harf (a-z), rakam (0-9) ve özel karakter (!@#$%...) karıştırın\n"
            f"• Yaygın şifrelerden (password123, admin, vb.) kaçının\n"
            f"• Kullanıcı adınızı şifrenizde kullanmayın\n"
            f"• Ardışık (123456) veya tekrarlanan (aaaa) karakterlerden kaçının\n"
            f"\nÖrnek güçlü şifre: K7$mP@ssW0rd!2025"
        )


# Test fonksiyonu
def test_password_policy():
    """Password policy testleri"""
    test_cases = [
        ("yagmur123", False, "Çok kısa"),
        ("YagmurYagmur123", False, "Özel karakter yok"),
        ("Yagmur@123456", False, "Yaygın şifre"),
        ("YagmurAdmin!123", True, "Geçerli"),
        ("K7$mP@ssW0rd!2025", True, "Çok güçlü"),
        ("aaaaaAAAAAAA111!", False, "Tekrarlanan karakterler"),
        ("Abcdef123456!@#", False, "Ardışık karakterler"),
    ]
    
    print("\n🧪 Password Policy Test:")
    for password, should_pass, description in test_cases:
        valid, message = PasswordPolicy.validate(password)
        score, strength = PasswordPolicy.get_strength_score(password)
        
        status = "✅" if valid == should_pass else "❌"
        print(f"{status} {description}: {password[:3]}*** - {message} (Score: {score}, {strength})")


if __name__ == "__main__":
    test_password_policy()

