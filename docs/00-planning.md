# Planeación — Agente de Conciliación ERP/Logística

Prueba técnica: Senior AI Backend Engineer (Castor). Time-box: 48-72h.

## Contexto

La Empresa A necesita conciliar facturas de logística vs. su ERP mediante un
sistema de agentes autónomos: recibe una consulta en lenguaje natural, consulta
SQL, busca normativa en un PDF (RAG) y decide entre notificar a un humano o
generar un ajuste en el ERP.

## Alcance por parte (enunciado original)

1. **Diseño de arquitectura y estrategia de IA** — diagrama de flujo + KPIs de evaluación (LLMOps).
2. **Implementación técnica** — agente con function calling, RAG con metadata filtering, API FastAPI con streaming.
3. **Integración y seguridad enterprise** — guardrail de prompt injection/PII, diseño de despliegue Azure.
4. **Gestión de incidentes y liderazgo** — respuesta escrita a un escenario de drift de modelo y a una queja de latencia.

## Stack elegido

| Capa | Elección | Justificación |
|---|---|---|
| Orquestación | `create_agent` de LangChain (API de alto nivel construida sobre LangGraph) | Da ReAct + tool-calling + checkpointer (memoria) + streaming de fábrica. Sigue siendo LangGraph por debajo — cumple "razonamiento iterativo y manejo de estados" sin reimplementar un `StateGraph` a mano. |
| LLM | `BaseChatModel` de LangChain apuntando a Azure OpenAI (gpt-4o) | Model-agnostic: el agente no queda acoplado a un proveedor; calza con el despliegue Azure de la Parte 3. |
| RAG / vectorstore | Chroma local + metadata filtering (`year: 2024`) | Simple de levantar, cumple el requisito explícito de filtrar por metadata. |
| "SQL Server" mock | SQLite vía SQLAlchemy, queries parametrizadas | El enunciado permite mock, pero la rúbrica penaliza SQL no parametrizado incluso simulado. |
| API | FastAPI + `StreamingResponse` (SSE) | Streaming de tokens pedido explícitamente. |
| Seguridad | Middleware de rol + detección de intento de fuga de PII/salarios | Parte 3.1. |
| Infra | Bicep (nativo Azure, más simple que Terraform para Container Apps) con VNet integration / Private Endpoint | Parte 3.2 — tráfico no sale de la red privada. |
| Evaluación LLMOps | Script con Ragas (Faithfulness, Answer Relevancy) | Parte 1.2. |

## Alcance de SDD

SDD (proposal → spec → design → tasks → apply) solo donde hay ambigüedad de
diseño real. Documento directo donde el entregable es texto/explicación.

## Desglose por features

Cada feature es una unidad de trabajo independiente: archivos propios, sin
pisar el trabajo de otra feature, para poder trabajarlas en paralelo desde
distintas sesiones/PCs sin conflictos de merge.

### Track A — Documentación (sin dependencias de código, 100% paralelizable)

| Feature | Entregable | Ruta | Depende de |
|---|---|---|---|
| **F-A1** Arquitectura agéntica | Diagrama Mermaid + guardrails + memoria de sesión | `docs/01-arquitectura-agentica.md` | — |
| **F-A2** Estrategia LLMOps | KPIs (Faithfulness, Answer Relevance) + framework (Ragas/Phoenix) | `docs/01-estrategia-llmops.md` | — |
| **F-A3** Despliegue Azure | Diseño + script Bicep, VNet/Private Endpoint | `docs/03-despliegue-azure.md`, `infra/main.bicep` | — |
| **F-A4** Incidentes y liderazgo | Respuesta escrita drift de modelo + latencia | `docs/04-incidentes-liderazgo.md` | — |

### Track B — Código core (SDD), con dependencias internas

| Feature | Entregable | Ruta | Depende de |
|---|---|---|---|
| **F-B1** Mock ERP data layer | `get_erp_data(order_id)` sobre SQLite/SQLAlchemy, queries parametrizadas | `app/tools/erp_data.py` | — |
| **F-B2** Lógica de discrepancia fiscal | `calculate_tax_discrepancy(amount, region)` | `app/tools/tax_discrepancy.py` | — |
| **F-B3** Pipeline RAG | Índice Chroma + ingesta + metadata filtering (`year`) | `app/rag/` | — |
| **F-B4** Guardrail de seguridad | Middleware de `create_agent` (hook antes/después del modelo) que detecta PII/salarios por rol | `app/security/` | — |
| **F-B5** Agente core | `create_agent` + tools (incl. `create_erp_adjustment`/`notify_human` — el agente decide cuál llamar vía ReAct, no un edge condicional) + checkpointer para memoria de sesión | `app/agent/` | F-B1, F-B2, F-B3 |
| **F-B6** API FastAPI | Endpoint streaming, manejo de errores LLM/ERP caído, integra F-B4 | `app/api/` | F-B5, F-B4 |

> Decisión "ajuste automático vs. notificar humano": no es un nodo/edge de grafo
> custom — son dos tools más (`create_erp_adjustment`, `notify_human`) que el
> agente elige vía su propio ReAct loop, igual que las demás tools. Evita
> reconstruir en un `StateGraph` a mano lo que `create_agent` ya resuelve
> (ver `docs/01-arquitectura-agentica.md`, actualizado tras revisar la
> documentación oficial de LangChain/LangGraph).

**F-B1, F-B2, F-B3, F-B4 no dependen entre sí** → 4 sesiones distintas pueden
tomarlas en paralelo de inmediato. F-B5 es el punto de integración (requiere
que B1-B3 estén listas). F-B6 cierra al final.

## Orden de trabajo sugerido (paralelo)

```
Sesión 1: F-A1 → F-A2 → F-A4         (documentación, sin bloqueos)
Sesión 2: F-A3                        (Azure/Bicep, sin bloqueos)
Sesión 3: F-B1 → F-B2                 (tools, sin bloqueos)
Sesión 4: F-B3                        (RAG, sin bloqueos)
Sesión 5: F-B4                        (seguridad, sin bloqueos)
   ↓ (cuando B1+B2+B3 estén mergeadas)
   F-B5 (agente/LangGraph, integra tools + RAG)
   ↓
   F-B6 (API, integra agente + guardrail F-B4)
```

Cada feature = 1 rama (`feature/f-b1-erp-mock`, etc.) + 1 PR propio. Evita que
una sesión toque archivos de otra feature.

## Checklist de entrega final

- [ ] F-A1, F-A2, F-A3, F-A4 (docs)
- [ ] F-B1, F-B2, F-B3, F-B4, F-B5, F-B6 (código)
- [ ] `README.md` con instrucciones de arranque
- [ ] `requirements.txt`
- [ ] Video de 5 min (cara visible, decisiones de diseño + demo)
