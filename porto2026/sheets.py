from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, date
from itertools import zip_longest
from typing import Any

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
    "attachment_url",
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
            return self.spreadsheet.add_worksheet(title=title, rows=1000, cols=40)

    def _ensure_headers(self) -> None:
        first_row = self.expenses_ws.row_values(1)
        if first_row != HEADERS:
            self.expenses_ws.update("A1", [HEADERS])

    @staticmethod
    def _parse_float(value: Any, default: float = 0.0) -> float:
        if value in (None, ""):
            return default
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    @staticmethod
    def _parse_created_at(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if value in (None, ""):
            return datetime.now()
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return datetime.now()

    def _row_to_record(self, row: dict[str, Any]) -> ExpenseRecord:
        payload = dict(row)
        payload["created_at"] = self._parse_created_at(payload.get("created_at"))
        payload["expense_date"] = self._parse_date(payload.get("expense_date"))
        payload["amount_original"] = self._parse_float(payload.get("amount_original"))
        payload["exchange_rate_to_brl"] = self._parse_float(payload.get("exchange_rate_to_brl"), 1.0)
        payload["amount_brl"] = self._parse_float(payload.get("amount_brl"))
        payload["confidence"] = self._parse_float(payload.get("confidence"), 0.0)

        for key in ("merchant", "payment_method", "attachment_url", "notes"):
            if payload.get(key) == "":
                payload[key] = None

        return ExpenseRecord(**payload)

    def _record_to_row(self, record: ExpenseRecord) -> list[Any]:
        return [
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
            record.attachment_url or "",
            record.source,
            record.confidence,
            record.notes or "",
            record.raw_text,
        ]

    def _all_rows(self) -> list[list[str]]:
        rows = self.expenses_ws.get_all_values()
        if not rows:
            return []
        return rows

    def _find_row_index(self, expense_id: str) -> tuple[int, ExpenseRecord]:
        rows = self._all_rows()
        for row_index, row in enumerate(rows[1:], start=2):
            row_data = {
                header: value
                for header, value in zip_longest(HEADERS, row, fillvalue="")
            }
            if row_data.get("expense_id") == expense_id:
                return row_index, self._row_to_record(row_data)
        raise KeyError(f"Despesa não encontrada: {expense_id}")

    def append_expense(self, record: ExpenseRecord, refresh_summary: bool = True) -> None:
        self.expenses_ws.append_row(self._record_to_row(record), value_input_option="USER_ENTERED")
        if refresh_summary:
            self.refresh_summary()

    def append_expenses(self, records: list[ExpenseRecord], refresh_summary: bool = True) -> None:
        if not records:
            return
        rows = [self._record_to_row(record) for record in records]
        self.expenses_ws.append_rows(rows, value_input_option="USER_ENTERED")
        if refresh_summary:
            self.refresh_summary()

    def get_expense(self, expense_id: str) -> ExpenseRecord | None:
        try:
            _, record = self._find_row_index(expense_id)
            return record
        except KeyError:
            return None

    def update_expense(self, record: ExpenseRecord, refresh_summary: bool = True) -> ExpenseRecord:
        row_index, _ = self._find_row_index(record.expense_id)
        self.expenses_ws.update(f"A{row_index}", [self._record_to_row(record)])
        if refresh_summary:
            self.refresh_summary()
        return record

    def delete_expense(self, expense_id: str, refresh_summary: bool = True) -> ExpenseRecord:
        row_index, record = self._find_row_index(expense_id)
        self.expenses_ws.delete_rows(row_index)
        if refresh_summary:
            self.refresh_summary()
        return record

    def list_expenses(self) -> list[ExpenseRecord]:
        rows = self._all_rows()
        if len(rows) <= 1:
            return []

        records: list[ExpenseRecord] = []
        for row in rows[1:]:
            row_data = {
                header: value
                for header, value in zip_longest(HEADERS, row, fillvalue="")
            }
            records.append(self._row_to_record(row_data))
        return records

    def list_records(self) -> list[dict[str, Any]]:
        return [record.model_dump(mode="json") for record in self.list_expenses()]

    def export_csv_text(self) -> str:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=HEADERS)
        writer.writeheader()
        for row in self.list_records():
            writer.writerow({header: row.get(header, "") for header in HEADERS})
        return buffer.getvalue()

    def refresh_summary(self) -> SummaryResponse:
        records = self.list_expenses()
        total_brl = 0.0
        by_category = defaultdict(float)
        by_person = defaultdict(float)

        for record in records:
            amount = float(record.amount_brl or 0.0)
            category = record.category.value
            person = record.person or "Não informado"

            total_brl += amount
            by_category[category] += amount
            by_person[person] += amount

        total_eur_equivalent = total_brl / settings.default_eur_brl if settings.default_eur_brl else 0

        summary = SummaryResponse(
            total_brl=round(total_brl, 2),
            total_eur_equivalent=round(total_eur_equivalent, 2),
            by_category_brl={k: round(v, 2) for k, v in sorted(by_category.items())},
            by_person_brl={k: round(v, 2) for k, v in sorted(by_person.items())},
            count=len(records),
        )

        self._write_summary(summary)
        return summary

    def _write_summary(self, summary: SummaryResponse) -> None:
        rows: list[list[Any]] = [
            ["Indicador", "Valor"],
            ["Total BRL", summary.total_brl],
            ["Total equivalente EUR", summary.total_eur_equivalent],
            ["Número de despesas", summary.count],
            ["", ""],
            ["Categoria", "Total BRL"],
        ]

        for category, value in summary.by_category_brl.items():
            rows.append([category, value])

        rows.extend(
            [
                ["", ""],
                ["Pessoa", "Total BRL"],
            ]
        )

        for person, value in summary.by_person_brl.items():
            rows.append([person, value])

        self.summary_ws.clear()
        self.summary_ws.update("A1", rows)
