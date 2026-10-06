# Personal OS

Seu sistema pessoal de **agenda, tarefas, projetos, estudos e treinos**, pensado para o celular (PWA) e **operado pelo Claude** via MCP.

```
        você ──────────────┐                         ┌────────────── Claude (desktop / mobile)
   (PWA, Next.js)          │                         │  conector MCP (OAuth, não expira)
                           ▼                         ▼
                  ┌──────────────────────── FastAPI ────────────────────────┐
                  │  REST (/tasks, /schedule…)        MCP (/mcp, 18 tools)  │
                  │          └──────── mesma camada de serviços ───────┘    │
                  │  regras: conflitos · evento fixo · passado · versões    │
                  │  auditoria + desfazer em toda escrita                   │
                  └──────────────────────────┬──────────────────────────────┘
                                             ▼
                                    PostgreSQL (fonte de verdade)
```

| Camada | Responsabilidade |
|---|---|
| **PostgreSQL** | Estado: tarefas, eventos, estudos, projetos, treinos, histórico de operações. |
| **FastAPI** | Regras: validação, conflitos de horário, proteção de eventos fixos, integridade, permissões. Nunca decide *o que fazer*. |
| **Claude** | Inteligência: prioriza, encaixa, replaneja, escolhe o que estudar. |

## Estrutura

```
apps/
  api/                       FastAPI + SQLAlchemy 2 + Alembic
    app/core/                config, db, ctx, runner, segurança, erros, ids
    app/domains/             um pacote por domínio (models · service · schemas)
      identity/ tasks/ projects/ calendar/ planning/ study/ routines/ audit/ overview/
    app/mcp/                 servidor MCP (tools, instruções, auth) – adaptador fino
    app/api/                 REST para o app + OAuth para o conector do Claude
    alembic/                 migrations
    tests/                   34 testes (REST + MCP via HTTP + OAuth)
  web/                       Next.js 16 · TypeScript · Tailwind 4 · PWA
scripts/                     seed_demo.py · mcp_smoke.py · make_icons.py
```

## Rodando localmente

Pré-requisitos: Python 3.12+ e Node 22+. Sem Docker nem Postgres: em desenvolvimento a API usa SQLite.

```bash
# 1) API  (http://localhost:8000)
cd apps/api
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt      # Linux/Mac: .venv/bin/pip
cp .env.example .env                                   # ajuste ADMIN_EMAIL / ADMIN_PASSWORD
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# 2) Web  (http://localhost:3000)
cd apps/web
npm install
npm run dev
```

A conta única é criada no primeiro boot com `ADMIN_EMAIL` / `ADMIN_PASSWORD`. Dados de exemplo (opcional):

```bash
apps/api/.venv/Scripts/python scripts/seed_demo.py http://localhost:8000 seu@email.com suasenha
```

Testes: `cd apps/api && .venv/Scripts/python -m pytest -q`

## Deploy no Railway

Crie um projeto com **3 serviços**: Postgres, `api` e `web`.

**1. Postgres**: *New → Database → PostgreSQL*.

**2. Serviço `api`**: *New → GitHub Repo*, **Root Directory = `apps/api`** (usa o `Dockerfile`; as migrations rodam a cada boot).

| Variável | Valor |
|---|---|
| `DATABASE_URL` | referência ao Postgres (`${{Postgres.DATABASE_URL}}`) |
| `JWT_SECRET` | string aleatória longa (`python -c "import secrets;print(secrets.token_urlsafe(48))"`) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | sua conta (criada no primeiro boot) |
| `ENVIRONMENT` | `production` (cookie `Secure`; exige `ADMIN_PASSWORD`) |
| `PORT` | `8000` (para a rede privada) |
| `PUBLIC_URL` | URL pública do serviço `api`, ex.: `https://personal-os-api.up.railway.app` (*Settings → Networking → Generate Domain*) |

**3. Serviço `web`**: mesmo repositório, **Root Directory = `apps/web`**.

| Variável | Valor |
|---|---|
| `API_URL` | `http://api.railway.internal:8000` (troque `api` pelo nome do serviço). É lida **no build**: se mudar, faça redeploy. |

Gere um domínio público para o `web`: é o endereço do app que você instala no celular.

## Conectar o Claude (Claude Desktop)

O Claude chama o app por um **conector MCP remoto**, então a URL precisa ser HTTPS pública (o serviço `api` no Railway).

1. *Claude Desktop → Configurações → Conectores → Adicionar conector personalizado*.
2. URL: `https://<seu-api>.up.railway.app/mcp` (também aparece em *Configurações* do app).
3. Uma janela abre pedindo e-mail e senha do Personal OS. Autorize.
4. Pronto. Teste: *"o que eu tenho hoje?"*, *"organiza meu dia de amanhã"*.

O token emitido **não expira**. Para cortar o acesso: app → *Configurações → Revogar acessos* (ou troque a senha).

> **Testar já na sua máquina**, antes do deploy, com um proxy local: em `claude_desktop_config.json`
> ```json
> { "mcpServers": { "personal-os": {
>     "command": "npx",
>     "args": ["-y", "mcp-remote", "http://localhost:8000/mcp",
>              "--header", "Authorization: Bearer SEU_TOKEN"] } } }
> ```
> `SEU_TOKEN` = campo `token` da resposta de `POST /auth/login`.

## As 18 tools MCP

| Leitura | |
|---|---|
| `get_context` | Primeira chamada de toda conversa: hora/fuso, preferências, hoje (com janelas livres), tarefas atrasadas, inbox, projetos, treinos com cota semanal, estudos disponíveis, próximos eventos fixos e o que *você* mudou à mão nas últimas 24h. |
| `get_schedule` | Entradas por dia (fixas + flexíveis, recorrências expandidas), plano do dia, **janelas livres calculadas**, sobreposições, estatísticas. |
| `list_tasks` | Filtros por status, projeto, prazo, `do_date`, texto, ids. Cada tarefa traz projeto, atraso e blocos agendados. |
| `get_projects` | Lista com contagens e última atividade, ou um projeto com suas tarefas. |
| `get_study` | Árvore do roadmap com progresso agregado, minutos, pré-requisitos pendentes; ou só os tópicos **disponíveis**. |
| `get_routines` | Treinos com cota semanal, **plano de exercícios** (séries, reps, carga, descanso) e últimas sessões (quantos exercícios foram feitos / não feitos). |
| `get_operation_log` | Trilha de auditoria agrupada por lote (inclui tentativas recusadas). |

| Escrita | Todas aceitam `dry_run` e devolvem o estado novo + `meta.batch_id` |
|---|---|
| `save_tasks` | Cria/edita/conclui/move tarefas em lote atômico (upsert; `client_ref` = idempotência). |
| `save_calendar_entries` | Eventos fixos e blocos flexíveis, recorrência (RRULE), ocorrência única (`scope=this`). |
| `set_day_plan` | **Declarativo**: "o dia deve conter estes blocos". Calcula o diff, valida conflitos e aplica. Idempotente. |
| `save_routines` | Treinos e seus exercícios (`workouts`: Treino A/B/C, cada um com sua lista). As chaves dos exercícios são estáveis, então editar o plano preserva o histórico. |
| `log_workout` | Registra uma sessão: cada exercício **feito / não feito / pendente**, o que foi realmente executado, exercícios extras, esforço, duração. `finished=true` marca pendentes como "não feito" e conclui o evento da agenda. |
| `save_projects` · `save_preferences` | Cadastros. |
| `save_study_topics` | Importa o roadmap inteiro em uma chamada (`children` aninhados, pré-requisitos, `client_ref`). |
| `log_study` | Registra sessão real e atualiza progresso; concluir um bloco de estudo também registra. |
| `delete_entity` | Exclusão **lógica** (recuperável). |
| `undo_operation` | Reverte um lote inteiro (falha com segurança se algo mudou depois). |

### Garantias do backend

- **Evento fixo ≠ bloco flexível** (`mobility`). O Claude só altera/exclui um evento fixo com `confirm_fixed=true` + motivo, e só se você pediu na conversa. Nada é movido automaticamente.
- **Conflitos**: bloco × fixo, bloco × bloco e fixo × fixo são recusados (`CONFLICT_*`) com os conflitos e as janelas livres sugeridas. A validação olha o **estado final** do lote (trocar dois blocos funciona). Na UI, sobreposição só gera aviso.
- **Passado protegido**: não se planeja no passado. Para registrar algo que já aconteceu, crie com `status: done|skipped`.
- **Concorrência otimista**: toda entidade tem `version`; atualizar com versão velha dá `STALE_VERSION` (você editou na UI enquanto o Claude trabalhava).
- **Transação por chamada**, lock por usuário no Postgres, `dry_run`, erros estruturados e acionáveis.
- **Auditoria**: cada mudança registra operação, quando, ator (`manual`/`claude`/`system`), canal, entidade e antes/depois. A tela **Atividade** mostra tudo e permite desfazer.
- **Autenticação**: JWT sem expiração, revogável (`token_version`); cookie `httpOnly` no app; OAuth 2.1 + PKCE para o conector; limite de tentativas de login.

## Evolução (sem refazer)

Já previsto no modelo: `user_id` em tudo; `routine.kind` (hoje `training`, amanhã hábitos); `created_by`/`updated_by` e log de operações (base para histórico de produtividade); `user_preferences.context_notes` (embrião de memória pessoal); `daily_plan.rationale` (continuidade entre conversas). Novas tools entram como adaptadores finos sobre `app/domains/*/service.py`.

Veja também [`docs/decisions.md`](docs/decisions.md).
