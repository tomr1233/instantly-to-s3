from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    instantly_api_key: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "ap-southeast-2"
    s3_bucket_name: str = "expressnext-workspace"
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "instantly-to-s3"


def get_settings() -> Settings:
    return Settings()
