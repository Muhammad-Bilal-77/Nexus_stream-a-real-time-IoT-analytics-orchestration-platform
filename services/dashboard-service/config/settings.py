"""
NexusStream Dashboard Service — Configuration (Full)
=====================================================
All configuration via environment variables — 12-factor compliant.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Service
    dashboard_port: int = 8002

    # JWT — must match auth-service (HS256 for current stub; RS256 in production)
    jwt_secret: str = "nexusstream-dev-jwt-secret-change-in-prod"
    jwt_algorithm: str = "RS256"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "nexusstream"
    postgres_user: str = "nexus_admin"
    postgres_password: str = "changeme"
    postgres_min_pool: int = 2
    postgres_max_pool: int = 10

    # InfluxDB
    influxdb_host: str = "localhost"
    influxdb_port: int = 8086
    influxdb_token: str = "changeme"
    influxdb_org: str = "nexusstream-org"
    influxdb_bucket: str = "iot_metrics"

    # Redis cache
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_cache_ttl_seconds: int = 10   # TTL for cached API responses

    # Analytics service WebSocket (for proxying live metrics)
    analytics_ws_url: str = "ws://localhost:8001/ws/analytics"

    # Logging
    log_level: str = "info"
    log_format: str = "json"

    @property
    def influxdb_url(self) -> str:
        return f"http://{self.influxdb_host}:{self.influxdb_port}"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
