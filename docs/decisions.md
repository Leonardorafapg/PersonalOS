# Decisões de arquitetura

Registro curto do que foi decidido na implementação e por quê (a proposta original está na conversa de planejamento).

## Modelo

| Decisão | Motivo |
|---|---|
| `calendar_entries` única, com `mobility = fixed \| flexible` | Evento fixo e bloco planejado são o mesmo conceito com regras diferentes. Duas tabelas duplicariam checagem de conflito e UI. |
| `daily_plans` fina (`plan_date`, `summary`, `rationale`) | O conteúdo do dia já está nas entradas. Sem cópia = sem divergência. `rationale` dá memória ao Claude entre conversas. |
| `study_topics` única (áreas são raízes, `kind=area`) | Uma árvore, consultas recursivas simples. Progresso de nós pai é **calculado**, nunca armazenado. |
| `prerequisite_ids` e `resources` como JSON no tópico | Evita duas tabelas auxiliares; o snapshot de auditoria já cobre. Ciclos são validados no serviço. |
| `study_sessions` | Histórico do que foi realmente estudado (separado do progresso). Concluir um bloco de estudo gera a sessão. |
| `routines` (kind=`training`) | Template de cadência. As sessões concretas são entradas de agenda com `routine_id`; a cota semanal é calculada. |
| `routines.workouts` (JSON) | Plano de exercícios editável (vários treinos A/B/C, cada um com exercícios). Chaves estáveis por exercício. |
| `workout_sessions` | Registro do que foi feito em cada treino. Copia (snapshot) o plano na hora de começar, então editar o plano depois não reescreve o histórico. Cada exercício é `done = true / false / null`. |
| `tasks.do_date` ≠ `due_date` | "Quando pretendo fazer" vs "prazo". Os blocos de agenda são o horário real. Status `inbox` para captura rápida. |
| `user_preferences` | Fuso, horários, refeições, regras livres e contexto pessoal: o que o Claude precisa para planejar sem perguntar tudo de novo. |
| Ids públicos tipados (`t42`, `c7`, `s3`…) | Curtos (poucos tokens) e impedem usar o id de uma entidade onde cabe outra. No banco são `bigint`. |
| Recorrência = RRULE + exceções (linhas filhas) | Expansão na leitura, em hora local (19:00 continua 19:00). Cancelar/alterar uma ocorrência cria uma exceção. |

## Segurança e consistência

- Toda escrita roda em **uma transação** com o log de operações; `dry_run` faz rollback.
- `delete_*` é **soft delete**; `undo_operation` reverte lotes (checando `version` para não pisar em edições posteriores).
- Confirmação de destrutivos: um token no servidor não prova que o *humano* confirmou (quem o repassa é o Claude). As proteções reais são reversibilidade, anotações MCP (`destructiveHint`) e a regra de `confirm_fixed` + motivo, tudo auditado.
- O modo **estrito** (Claude/system) protege passado, conflitos e fixos; o modo **manual** (UI) só avisa.

## Limites conhecidos (v1)

- Offline: o PWA lê o último estado em cache; escrever exige internet.
- A recorrência não tem "esta e as próximas" (use editar a série ou criar uma nova a partir de uma data).
- Single-user na prática (um dono); o esquema já carrega `user_id`.
- Notificações, hábitos, metas e integração com calendários externos ficam para depois.
- O schema das tools ocupa ~30 KB (~8k tokens) no contexto do Claude. Se virar problema, podar descrições é a primeira alavanca.
- Testado com SQLite local; a migration e os tipos (`JSONB`, `timestamptz`, lock consultivo) foram escritos para PostgreSQL e **precisam do primeiro deploy para validação real**.
