"""
JWT Authentication Module
JWT token ile hastane kimlik doğrulama sistemi (HMAC-SHA256, 30 dakika expire)
"""

import os
from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# =============================================================================
# YAPILANDIRMA
# =============================================================================

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE-THIS-IN-PRODUCTION-USE-ENV-VAR")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

security = HTTPBearer()

# Yetkili hastaneler (Production'da veritabanından gelir)
AUTHORIZED_HOSPITALS = {
    "hospital_001": {"name": "Ankara Şehir Hastanesi", "api_key": "test_key_ankara_123", "active": True},
    "hospital_002": {"name": "İstanbul Tıp Fakültesi", "api_key": "test_key_istanbul_456", "active": True},
    "hospital_test": {"name": "Test Hospital", "api_key": "test_key_demo", "active": True}
}

# =============================================================================
# ANA FONKSİYONLAR
# =============================================================================

#1 (Login endpoint'inde çağrılır)
# Açıklama: Hospital ID ve API key doğrulayıp JWT token oluşturur
def create_access_token(hospital_id: str, api_key: str) -> dict:
    if hospital_id not in AUTHORIZED_HOSPITALS:
        raise HTTPException(status_code=401, detail=f"Hospital not found: {hospital_id}")
    
    hospital = AUTHORIZED_HOSPITALS[hospital_id]
    
    if not hospital["active"]:
        raise HTTPException(status_code=403, detail=f"Hospital deactivated: {hospital_id}")
    
    if hospital["api_key"] != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    now = datetime.utcnow()
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "hospital_id": hospital_id,
        "hospital_name": hospital["name"],
        "exp": expire,
        "iat": now,
        "type": "access_token"
    }
    
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "hospital_id": hospital_id,
        "hospital_name": hospital["name"]
    }


#2 (Her korumalı endpoint'te Depends ile çağrılır)
# Açıklama: JWT token'ı doğrular ve hospital bilgilerini döndürür
def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True
        })
        
        hospital_id = payload.get("hospital_id")
        if not hospital_id:
            raise HTTPException(status_code=403, detail="Invalid token payload: missing hospital_id")
        
        if hospital_id not in AUTHORIZED_HOSPITALS or not AUTHORIZED_HOSPITALS[hospital_id]["active"]:
            raise HTTPException(status_code=403, detail=f"Hospital no longer authorized: {hospital_id}")
        
        return {
            "hospital_id": hospital_id,
            "hospital_name": payload.get("hospital_name", "Unknown"),
            "token_issued_at": payload.get("iat"),
            "token_expires_at": payload.get("exp")
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi dolmuş. Yeni token isteyin.")
    except jwt.InvalidSignatureError:
        raise HTTPException(status_code=403, detail="Geçersiz token signature. Token kurcalanmış olabilir!")
    except jwt.DecodeError:
        raise HTTPException(status_code=403, detail="Geçersiz token formatı. Decode edilemiyor.")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=403, detail=f"Geçersiz token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token doğrulama hatası: {str(e)}")


#3 (verify_token wrapper'ı, sadece hospital_id döndürür)
# Açıklama: Token'dan sadece hospital_id çıkarır
def get_hospital_id(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    hospital_info = verify_token(credentials)
    return hospital_info["hospital_id"]


# =============================================================================
# ADMİN FONKSİYONLARI (Opsiyonel)
# =============================================================================

#4 (Admin tarafından yeni hastane eklemek için)
# Açıklama: Sisteme yeni hastane ekler
def add_hospital(hospital_id: str, name: str, api_key: str) -> dict:
    if hospital_id in AUTHORIZED_HOSPITALS:
        raise ValueError(f"Hospital already exists: {hospital_id}")
    
    AUTHORIZED_HOSPITALS[hospital_id] = {"name": name, "api_key": api_key, "active": True}
    return {"hospital_id": hospital_id, "name": name, "status": "added"}


#5 (Admin tarafından hastane devre dışı bırakmak için)
# Açıklama: Hastaneyi pasif hale getirir
def deactivate_hospital(hospital_id: str) -> dict:
    if hospital_id not in AUTHORIZED_HOSPITALS:
        raise ValueError(f"Hospital not found: {hospital_id}")
    
    AUTHORIZED_HOSPITALS[hospital_id]["active"] = False
    return {"hospital_id": hospital_id, "status": "deactivated"}


#6 (Admin tarafından hastane tekrar aktif etmek için)
# Açıklama: Pasif hastaneyi tekrar aktif eder
def reactivate_hospital(hospital_id: str) -> dict:
    if hospital_id not in AUTHORIZED_HOSPITALS:
        raise ValueError(f"Hospital not found: {hospital_id}")
    
    AUTHORIZED_HOSPITALS[hospital_id]["active"] = True
    return {"hospital_id": hospital_id, "status": "reactivated"}


#7 (Test için hızlı token üretme)
# Açıklama: Test amaçlı token oluşturur
def create_test_token(hospital_id: str = "hospital_test") -> str:
    if hospital_id not in AUTHORIZED_HOSPITALS:
        raise ValueError(f"Hospital not found: {hospital_id}")
    
    api_key = str(AUTHORIZED_HOSPITALS[hospital_id]["api_key"])
    token_data = create_access_token(hospital_id, api_key)
    return token_data["access_token"]

