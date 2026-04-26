import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    spreadsheet_id: str = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "./service-account.json")
    default_eur_brl: float = float(os.getenv("DEFAULT_EUR_BRL", "5.50"))
    timezone: str = os.getenv("TIMEZONE", "America/Sao_Paulo")


settings = Settings()
