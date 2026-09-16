# Logistics-erp-agent

Prototipo de agente autónomo (prueba técnica Senior AI Backend — Castor) que
concilia facturas de logística vs. ERP: recibe una consulta en lenguaje
natural, consulta datos ERP (mock), busca normativa en un PDF (RAG) y decide
entre notificar a un humano o generar un ajuste en el ERP.

Plan completo (alcance por parte, features, orden de trabajo) →
[`docs/00-planning.md`](docs/00-planning.md). Este archivo no lo duplica —
solo da el contexto y las herramientas que debe usar cualquier sesión que
trabaje aquí.

## Stack

| Capa | Elección |
|---|---|
| Orquestación | LangGraph (sobre LangChain) — ReAct + estado explícito |
| LLM | `BaseChatModel` de LangChain → Azure OpenAI (gpt-4o), model-agnostic |
| RAG | Chroma local + metadata filtering (`year`) |
| "SQL Server" mock | SQLite + SQLAlchemy, queries parametrizadas |
| API | FastAPI + `StreamingResponse` (SSE) |
| Seguridad | Middleware de rol + detección de fuga de PII/salarios |
| Infra | Bicep, Azure Container Apps + Azure OpenAI, VNet/Private Endpoint |
| Evaluación | Ragas (Faithfulness, Answer Relevancy) |

## Superficies sensibles (requieren más cuidado, no se recortan por lazy/YAGNI)

- Cualquier código que genere o apruebe un **ajuste en el ERP** (irreversible sobre datos financieros).
- Cualquier acceso a **datos de salario/PII** — deben pasar por el guardrail de rol (F-B4) antes de llegar al LLM o a la respuesta.

## Trabajo multi-sesión (mismo repo desde varias PCs)

- `git pull` antes de empezar a trabajar en cualquier feature.
- Cada feature de `docs/00-planning.md` vive en su propia rama
  (`feature/f-b1-erp-mock`, etc.) — evita que dos sesiones toquen los mismos
  archivos a la vez.
- Antes de `git push`: si hay commits nuevos en remoto sin overlap de
  archivos, rebase y push; si hay overlap, resolver el conflicto a mano, no
  forzar.

## Skills disponibles en este repo — cuándo usar cada una

| Skill | Úsala cuando... |
|---|---|
| `architecture-patterns` | Decidas cómo estructurar un módulo nuevo (`app/agent`, `app/tools`, `app/rag`, `app/security`, `app/api`) antes de escribir código. |
| `solid-principles` | Escribas cualquier clase o función con lógica no trivial (tools, nodos del grafo, middleware) — antes de comitear. |
| `fastapi-backend-architecture` | Construyas o modifiques `app/api/` (rutas, dependencias, streaming). |
| `api-contract-first` | Definas el contrato del endpoint (`request`/`response`, streaming shape) antes de implementarlo, no después. |
| `pytest` | Escribas tests para tools, agente o API — todo el Track B de código necesita al menos un test que falle si la lógica se rompe. |
| `azure-deploy` (Microsoft) | Trabajes en `infra/main.bicep` o el diseño de despliegue (F-A3) — VNet, Private Endpoint, Container Apps. |
| `diagram-design` | Generes el diagrama de arquitectura agéntica (F-A1) — Mermaid con nodos de decisión, memoria, guardrails. |
| `security-review` | Termines el guardrail de PII/prompt injection (F-B4), y antes de cualquier PR que toque datos sensibles o el ERP. |
| `cognitive-doc-design` | Escribas el README final o cualquier doc de entrega (F-A1, F-A2, F-A4). |
| `work-unit-commits` | Planees cómo dividir una feature en commits/PRs revisables. |
| `codegraph` (MCP) | Necesites entender código ya existente en el repo ("cómo funciona X", impacto de un cambio) — antes que grep/Read manual. |
| `ponytail` | Siempre, por defecto: código mínimo que resuelve el problema, sin abstracciones especulativas. |
| `engram` | Automática — memoria persistente entre sesiones, no requiere invocación manual. |

## Alcance de SDD

Solo Track B de `docs/00-planning.md` (agente, tools, RAG, API, guardrail de
seguridad) pasa por SDD completo (proposal → spec → design → tasks → apply).
Track A (documentación: arquitectura, LLMOps, Azure, incidentes) se entrega
directo, sin ceremonia de spec.

## Ramas y commits

Nada estricto ni ceremonioso — solo lo mínimo para que cualquiera (tú en otra
PC, o un evaluador leyendo el historial) entienda qué cambió y por qué sin
tener que preguntar.

**Ramas** — una por feature de `docs/00-planning.md`, nombrada
`<tipo>/<id-feature>-<slug-corto>`:
- `feature/f-b1-erp-mock`, `feature/f-a1-arquitectura`, `docs/f-a4-incidentes`
- `fix/<slug>` para arreglos que no pertenecen a una feature planeada.

**Commits** — [Conventional Commits](https://www.conventionalcommits.org/),
sin trailer de autoría de IA (nunca `Co-Authored-By: Claude` ni similar):
```
<tipo>(<alcance opcional>): <qué cambia, en imperativo>
```
- Tipos: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`.
- Un commit = un cambio lógico. No mezclar, por ejemplo, la tool `get_erp_data`
  con el middleware de seguridad en el mismo commit aunque se hayan hecho en
  la misma sesión.
- El mensaje dice **qué** cambia — el *por qué*, si no es obvio, va en el
  cuerpo del commit o en la descripción del PR, no en el asunto.

**Ejemplos de este repo:**
```
feat(agent): add get_erp_data mock tool
fix(rag): correct year metadata filter
docs: add architecture diagram
```
