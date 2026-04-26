from __future__ import annotations

from collections import defaultdict
from typing import List
import gspread
from google.oauth2.service_account import Credentials

from .config import settings
from .models import ExpenseRecord, SummaryResponse


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "expense_id",
    "created_at",
    "expense_date",
    "category",
    "description",
    "merchant",
    "person",
    "currency",
    "amount_original",
    "exchange_rate_to_brl",
    "amount_brl",
    "payment_method",
    "status",
    "source",
    "confidence",
    "notes",
    "raw_text",
]


class SheetsStore:
    def __init__(self) -> None:
        if not settings.spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID não configurado.")

        credentials = Credentials.from_service_account_file(
            settings.service_account_json,
            scopes=SCOPES,
        )
        self.client = gspread.authorize(credentials)
        self.spreadsheet = self.client.open_by_key(settings.spreadsheet_id)
        self.expenses_ws = self._get_or_create("Despesas")
        self.summary_ws = self._get_or_create("Resumo")
        self._ensure_headers()

    def _get_or_create(self, title: str):
        try:
            return self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return self.spreadsheet.add_worksheet(title=title, rows=1000, cols=30)

    def _ensure_headers(self) -> None:
        first_row = self.expenses_ws.row_values(1)
        if first_row != HEADERS:
            self.expenses_ws.clear()
            self.expenses_ws.append_row(HEADERS)

    def append_expense(self, record: ExpenseRecord) -> None:
        row = [
            record.expense_id,
            record.created_at.isoformat(),
            record.expense_date.isoformat() if record.expense_date else "",
            record.category.value,
            record.description,
            record.merchant or "",
            record.person,
            record.currency.value,
            record.amount_original,
            record.exchange_rate_to_brl,
            record.amount_brl,
            record.payment_method or "",
            record.status,
            record.source,
            record.confidence,
            record.notes or "",
            record.raw_text,
        ]
        self.expenses_ws.append_row(row, value_input_option="USER_ENTERED")
        self.refresh_summary()

    def list_records(self) -> List[dict]:
        return self.expenses_ws.get_all_records()

    def refresh_summary(self) -> SummaryResponse:
        rows = self.list_records()
        total_brl = 0.0
        by_category = defaultdict(float)
        by_person = defaultdict(float)

        for row in rows:
            try:
                amount = float(str(row.get("amount_brl", 0)).replace(",", "."))
            except Exception:
                amount = 0.0

            category = row.get("category") or "Não classificado"
            person = row.get("person") or "Não informado"

            total_brl += amount
            by_category[category] += amount
            by_person[person] += amount

        total_eur_equivalent = total_brl / settings.default_eur_brl if settings.default_eur_brl else 0

        summary = SummaryResponse(
            total_brl=round(total_brl, 2),
            total_eur_equivalent=round(total_eur_equivalent, 2),
            by_category_brl={k: round(v, 2) for k, v in sorted(by_category.items())},
            by_person_brl={k: round(v, 2) for k, v in sorted(by_person.items())},
            count=len(rows),
        )

        self._write_summary(summary)
        return summary

    def _write_summary(self, summary: SummaryResponse) -> None:
        self.summary_ws.clear()
        self.summary_ws.append_row(["Indicador", "Valor"])
        self.summary_ws.append_row(["Total BRL", summary.total_brl])
        self.summary_ws.append_row(["Total equivalente EUR", summary.total_eur_equivalent])
        self.summary_ws.append_row(["Número de despesas", summary.count])

        self.summary_ws.append_row([])
        self.summary_ws.append_row(["Categoria", "Total BRL"])
        for category, value in summary.by_category_brl.items():
            self.summary_ws.append_row([category, value])

        self.summary_ws.append_row([])
        self.summary_ws.append_row(["Pessoa", "Total BRL"])
        for person, value in summary.by_person_brl.items():
            self.summary_ws.append_row([person, value])
