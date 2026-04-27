import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "Porto2026.env")
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    minimax_api_key: str = os.getenv("MINIMAX_API_KEY", "")
    minimax_base_url: str = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    spreadsheet_id: str = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "./service-account.json")
    default_eur_brl: float = float(os.getenv("DEFAULT_EUR_BRL", "5.50"))
    timezone: str = os.getenv("TIMEZONE", "America/Sao_Paulo")
    api_key: str = os.getenv("PORTO2026_API_KEY", "")


settings = Settings()
