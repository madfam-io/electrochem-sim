"""
Configuration management with environment validation
"""

import os
from typing import Optional
from pydantic import BaseSettings, validator, Field
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings with validation"""
    
    # Environment
    environment: str = Field("development", regex="^(development|staging|production)$")
    debug: bool = Field(False)
    log_level: str = Field("INFO", regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    
    # API Configuration
    api_host: str = Field("0.0.0.0")
    api_port: int = Field(8080, ge=1024, le=65535)
    api_workers: int = Field(4, ge=1, le=16)
    
    # Security
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = Field("HS256")
    access_token_expire_minutes: int = Field(30, ge=5, le=1440)
    cors_origins: list = Field(["http://localhost:3000"])
    
    # Database
    database_url: str = Field(...)
    database_pool_size: int = Field(10, ge=1, le=50)
    database_max_overflow: int = Field(20, ge=0, le=100)
    
    # Redis
    redis_url: str = Field(...)
    redis_max_connections: int = Field(50, ge=10, le=200)
    redis_ttl: int = Field(3600, ge=60, le=86400)
    
    # S3/MinIO
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: str = Field("galvana-artifacts")
    s3_region: str = Field("us-east-1")
    s3_use_ssl: bool = Field(True)
    
    # Rate Limiting
    rate_limit_enabled: bool = Field(True)
    rate_limit_requests: int = Field(100, ge=10, le=1000)
    rate_limit_period: int = Field(60, ge=1, le=3600)
    
    # Simulation
    max_simulation_time: int = Field(86400, ge=60, le=604800)  # Max 1 week
    max_mesh_elements: int = Field(10000, ge=100, le=100000)
    simulation_timeout: int = Field(3600, ge=60, le=86400)
    
    @validator("jwt_secret_key")
    def validate_jwt_secret(cls, v, values):
        """Ensure JWT secret is secure"""
        if values.get("environment") == "production":
            if len(v) < 64:
                raise ValueError("JWT secret must be at least 64 characters in production")
            if v == "your-secret-key-change-in-production":
                raise ValueError("Default JWT secret cannot be used in production")
        return v
    
    @validator("database_url")
    def validate_database_url(cls, v):
        """Validate database connection string"""
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("Only PostgreSQL databases are supported")
        if "password" not in v and "@" in v:
            raise ValueError("Database password is required")
        return v
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("s3_endpoint")
    def validate_s3_config(cls, v, values):
        """Validate S3 configuration"""
        if v and not values.get("s3_access_key"):
            raise ValueError("S3 access key required when endpoint is specified")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    try:
        return Settings()
    except Exception as e:
        # Log error and provide helpful message
        import sys
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error loading configuration: {e}")
        logger.error("Please ensure all required environment variables are set:")
        logger.error("- JWT_SECRET_KEY (min 32 chars)")
        logger.error("- DATABASE_URL (PostgreSQL connection string)")
        logger.error("- REDIS_URL (Redis connection string)")
        logger.error("See .env.example for reference")
        sys.exit(1)

# Create settings instance
settings = get_settings()