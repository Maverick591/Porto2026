from collections import defaultdict
import csv
import io

from fastapi.testclient import TestClient

from porto2026 import api as porto_api
from porto2026.config import Settings
from porto2026.models import Currency, ExpenseCategory, ParsedExpense, SummaryResponse
from porto2026.sheets import HEADERS


class FakeExtractor:
    def parse_text(self, text: str) -> ParsedExpense:
        return ParsedExpense(
            description="Jantar no Porto",
            category=ExpenseCategory.ALIMENTACAO,
            currency=Currency.EUR,
            amount_original=80,
            merchant="Restaurante",
            person="Casal",
            payment_method="Cartão",
            notes=text,
        )

    def parse_photo(self, file_bytes: bytes, mime_type: str, hint: str | None = None) -> ParsedExpense:
        return ParsedExpense(
            description="Café da manhã",
            category=ExpenseCategory.ALIMENTACAO,
            currency=Currency.EUR,
            amount_original=12,
            merchant="Padaria",
            person="Casal",
            payment_method="Dinheiro",
            notes=hint,
        )

    def transcribe_audio(self, file_bytes: bytes, filename: str = "audio.m4a") -> str:
        return "Táxi 12 euros"


class FakeStore:
    def __init__(self) -> None:
        self.records = []

    def append_expense(self, record):
        self.records.append(record)

    def get_expense(self, expense_id: str):
        for record in self.records:
            if record.expense_id == expense_id:
                return record
        return None

    def update_expense(self, record):
        for index, current in enumerate(self.records):
            if current.expense_id == record.expense_id:
                self.records[index] = record
                return record
        raise KeyError(record.expense_id)

    def delete_expense(self, expense_id: str):
        for index, current in enumerate(self.records):
            if current.expense_id == expense_id:
                return self.records.pop(index)
        raise KeyError(expense_id)

    def list_expenses(self):
        return list(self.records)

    def list_records(self):
        return [record.model_dump(mode="json") for record in self.records]

    def refresh_summary(self):
        total_brl = sum(float(record.amount_brl) for record in self.records)
        by_category = defaultdict(float)
        by_person = defaultdict(float)

        for record in self.records:
            by_category[record.category.value] += float(record.amount_brl)
            by_person[record.person] += float(record.amount_brl)

        summary = SummaryResponse(
            total_brl=round(total_brl, 2),
            total_eur_equivalent=round(total_brl / 5.5, 2) if total_brl else 0.0,
            by_category_brl={k: round(v, 2) for k, v in sorted(by_category.items())},
            by_person_brl={k: round(v, 2) for k, v in sorted(by_person.items())},
            count=len(self.records),
        )
        self.summary = summary
        return summary

    def export_csv_text(self):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=HEADERS)
        writer.writeheader()
        for record in self.list_records():
            writer.writerow({header: record.get(header, "") for header in HEADERS})
        return output.getvalue()


def make_client(monkeypatch, api_key: str = ""):
    monkeypatch.setattr(
        porto_api,
        "settings",
        Settings(
            openai_api_key="test",
            minimax_api_key="test",
            minimax_base_url="https://api.minimaxi.com/v1",
            spreadsheet_id="sheet",
            service_account_json="service-account.json",
            default_eur_brl=5.5,
            timezone="America/Sao_Paulo",
            api_key=api_key,
        ),
        raising=False,
    )
    monkeypatch.setattr(porto_api, "extractor", FakeExtractor(), raising=False)
    monkeypatch.setattr(porto_api, "store", FakeStore(), raising=False)
    return TestClient(porto_api.app)


def test_dashboard_is_available(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Dashboard despesas EHS 2026" in response.text


def test_photo_endpoint_rejects_pdfs_and_accepts_images(monkeypatch):
    client = make_client(monkeypatch)

    bad_response = client.post(
        "/expense/photo",
        files={"file": ("receipt.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert bad_response.status_code == 400

    good_response = client.post(
        "/expense/photo",
        files={"file": ("receipt.jpg", b"fake-image", "image/jpeg")},
        data={"hint": "café", "attachment_url": "https://storage.example/receipt.jpg"},
    )

    assert good_response.status_code == 200
    payload = good_response.json()
    assert payload["expense"]["attachment_url"] == "https://storage.example/receipt.jpg"
    assert payload["expense"]["amount_brl"] == 66.0


def test_auth_patch_delete_and_csv_flow(monkeypatch):
    client = make_client(monkeypatch, api_key="secret")
    headers = {"X-Porto2026-Key": "secret"}

    missing_key = client.post("/expense/text", json={"text": "Jantar no Porto 80 euros"})
    assert missing_key.status_code == 401

    created = client.post("/expense/text", headers=headers, json={"text": "Jantar no Porto 80 euros"})
    assert created.status_code == 200
    expense_id = created.json()["expense"]["expense_id"]
    assert created.json()["expense"]["amount_brl"] == 440.0

    updated = client.patch(
        f"/expense/{expense_id}",
        headers=headers,
        json={"amount_original": 100, "currency": "BRL", "description": "Jantar corrigido"},
    )
    assert updated.status_code == 200
    assert updated.json()["expense"]["amount_brl"] == 100.0
    assert updated.json()["expense"]["description"] == "Jantar corrigido"

    summary = client.get("/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["count"] == 1
    assert summary.json()["total_brl"] == 100.0

    expenses = client.get("/expenses?limit=10", headers=headers)
    assert expenses.status_code == 200
    assert len(expenses.json()) == 1

    csv_response = client.get("/export/csv", headers=headers)
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "Jantar corrigido" in csv_response.text

    deleted = client.delete(f"/expense/{expense_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    empty_summary = client.get("/summary", headers=headers)
    assert empty_summary.json()["count"] == 0


def test_audio_endpoint_stays_available(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post(
        "/expense/audio",
        files={"file": ("note.m4a", b"fake-audio", "audio/mp4")},
    )

    assert response.status_code == 200
    assert response.json()["transcript"] == "Táxi 12 euros"
