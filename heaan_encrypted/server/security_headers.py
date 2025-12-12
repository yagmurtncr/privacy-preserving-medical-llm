#!/usr/bin/env python3
"""
Security Headers Middleware
XSS, clickjacking, MIME sniffing koruması + CSP
"""

def add_security_headers(app, enable_hsts=False):
    """
    Güvenlik header'larını ekle
    
    Headers:
    - X-Content-Type-Options: MIME sniffing önleme
    - X-Frame-Options: Clickjacking önleme
    - X-XSS-Protection: XSS önleme
    - Content-Security-Policy: XSS, injection saldırılarına karşı koruma
    - Permissions-Policy: Tarayıcı API erişim kontrolü
    - Referrer-Policy: Referrer bilgisi kontrolü
    - HSTS: HTTPS zorunluluğu (production'da)
    """
    @app.middleware("http")
    async def security_headers_middleware(request, call_next):
        response = await call_next(request)
        
        # ✅ Mevcut header'lar
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # 🆕 Content Security Policy (CSP)
        # XSS, injection saldırılarına karşı güçlü koruma
        csp_policy = (
            "default-src 'self'; "  # Varsayılan: sadece kendi domain'imiz
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net unpkg.com; "  # Swagger UI için
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net unpkg.com; "  # Swagger UI için
            "img-src 'self' data: https:; "  # Resimler: kendi domain + data URL + HTTPS
            "font-src 'self' data:; "  # Font'lar: kendi domain + data URL
            "connect-src 'self'; "  # AJAX/fetch: sadece kendi domain
            "frame-ancestors 'none'; "  # iframe'e alınamaz
            "base-uri 'self'; "  # Base URL: sadece kendi domain
            "form-action 'self'; "  # Form submit: sadece kendi domain
            "upgrade-insecure-requests; "  # HTTP → HTTPS yönlendirme
        )
        response.headers["Content-Security-Policy"] = csp_policy
        
        # 🆕 Permissions Policy (eski adı: Feature Policy)
        # Tarayıcı API'lerine erişim kontrolü
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "  # Konum erişimi yok
            "microphone=(), "  # Mikrofon erişimi yok
            "camera=(), "  # Kamera erişimi yok
            "payment=(), "  # Payment API yok
            "usb=(), "  # USB erişimi yok
            "accelerometer=(), "  # Ivmeölçer yok
            "gyroscope=(), "  # Jiroskop yok
            "magnetometer=(), "  # Manyetometre yok
            "interest-cohort=()"  # FLoC tracking yok
        )
        
        # 🆕 Referrer Policy
        # Referrer bilgisini kontrol et (privacy)
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # 🆕 Cross-Origin Policies
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        
        # ✅ HSTS (HTTP Strict Transport Security)
        # Production'da HTTPS zorunlu
        if enable_hsts:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; "  # 1 yıl
                "includeSubDomains; "  # Alt domainler dahil
                "preload"  # HSTS preload list'e eklenebilir
            )
        
        return response

