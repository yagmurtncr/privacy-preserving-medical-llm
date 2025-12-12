#!/usr/bin/env python3
"""HTTPS Redirect Middleware"""

def add_https_redirect(app, enabled=False):
    """HTTPS yönlendirme (Production için)"""
    if not enabled:
        return
    
    @app.middleware("http")
    async def https_redirect_middleware(request, call_next):
        if request.url.scheme != "https":
            url = request.url.replace(scheme="https")
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url)
        return await call_next(request)

