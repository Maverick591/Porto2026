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
    @import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=Manrope:wght@400;500;700;800&display=swap");

    :root {
      --bg: #050b15;
      --panel: rgba(11, 24, 43, 0.9);
      --panel-strong: rgba(9, 18, 33, 0.96);
      --line: rgba(147, 197, 253, 0.18);
      --line-strong: rgba(255, 255, 255, 0.12);
      --text: #eaf2ff;
      --muted: #9badcb;
      --accent: #ffb703;
      --accent-2: #5eead4;
      --success: #34d399;
      --danger: #fb7185;
      color-scheme: dark;
    }

    body[data-theme="conservative"] {
      --bg: #071019;
      --panel: rgba(12, 21, 36, 0.92);
      --panel-strong: rgba(9, 16, 29, 0.96);
      --line: rgba(173, 188, 214, 0.14);
      --line-strong: rgba(255, 255, 255, 0.08);
      --text: #edf3fb;
      --muted: #a1afc5;
      --accent: #e2b14f;
      --accent-2: #7dd7cc;
      --success: #40c98a;
      --danger: #f27f91;
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: "Manrope", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(255, 183, 3, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(94, 234, 212, 0.12), transparent 24%),
        radial-gradient(circle at 20% 85%, rgba(52, 211, 153, 0.08), transparent 24%),
        linear-gradient(160deg, #07111d 0%, #102542 100%);
      min-height: 100vh;
      position: relative;
      overflow-x: hidden;
    }

    body[data-theme="conservative"] {
      background:
        radial-gradient(circle at top left, rgba(226, 177, 79, 0.12), transparent 26%),
        radial-gradient(circle at top right, rgba(125, 215, 204, 0.08), transparent 24%),
        linear-gradient(180deg, #08111a 0%, #0f1d31 100%);
    }

    body::before,
    body::after {
      content: "";
      position: fixed;
      pointer-events: none;
      z-index: -1;
      border-radius: 999px;
      filter: blur(24px);
      opacity: 0.75;
    }

    body::before {
      inset: -8rem auto auto -8rem;
      width: 28rem;
      height: 28rem;
      background: radial-gradient(circle, rgba(255, 183, 3, 0.18), transparent 68%);
    }

    body[data-theme="conservative"]::before {
      background: radial-gradient(circle, rgba(226, 177, 79, 0.12), transparent 68%);
    }

    body::after {
      inset: 10rem -6rem auto auto;
      width: 24rem;
      height: 24rem;
      background: radial-gradient(circle, rgba(94, 234, 212, 0.14), transparent 68%);
    }

    body[data-theme="conservative"]::after {
      background: radial-gradient(circle, rgba(125, 215, 204, 0.08), transparent 68%);
    }

    .wrap {
      width: min(1200px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 56px;
    }

    .hero {
      display: grid;
      gap: 16px;
      grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.85fr);
      align-items: stretch;
      margin-bottom: 24px;
    }

    .hero-card,
    .panel {
      position: relative;
      overflow: hidden;
      background: var(--panel);
      backdrop-filter: blur(16px);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
    }

    body[data-theme="conservative"] .hero-card,
    body[data-theme="conservative"] .panel {
      box-shadow: 0 18px 42px rgba(0, 0, 0, 0.22);
      border-radius: 22px;
    }

    .hero-card::before,
    .panel::before {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 38%);
      pointer-events: none;
    }

    body[data-theme="conservative"] .hero-card::before,
    body[data-theme="conservative"] .panel::before {
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), transparent 45%);
    }

    .hero-card {
      padding: 30px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 248px;
    }

    .meta {
      padding: 24px;
      display: grid;
      gap: 14px;
      align-content: start;
      background: linear-gradient(180deg, rgba(13, 29, 52, 0.95), rgba(9, 20, 38, 0.92));
    }

    body[data-theme="conservative"] .meta {
      background: linear-gradient(180deg, rgba(15, 26, 42, 0.96), rgba(8, 16, 28, 0.94));
    }

    h1 {
      margin: 14px 0 12px;
      font-size: clamp(2.3rem, 5vw, 4.3rem);
      line-height: 0.92;
      letter-spacing: -0.07em;
      font-weight: 800;
      max-width: 10ch;
    }

    body[data-theme="conservative"] h1 {
      max-width: 11ch;
      letter-spacing: -0.06em;
      font-size: clamp(2.1rem, 4.4vw, 3.8rem);
    }

    .lede {
      margin: 0;
      max-width: 62ch;
      color: var(--muted);
      font-size: 1.03rem;
      line-height: 1.7;
    }

    body[data-theme="conservative"] .lede {
      font-size: 1rem;
      line-height: 1.75;
    }

    .pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--line-strong);
      color: var(--text);
      font-size: 0.88rem;
      white-space: nowrap;
    }

    body[data-theme="conservative"] .pill {
      background: rgba(255, 255, 255, 0.035);
    }

    .field {
      display: grid;
      gap: 6px;
    }

    label {
      font-size: 0.86rem;
      letter-spacing: 0.01em;
      color: var(--muted);
    }

    input,
    textarea,
    button,
    select {
      font: inherit;
    }

    input,
    textarea {
      width: 100%;
      border: 1px solid rgba(255, 255, 255, 0.1);
      background: rgba(5, 12, 24, 0.92);
      color: var(--text);
      border-radius: 16px;
      padding: 14px 15px;
      outline: none;
      transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
    }

    input::placeholder,
    textarea::placeholder {
      color: rgba(149, 169, 199, 0.68);
    }

    input:focus,
    textarea:focus {
      border-color: rgba(94, 234, 212, 0.42);
      box-shadow: 0 0 0 4px rgba(94, 234, 212, 0.12);
      background: rgba(7, 15, 29, 0.98);
    }

    textarea {
      min-height: 120px;
      resize: vertical;
    }

    button {
      border: 0;
      border-radius: 16px;
      padding: 13px 18px;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: #09111f;
      background: linear-gradient(135deg, var(--accent), #ffd166);
      cursor: pointer;
      box-shadow: 0 12px 30px rgba(255, 183, 3, 0.18);
      transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
    }

    button:hover {
      transform: translateY(-1px);
      filter: brightness(1.03);
      box-shadow: 0 16px 34px rgba(255, 183, 3, 0.22);
    }

    button:active {
      transform: translateY(0);
    }

    button.secondary {
      color: var(--text);
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--line);
      box-shadow: none;
    }

    button.secondary:hover {
      background: rgba(255, 255, 255, 0.08);
    }

    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .segmented {
      display: inline-grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
      padding: 6px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--line);
    }

    .segmented button {
      padding: 10px 14px;
      border-radius: 12px;
      box-shadow: none;
      font-weight: 800;
      letter-spacing: -0.01em;
    }

    .segmented button.secondary {
      background: transparent;
      border-color: transparent;
      color: var(--muted);
    }

    .segmented button.secondary[data-active="true"] {
      background: linear-gradient(135deg, rgba(255, 183, 3, 0.95), rgba(255, 209, 102, 0.95));
      color: #09111f;
    }

    .status {
      color: var(--accent-2);
      font-size: 0.92rem;
      min-height: 1.5em;
    }

    .sync-state {
      padding: 13px 15px;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.09);
      background: linear-gradient(180deg, rgba(7, 15, 29, 0.92), rgba(2, 8, 20, 0.78));
      color: #d7e8ff;
      min-height: 3rem;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }

    .sync-state[data-tone="success"] {
      border-color: rgba(52, 211, 153, 0.42);
      color: #d9ffef;
      background: linear-gradient(180deg, rgba(7, 22, 18, 0.92), rgba(3, 11, 10, 0.82));
    }

    .sync-state[data-tone="error"] {
      border-color: rgba(251, 113, 133, 0.42);
      color: #ffe3e8;
      background: linear-gradient(180deg, rgba(39, 10, 17, 0.92), rgba(18, 4, 9, 0.82));
    }

    .grid {
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      align-items: start;
    }

    .panel {
      padding: 20px;
    }

    .summary {
      grid-column: span 12;
    }

    .summary-head {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .cards {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      margin-top: 14px;
    }

    .card {
      position: relative;
      overflow: hidden;
      padding: 16px;
      border-radius: 20px;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.03));
      border: 1px solid rgba(255, 255, 255, 0.09);
      min-height: 102px;
    }

    body[data-theme="conservative"] .card {
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
    }

    .card::after {
      content: "";
      position: absolute;
      inset: auto -20% -40% 55%;
      width: 120px;
      height: 120px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(94, 234, 212, 0.18), transparent 70%);
    }

    body[data-theme="conservative"] .card::after {
      background: radial-gradient(circle, rgba(125, 215, 204, 0.12), transparent 70%);
    }

    .card .k {
      display: block;
      color: var(--muted);
      font-size: 0.84rem;
      margin-bottom: 8px;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }

    .card .v {
      display: block;
      font-size: clamp(1.2rem, 2vw, 1.6rem);
      font-weight: 800;
      letter-spacing: -0.05em;
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, monospace;
    }

    body[data-theme="conservative"] .card .v {
      font-family: "Manrope", ui-sans-serif, system-ui, sans-serif;
    }

    .section-title {
      margin: 0 0 12px;
      font-size: 1.05rem;
      letter-spacing: -0.03em;
    }

    body[data-theme="conservative"] .section-title {
      font-size: 1rem;
      letter-spacing: -0.02em;
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
      align-content: start;
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
      border-collapse: separate;
      border-spacing: 0;
      overflow: hidden;
    }

    body[data-theme="conservative"] table {
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 18px;
    }

    thead th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: linear-gradient(180deg, rgba(10, 20, 37, 0.96), rgba(10, 20, 37, 0.88));
      backdrop-filter: blur(10px);
    }

    th,
    td {
      text-align: left;
      padding: 13px 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      vertical-align: top;
    }

    tbody tr {
      transition: background 0.18s ease;
    }

    tbody tr:hover {
      background: rgba(255, 255, 255, 0.03);
    }

    th {
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }

    body[data-theme="conservative"] th {
      font-size: 0.76rem;
    }

    .hint {
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.55;
    }

    .spacer {
      height: 2px;
    }

    @media (max-width: 980px) {
      .hero {
        grid-template-columns: 1fr;
      }

      .summary,
      .records,
      .forms,
      .side {
        grid-column: span 12;
      }

      .cards {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .hero-card {
        min-height: auto;
      }
    }

    @media (max-width: 640px) {
      .wrap {
        width: min(100% - 20px, 1200px);
      }

      .cards,
      .row {
        grid-template-columns: 1fr;
      }

      .panel,
      .hero-card {
        padding: 18px;
      }

      .actions button {
        flex: 1 1 100%;
      }

      h1 {
        max-width: none;
      }
    }
  </style>
</head>
<body data-theme="premium">
  <div class="wrap">
    <section class="hero">
      <div class="hero-card">
        <div class="pill-row">
          <span class="pill">Porto2026</span>
          <span class="pill">Google Sheets</span>
          <span class="pill">Texto, foto e áudio</span>
          <span class="pill">Chave protegida</span>
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
          <label for="apiKey">Senha de acesso</label>
          <input id="apiKey" type="password" placeholder="X-Porto2026-Key" autocomplete="off" />
        </div>
        <div class="field">
          <label>Estilo visual</label>
          <div class="segmented" role="tablist" aria-label="Estilo visual">
            <button id="themePremium" class="secondary" type="button" data-active="true">Premium</button>
            <button id="themeConservative" class="secondary" type="button">Conservador</button>
          </div>
        </div>
        <div class="actions">
          <button id="saveKey" class="secondary" type="button">Salvar chave</button>
          <button id="loadData" type="button">Carregar dados</button>
          <button id="exportCsv" class="secondary" type="button">Exportar CSV</button>
        </div>
        <div class="status" id="status">Insira a senha de acesso para sincronizar com o Google Sheets.</div>
        <div class="sync-state" id="syncState" data-tone="idle">Sincronização ainda não executada.</div>
      </div>
    </section>

    <section class="grid">
      <div class="panel summary">
        <div class="summary-head">
          <h2 class="section-title">Resumo</h2>
        </div>
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
            A dashboard usa <code>fetch</code> para enviar <code>X-Porto2026-Key</code> ao backend.
            A senha de acesso fica salva localmente no navegador.
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
    const storageTheme = "porto2026DashboardTheme";
    const apiKeyInput = document.getElementById("apiKey");
    const statusNode = document.getElementById("status");
    const syncStateNode = document.getElementById("syncState");
    const recordsBody = document.getElementById("recordsBody");
    const themePremiumButton = document.getElementById("themePremium");
    const themeConservativeButton = document.getElementById("themeConservative");
    const bodyNode = document.body;

    apiKeyInput.value = localStorage.getItem(storageKey) || "";

    function applyTheme(theme) {
      const normalized = theme === "conservative" ? "conservative" : "premium";
      bodyNode.dataset.theme = normalized;
      localStorage.setItem(storageTheme, normalized);
      themePremiumButton.dataset.active = String(normalized === "premium");
      themeConservativeButton.dataset.active = String(normalized === "conservative");
    }

    function activeKey() {
      return (apiKeyInput.value || localStorage.getItem(storageKey) || "").trim();
    }

    function apiHeaders(extra = {}) {
      const key = activeKey();
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
      syncStateNode.dataset.tone = message.includes("bem-sucedida")
        ? "success"
        : message.includes("não concluída")
          ? "error"
          : "idle";
    }

    function setStatus(message) {
      statusNode.textContent = message;
    }

    function clearEntryForms() {
      document.getElementById("textInput").value = "";
      document.getElementById("photoForm").reset();
      document.getElementById("audioForm").reset();
      document.getElementById("photoAttachmentUrl").value = "";
      document.getElementById("photoHint").value = "";
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
      const key = activeKey();
      if (!key) {
        setStatus("Insira a senha de acesso para carregar resumo e despesas.");
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
      const key = activeKey();
      if (!key) {
        setStatus("Insira a senha de acesso para exportar CSV.");
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
        clearEntryForms();
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
        clearEntryForms();
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
        clearEntryForms();
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
    themePremiumButton.addEventListener("click", () => applyTheme("premium"));
    themeConservativeButton.addEventListener("click", () => applyTheme("conservative"));
    applyTheme(localStorage.getItem(storageTheme) || "premium");
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
    except Exception as exc:
        transcript = f"Áudio sem transcrição: {file.filename or 'arquivo enviado'}"

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
