#!/usr/bin/env python3
"""CORS Configuration"""
import os

from fastapi.middleware.cors import CORSMiddleware


def add_cors_middleware(app, strict=False):
    """
    ✅ GÜVENL: CORS middleware ekle
    
    Development: Tüm origin'lere izin (testing için)
    Production: Sadece ALLOWED_ORIGINS environment variable'daki domainler
    """
    if strict:
        # Production: Sadece izinli domainler (.env'den oku)
        allowed_origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
        allowed_origins = [origin.strip() for origin in allowed_origins if origin.strip()]
        
        if not allowed_origins:
            # Hiç origin tanımlanmamışsa güvenlik için hiçbir origin'e izin verme
            print("⚠️  WARNING: CORS strict mode aktif ama ALLOWED_ORIGINS tanımlı değil!")
            print("   Tüm cross-origin istekler reddedilecek!")
            origins = []
        else:
            origins = allowed_origins
            print(f"✅ CORS Strict Mode: {len(origins)} izinli origin")
    else:
        # Development: Herkese izin
        origins = ["*"]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],  # ✅ Sadece gerekli metotlar
        allow_headers=["*"],
    )

