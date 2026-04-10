"""
NexusStream Analytics Service — Configuration (updated)
=========================================================
All config via environment variables — 12-factor compliant.
pydantic-settings auto-reads from the .env file and environment.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Service
    analytics_port: int = 8001

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_iot_channel: str = "iot:metrics"

    # InfluxDB
    influxdb_host: str = "localhost"
    influxdb_port: int = 8086
    influxdb_token: str = "changeme"
    influxdb_org: str = "nexusstream-org"
    influxdb_bucket: str = "iot_metrics"

    # Sliding window
    window_size_seconds: int = 60

    # Anomaly thresholds — per device type
    anomaly_threshold_temperature_min: float = -20.0
    anomaly_threshold_temperature_max: float = 85.0
    anomaly_threshold_pressure_min: float = 80_000.0
    anomaly_threshold_pressure_max: float = 120_000.0
    anomaly_threshold_humidity_min: float = 0.0
    anomaly_threshold_humidity_max: float = 100.0
    anomaly_threshold_vibration_min: float = 0.0
    anomaly_threshold_vibration_max: float = 500.0
    anomaly_threshold_power_min: float = 0.0
    anomaly_threshold_power_max: float = 5_000.0

    # InfluxDB batching
    influx_batch_size: int = 50
    influx_batch_interval_ms: int = 1000

    # Anomaly cache (in-memory for /anomalies/recent)
    anomaly_cache_size: int = 200

    # Logging
    log_level: str = "info"
    log_format: str = "json"

    @property
    def influxdb_url(self) -> str:
        return f"http://{self.influxdb_host}:{self.influxdb_port}"


settings = Settings()
