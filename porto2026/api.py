from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .config import settings
from .extractor import ExpenseExtractor
from .models import Currency, ExpenseInput, ExpensePatch, ExpenseRecord, ParsedExpense
from .sheets import SheetsStore


app = FastAPI(
    title="Porto2026",
    version="1.2.0",
    description="Controle financeiro da viagem EHS Porto 2026.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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


def require_api_key(x_porto2026_key: str | None = Header(default=None, alias="X-Porto2026-Key")) -> None:
    if not settings.api_key:
        return
    if x_porto2026_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Chave de API inválida.")


def exchange_rate(currency: Currency) -> float:
    if currency == Currency.BRL:
        return 1.0
    return settings.default_eur_brl


def build_record(
    parsed: ParsedExpense,
    raw_text: str,
    source: str,
    attachment_url: str | None = None,
    expense_id: str | None = None,
    created_at: datetime | None = None,
) -> ExpenseRecord:
    tz = ZoneInfo(settings.timezone)
    rate = exchange_rate(parsed.currency)

    parsed_date = None
    if parsed.expense_date:
        try:
            parsed_date = date.fromisoformat(parsed.expense_date)
        except ValueError:
            parsed_date = None

    return ExpenseRecord(
        expense_id=expense_id or str(uuid4()),
        created_at=created_at or datetime.now(tz),
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
        attachment_url=attachment_url,
        source=source,  # type: ignore[arg-type]
        raw_text=raw_text,
        confidence=parsed.confidence,
        notes=parsed.notes,
    )


def apply_patch(existing: ExpenseRecord, patch: ExpensePatch) -> ExpenseRecord:
    data = existing.model_dump()
    updates = patch.model_dump(exclude_unset=True)
    data.update(updates)

    currency = data.get("currency", existing.currency)
    amount_original = float(data.get("amount_original", existing.amount_original))
    rate = exchange_rate(currency)
    data["exchange_rate_to_brl"] = rate
    data["amount_brl"] = round(amount_original * rate, 2)

    return ExpenseRecord(**data)


def dashboard_html() -> str:
    default_rate = f"{settings.default_eur_brl:.2f}"
    return (
        """
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dashboard despesas EHS 2026</title>
  <style>
    :root {
      --bg: #07111f;
      --panel: rgba(11, 24, 43, 0.88);
      --panel-strong: #0d1d34;
      --line: rgba(147, 197, 253, 0.18);
      --text: #e8f1ff;
      --muted: #95a9c7;
      --accent: #ffb703;
      --accent-2: #5eead4;
      --danger: #fb7185;
      color-scheme: dark;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(255, 183, 3, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(94, 234, 212, 0.12), transparent 24%),
        linear-gradient(160deg, #08111d 0%, #102542 100%);
      min-height: 100vh;
    }

    .wrap {
      width: min(1200px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }

    .hero {
      display: grid;
      gap: 16px;
      grid-template-columns: 1.5fr 1fr;
      align-items: start;
      margin-bottom: 24px;
    }

    .hero-card, .panel {
      background: var(--panel);
      backdrop-filter: blur(14px);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.24);
    }

    .hero-card {
      padding: 28px;
    }

    h1 {
      margin: 0 0 10px;
      font-size: clamp(2rem, 4vw, 3.6rem);
      line-height: 0.95;
      letter-spacing: -0.05em;
    }

    .lede {
      margin: 0;
      max-width: 62ch;
      color: var(--muted);
      font-size: 1.02rem;
      line-height: 1.6;
    }

    .pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--line);
      color: var(--text);
      font-size: 0.9rem;
    }

    .meta {
      padding: 24px;
      display: grid;
      gap: 14px;
    }

    .meta .field {
      display: grid;
      gap: 6px;
    }

    label {
      font-size: 0.88rem;
      color: var(--muted);
    }

    input, textarea, button, select {
      font: inherit;
    }

    input, textarea {
      width: 100%;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(7, 15, 29, 0.9);
      color: var(--text);
      border-radius: 14px;
      padding: 12px 14px;
      outline: none;
    }

    textarea { min-height: 104px; resize: vertical; }

    button {
      border: 0;
      border-radius: 14px;
      padding: 12px 16px;
      font-weight: 700;
      color: #09111f;
      background: linear-gradient(135deg, var(--accent), #ffd166);
      cursor: pointer;
    }

    button.secondary {
      color: var(--text);
      background: rgba(255,255,255,0.06);
      border: 1px solid var(--line);
    }

    .grid {
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(12, 1fr);
    }

    .panel {
      padding: 20px;
    }

    .summary {
      grid-column: span 12;
    }

    .cards {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      margin-top: 14px;
    }

    .card {
      padding: 16px;
      border-radius: 18px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.09);
    }

    .card .k {
      display: block;
      color: var(--muted);
      font-size: 0.86rem;
      margin-bottom: 6px;
    }

    .card .v {
      font-size: 1.45rem;
      font-weight: 800;
      letter-spacing: -0.03em;
    }

    .section-title {
      margin: 0 0 12px;
      font-size: 1.05rem;
    }

    .forms {
      grid-column: span 7;
      display: grid;
      gap: 16px;
    }

    .side {
      grid-column: span 5;
      display: grid;
      gap: 16px;
    }

    .stack {
      display: grid;
      gap: 12px;
    }

    .row {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .records {
      grid-column: span 12;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
    }

    th, td {
      text-align: left;
      padding: 12px 10px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      vertical-align: top;
    }

    th {
      color: var(--muted);
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .status {
      color: var(--accent-2);
      font-size: 0.92rem;
      min-height: 1.5em;
    }

    .sync-state {
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.09);
      background: rgba(2, 8, 20, 0.7);
      color: #d7e8ff;
      min-height: 3rem;
    }

    .hint {
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.5;
    }

    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .spacer { height: 2px; }

    @media (max-width: 980px) {
      .hero, .forms, .side, .summary, .records { grid-column: span 12; }
      .hero { grid-template-columns: 1fr; }
      .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .grid { grid-template-columns: 1fr; }
      .forms, .side { grid-column: auto; }
    }

    @media (max-width: 640px) {
      .wrap { width: min(100% - 20px, 1200px); }
      .cards, .row { grid-template-columns: 1fr; }
      .panel, .hero-card { padding: 18px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-card">
        <div class="pill-row">
          <span class="pill">Porto2026</span>
          <span class="pill">Google Sheets</span>
          <span class="pill">Auth via X-Porto2026-Key</span>
          <span class="pill">EUR/BRL @ __DEFAULT_RATE__</span>
        </div>
        <h1>Dashboard despesas EHS 2026</h1>
        <p class="lede">
          Registre despesas por texto, foto/print ou áudio, corrija lançamentos manualmente e exporte CSV sem sair desta tela.
          O envio de comprovantes aceita somente imagens; PDFs são rejeitados na API.
        </p>
        <div class="pill-row">
          <span class="pill">Texto, foto/print e áudio</span>
          <span class="pill">Edição e exclusão manual</span>
          <span class="pill">Resumo em tempo real</span>
          <span class="pill">Exportação CSV</span>
        </div>
      </div>
      <div class="hero-card meta">
        <div class="field">
          <label for="apiKey">API key</label>
          <input id="apiKey" type="password" placeholder="X-Porto2026-Key" autocomplete="off" />
        </div>
        <div class="actions">
          <button id="saveKey" class="secondary" type="button">Salvar chave</button>
          <button id="loadData" type="button">Carregar dados</button>
          <button id="exportCsv" class="secondary" type="button">Exportar CSV</button>
        </div>
        <div class="status" id="status">Insira a chave para sincronizar com o Google Sheets.</div>
        <div class="sync-state" id="syncState">Sincronização ainda não executada.</div>
      </div>
    </section>

    <section class="grid">
      <div class="panel summary">
        <h2 class="section-title">Resumo</h2>
        <div class="cards">
          <div class="card"><span class="k">Total BRL</span><span class="v" id="totalBrl">-</span></div>
          <div class="card"><span class="k">Equivalente EUR</span><span class="v" id="totalEur">-</span></div>
          <div class="card"><span class="k">Despesas</span><span class="v" id="count">-</span></div>
          <div class="card"><span class="k">Última atualização</span><span class="v" id="updatedAt">-</span></div>
        </div>
      </div>

      <div class="panel forms">
        <div class="stack">
          <h2 class="section-title">Lançamento por texto</h2>
          <form id="textForm" class="stack">
            <textarea id="textInput" placeholder="Ex.: Jantar no Porto 78 euros casal pago no cartão"></textarea>
            <button type="submit">Salvar despesa de texto</button>
          </form>
        </div>

        <div class="stack">
          <h2 class="section-title">Lançamento por foto/print</h2>
          <form id="photoForm" class="stack">
            <div class="row">
              <input id="photoFile" type="file" accept="image/*" />
              <input id="photoAttachmentUrl" type="url" placeholder="attachment_url opcional" />
            </div>
            <input id="photoHint" type="text" placeholder="Dica opcional do comprovante" />
            <button type="submit">Salvar foto/print</button>
          </form>
        </div>

        <div class="stack">
          <h2 class="section-title">Lançamento por áudio</h2>
          <form id="audioForm" class="stack">
            <input id="audioFile" type="file" accept="audio/*" />
            <button type="submit">Salvar áudio</button>
          </form>
        </div>
      </div>

      <div class="panel side">
        <div class="stack">
          <h2 class="section-title">Como funciona</h2>
          <p class="hint">
            A dashboard usa fetch para enviar `X-Porto2026-Key` ao backend.
            O resumo, as últimas despesas e o CSV dependem da chave salva localmente no navegador.
          </p>
        </div>
        <div class="stack">
          <h2 class="section-title">Regras principais</h2>
          <p class="hint">
            Somente imagens são aceitas em comprovantes. Todas as conversões usam a taxa padrão EUR/BRL configurada no ambiente.
          </p>
        </div>
      </div>

      <div class="panel records">
        <h2 class="section-title">Últimas despesas</h2>
        <div class="spacer"></div>
        <table>
          <thead>
            <tr>
              <th>Data</th>
              <th>Categoria</th>
              <th>Descrição</th>
              <th>Pessoa</th>
              <th>Moeda</th>
              <th>Total BRL</th>
            </tr>
          </thead>
          <tbody id="recordsBody">
            <tr><td colspan="6" class="hint">Carregue os dados para ver o histórico mais recente.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <script>
    const storageKey = "porto2026ApiKey";
    const apiKeyInput = document.getElementById("apiKey");
    const statusNode = document.getElementById("status");
    const syncStateNode = document.getElementById("syncState");
    const recordsBody = document.getElementById("recordsBody");

    apiKeyInput.value = localStorage.getItem(storageKey) || "";

    function apiHeaders(extra = {}) {
      const key = (apiKeyInput.value || "").trim() || localStorage.getItem(storageKey) || "";
      const headers = { ...extra };
      if (key) {
        headers["X-Porto2026-Key"] = key;
      }
      return headers;
    }

    function saveKey() {
      localStorage.setItem(storageKey, (apiKeyInput.value || "").trim());
      statusNode.textContent = "Chave salva no navegador.";
    }

    function setSyncState(message) {
      syncStateNode.textContent = message;
    }

    function setStatus(message) {
      statusNode.textContent = message;
    }

    function renderSummary(summary) {
      document.getElementById("totalBrl").textContent = Number(summary.total_brl || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
      document.getElementById("totalEur").textContent = Number(summary.total_eur_equivalent || 0).toLocaleString("pt-BR", { style: "currency", currency: "EUR" });
      document.getElementById("count").textContent = summary.count ?? 0;
      document.getElementById("updatedAt").textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    }

    function renderRecords(records) {
      if (!records.length) {
        recordsBody.innerHTML = '<tr><td colspan="6" class="hint">Nenhuma despesa encontrada.</td></tr>';
        return;
      }
      const escapeHtml = (value) => String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
      recordsBody.innerHTML = records.map((item) => `
        <tr>
          <td>${escapeHtml(item.expense_date || "")}</td>
          <td>${escapeHtml(item.category || "")}</td>
          <td>${escapeHtml(item.description || "")}</td>
          <td>${escapeHtml(item.person || "")}</td>
          <td>${escapeHtml(item.currency || "")}</td>
          <td>${Number(item.amount_brl || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}</td>
        </tr>
      `).join("");
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, {
        ...options,
        headers: {
          ...(options.headers || {}),
          ...apiHeaders(options.headers || {}),
        },
      });
      const text = await response.text();
      let body = text;
      try {
        body = text ? JSON.parse(text) : {};
      } catch (error) {
        // keep raw text
      }
      if (!response.ok) {
        const detail = typeof body === "object" ? JSON.stringify(body) : String(body);
        throw new Error(detail || `HTTP ${response.status}`);
      }
      return body;
    }

    async function loadData() {
      saveKey();
      const key = localStorage.getItem(storageKey) || "";
      if (!key) {
        setStatus("Insira a chave de API para carregar resumo e despesas.");
        return;
      }

      setStatus("Carregando dados do Sheets...");
      try {
        const [summary, expenses] = await Promise.all([
          fetchJson("/summary"),
          fetchJson("/expenses?limit=12"),
        ]);
        renderSummary(summary);
        renderRecords(expenses);
        setStatus("Dados sincronizados com sucesso.");
        setSyncState("Sincronização bem-sucedida.");
      } catch (error) {
        setStatus(error?.message ? `Falha ao carregar dados: ${error.message}` : "Falha ao carregar dados.");
        setSyncState("Sincronização não concluída.");
      }
    }

    async function exportCsv() {
      saveKey();
      const key = localStorage.getItem(storageKey) || "";
      if (!key) {
        setStatus("Insira a chave de API para exportar CSV.");
        return;
      }

      try {
        const response = await fetch("/export/csv", { headers: apiHeaders() });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "porto2026-despesas.csv";
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        setStatus("CSV exportado.");
        setSyncState("Sincronização bem-sucedida.");
      } catch (error) {
        setStatus(error?.message ? `Falha na exportação CSV: ${error.message}` : "Falha na exportação CSV.");
        setSyncState("Sincronização não concluída.");
      }
    }

    async function submitText(event) {
      event.preventDefault();
      saveKey();
      const text = document.getElementById("textInput").value.trim();
      if (!text) {
        setStatus("Digite um texto para salvar.");
        return;
      }
      try {
        const result = await fetchJson("/expense/text", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        setStatus("Despesa salva a partir do texto.");
        setSyncState("Sincronização bem-sucedida.");
        await loadData();
      } catch (error) {
        setStatus(error?.message ? `Erro ao salvar despesa de texto: ${error.message}` : "Erro ao salvar despesa de texto.");
        setSyncState("Sincronização não concluída.");
      }
    }

    async function submitPhoto(event) {
      event.preventDefault();
      saveKey();
      const file = document.getElementById("photoFile").files[0];
      if (!file) {
        setStatus("Escolha uma imagem para o comprovante.");
        return;
      }
      const formData = new FormData();
      formData.append("file", file);
      const hint = document.getElementById("photoHint").value.trim();
      const attachmentUrl = document.getElementById("photoAttachmentUrl").value.trim();
      if (hint) formData.append("hint", hint);
      if (attachmentUrl) formData.append("attachment_url", attachmentUrl);
      try {
        const result = await fetchJson("/expense/photo", {
          method: "POST",
          body: formData,
        });
        setStatus("Foto/print enviado com sucesso.");
        setSyncState("Sincronização bem-sucedida.");
        await loadData();
      } catch (error) {
        setStatus(error?.message ? `Erro ao salvar foto/print: ${error.message}` : "Erro ao salvar foto/print.");
        setSyncState("Sincronização não concluída.");
      }
    }

    async function submitAudio(event) {
      event.preventDefault();
      saveKey();
      const file = document.getElementById("audioFile").files[0];
      if (!file) {
        setStatus("Escolha um áudio para salvar.");
        return;
      }
      const formData = new FormData();
      formData.append("file", file);
      try {
        const result = await fetchJson("/expense/audio", {
          method: "POST",
          body: formData,
        });
        setStatus("Áudio enviado com sucesso.");
        setSyncState("Sincronização bem-sucedida.");
        await loadData();
      } catch (error) {
        setStatus(error?.message ? `Erro ao salvar áudio: ${error.message}` : "Erro ao salvar áudio.");
        setSyncState("Sincronização não concluída.");
      }
    }

    document.getElementById("saveKey").addEventListener("click", saveKey);
    document.getElementById("loadData").addEventListener("click", loadData);
    document.getElementById("exportCsv").addEventListener("click", exportCsv);
    document.getElementById("textForm").addEventListener("submit", submitText);
    document.getElementById("photoForm").addEventListener("submit", submitPhoto);
    document.getElementById("audioForm").addEventListener("submit", submitAudio);
  </script>
</body>
</html>
        """
    ).replace("__DEFAULT_RATE__", default_rate)


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(dashboard_html())


@app.get("/health")
def health():
    return {"ok": True, "skill": "Porto2026"}


@app.post("/expense/text", dependencies=[Depends(require_api_key)])
def create_expense_from_text(payload: ExpenseInput):
    try:
        parsed = get_extractor().parse_text(payload.text)
        record = build_record(parsed, raw_text=payload.text, source="text")
        get_store().append_expense(record)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao salvar despesa de texto: {exc}")
    return {"saved": True, "expense": record}


@app.post("/expense/photo", dependencies=[Depends(require_api_key)])
async def create_expense_from_photo(
    file: UploadFile = File(...),
    hint: str | None = Form(None),
    attachment_url: str | None = Form(None),
):
    mime_type = file.content_type or ""
    content = await file.read()

    if not mime_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Envie somente foto ou print em formato de imagem: jpg, png, webp, heic/heif.",
        )

    try:
        parsed = get_extractor().parse_photo(content, mime_type=mime_type, hint=hint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao salvar foto/print: {exc}")

    raw_text = f"Foto/print: {file.filename or ''}; dica={hint or ''}"
    record = build_record(
        parsed,
        raw_text=raw_text,
        source="photo",
        attachment_url=attachment_url,
    )
    get_store().append_expense(record)
    return {"saved": True, "expense": record}


@app.post("/expense/audio", dependencies=[Depends(require_api_key)])
async def create_expense_from_audio(file: UploadFile = File(...)):
    content = await file.read()
    try:
        transcript = get_extractor().transcribe_audio(content, filename=file.filename or "audio.m4a")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    try:
        parsed = get_extractor().parse_text(transcript)
        record = build_record(parsed, raw_text=transcript, source="audio")
        get_store().append_expense(record)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao salvar áudio: {exc}")
    return {"saved": True, "transcript": transcript, "expense": record}


@app.get("/expenses", dependencies=[Depends(require_api_key)])
def list_expenses(limit: int = Query(20, ge=1, le=200)):
    records = get_store().list_records()
    return records[-limit:]


@app.patch("/expense/{expense_id}", dependencies=[Depends(require_api_key)])
def update_expense(expense_id: str, payload: ExpensePatch):
    current = get_store().get_expense(expense_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Despesa não encontrada.")

    updated = apply_patch(current, payload)
    get_store().update_expense(updated)
    return {"updated": True, "expense": updated}


@app.delete("/expense/{expense_id}", dependencies=[Depends(require_api_key)])
def delete_expense(expense_id: str):
    try:
        deleted = get_store().delete_expense(expense_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": True, "expense": deleted}


@app.get("/export/csv", dependencies=[Depends(require_api_key)])
@app.get("/expenses.csv", dependencies=[Depends(require_api_key)])
def export_csv():
    csv_text = get_store().export_csv_text()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="porto2026-despesas.csv"'},
    )


@app.get("/summary", dependencies=[Depends(require_api_key)])
def get_summary():
    return get_store().refresh_summary()
