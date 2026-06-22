from pydantic_settings import BaseSettings
from functools import lru_cache
from urllib.parse import quote


class Settings(BaseSettings):
    db_user: str = "bap"
    db_password: str = "bappassword"
    db_name: str = "bapdb"
    db_host: str = "db"
    db_port: int = 5432

    secret_key: str = "gelistirme-anahtari-uretimde-degistir"
    access_token_expire_minutes: int = 480

    ldap_enabled: bool = False
    ldap_host: str = ""
    ldap_port: int = 389
    ldap_base_dn: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""

    app_title: str = "BAP Çıktı Yönetim Sistemi"
    upload_dir: str = "/app/uploads"
    max_upload_mb: int = 20

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{quote(self.db_password, safe='')}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
