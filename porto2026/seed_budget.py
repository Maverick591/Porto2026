from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4

from .config import settings
from .models import ExpenseRecord, ExpenseCategory, Currency
from .sheets import SheetsStore


def make_record(category, description, person, currency, amount, status="Realizado", notes=None):
    rate = 1.0 if currency == Currency.BRL else settings.default_eur_brl
    return ExpenseRecord(
        expense_id=str(uuid4()),
        created_at=datetime.now(ZoneInfo(settings.timezone)),
        expense_date=None,
        category=category,
        description=description,
        merchant=None,
        person=person,
        currency=currency,
        amount_original=amount,
        exchange_rate_to_brl=rate,
        amount_brl=round(amount * rate, 2),
        payment_method=None,
        status=status,
        source="text",
        raw_text=description,
        confidence=1.0,
        notes=notes,
    )


records = [
    make_record(ExpenseCategory.PASSAGENS, "LATAM ida e volta São Paulo-Porto para casal", "Casal", Currency.BRL, 10329.34),
    make_record(ExpenseCategory.HOSPEDAGEM, "Dorma Essenzia Porto, 9 noites, com taxa turística", "Casal", Currency.EUR, 1297.20),
    make_record(ExpenseCategory.CONGRESSO, "Inscrições e eventos EHS 2026", "Jocielle/Solange", Currency.EUR, 1330.00),
    make_record(ExpenseCategory.PASSEIO, "Douro Valley Tour completo - estimativa casal", "Casal", Currency.EUR, 320.00, status="Estimado"),
    make_record(ExpenseCategory.ALIMENTACAO, "Alimentação estimada no destino", "Casal", Currency.EUR, 1100.00, status="Estimado"),
    make_record(ExpenseCategory.TRANSPORTE, "Uber/Bolt estimado no destino", "Casal", Currency.EUR, 170.00, status="Estimado"),
    make_record(ExpenseCategory.EXTRAS, "Extras estimados", "Casal", Currency.EUR, 250.00, status="Estimado"),
]


if __name__ == "__main__":
    store = SheetsStore()
    for record in records:
        store.append_expense(record)
    print(f"{len(records)} registros iniciais salvos.")
