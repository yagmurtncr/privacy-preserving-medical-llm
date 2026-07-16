#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IP Whitelist Middleware - Sadece izin verilen IP'lerden erişim
"""

import ipaddress
from typing import List, Union

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """
    Kullanım Sırası: 1 (Her request'te ilk kontrol)
    Açıklama: Sadece whitelist'teki IP'lerden gelen istekleri kabul eder
    """
    
    def __init__(self, app, allowed_ips: List[str] = None, enabled: bool = True):
        """
        Kullanım Sırası: 0 (Middleware başlatma)
        Açıklama: IP whitelist konfigürasyonunu hazırlar
        
        Args:
            app: FastAPI application
            allowed_ips: İzin verilen IP adresleri ve CIDR blokları
            enabled: Middleware aktif mi? (Development'ta False olabilir)
        
        Örnek:
            allowed_ips = [
                "127.0.0.1",           # Localhost
                "::1",                 # IPv6 localhost
                "10.0.0.0/8",          # Private network
                "172.16.0.0/12",       # Private network
                "192.168.0.0/16"       # Private network
            ]
        """
        super().__init__(app)
        self.enabled = enabled
        
        if not self.enabled:
            print("⚠️  IP Whitelist DISABLED (development mode)")
            return
        
        # Default: sadece localhost
        if allowed_ips is None:
            allowed_ips = ["127.0.0.1", "::1"]
        
        self.allowed_networks = []
        
        for ip_str in allowed_ips:
            try:
                # CIDR notation mı kontrol et (örn: 10.0.0.0/8)
                if "/" in ip_str:
                    network = ipaddress.ip_network(ip_str, strict=False)
                    self.allowed_networks.append(network)
                else:
                    # Tek IP adresi
                    ip = ipaddress.ip_address(ip_str)
                    # Tek IP'yi /32 veya /128 network olarak ekle
                    if ip.version == 4:
                        network = ipaddress.ip_network(f"{ip_str}/32", strict=False)
                    else:
                        network = ipaddress.ip_network(f"{ip_str}/128", strict=False)
                    self.allowed_networks.append(network)
                    
            except ValueError as e:
                print(f"⚠️  Invalid IP/CIDR: {ip_str} - {e}")
        
        print(f"✅ IP Whitelist enabled: {len(self.allowed_networks)} networks")
        for net in self.allowed_networks:
            print(f"   ✓ {net}")
    
    async def dispatch(self, request: Request, call_next):
        """
        Kullanım Sırası: 1 (Her request'te)
        Açıklama: Client IP'yi kontrol eder, whitelist'te yoksa 403 döner
        """
        
        # Disabled ise bypass
        if not self.enabled:
            return await call_next(request)
        
        # Client IP al
        client_ip = request.client.host
        
        try:
            # IP adresini parse et
            ip_addr = ipaddress.ip_address(client_ip)
            
            # Whitelist'te var mı kontrol et
            is_allowed = False
            for network in self.allowed_networks:
                if ip_addr in network:
                    is_allowed = True
                    break
            
            if not is_allowed:
                # Güvenlik log'u
                print(f"🚫 IP BLOCKED: {client_ip} (not in whitelist)")
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied: IP {client_ip} not whitelisted"
                )
            
            # İzin verildi, devam et
            return await call_next(request)
            
        except ValueError:
            # IP parse edilemedi
            print(f"⚠️  Invalid IP format: {client_ip}")
            raise HTTPException(
                status_code=400,
                detail="Invalid client IP address"
            )


# Kullanım örneği (hybrid_gpu_server.py'den çağrılacak)
def add_ip_whitelist(app, allowed_ips: List[str] = None, enabled: bool = True):
    """
    Kullanım Sırası: 0 (Server startup'ta)
    Açıklama: IP whitelist middleware'ini FastAPI app'e ekler
    
    Örnek:
        from heaan_encrypted.server.ip_whitelist import add_ip_whitelist
        
        # Development
        add_ip_whitelist(app, enabled=False)
        
        # Production
        add_ip_whitelist(app, allowed_ips=["10.0.0.0/8"], enabled=True)
    """
    app.add_middleware(IPWhitelistMiddleware, allowed_ips=allowed_ips, enabled=enabled)

