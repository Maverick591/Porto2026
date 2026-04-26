from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


class Currency(str, Enum):
    BRL = "BRL"
    EUR = "EUR"
    USD = "USD"


class ExpenseCategory(str, Enum):
    PASSAGENS = "Passagens"
    HOSPEDAGEM = "Hospedagem"
    CONGRESSO = "Congresso"
    CURSO = "Curso"
    ALIMENTACAO = "Alimentação"
    TRANSPORTE = "Transporte"
    PASSEIO = "Passeio"
    EXTRAS = "Extras"
    SEGURO = "Seguro"
    COMPRAS = "Compras"
    NAO_CLASSIFICADO = "Não classificado"


class ExpenseInput(BaseModel):
    text: str = Field(..., description="Texto livre descrevendo a despesa.")


class ParsedExpense(BaseModel):
    expense_date: Optional[str] = None
    category: ExpenseCategory = ExpenseCategory.NAO_CLASSIFICADO
    description: str
    merchant: Optional[str] = None
    person: str = "Casal"
    currency: Currency = Currency.EUR
    amount_original: float
    payment_method: Optional[str] = None
    status: str = "Realizado"
    confidence: float = 0.75
    notes: Optional[str] = None


class ExpenseRecord(BaseModel):
    expense_id: str
    created_at: datetime
    expense_date: Optional[date] = None
    category: ExpenseCategory
    description: str
    merchant: Optional[str] = None
    person: str = "Casal"
    currency: Currency
    amount_original: float
    exchange_rate_to_brl: float
    amount_brl: float
    payment_method: Optional[str] = None
    status: str = "Realizado"
    source: Literal["text", "photo", "audio"] = "text"
    raw_text: str
    confidence: float = 0.75
    notes: Optional[str] = None


class SummaryResponse(BaseModel):
    total_brl: float
    total_eur_equivalent: float
    by_category_brl: dict[str, float]
    by_person_brl: dict[str, float]
    count: int
