from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo
from uuid import uuid4

from fastapi import FastAPI, UploadFile, File, Form, HTTPException

from .config import settings
from .extractor import ExpenseExtractor
from .models import ExpenseInput, ExpenseRecord, ParsedExpense, Currency
from .sheets import SheetsStore


app = FastAPI(
    title="Porto2026",
    version="1.1.0",
    description="Controle financeiro da viagem EHS Porto 2026.",
)

extractor: ExpenseExtractor | None = None
store: SheetsStore | None = None


def get_extractor() -> ExpenseExtractor:
    global extractor
    if extractor is None:
        extractor = ExpenseExtractor()
    return extractor


def get_store() -> SheetsStore:
    global store
    if store is None:
        store = SheetsStore()
    return store


def exchange_rate(currency: Currency) -> float:
    if currency == Currency.BRL:
        return 1.0
    if currency == Currency.EUR:
        return settings.default_eur_brl
    if currency == Currency.USD:
        return settings.default_eur_brl * 0.92
    return settings.default_eur_brl


def build_record(parsed: ParsedExpense, raw_text: str, source: str) -> ExpenseRecord:
    tz = ZoneInfo(settings.timezone)
    rate = exchange_rate(parsed.currency)

    parsed_date = None
    if parsed.expense_date:
        try:
            parsed_date = date.fromisoformat(parsed.expense_date)
        except ValueError:
            parsed_date = None

    return ExpenseRecord(
        expense_id=str(uuid4()),
        created_at=datetime.now(tz),
        expense_date=parsed_date,
        category=parsed.category,
        description=parsed.description,
        merchant=parsed.merchant,
        person=parsed.person,
        currency=parsed.currency,
        amount_original=parsed.amount_original,
        exchange_rate_to_brl=rate,
        amount_brl=round(parsed.amount_original * rate, 2),
        payment_method=parsed.payment_method,
        status=parsed.status,
        source=source,  # type: ignore
        raw_text=raw_text,
        confidence=parsed.confidence,
        notes=parsed.notes,
    )


@app.get("/health")
def health():
    return {"ok": True, "skill": "Porto2026"}


@app.post("/expense/text")
def create_expense_from_text(payload: ExpenseInput):
    parsed = get_extractor().parse_text(payload.text)
    record = build_record(parsed, raw_text=payload.text, source="text")
    get_store().append_expense(record)
    return {"saved": True, "expense": record}


@app.post("/expense/photo")
async def create_expense_from_photo(
    file: UploadFile = File(...),
    hint: str | None = Form(None),
):
    content = await file.read()
    mime_type = file.content_type or "image/jpeg"

    if not mime_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Envie somente foto ou print em formato de imagem: jpg, png, webp, heic/heif.",
        )

    try:
        parsed = get_extractor().parse_photo(content, mime_type=mime_type, hint=hint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    raw_text = f"Foto/print: {file.filename}; dica={hint or ''}"
    record = build_record(parsed, raw_text=raw_text, source="photo")
    get_store().append_expense(record)
    return {"saved": True, "expense": record}


@app.post("/expense/audio")
async def create_expense_from_audio(file: UploadFile = File(...)):
    content = await file.read()
    transcript = get_extractor().transcribe_audio(content, filename=file.filename or "audio.m4a")
    parsed = get_extractor().parse_text(transcript)
    record = build_record(parsed, raw_text=transcript, source="audio")
    get_store().append_expense(record)
    return {"saved": True, "transcript": transcript, "expense": record}


@app.get("/summary")
def get_summary():
    return get_store().refresh_summary()
