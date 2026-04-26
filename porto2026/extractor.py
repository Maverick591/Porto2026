from __future__ import annotations

import base64
import json
import tempfile
import os
from typing import Optional
from openai import OpenAI

from .config import settings
from .models import ParsedExpense


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
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY não configurada.")
        self.client = OpenAI(api_key=settings.openai_api_key)

    def parse_text(self, text: str) -> ParsedExpense:
        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        data = json.loads(response.choices[0].message.content or "{}")
        return ParsedExpense(**data)

    def parse_photo(self, file_bytes: bytes, mime_type: str, hint: Optional[str] = None) -> ParsedExpense:
        supported = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
        if mime_type not in supported:
            raise ValueError(f"Formato não suportado para foto/print: {mime_type}")

        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        prompt = "Extraia a despesa a partir desta foto ou print de comprovante."
        if hint:
            prompt += f"\nContexto adicional do usuário: {hint}"

        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        data = json.loads(response.choices[0].message.content or "{}")
        return ParsedExpense(**data)

    def transcribe_audio(self, file_bytes: bytes, filename: str = "audio.m4a") -> str:
        suffix = "." + filename.split(".")[-1] if "." in filename else ".m4a"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe",
                    file=audio_file,
                )
            return transcription.text
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
