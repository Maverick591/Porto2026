# Tarefas para o Codex

## Objetivo
Evoluir o projeto Porto2026 para uma skill OpenClaw de controle financeiro da viagem EHS Porto 2026.

## Regras de produto
- Aceitar somente fotos/prints para comprovantes, não PDF.
- Manter endpoints:
  - POST /expense/text
  - POST /expense/photo
  - POST /expense/audio
  - GET /summary
- Salvar todos os registros em Google Sheets.
- Manter categorias em português.
- Sempre converter para BRL usando DEFAULT_EUR_BRL.
- Retornar JSON com o registro salvo.

## Melhorias sugeridas
1. Criar autenticação simples via API key no header X-Porto2026-Key.
2. Adicionar endpoint DELETE /expense/{expense_id}.
3. Adicionar endpoint PATCH /expense/{expense_id} para correção manual.
4. Adicionar campo attachment_url se OpenClaw salvar imagem em storage.
5. Criar dashboard web simples com FastAPI + HTML.
6. Adicionar importação/exportação CSV.
7. Adicionar integração com WhatsApp/Telegram caso o OpenClaw suporte canal.
