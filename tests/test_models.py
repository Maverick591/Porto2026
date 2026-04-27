from porto2026 import api as porto_api
from porto2026.config import Settings
from porto2026.models import Currency, ExpenseCategory, ExpensePatch, ParsedExpense


def test_build_record_converts_foreign_currency_using_default_rate(monkeypatch):
    monkeypatch.setattr(
        porto_api,
        "settings",
        Settings(
            openai_api_key="test",
            minimax_api_key="test",
            minimax_base_url="https://api.minimaxi.com/v1",
            spreadsheet_id="sheet",
            service_account_json="service-account.json",
            default_eur_brl=5.75,
            timezone="America/Sao_Paulo",
            api_key="secret",
        ),
        raising=False,
    )

    parsed = ParsedExpense(
        description="Jantar no Porto",
        category=ExpenseCategory.ALIMENTACAO,
        currency=Currency.EUR,
        amount_original=80,
    )

    record = porto_api.build_record(parsed, raw_text="texto", source="text")

    assert record.exchange_rate_to_brl == 5.75
    assert record.amount_brl == 460.0


def test_apply_patch_recomputes_amount_in_brl(monkeypatch):
    monkeypatch.setattr(
        porto_api,
        "settings",
        Settings(
            openai_api_key="test",
            minimax_api_key="test",
            minimax_base_url="https://api.minimaxi.com/v1",
            spreadsheet_id="sheet",
            service_account_json="service-account.json",
            default_eur_brl=6.10,
            timezone="America/Sao_Paulo",
            api_key="secret",
        ),
        raising=False,
    )

    parsed = ParsedExpense(
        description="Jantar no Porto",
        category=ExpenseCategory.ALIMENTACAO,
        currency=Currency.EUR,
        amount_original=80,
    )
    original = porto_api.build_record(parsed, raw_text="texto", source="text")

    patched = porto_api.apply_patch(
        original,
        ExpensePatch(amount_original=100, currency=Currency.BRL, description="Jantar ajustado"),
    )

    assert patched.description == "Jantar ajustado"
    assert patched.exchange_rate_to_brl == 1.0
    assert patched.amount_brl == 100.0
