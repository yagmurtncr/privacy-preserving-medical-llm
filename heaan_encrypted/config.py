#!/usr/bin/env python3
"""
Production Configuration Management
Environment-based configuration loader
"""

import os
import secrets
from pathlib import Path
from typing import Optional

# Base directory
BASE_DIR = Path(__file__).parent.parent

# Environment file path
ENV_FILE = BASE_DIR / ".env"


class Config:
    """Production configuration manager"""
    
    # #1 Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "9200"))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # #2 Security Configuration
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_MINUTES: int = int(os.getenv("JWT_EXPIRATION_MINUTES", "30"))
    
    # #3 HTTPS Configuration
    HTTPS_ENABLED: bool = os.getenv("HTTPS_ENABLED", "false").lower() == "true"
    SSL_CERT_PATH: Optional[str] = os.getenv("SSL_CERT_PATH")
    SSL_KEY_PATH: Optional[str] = os.getenv("SSL_KEY_PATH")
    
    # #4 Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    RATE_LIMIT_PER_HOUR: int = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    
    # #5 IP Whitelist
    IP_WHITELIST: set = set(os.getenv("IP_WHITELIST", "127.0.0.1").split(","))
    IP_WHITELIST_ENABLED: bool = os.getenv("IP_WHITELIST_ENABLED", "false").lower() == "true"
    
    # #6 CORS
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    CORS_CREDENTIALS: bool = os.getenv("CORS_CREDENTIALS", "true").lower() == "true"
    
    # #7 Model Configuration
    MODEL_NAME: str = os.getenv("MODEL_NAME", "meta-llama/Meta-Llama-3.1-8B-Instruct")
    MODEL_DEVICE: str = os.getenv("MODEL_DEVICE", "cuda")
    MODEL_QUANTIZATION: str = os.getenv("MODEL_QUANTIZATION", "int8")
    MODEL_MAX_LENGTH: int = int(os.getenv("MODEL_MAX_LENGTH", "512"))
    
    # #8 GPU Configuration
    CUDA_VISIBLE_DEVICES: str = os.getenv("CUDA_VISIBLE_DEVICES", "0")
    
    # #9 Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/server.log")
    LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # #10 Monitoring
    ENABLE_METRICS: bool = os.getenv("ENABLE_METRICS", "true").lower() == "true"
    METRICS_PORT: int = int(os.getenv("METRICS_PORT", "9090"))
    
    # #11 Backup
    BACKUP_ENABLED: bool = os.getenv("BACKUP_ENABLED", "true").lower() == "true"
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "/backups")
    BACKUP_RETENTION_DAYS: int = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
    
    # #12 Performance
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "4"))
    TIMEOUT_SECONDS: int = int(os.getenv("TIMEOUT_SECONDS", "120"))
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "8"))
    
    # #13 Feature Flags
    ENABLE_DIFFERENTIAL_PRIVACY: bool = os.getenv("ENABLE_DIFFERENTIAL_PRIVACY", "true").lower() == "true"
    ENABLE_PII_MASKING: bool = os.getenv("ENABLE_PII_MASKING", "true").lower() == "true"
    ENABLE_SECURE_MEMORY: bool = os.getenv("ENABLE_SECURE_MEMORY", "true").lower() == "true"
    ENABLE_INFERENCE_ONLY: bool = os.getenv("ENABLE_INFERENCE_ONLY", "true").lower() == "true"
    
    @classmethod
    def is_production(cls) -> bool:
        """Production environment check"""
        return cls.ENVIRONMENT == "production"
    
    @classmethod
    def is_development(cls) -> bool:
        """Development environment check"""
        return cls.ENVIRONMENT == "development"
    
    @classmethod
    def validate(cls) -> list[str]:
        """Configuration validation - returns list of errors"""
        errors = []
        
        if cls.is_production():
            # Production mandatory checks
            if cls.JWT_SECRET_KEY == "CHANGE-THIS-IN-PRODUCTION":
                errors.append("JWT_SECRET_KEY must be changed in production!")
            
            if not cls.HTTPS_ENABLED:
                errors.append("HTTPS must be enabled in production!")
            
            if cls.HTTPS_ENABLED and (not cls.SSL_CERT_PATH or not cls.SSL_KEY_PATH):
                errors.append("SSL_CERT_PATH and SSL_KEY_PATH required when HTTPS enabled!")
            
            if cls.DEBUG:
                errors.append("DEBUG must be false in production!")
        
        # General doğrulamas
        if cls.JWT_EXPIRATION_MINUTES < 5:
            errors.append("JWT_EXPIRATION_MINUTES too short (min 5)!")
        
        if cls.PORT < 1024 or cls.PORT > 65535:
            errors.append(f"Invalid PORT: {cls.PORT}")
        
        return errors
    
    @classmethod
    def print_config(cls, hide_secrets: bool = True):
        """Print current configuration"""
        print("\n" + "="*70)
        print("⚙️  PRODUCTION CONFIGURATION")
        print("="*70)
        print(f"Environment:     {cls.ENVIRONMENT}")
        print(f"Debug Mode:      {cls.DEBUG}")
        print(f"Host:Port:       {cls.HOST}:{cls.PORT}")
        print(f"HTTPS Enabled:   {cls.HTTPS_ENABLED}")
        
        if hide_secrets:
            print(f"JWT Secret:      {'*' * 20}")
        else:
            print(f"JWT Secret:      {cls.JWT_SECRET_KEY[:10]}...")
        
        print(f"Rate Limiting:   {cls.RATE_LIMIT_ENABLED}")
        print(f"IP Whitelist:    {cls.IP_WHITELIST_ENABLED}")
        print(f"Model Device:    {cls.MODEL_DEVICE}")
        print(f"Log Level:       {cls.LOG_LEVEL}")
        print(f"Backup Enabled:  {cls.BACKUP_ENABLED}")
        
        # Validation
        errors = cls.validate()
        if errors:
            print("\n⚠️  CONFIGURATION ERRORS:")
            for error in errors:
                print(f"   ❌ {error}")
        else:
            print("\n✅ Configuration valid!")
        
        print("="*70 + "\n")


def load_env_file(env_file: Path = ENV_FILE):
    """Load environment variables from .env file"""
    if not env_file.exists():
        print(f"⚠️  {env_file} not found, using defaults")
        return
    
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Only set eğer not already içinde environment
                    if key not in os.environ:
                        os.environ[key] = value
    
    print(f"✅ Loaded environment from {env_file}")


# Auto-load üzerinde import
if ENV_FILE.exists():
    load_env_file()


if __name__ == "__main__":
    # Test configuration
    Config.print_config(hide_secrets=False)



