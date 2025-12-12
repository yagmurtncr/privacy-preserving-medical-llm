"""
Rate Limiter Module
IP bazlı rate limiting middleware (20/min, 500/hour, sliding window)
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from datetime import datetime, timedelta

# =============================================================================
# RATE LIMITER CLASS
# =============================================================================

class RateLimiter:
    """IP bazlı rate limiting (in-memory, sliding window algoritması)"""
    
    #   1 (Middleware tarafından başlatılır)
    # Açıklama: Rate limiter'ı başlatır ve memory storage'ı hazırlar
    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.minute_requests = defaultdict(list)  # {ip: [timestamp1, timestamp2, ...]}
        self.hour_requests = defaultdict(list)
    
    #   3 (is_allowed içinde otomatik çağrılır)
    # Açıklama: Süresi geçmiş kayıtları bellekten temizler
    def _cleanup_old_requests(self):
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        
        for ip in list(self.minute_requests.keys()):
            self.minute_requests[ip] = [ts for ts in self.minute_requests[ip] if ts > minute_ago]
            if not self.minute_requests[ip]:
                del self.minute_requests[ip]
        
        for ip in list(self.hour_requests.keys()):
            self.hour_requests[ip] = [ts for ts in self.hour_requests[ip] if ts > hour_ago]
            if not self.hour_requests[ip]:
                del self.hour_requests[ip]
    
    #   2 (Her request'te çağrılır)
    # Açıklama: IP'nin rate limitini kontrol eder ve izin verir/reddeder
    def is_allowed(self, ip: str) -> tuple[bool, str]:
        now = datetime.now()
        
        # Dakika limiti kontrol
        minute_count = len([ts for ts in self.minute_requests[ip] if ts > now - timedelta(minutes=1)])
        if minute_count >= self.requests_per_minute:
            return False, f"Rate limit aşıldı: {self.requests_per_minute} istek/dakika"
        
        # Saat limiti kontrol
        hour_count = len([ts for ts in self.hour_requests[ip] if ts > now - timedelta(hours=1)])
        if hour_count >= self.requests_per_hour:
            return False, f"Rate limit aşıldı: {self.requests_per_hour} istek/saat"
        
        # İsteği kaydet
        self.minute_requests[ip].append(now)
        self.hour_requests[ip].append(now)
        
        # Periyodik temizlik (her 100 istek)
        if len(self.minute_requests) % 100 == 0:
            self._cleanup_old_requests()
        
        return True, "OK"


# =============================================================================
# FASTAPI MIDDLEWARE
# =============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware olarak rate limiting uygular"""
    
    #   1 (app.add_middleware ile eklenir)
    # Açıklama: Middleware'ı başlatır ve RateLimiter oluşturur
    def __init__(self, app, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        super().__init__(app)
        self.limiter = RateLimiter(requests_per_minute, requests_per_hour)
        self.whitelist = ["/health", "/docs", "/openapi.json", "/redoc"]  # Rate limit dışı endpoint'ler
    
    #   2 (Her HTTP request'te otomatik çağrılır)
    # Açıklama: Request'i yakalar, rate limit kontrol eder ve response header'ları ekler
    async def dispatch(self, request: Request, call_next):
        # Whitelist kontrolü
        if any(request.url.path.startswith(path) for path in self.whitelist):
            return await call_next(request)
        
        # Client IP çıkar (proxy header desteği ile)
        client_ip = request.client.host
        if "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        
        # Rate limit kontrol
        allowed, message = self.limiter.is_allowed(client_ip)
        
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit aşıldı: {message} (IP: {client_ip})",
                headers={"Retry-After": "60"}
            )
        
        # Request'i işle
        response = await call_next(request)
        
        # Response header'larına rate limit bilgisi ekle
        now = datetime.now()
        minute_count = len([ts for ts in self.limiter.minute_requests[client_ip] 
                           if ts > now - timedelta(minutes=1)])
        hour_count = len([ts for ts in self.limiter.hour_requests[client_ip] 
                         if ts > now - timedelta(hours=1)])
        
        response.headers["X-RateLimit-Limit-Minute"] = str(self.limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(max(0, self.limiter.requests_per_minute - minute_count))
        response.headers["X-RateLimit-Limit-Hour"] = str(self.limiter.requests_per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(max(0, self.limiter.requests_per_hour - hour_count))
        
        return response

