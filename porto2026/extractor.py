from __future__ import annotations

import base64
import io
import json
import re
from typing import Optional
from openai import OpenAI

from .config import settings
from .models import Currency, ExpenseCategory, ParsedExpense


SYSTEM_PROMPT = """
Você é um extrator financeiro da viagem Porto 2026 / EHS.

Extraia UMA despesa por vez.

Responda exclusivamente em JSON válido, sem markdown, no formato:
{
  "expense_date": "YYYY-MM-DD ou null",
  "category": "Passagens|Hospedagem|Congresso|Curso|Alimentação|Transporte|Passeio|Extras|Seguro|Compras|Não classificado",
  "description": "descrição curta",
  "merchant": "fornecedor ou null",
  "person": "Jocielle|Solange|Casal|Outro",
  "currency": "EUR|BRL|USD",
  "amount_original": número,
  "payment_method": "Apple Pay|Cartão|Dinheiro|Pix|Outro|null",
  "status": "Realizado|Planejado|Estimado",
  "confidence": 0.0 a 1.0,
  "notes": "observações ou null"
}

Regras:
- Se aparecer €, Portugal, Porto, Douro, Uber/Bolt em Portugal, use EUR.
- Se aparecer R$, Brasil, LATAM, use BRL.
- Se for restaurante, almoço, jantar, café, mercado: Alimentação.
- Se for Uber, Bolt, táxi, metrô, trem local: Transporte.
- Se for Douro, vinícola, cruzeiro, passeio turístico: Passeio.
- Se for EHS, inscrição, congress, gala, welcome reception: Congresso.
- Se for curso pré-congresso, robótica, Hospital São João: Curso.
- Se a despesa beneficiar os dois, use person="Casal".
- Não invente valor. Se não identificar valor, use 0 e confidence baixo.
"""


class ExpenseExtractor:
    def __init__(self) -> None:
        if not settings.minimax_api_key:
            raise RuntimeError("MINIMAX_API_KEY não configurada.")
        self.client = OpenAI(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
        )
        self.fallback_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    @staticmethod
    def _parse_response_content(content: str | None) -> ParsedExpense:
        data = json.loads(content or "{}")
        return ParsedExpense(**data)

    def _chat_json(self, client: OpenAI, model: str, messages: list[dict[str, object]]) -> ParsedExpense:
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=messages,
        )
        return self._parse_response_content(response.choices[0].message.content)

    @staticmethod
    def _fallback_category(text: str) -> ExpenseCategory:
        normalized = text.lower()
        rules = [
            (ExpenseCategory.PASSAGENS, ("voo", "avião", "passagem", "trem", "comboio", "latam", "tap", "ryanair", "uber")),
            (ExpenseCategory.HOSPEDAGEM, ("hotel", "hosped", "airbnb", "hostel", "dorma", "essenzia", "alojamento")),
            (ExpenseCategory.CONGRESSO, ("ehs", "congresso", "conference", "inscri", "gala", "reception", "welcome")),
            (ExpenseCategory.CURSO, ("curso", "workshop", "pre-congresso", "pré-congresso", "robótica", "robotica")),
            (ExpenseCategory.ALIMENTACAO, ("jantar", "almoço", "almoco", "café", "cafe", "restaurante", "bar", "mercado", "lanche")),
            (ExpenseCategory.TRANSPORTE, ("metro", "metrô", "taxi", "táxi", "bolt", "uber", "bus", "ônibus", "autocarro")),
            (ExpenseCategory.PASSEIO, ("douro", "passeio", "tour", "vinícola", "vinicola", "cruzeiro", "city tour")),
            (ExpenseCategory.SEGURO, ("seguro",)),
            (ExpenseCategory.COMPRAS, ("compr", "loja", "shopping", "market", "mercad", "souvenir")),
        ]
        for category, keywords in rules:
            if any(keyword in normalized for keyword in keywords):
                return category
        return ExpenseCategory.NAO_CLASSIFICADO

    @staticmethod
    def _fallback_currency(text: str) -> Currency:
        normalized = text.lower()
        if "r$" in normalized or "real" in normalized or "reais" in normalized:
            return Currency.BRL
        if "$" in normalized or "usd" in normalized or "dólar" in normalized or "dolar" in normalized:
            return Currency.USD
        return Currency.EUR

    @staticmethod
    def _fallback_amount(text: str) -> float:
        normalized = text.replace("\u00a0", " ")
        matches = re.findall(r"(?<!\d)(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?!\d)", normalized)
        if not matches:
            return 0.0
        raw = matches[0].replace(".", "").replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return 0.0

    @staticmethod
    def _fallback_person(text: str) -> str:
        normalized = text.lower()
        if "casal" in normalized:
            return "Casal"
        if "jocielle" in normalized and "solange" in normalized:
            return "Jocielle/Solange"
        if "jocielle" in normalized:
            return "Jocielle"
        if "solange" in normalized:
            return "Solange"
        return "Outro"

    @staticmethod
    def _fallback_payment_method(text: str) -> Optional[str]:
        normalized = text.lower()
        if "apple pay" in normalized:
            return "Apple Pay"
        if "cartão" in normalized or "cartao" in normalized or "card" in normalized:
            return "Cartão"
        if "pix" in normalized:
            return "Pix"
        if "dinheiro" in normalized or "cash" in normalized:
            return "Dinheiro"
        return None

    @staticmethod
    def _fallback_description(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?\b", "", cleaned)
        cleaned = re.sub(r"\b(euros?|eur|r\$|reais?|usd|dólares?|dolares?)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;,")
        return cleaned or "Despesa sem descrição"

    def _fallback_parse_text(self, text: str) -> ParsedExpense:
        amount = self._fallback_amount(text)
        return ParsedExpense(
            expense_date=None,
            category=self._fallback_category(text),
            description=self._fallback_description(text),
            merchant=None,
            person=self._fallback_person(text),
            currency=self._fallback_currency(text),
            amount_original=amount,
            payment_method=self._fallback_payment_method(text),
            status="Realizado",
            confidence=0.35,
            notes="Fallback local usado porque a IA não respondeu.",
        )

    def parse_text(self, text: str) -> ParsedExpense:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        try:
            return self._chat_json(self.client, "MiniMax-M2.7", messages)
        except Exception:
            if self.fallback_client is None:
                return self._fallback_parse_text(text)
            try:
                return self._chat_json(self.fallback_client, "gpt-4o-mini", messages)
            except Exception:
                return self._fallback_parse_text(text)

    def parse_photo(self, file_bytes: bytes, mime_type: str, hint: Optional[str] = None) -> ParsedExpense:
        supported = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
        if mime_type not in supported:
            raise ValueError(f"Formato não suportado para foto/print: {mime_type}")

        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        prompt = "Extraia a despesa a partir desta foto ou print de comprovante."
        if hint:
            prompt += f"\nContexto adicional do usuário: {hint}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        try:
            return self._chat_json(self.client, "MiniMax-M2.7", messages)
        except Exception:
            if self.fallback_client is None:
                return self._fallback_parse_text(hint or "Comprovante em imagem")
            try:
                return self._chat_json(self.fallback_client, "gpt-4o-mini", messages)
            except Exception:
                return self._fallback_parse_text(hint or "Comprovante em imagem")

    def transcribe_audio(self, file_bytes: bytes, filename: str = "audio.m4a") -> str:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY não configurada.")

        audio_client = OpenAI(api_key=settings.openai_api_key)
        suffix = filename.split(".")[-1] if "." in filename else "m4a"
        buffer = io.BytesIO(file_bytes)
        buffer.name = filename if "." in filename else f"audio.{suffix}"  # type: ignore[attr-defined]
        transcription = audio_client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=buffer,
        )
        return transcription.text
