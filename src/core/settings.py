from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )

    ozon_search_url: str = "https://www.ozon.ru/search/?text="
    google_spreadsheet_id: str
    google_sheet_name: str
    google_credentials_path: Path = BASE_DIR / "credentials.json"


settings = Settings()
