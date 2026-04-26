# Porto2026

Skill/API para registrar despesas da viagem EHS Porto 2026.

Funcionalidades principais:
- texto livre
- fotos/prints de comprovantes
- áudio
- resumo em tempo real no Google Sheets
- autenticação por API key
- correção manual com `PATCH`
- exclusão com `DELETE`
- dashboard web simples
- exportação CSV

## Regras de produto

- Aceita somente fotos/prints em `POST /expense/photo`; PDFs são rejeitados.
- Mantém os endpoints principais:
  - `POST /expense/text`
  - `POST /expense/photo`
  - `POST /expense/audio`
  - `GET /summary`
- Salva todos os registros em Google Sheets.
- Mantém categorias em português.
- Converte para BRL usando `DEFAULT_EUR_BRL`.
- Retorna JSON com o registro salvo nas rotas de criação.

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example Porto2026.env
uvicorn porto2026.api:app --reload --port 8000
```

## Variáveis de ambiente

```env
OPENAI_API_KEY=
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimaxi.com/v1
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=./service-account.json
DEFAULT_EUR_BRL=5.50
TIMEZONE=America/Sao_Paulo
PORTO2026_API_KEY=
```

## Dashboard

Abra:

```bash
http://localhost:8000/dashboard
```

A tela permite:
- enviar despesas por texto, foto/print ou áudio
- carregar resumo e últimas despesas
- exportar CSV

## Endpoints

### Texto

```bash
curl -X POST http://localhost:8000/expense/text \
  -H "Content-Type: application/json" \
  -H "X-Porto2026-Key: SUA_CHAVE" \
  -d '{"text":"Jantar no Porto 78 euros casal pago no cartão"}'
```

### Foto/print

```bash
curl -X POST http://localhost:8000/expense/photo \
  -H "X-Porto2026-Key: SUA_CHAVE" \
  -F "file=@recibo.jpg" \
  -F "hint=Jantar no Porto" \
  -F "attachment_url=https://storage.exemplo/recibo.jpg"
```

### Áudio

```bash
curl -X POST http://localhost:8000/expense/audio \
  -H "X-Porto2026-Key: SUA_CHAVE" \
  -F "file=@audio.m4a"
```

### Resumo

```bash
curl -H "X-Porto2026-Key: SUA_CHAVE" http://localhost:8000/summary
```

### Edição manual

```bash
curl -X PATCH http://localhost:8000/expense/ID_DA_DESPESA \
  -H "Content-Type: application/json" \
  -H "X-Porto2026-Key: SUA_CHAVE" \
  -d '{"description":"Correção manual","amount_original":100,"currency":"BRL"}'
```

### Exclusão

```bash
curl -X DELETE http://localhost:8000/expense/ID_DA_DESPESA \
  -H "X-Porto2026-Key: SUA_CHAVE"
```

### Exportação CSV

```bash
curl -L -H "X-Porto2026-Key: SUA_CHAVE" \
  http://localhost:8000/export/csv \
  -o porto2026-despesas.csv
```

### Listagem das últimas despesas

```bash
curl -H "X-Porto2026-Key: SUA_CHAVE" http://localhost:8000/expenses?limit=10
```

## Seed inicial

```bash
python -m porto2026.seed_budget
```

## GitHub

```bash
git init
git add .
git commit -m "Initial Porto2026 expense tracker"
git branch -M main
git remote add origin git@github.com:SEU_USUARIO/Porto2026.git
git push -u origin main
```
