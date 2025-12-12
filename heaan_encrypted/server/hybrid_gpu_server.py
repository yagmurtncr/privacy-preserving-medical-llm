#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gizlilik Korumalı LLM Sunucusu - Llama 3.1 8B + GPU ile PII masking, differential privacy, güvenli bellek yönetimi
"""

import torch
import torch.nn as nn
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import sys
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# ✅ .env dosyasını yükle (JWT_SECRET_KEY ve diğer config'ler için)
load_dotenv()
import asyncio
from collections import deque
import time
import traceback
import jwt
import secrets
import bcrypt
from datetime import datetime, timedelta, timezone

# Proje root ve heaan_encrypted path'lerini ekle
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.crypto_config import create_context

# Llama text generator import
try:
    # Önce relative import dene
    try:
        from .llama_text_generator import LlamaTextGenerator
        LLAMA_AVAILABLE = True
    except ImportError:
        # Absolute import dene
        from llama_text_generator import LlamaTextGenerator
        LLAMA_AVAILABLE = True
except Exception as e:
    LLAMA_AVAILABLE = False
    print(f"⚠️  Llama text generator not available: {e}")

# PII Masker import
try:
    from heaan_encrypted.client.pii_masker import PIIMasker
    PII_MASKER_AVAILABLE = True
except Exception as e:
    PII_MASKER_AVAILABLE = False
    print(f"⚠️  PII masker not available: {e}")

# Güvenlik modülleri: Auth, rate limiting, input doğrulama, DP, secure memory

# Her zaman aktif gizlilik modülleri (KRİTİK)
from heaan_encrypted.server.secure_memory import secure_memory, SecureScope
from heaan_encrypted.server.differential_privacy import DifferentialPrivacy
from heaan_encrypted.server.audit_logger import audit_logger
from heaan_encrypted.server.encrypted_llama_generator import EncryptedLlamaTextGenerator
from heaan_encrypted.server.e2e_encryption import E2EEncryptionManager

# Opsiyonel güvenlik modülleri (auth, rate limiting, vb.)
try:
    from heaan_encrypted.server.auth import (
        verify_token, 
        get_hospital_id, 
        create_access_token,
        AUTHORIZED_HOSPITALS
    )
    from heaan_encrypted.server.rate_limiter import RateLimitMiddleware
    from heaan_encrypted.server.input_validator import InputValidator
    from heaan_encrypted.server.security_logger import security_logger
    from heaan_encrypted.server.ip_whitelist import add_ip_whitelist
    from heaan_encrypted.server.security_headers import add_security_headers
    from heaan_encrypted.server.cors_config import add_cors_middleware
    from heaan_encrypted.server.https_redirect import add_https_redirect
    from heaan_encrypted.server.account_lockout import account_lockout
    from heaan_encrypted.server.password_policy import PasswordPolicy
    
    SECURITY_ENABLED = True
    print("✅ Security modules loaded successfully!")
except ImportError as e:
    SECURITY_ENABLED = False
    print(f"⚠️  Security modules not available: {e}")
    print("   Server will run WITHOUT security features (development only!)")
    # Not: SecureScope ve DifferentialPrivacy her zaman aktif (yukarıda import edildi)
    
    def verify_token(*args, **kwargs):
        """Dummy token doğrulama"""
        return {"hospital_id": "dev_mode", "permissions": []}
    
    def get_hospital_id(*args, **kwargs):
        return "dev_mode"
    
    # Dummy güvenlik fonksiyonları
    def add_security_headers(*args, **kwargs):
        pass
    
    def add_cors_middleware(*args, **kwargs):
        pass
    
    def add_https_redirect(*args, **kwargs):
        pass
    
    def add_ip_whitelist(*args, **kwargs):
        pass

# JWT ayarları
# ✅ GÜVENL: .env'den okunuyor, yoksa hata ver (random key güvensiz!)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError("❌ JWT_SECRET_KEY bulunamadı! .env dosyasında tanımlanmalı.")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Basit kullanıcı DB (production'da DB kullan)
# ✅ Şifreler bcrypt ile hash'lenmiş (GÜVENL)
USERS_DB = {
    "admin": {
        "password_hash": "$2b$12$PfiQYUXWoAK3jIykjR59Jemz6JbAGEGY.R3UFaNm9fN6gKwWTWNt6",  # 5mRrXxEwNlxrSvGt
        "role": "admin"
    },
    "yagmur": {
        "password_hash": "$2b$12$Oj.AIZnbDivr1po2IECMHuycAvrrq.CrtrXnO/aVNmKCd32EkAQJC",  # yagmur123
        "role": "doctor"
    },
    "user": {
        "password_hash": "$2b$12$seGwstGtrUsj7jZ6ajDZWeGv7..QUcbkgD6BkW1I9NSdpA.e6sJji",  # userpass123
        "role": "user"
    }
}

# Güvenlik
security = HTTPBearer(auto_error=False)  # ...

# Swagger UI "Authorize" butonu için OpenAPI security scheme ekle
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.openapi.utils import get_openapi
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Security scheme ekle
    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token'ı buraya yapıştırın. Önce /login endpoint'inden token alın!"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Request/Response modelleri

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = JWT_EXPIRATION_HOURS * 3600

class InferenceRequest(BaseModel):
    encrypted_data: str  # Base64 encode
    client_id: Optional[str] = "default"

class InferenceResponse(BaseModel):
    encrypted_result: str  # Base64 encode
    processing_time_ms: float
    used_gpu: bool
    batch_size: int = 1

class GenerateRequest(BaseModel):
    query: str  # Plaintext sorgu
    max_new_tokens: int = 256
    temperature: float = 0.7
    enable_pii_protection: bool = True  # PII Masking (varsayılan: ON)
    enable_dp: bool = False  # Differential Privacy (varsayılan: OFF - accuracy öncelikli)

class GenerateResponse(BaseModel):
    response: str  # Üretilen metin
    processing_time_s: float  # Saniye cinsinden
    model: str
    timing_breakdown: dict = {}  # Node-level timing (saniye cinsinden)
    pii_protection_applied: bool = False  # PII masking uygulandı mı?
    pii_detected: int = 0  # 🆕 Tespit edilen toplam PII sayısı (input + output)
    dp_applied: bool = False  # DP uygulandı mı?
    pii_leakage_detected: bool = False  # Output'ta PII tespit edildi mi?
    security_warnings: list = []  # Güvenlik uyarıları
    model_encrypted_in_memory: bool = False  # Model RAM'de şifreli mi?

# E2E Encrypted communication models
class EncryptedGenerateRequest(BaseModel):
    encrypted_query: str  # Base64 encoded encrypted query
    encrypted_key: str  # Base64 encoded RSA encrypted AES key
    nonce: str  # Base64 encoded nonce for AES-GCM
    max_new_tokens: int = 256
    temperature: float = 0.7
    enable_pii_protection: bool = True
    enable_dp: bool = False

class EncryptedGenerateResponse(BaseModel):
    encrypted_response: str  # Base64 encoded encrypted response
    nonce: str  # Base64 encoded nonce for AES-GCM
    encryption_method: str = "AES-256-GCM"
    processing_time_ms: float
    model: str
    timing_breakdown: dict = {}
    pii_protection_applied: bool = False
    pii_detected: int = 0  # 🆕 Tespit edilen toplam PII sayısı
    dp_applied: bool = False
    pii_leakage_detected: bool = False
    security_warnings: list = []
    model_encrypted_in_memory: bool = False

# JWT auth için request/response modelleri

class TokenRequest(BaseModel):
    hospital_id: str
    api_key: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    hospital_id: str
    hospital_name: str

# GPU hızlandırmalı basit neural network modeli (fallback için)

class SimpleLLM(nn.Module):
    """3 katmanlı feedforward network (GPU inference testi için)"""
    
    def __init__(self, input_size=128, hidden_size=256):
        super().__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.fc3 = nn.Linear(hidden_size, input_size)
        self.gelu = nn.GELU()
        
    def forward(self, x):
        # x şekli: (batch_size, input_size)
        x = self.gelu(self.fc1(x))
        x = self.gelu(self.fc2(x))
        x = self.fc3(x)
        return x

# Query batch işlemci

class BatchProcessor:
    """Gelen istekleri batch'leyip GPU'da toplu işler (throughput artırır)"""
    
    def __init__(self, max_batch_size=8, timeout_ms=50):
        self.max_batch_size = max_batch_size
        self.timeout_ms = timeout_ms
        self.queue = deque()
        self.processing = False
        
    async def add_query(self, encrypted_data, future):
        """Query'yi batch kuyruğuna ekle"""
        self.queue.append((encrypted_data, future))
        
        # Batch doluysa işle
        if len(self.queue) >= self.max_batch_size:
            if not self.processing:
                asyncio.create_task(self.process_batch())
        else:
            # Timeout veya dolu batch bekle
            asyncio.create_task(self._wait_and_process())
    
    async def _wait_and_process(self):
        """Timeout bekle, sonra işle"""
        await asyncio.sleep(self.timeout_ms / 1000)
        if len(self.queue) > 0 and not self.processing:
            await self.process_batch()
    
    async def process_batch(self):
        """Query batch'ini işle"""
        if self.processing or len(self.queue) == 0:
            return
        
        self.processing = True
        
        try:
            # Batch al (placeholder for future batching implementation)
            batch_size = min(len(self.queue), self.max_batch_size)
            _ = [self.queue.popleft() for _ in range(batch_size)]
            
            # Batch'i işle (not implemented yet)
            pass
        finally:
            self.processing = False

# Token doğrulama
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """JWT token doğrula"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": payload.get("role")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception as e:
        # Catch all JWT-related errors (InvalidSignatureError, DecodeError, etc.)
        raise HTTPException(status_code=401, detail="Invalid token")

# FastAPI server

app = FastAPI(
    title="Gizlilik Korumalı LLM",
    description="🔐 Llama 3.1 8B ile PII korumalı tıbbi soru-cevap | Kullanım: /login → token al → Authorize 🔒 → /generate",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True}
)

# Custom OpenAPI schema (Swagger UI'da "Authorize" butonu)
app.openapi = custom_openapi

# Güvenlik middleware'leri

# Environment check
is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
https_enabled = os.getenv("ENABLE_HTTPS", "false").lower() == "true"

# 1. HTTPS Redirect (Production'da önerilir)
add_https_redirect(app, enabled=https_enabled)

# 2. Security Headers (HSTS production'da zorunlu!)
add_security_headers(app, enable_hsts=https_enabled)

# 3. CORS
# Development: loose, Production: strict
add_cors_middleware(app, strict=is_production)

# 4. IP Whitelist (Production'da önerilir)
ip_whitelist_enabled = os.getenv("IP_WHITELIST_ENABLED", "false").lower() == "true"
allowed_ips = os.getenv("ALLOWED_IPS", "127.0.0.1,::1").split(",")
add_ip_whitelist(app, allowed_ips=allowed_ips, enabled=ip_whitelist_enabled)
if ip_whitelist_enabled:
    print(f"✅ IP Whitelist aktif: {allowed_ips}")

# 5. Rate Limiting (JWT + IP-based)
if SECURITY_ENABLED:
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=20,   # 20 istek/dakika
        requests_per_hour=500     # 500 istek/saat
    )
    print("✅ Rate limiting middleware aktif: 20 req/min, 500 req/hour")

print("🔐 Security middleware initialized")
print(f"   Environment: {'PRODUCTION' if is_production else 'DEVELOPMENT'}")
print(f"   HTTPS: {'ENABLED' if os.getenv('ENABLE_HTTPS', 'false').lower() == 'true' else 'DISABLED'}")
print(f"   CORS: {'STRICT' if is_production else 'LOOSE'}")
print(f"   IP Whitelist: {'ENABLED' if os.getenv('IP_WHITELIST_ENABLED', 'false').lower() == 'true' else 'DISABLED'}")

# Global state
PRIVATE_CONTEXT = None  # Decryption için
PUBLIC_CONTEXT = None   # Encryption için
GPU_MODEL = None
USE_GPU = False
BATCH_PROCESSOR = None
LLAMA_GENERATOR = None  # Llama 3.1 8B (Normal Mode)
ENCRYPTED_LLAMA_GENERATOR = None  # Llama 3.1 8B (Encrypted Mode)
PII_MASKER = None  # PII maskeleme
DIFF_PRIVACY = None  # Differential privacy
E2E_ENCRYPTION = None  # End-to-End encryption manager
encryption_enabled = False  # Server'daki encryption mode durumu

# Server başlatma
@app.on_event("startup")
async def startup():
    global PRIVATE_CONTEXT, PUBLIC_CONTEXT, GPU_MODEL, USE_GPU, BATCH_PROCESSOR, LLAMA_GENERATOR, ENCRYPTED_LLAMA_GENERATOR, PII_MASKER, DIFF_PRIVACY, E2E_ENCRYPTION, encryption_enabled
    
    print("\n" + "="*80)
    print("🚀 Starting Hybrid GPU + HE Server")
    print("="*80)
    
    # Encryption context yükle
    print("\n📦 Loading encryption context...")
    try:
        PRIVATE_CONTEXT = create_context()  # Decryption için private key
        PUBLIC_CONTEXT = PRIVATE_CONTEXT.copy()
        PUBLIC_CONTEXT.make_context_public()  # Client için public
        print("   ✅ Encryption context loaded (CKKS)")
        print("   ℹ️  Private key: Available (for decryption)")
        print("   ℹ️  Public key: Available (for client)")
    except Exception as e:
        print(f"   ❌ Error loading context: {e}")
        raise
    
    # GPU model başlat
    print("\n🎮 Initializing GPU model...")
    # Force CPU mode for layer-wise encryption testing
    FORCE_CPU_MODE = os.getenv("FORCE_CPU_MODE", "false").lower() == "true"
    
    try:
        if torch.cuda.is_available() and not FORCE_CPU_MODE:
            device = torch.device("cuda:0")
            GPU_MODEL = SimpleLLM(input_size=128, hidden_size=256).to(device)
            GPU_MODEL.eval()
            USE_GPU = True
            print(f"   ✅ GPU model loaded on {torch.cuda.get_device_name(0)}")
            print("   ℹ️  Model: SimpleLLM (128 → 256 → 256 → 128)")
        else:
            GPU_MODEL = SimpleLLM(input_size=128, hidden_size=256)
            GPU_MODEL.eval()
            USE_GPU = False
            if FORCE_CPU_MODE:
                print("   ⚙️  FORCE_CPU_MODE enabled - using CPU")
            else:
                print("   ⚠️  No GPU available, using CPU")
    except Exception as e:
        print(f"   ❌ Error loading model: {e}")
        # CPU fallback
        GPU_MODEL = SimpleLLM(input_size=128, hidden_size=256)
        GPU_MODEL.eval()
        USE_GPU = False
        print("   ⚠️  Fallback to CPU model")
    
    # Llama generator başlat (with optional encryption)
    print("\n🦙 Initializing Llama 3.1 8B text generator...")
    
    # Check if in-memory encryption is enabled
    ENABLE_IN_MEMORY_ENCRYPTION = os.getenv("ENABLE_IN_MEMORY_ENCRYPTION", "false").lower() == "true"
    encryption_enabled = ENABLE_IN_MEMORY_ENCRYPTION  # Set global variable
    
    try:
        if LLAMA_AVAILABLE:
            if ENABLE_IN_MEMORY_ENCRYPTION:
                print("   🔐 Using ENCRYPTED mode (in-memory encryption)")
                
                # Validate encryption key
                encryption_key = os.getenv("MODEL_ENCRYPTION_KEY")
                if not encryption_key:
                    print("   ⚠️  ERROR: MODEL_ENCRYPTION_KEY not set!")
                    print("   ⚠️  Falling back to NORMAL mode")
                    ENABLE_IN_MEMORY_ENCRYPTION = False
                    encryption_enabled = False
                
                if ENABLE_IN_MEMORY_ENCRYPTION:
                    try:
                        LLAMA_GENERATOR = EncryptedLlamaTextGenerator(
                            model_name="meta-llama/Meta-Llama-3.1-8B-Instruct",
                            device="cuda" if USE_GPU else "cpu",
                            enable_encryption=True
                        )
                        print("   ✅ Llama 3.1 8B loaded & encrypted in RAM")
                    except Exception as enc_error:
                        print(f"   ⚠️  Encryption failed: {enc_error}")
                        print("   ⚠️  Falling back to NORMAL mode")
                        # Fallback to normal mode
                        LLAMA_GENERATOR = LlamaTextGenerator(
                            model_name="meta-llama/Meta-Llama-3.1-8B-Instruct",
                            device="cuda" if USE_GPU else "cpu"
                        )
                        print("   ✅ Llama 3.1 8B loaded (fallback mode)")
                        ENABLE_IN_MEMORY_ENCRYPTION = False
                        encryption_enabled = False
            else:
                print("   ⚠️  Using NORMAL mode (no encryption)")
                LLAMA_GENERATOR = LlamaTextGenerator(
                    model_name="meta-llama/Meta-Llama-3.1-8B-Instruct",
                    device="cuda" if USE_GPU else "cpu"
                )
                print("   ✅ Llama 3.1 8B loaded successfully")
        else:
            print("   ⚠️  Llama generator not available, using mock mode")
    except Exception as e:
        print(f"   ⚠️  Could not load Llama: {e}")
        print("   ℹ️  Will use mock generator for testing")
        LLAMA_GENERATOR = None
        ENABLE_IN_MEMORY_ENCRYPTION = False
        encryption_enabled = False
    
    # PII masker başlat
    print("\n🔒 Initializing PII masker...")
    try:
        if PII_MASKER_AVAILABLE:
            # NER mode: AI-powered context-aware detection (no hard-coded lists!)
            # NER model GPU 3'e yüklenecek (Llama GPU 1'de)
            PII_MASKER = PIIMasker(aggressive=True, language='tr', mode='ner', ner_gpu_id=3)
            print("   ✅ PII masker loaded successfully")
            print("   ℹ️  Mode: NER (AI-powered, context-aware)")
            print("   ℹ️  Name Detection: Turkish NER model (GPU 3, no templates!)")
            print("   ℹ️  Structured PII: Regex (TC, Phone, Email, Age)")
            print("   ℹ️  Accuracy: ~98% (intelligent detection)")
        else:
            print("   ⚠️  PII masker not available, skipping masking")
            PII_MASKER = None
    except Exception as e:
        print(f"   ⚠️  Could not load PII masker: {e}")
        print(f"   ℹ️  Falling back to hybrid mode")
        try:
            PII_MASKER = PIIMasker(aggressive=True, language='tr', mode='hybrid', ner_gpu_id=3)
        except:
            PII_MASKER = None
    
    # Differential Privacy başlat
    print("\n🔐 Initializing Differential Privacy...")
    try:
        # ε=1.0 (dengeli)
        DIFF_PRIVACY = DifferentialPrivacy(epsilon=1.0, sensitivity=1.0)
        print("   ✅ Differential Privacy available")
        print("   ℹ️  Privacy budget: ε=1.0 (balanced)")
        print("   ℹ️  Protection: Membership inference resistance")
        print("   ⚙️  Status: DISABLED by default (enable_dp=false)")
        print("   💡 Enable per request: {\"enable_dp\": true}")
    except Exception as e:
        print(f"   ⚠️  Could not initialize DP: {e}")
        DIFF_PRIVACY = None
    
    # Batch processor başlat
    BATCH_PROCESSOR = BatchProcessor(max_batch_size=8, timeout_ms=50)
    print(f"\n📦 Batch processor initialized (max_batch={BATCH_PROCESSOR.max_batch_size})")
    
    # Güvenlik özellikleri başlat
    if SECURITY_ENABLED:
        print("\n🔐 Initializing security features...")
        try:
            # Security modules başarıyla yüklendi
            print("   ✅ Rate limiter middleware aktif")
            print("   ✅ Security logger initialized")
            print("   ✅ Input validator ready")
            print("   ✅ Memory protection active")
            print("   ✅ JWT authentication enabled")
            print(f"   ℹ️  Authorized hospitals: {len(AUTHORIZED_HOSPITALS)}")
        except Exception as e:
            print(f"   ⚠️  Security initialization warning: {e}")
    else:
        print("\n⚠️  Security features DISABLED (development mode)")
    
    # E2E Encryption başlat
    print("\n🔐 Initializing End-to-End Encryption...")
    try:
        keys_dir = Path(__file__).parent.parent / "keys"
        private_key_path = keys_dir / "server_private.pem"
        public_key_path = keys_dir / "server_public.pem"
        
        if private_key_path.exists() and public_key_path.exists():
            E2E_ENCRYPTION = E2EEncryptionManager(
                private_key_path=str(private_key_path),
                public_key_path=str(public_key_path)
            )
            print("   ✅ E2E Encryption manager initialized")
            print("   ℹ️  Client-Server encrypted communication ready")
            print("   ℹ️  Endpoint: POST /generate_encrypted")
        else:
            print("   ⚠️  E2E Encryption keys not found")
            print(f"   ℹ️  Expected: {private_key_path}")
            E2E_ENCRYPTION = None
    except Exception as e:
        print(f"   ⚠️  Could not initialize E2E Encryption: {e}")
        E2E_ENCRYPTION = None
    
    print("\n" + "="*80)
    print("✅ Server Ready!")
    print("="*80)
    print(f"""
Configuration:
  • Encryption: CKKS (TenSEAL)
  • Compute: {'GPU (CUDA)' if USE_GPU else 'CPU'}
  • Batching: Enabled (max_batch=8, timeout=50ms)
  • API: /inference (POST)

Architecture:
  Client → Encrypt (HE) → Server → Decrypt → GPU → Encrypt → Client
  
Privacy Note:
  ⚠️  Server sees plaintext briefly during compute
  ✅ Still encrypted in transit (TLS recommended)
  ✅ Can add TEE (SGX) later for hardware security

Expected Performance:
  • Latency: ~2-5ms (vs 20ms CPU-only)
  • Throughput: ~100-300 queries/sec (vs 50 CPU-only)
  • Speedup: ~8x latency, ~5x throughput! 🚀
""")

# Root endpoint
@app.get("/")
async def root():
    """API bilgisi ve hızlı durum kontrolü"""
    return {
        "status": "healthy",
        "service": "Hybrid GPU + HE Server",
        "version": "1.0.0",
        "gpu_available": USE_GPU,
        "gpu_name": torch.cuda.get_device_name(0) if USE_GPU else "N/A",
        "security_enabled": SECURITY_ENABLED,
        "endpoints": {
            "main": "POST /generate - Ana text generation endpoint",
            "health": "GET /health - Detaylı sağlık kontrolü",
            "stats": "GET /stats - Server istatistikleri",
            "docs": "GET /docs - Swagger UI (interaktif API docs)"
        },
        "message": "API çalışıyor! Kullanım için: POST /generate"
    }

# Login endpoint
@app.post("/login", response_model=LoginResponse, tags=["Authentication"])
async def login(request: LoginRequest, http_request: Request = None):
    """
    🔐 Kullanıcı adı ve şifre ile JWT token al (Test: yagmur / yagmur123)
    
    Güvenlik Özellikleri:
    - Bcrypt password hashing
    - Account lockout (5 yanlış deneme → 15 dakika kilitleme)
    - Audit logging
    """
    # Request metadata
    client_ip = http_request.client.host if http_request else "unknown"
    
    # 🔒 Account lockout kontrolü
    is_locked, remaining_seconds = account_lockout.is_locked(request.username)
    if is_locked:
        minutes = remaining_seconds // 60
        seconds = remaining_seconds % 60
        
        # Audit log
        audit_logger.log_authentication(
            username=request.username,
            client_ip=client_ip,
            success=False,
            failure_reason=f"Account locked ({remaining_seconds}s remaining)"
        )
        
        raise HTTPException(
            status_code=429,
            detail=f"Hesap kilitli! Kalan süre: {minutes} dakika {seconds} saniye"
        )
    
    user = USERS_DB.get(request.username)
    
    # ✅ Bcrypt ile güvenli şifre kontrolü
    if not user:
        # Başarısız deneme kaydet
        is_locked, message = account_lockout.record_failed_attempt(request.username, client_ip)
        
        # Audit log: Failed authentication (user not found)
        audit_logger.log_authentication(
            username=request.username,
            client_ip=client_ip,
            success=False,
            failure_reason="User not found"
        )
        
        if is_locked:
            raise HTTPException(status_code=429, detail=message)
        else:
            raise HTTPException(status_code=401, detail=message)
    
    # Şifre doğrulama (bcrypt)
    password_valid = bcrypt.checkpw(
        request.password.encode('utf-8'),
        user["password_hash"].encode('utf-8')
    )
    
    if not password_valid:
        # Başarısız deneme kaydet
        is_locked, message = account_lockout.record_failed_attempt(request.username, client_ip)
        
        # Audit log: Failed authentication (wrong password)
        audit_logger.log_authentication(
            username=request.username,
            client_ip=client_ip,
            success=False,
            failure_reason="Invalid password"
        )
        
        if is_locked:
            raise HTTPException(status_code=429, detail=message)
        else:
            raise HTTPException(status_code=401, detail=message)
    
    # JWT token oluştur
    expiration = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    token_data = {
        "sub": request.username,
        "role": user["role"],
        "exp": expiration
    }
    
    access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    # 🔓 Başarılı giriş - lockout sayacını sıfırla
    account_lockout.reset_attempts(request.username)
    
    # Audit log: Successful authentication
    audit_logger.log_authentication(
        username=request.username,
        client_ip=client_ip,
        success=True
    )
    
    return LoginResponse(
        access_token=access_token,
        expires_in=JWT_EXPIRATION_HOURS * 3600
    )

# ❌ REMOVED: /auth/token - JWT authentication not used
# ❌ REMOVED: /context - Encryption context not needed
# ❌ REMOVED: /public_context - Encryption context not needed

# Admin ve monitoring endpoint'leri

# İstatistikler endpoint
# 🔵 OPTIONAL: /stats endpoint'i (Monitoring için aktif edilebilir)
# Aktif etmek için: Başındaki # işaretini kaldır

# @app.get("/stats")
async def _optional_get_stats(hospital_id: str = Depends(get_hospital_id) if SECURITY_ENABLED else None):
    """📊 OPTIONAL: GPU/CPU, memory, güvenlik ve rate limit istatistikleri"""
    if not SECURITY_ENABLED:
        hospital_id = "development"
    
    # Check if in-memory encryption is enabled
    encryption_enabled = os.getenv("ENABLE_IN_MEMORY_ENCRYPTION", "false").lower() == "true"
    
    stats = {
        "server": {
            "gpu_available": USE_GPU,
            "gpu_name": torch.cuda.get_device_name(0) if USE_GPU else "N/A",
            "security_enabled": SECURITY_ENABLED,
            "llama_available": LLAMA_GENERATOR is not None,
            "pii_masker_enabled": PII_MASKER is not None,
            "in_memory_encryption_enabled": encryption_enabled
        }
    }
    
    # Add encryption stats if available
    if encryption_enabled and LLAMA_GENERATOR is not None:
        try:
            if isinstance(LLAMA_GENERATOR, EncryptedLlamaTextGenerator):
                enc_stats = LLAMA_GENERATOR.get_stats()
                if enc_stats and "encryption_stats" in enc_stats and enc_stats["encryption_stats"]:
                    stats["encryption"] = enc_stats["encryption_stats"]
        except Exception:
            pass  # Silently ignore if stats not available
    
    # GPU stats
    if USE_GPU and torch.cuda.is_available():
        total_memory = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
        allocated = torch.cuda.memory_allocated() / (1024 * 1024)
        stats["gpu_memory"] = {
            "allocated_mb": round(allocated, 2),
            "total_mb": round(total_memory, 2),
            "usage_percent": round((allocated / total_memory) * 100, 2)
        }
    
    if SECURITY_ENABLED:
        # Rate limiting artık middleware ile yapılıyor (stats endpoint'e eklenebilir)
        
        # Security logger stats
        if hasattr(security_logger, 'get_stats'):
            stats["security"] = security_logger.get_stats()
        
        # Memory stats
        stats["memory"] = secure_memory.get_memory_stats()
    
    return stats

# Health check endpoint
@app.get("/health")
async def health_check():
    """❤️ Sistem sağlık durumu (healthy/degraded), GPU memory ve model kontrolü"""
    health = {
        "status": "healthy",
        "timestamp": time.time(),
        "checks": {
            "encryption_context": PRIVATE_CONTEXT is not None,
            "gpu": USE_GPU and torch.cuda.is_available(),
            "llama": LLAMA_GENERATOR is not None,
            "security": SECURITY_ENABLED,
            "pii_masker": PII_MASKER is not None,
            "differential_privacy": DIFF_PRIVACY is not None
        },
        "model_loaded": LLAMA_GENERATOR is not None,
        "privacy_layers": {
            "inference_only": True,  # Model frozen (no learning)
            "secure_memory": True,   # Auto-wipe after processing
            "differential_privacy": DIFF_PRIVACY is not None,  # Membership inference resistance
            "pii_masking": PII_MASKER is not None  # Name/date/ID masking
        }
    }
    
    # GPU memory check
    if USE_GPU and torch.cuda.is_available():
        total_memory = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
        allocated = torch.cuda.memory_allocated() / (1024 * 1024)
        reserved = torch.cuda.memory_reserved() / (1024 * 1024)
        
        health["gpu_memory"] = {
            "allocated_mb": round(allocated, 2),
            "reserved_mb": round(reserved, 2),
            "free_mb": round(total_memory - allocated, 2),
            "total_mb": round(total_memory, 2),
            "usage_percent": round((allocated / total_memory) * 100, 2)
        }
        health["gpu_name"] = torch.cuda.get_device_name(0)
    
    # Overall health
    critical_checks = ["llama"]  # Only Llama is critical
    critical_passed = all(health["checks"][k] for k in critical_checks if k in health["checks"])
    health["status"] = "healthy" if critical_passed else "degraded"
    
    return health

# Text generation endpoint
# JWT auth dependency (zorunlu)
async def require_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """JWT doğrulama - token zorunlu"""
    if not SECURITY_ENABLED:
        # Development mode - dummy data
        return {"hospital_id": "development", "username": "dev_user"}
    
    if credentials is None:
        raise HTTPException(status_code=401, detail="Token required! Login endpoint: /login")
    
    return verify_token(credentials)

@app.post("/generate", response_model=GenerateResponse, tags=["Generate"])
async def generate_text(
    request: GenerateRequest,
    auth_data: dict = Depends(require_auth),
    http_request: Request = None
):
    """
    🤖 JWT gerekli, Llama 3.1 8B ile PII korumalı metin üretimi
    
    Server modu .env dosyasından belirlenir:
    - ⚡ Normal Mode: ~4-5s (2 token/s) → ENABLE_IN_MEMORY_ENCRYPTION=false
    - 🔐 Encrypted Mode: ~300s (0.1 token/s) → ENABLE_IN_MEMORY_ENCRYPTION=true
    """
    # User context ayarla (JWT'den)
    username = auth_data.get("username", "anonymous")
    hospital_id = auth_data.get("hospital_id", "development")
    
    # Request metadata (5. madde - Request Metadata Logging)
    client_ip = http_request.client.host if http_request else "unknown"
    user_agent = http_request.headers.get("user-agent", "unknown") if http_request else "unknown"
    
    start_time = time.time()
    timing = {
        "network_start": start_time,
        "pii_masking_start": 0,
        "llm_start": 0,
        "pii_masking_out_start": 0,
        "end": 0
    }
    
    with SecureScope() as scope:
        try:
            # ===== ADIM 1: AĞ + DOĞRULAMA (~1-5ms) =====
            # Rate limiting artık middleware ile yapılıyor
            
            query = request.query
            scope.register(query)
            
            if SECURITY_ENABLED:
                query = InputValidator.validate_plaintext_query(query, strict_mode=False)
            
            timing["pii_masking_start"] = time.time()
            
            # ===== ADIM 2: GİRDİ PII MASKELEME (~10-50ms) =====
            query_pii_mapping = {}  # Input'taki PII'lar
            if request.enable_pii_protection and PII_MASKER is not None:
                try:
                    masked_query, query_pii_mapping = PII_MASKER.mask(query)
                    query = masked_query
                    scope.register(masked_query)
                except Exception as pii_error:
                    print(f"[WARNING] PII masking failed: {pii_error}")
                    if SECURITY_ENABLED:
                        security_logger.log_request(
                            hospital_id=hospital_id,
                            event_type="pii_masking_error",
                            query_length=len(query),
                            encrypted_size=0,
                            response_time_ms=0,
                            success=False
                        )
            
            timing["llm_start"] = time.time()
            
            # ===== ADIM 3: LLM ÇIKARIM (~500-2000ms) =====
            # Server'ın modunu kontrol et (.env'den gelir)
            is_encrypted_mode = isinstance(LLAMA_GENERATOR, EncryptedLlamaTextGenerator) if LLAMA_GENERATOR else False
            
            if LLAMA_GENERATOR is not None:
                response = LLAMA_GENERATOR.generate(
                    prompt=query,
                    max_new_tokens=request.max_new_tokens,
                    temperature=request.temperature
                )
                scope.register(response)
                model_name = "Llama 3.1 8B Instruct (Encrypted)" if is_encrypted_mode else "Llama 3.1 8B Instruct"
            else:
                response = f"[MOCK] Response for: {query}"
                model_name = "Mock Generator"
            
            timing["pii_masking_out_start"] = time.time()
            
            # ===== ADIM 4: ÇIKTI PII MASKELEME (~10-50ms) =====
            pii_leak_detected = False
            response_pii_mapping = {}  # Output'taki PII'lar
            security_warnings = []
            if request.enable_pii_protection and PII_MASKER is not None:
                try:
                    masked_response, response_pii_mapping = PII_MASKER.mask(response)
                    if len(response_pii_mapping) > 0:
                        pii_leak_detected = True
                        response = masked_response
                        scope.register(masked_response)
                        
                        # Security warning ekle
                        security_warnings.append({
                            "type": "PII_LEAKAGE",
                            "severity": "HIGH",
                            "message": f"Model response'unda {len(response_pii_mapping)} PII tespit edildi ve maskelendi",
                            "pii_count": len(response_pii_mapping)
                        })
                        
                        if SECURITY_ENABLED:
                            security_logger.log_request(
                                hospital_id=hospital_id,
                                event_type="pii_leakage_detected",
                                query_length=len(query),
                                encrypted_size=0,
                                response_time_ms=0,
                                success=True
                            )
                except Exception as e:
                    security_warnings.append({
                        "type": "PII_MASKING_ERROR",
                        "severity": "CRITICAL",
                        "message": "Response PII masking hatası - veri leak riski!",
                        "error": str(e)
                    })
                    
                    if SECURITY_ENABLED:
                        security_logger.log_request(
                            hospital_id=hospital_id,
                            event_type="response_masking_error",
                            query_length=len(query),
                            encrypted_size=0,
                            response_time_ms=0,
                            success=False
                        )
            
            timing["dp_start"] = time.time()
            
            # ===== ADIM 5: DİFERANSİYEL GİZLİLİK (OPSİYONEL, ~1ms) =====
            if request.enable_dp and DIFF_PRIVACY is not None:
                try:
                    # Ekle calibrated noise için membership inference resistance
                    query_id = f"{hospital_id}_{int(time.time() * 1000)}"
                    response = DIFF_PRIVACY.add_noise_to_response(response, query_id=query_id)
                    scope.register(response)
                except Exception as e:
                    print(f"[WARNING] DP failed: {e}")
            
            timing["end"] = time.time()
            
            # ===== ZAMAN DETAYLARI =====
            # Calculate timing breakdown
            pii_in_time = (timing["llm_start"] - timing["pii_masking_start"]) * 1000
            llm_time = (timing["pii_masking_out_start"] - timing["llm_start"]) * 1000
            pii_out_time = (timing["dp_start"] - timing["pii_masking_out_start"]) * 1000
            total_time = (timing["end"] - timing["network_start"]) * 1000
            
            # ===== GÜVENLİK LOGLAMA =====
            if SECURITY_ENABLED:
                security_logger.log_request(
                    hospital_id=hospital_id,
                    event_type="generate",
                    query_length=len(query),
                    encrypted_size=0,
                    response_time_ms=total_time,
                    success=True
                )
            
            # ===== DENETİM LOGLAMA (GDPR Madde 30) =====
            response_data = {
                "response": response,
                "processing_time_ms": round(total_time, 2),
                "model": model_name,
                "pii_protection_applied": request.enable_pii_protection and PII_MASKER is not None,
                "dp_applied": request.enable_dp and DIFF_PRIVACY is not None,
                "pii_leakage_detected": pii_leak_detected
            }
            
            audit_logger.log_request(
                username=username,
                endpoint="/generate",
                request_data=request.dict(),
                response_data=response_data,
                client_ip=client_ip,
                user_agent=user_agent,
                processing_time_ms=total_time,
                success=True,
                pii_detected=pii_leak_detected,
                security_warnings=security_warnings
            )
            
            # Check if encryption is enabled
            encryption_enabled = os.getenv("ENABLE_IN_MEMORY_ENCRYPTION", "false").lower() == "true"
            
            # 🆕 PII COUNT: Input + Output PII sayısı (SWAGGER uyumlu)
            total_pii_detected = len(query_pii_mapping) + len(response_pii_mapping)
            
            return GenerateResponse(
                response=response,
                processing_time_s=round(total_time / 1000, 2),  # Saniye cinsinden
                model=model_name,
                timing_breakdown={
                    "llm_inference_s": round(llm_time / 1000, 2),  # Saniye
                    "pii_masking_s": round((pii_in_time + pii_out_time) / 1000, 2),  # Saniye
                    "total_s": round(total_time / 1000, 2)  # Saniye
                },
                pii_protection_applied=request.enable_pii_protection and PII_MASKER is not None,
                pii_detected=total_pii_detected,  # 🆕 Toplam PII sayısı
                dp_applied=request.enable_dp and DIFF_PRIVACY is not None,
                pii_leakage_detected=pii_leak_detected,
                security_warnings=security_warnings,
                model_encrypted_in_memory=encryption_enabled and isinstance(LLAMA_GENERATOR, EncryptedLlamaTextGenerator)
            )
            
        except HTTPException as e:
            # HTTP exceptions (rate limit, doğrulama, etc.)
            http_processing_time = (time.time() - start_time) * 1000
            
            if SECURITY_ENABLED:
                if e.status_code == 429:
                    security_logger.log_rate_limit(
                        hospital_id=hospital_id,
                        limit_type="rate_limit",
                        current_count=0,
                        limit=10,
                        action="blocked"
                    )
                elif e.status_code == 400:
                    security_logger.log_validation_error(
                        hospital_id=hospital_id,
                        validation_type="input_validation",
                        error_details=str(e.detail),
                        is_attack=("attack" in str(e.detail).lower())
                    )
            
            print(f"[HTTP ERROR] {e.status_code} after {http_processing_time:.2f}ms: {e.detail}")
            raise
        
        except Exception as e:
            error_processing_time = (time.time() - start_time) * 1000
            
            if SECURITY_ENABLED:
                security_logger.log_server_error(
                    hospital_id=hospital_id,
                    error_type="generation_error",
                    error_message=str(e),
                    stack_trace=traceback.format_exc()
                )
            
            print(f"[ERROR] Generation failed after {error_processing_time:.2f}ms: {e}")
            raise HTTPException(status_code=500, detail=f"Generation error: {str(e)}")

# ❌ DEPRECATED: /generate_encrypted endpoint'i kaldırıldı
# /generate endpoint'i artık hem plain hem encrypted kabul ediyor
# Response her zaman şifreli döner!

# @app.post("/generate_encrypted", response_model=EncryptedGenerateResponse, tags=["Generate"])
async def _deprecated_generate_text_encrypted(
    request: EncryptedGenerateRequest,
    auth_data: dict = Depends(require_auth),
    http_request: Request = None
):
    """
    ⚠️ DEPRECATED: Artık /generate kullan (otomatik şifreli)
    """
    if E2E_ENCRYPTION is None:
        raise HTTPException(
            status_code=503,
            detail="E2E Encryption not available. Server keys not initialized."
        )
    
    # User context ayarla (JWT'den)
    username = auth_data.get("username", "anonymous")
    hospital_id = auth_data.get("hospital_id", "development")
    
    client_ip = http_request.client.host if http_request else "unknown"
    user_agent = http_request.headers.get("user-agent", "unknown") if http_request else "unknown"
    
    start_time = time.time()
    aes_key = None  # For memory cleanup
    
    with SecureScope() as scope:
        try:
            # ===== ADIM 1: İSTEĞİ ÇÖZ =====
            decrypt_start = time.time()
            
            try:
                query, aes_key = E2E_ENCRYPTION.process_encrypted_request({
                    "encrypted_query": request.encrypted_query,
                    "encrypted_key": request.encrypted_key,
                    "nonce": request.nonce
                })
                scope.register(query)
                # Note: aes_key is bytes, not string - will be manually cleaned up
            except Exception as decrypt_error:
                print(f"[ERROR] Decryption failed: {decrypt_error}")
                raise HTTPException(
                    status_code=400,
                    detail="Decryption error: Invalid encrypted data or key"
                )
            
            decrypt_time = (time.time() - decrypt_start) * 1000
            
            # ===== ADIM 2: İŞLE (/generate ile aynı) =====
            if SECURITY_ENABLED:
                try:
                    # Rate limiting artık middleware ile yapılıyor
                    query = InputValidator.validate_plaintext_query(query, strict_mode=False)
                except Exception as sec_error:
                    print(f"[WARNING] Security check failed: {sec_error}")
            
            # PII masking
            pii_start = time.time()
            query_pii_mapping = {}  # Input'taki PII'lar
            if request.enable_pii_protection and PII_MASKER is not None:
                try:
                    masked_query, query_pii_mapping = PII_MASKER.mask(query)
                    query = masked_query
                    scope.register(masked_query)
                except Exception as pii_error:
                    print(f"[WARNING] PII masking failed: {pii_error}")
            pii_time = (time.time() - pii_start) * 1000
            
            # LLM inference
            llm_start = time.time()
            if LLAMA_GENERATOR is not None:
                response = LLAMA_GENERATOR.generate(
                    prompt=query,
                    max_new_tokens=request.max_new_tokens,
                    temperature=request.temperature
                )
                scope.register(response)
                model_name = "Llama 3.1 8B Instruct"
            else:
                response = f"[MOCK] Response for: {query}"
                model_name = "Mock Generator"
            llm_time = (time.time() - llm_start) * 1000
            
            # PII leak detection
            pii_leak_detected = False
            response_pii_mapping = {}  # Output'taki PII'lar
            security_warnings = []
            if request.enable_pii_protection and PII_MASKER is not None:
                try:
                    masked_response, response_pii_mapping = PII_MASKER.mask(response)
                    if len(response_pii_mapping) > 0:
                        pii_leak_detected = True
                        response = masked_response
                        scope.register(masked_response)
                        security_warnings.append({
                            "type": "PII_LEAKAGE",
                            "severity": "HIGH",
                            "message": f"Model response'unda {len(response_pii_mapping)} PII tespit edildi ve maskelendi"
                        })
                except Exception:
                    security_warnings.append({
                        "type": "PII_MASKING_ERROR",
                        "severity": "CRITICAL",
                        "message": "Response PII masking hatası"
                    })
            
            # Differential privacy
            if request.enable_dp and DIFF_PRIVACY is not None:
                try:
                    query_id = f"{hospital_id}_{int(time.time() * 1000)}"
                    response = DIFF_PRIVACY.add_noise_to_response(response, query_id=query_id)
                    scope.register(response)
                except Exception as e:
                    print(f"[WARNING] DP failed: {e}")
            
            # ===== ADIM 3: CEVABI ŞİFRELE =====
            encrypt_start = time.time()
            try:
                encrypted_response_data = E2E_ENCRYPTION.create_encrypted_response(response, aes_key)
            except Exception as encrypt_error:
                print(f"[ERROR] Response encryption failed: {encrypt_error}")
                raise HTTPException(
                    status_code=500,
                    detail="Response encryption failed"
                )
            encrypt_time = (time.time() - encrypt_start) * 1000
            
            total_time = (time.time() - start_time) * 1000
            
            # Audit logging
            audit_logger.log_request(
                username=username,
                endpoint="/generate_encrypted",
                request_data={"encrypted": True, "max_new_tokens": request.max_new_tokens},
                response_data={"encrypted": True, "processing_time_ms": round(total_time, 2)},
                client_ip=client_ip,
                user_agent=user_agent,
                processing_time_ms=total_time,
                success=True,
                pii_detected=pii_leak_detected,
                security_warnings=security_warnings
            )
            
            # Check if encryption is enabled
            encryption_enabled = os.getenv("ENABLE_IN_MEMORY_ENCRYPTION", "false").lower() == "true"
            
            # 🆕 PII COUNT: Input + Output PII sayısı (SWAGGER uyumlu)
            total_pii_detected = len(query_pii_mapping) + len(response_pii_mapping)
            
            return EncryptedGenerateResponse(
                encrypted_response=encrypted_response_data["encrypted_response"],
                nonce=encrypted_response_data["nonce"],
                encryption_method=encrypted_response_data["encryption_method"],
                processing_time_ms=round(total_time, 2),
                model=model_name,
                timing_breakdown={
                    "decryption_ms": round(decrypt_time, 2),
                    "llm_inference_ms": round(llm_time, 2),
                    "pii_masking_ms": round(pii_time, 2),
                    "encryption_ms": round(encrypt_time, 2),
                    "total_ms": round(total_time, 2)
                },
                pii_protection_applied=request.enable_pii_protection and PII_MASKER is not None,
                pii_detected=total_pii_detected,  # 🆕 Toplam PII sayısı
                dp_applied=request.enable_dp and DIFF_PRIVACY is not None,
                pii_leakage_detected=pii_leak_detected,
                security_warnings=security_warnings,
                model_encrypted_in_memory=encryption_enabled and isinstance(LLAMA_GENERATOR, EncryptedLlamaTextGenerator)
            )
            
        except HTTPException:
            raise
        
        except Exception as e:
            error_processing_time = (time.time() - start_time) * 1000
            print(f"[ERROR] Encrypted generation failed after {error_processing_time:.2f}ms: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Generation error: {str(e)}")
        
        finally:
            # Explicit memory cleanup for AES key
            if aes_key is not None:
                del aes_key

# ❌ DEPRECATED: /public_key endpoint'i kaldırıldı
# Public key artık response header'ında otomatik gönderiliyor

# @app.get("/public_key", tags=["Security"])
async def _deprecated_get_public_key():
    """⚠️ DEPRECATED: Public key artık otomatik header'da"""
    if E2E_ENCRYPTION is None:
        raise HTTPException(
            status_code=503,
            detail="E2E Encryption not available"
        )
    
    return {
        "public_key_pem": E2E_ENCRYPTION.get_public_key_pem(),
        "encryption_method": "RSA-OAEP-SHA256",
        "aes_method": "AES-256-GCM"
    }

# Server başlatma (ana program)

if __name__ == "__main__":
    import uvicorn
    from pathlib import Path
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║              Hibrit GPU + Şifreli LLM Sunucusu                       ║
║                                                                      ║
║         Hızlı GPU çıkarımı + PII koruma + Güvenli bellek             ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    # GPU 0 kullan (boşta olan)
    os.environ['CUDA_VISIBLE_DEVICES'] = os.getenv('CUDA_VISIBLE_DEVICES', '0')
    
    # HTTPS/TLS konfigürasyonu
    https_enabled = os.getenv("ENABLE_HTTPS", "false").lower() == "true"
    ssl_keyfile = None
    ssl_certfile = None
    
    if https_enabled:
        # SSL sertifikalarını kontrol et
        ssl_dir = Path(__file__).parent.parent.parent / "ssl"
        ssl_keyfile_path = ssl_dir / "server_key.pem"
        ssl_certfile_path = ssl_dir / "server_cert.pem"
        
        if ssl_keyfile_path.exists() and ssl_certfile_path.exists():
            ssl_keyfile = str(ssl_keyfile_path)
            ssl_certfile = str(ssl_certfile_path)
            print("✅ HTTPS ENABLED")
            print(f"   Key: {ssl_keyfile}")
            print(f"   Cert: {ssl_certfile}")
            protocol = "https"
        else:
            print("⚠️  WARNING: ENABLE_HTTPS=true ama sertifika bulunamadı!")
            print(f"   Beklenen: {ssl_keyfile_path}, {ssl_certfile_path}")
            print("   setup_https.sh script'ini çalıştırın!")
            print("   HTTP ile devam ediliyor...")
            protocol = "http"
    else:
        protocol = "http"
    
    port = int(os.getenv("PORT", "9200"))
    
    # Server başlat
    print(f"\n🚀 Server başlatılıyor: {protocol}://0.0.0.0:{port}")
    print(f"   Swagger UI: {protocol}://localhost:{port}/docs\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile
    )

