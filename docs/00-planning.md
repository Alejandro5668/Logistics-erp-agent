# Planeación — Agente de Conciliación ERP/Logística

Prueba técnica: Senior AI Backend Engineer (Castor). Time-box: 48-72h.

## Contexto

La Empresa A necesita conciliar facturas de logística vs. su ERP mediante un
sistema de agentes autónomos: recibe una consulta en lenguaje natural, consulta
SQL, busca normativa en un PDF (RAG) y decide entre notificar a un humano o
generar un ajuste en el ERP.

## Alcance por parte (del enunciado original)

1. **Diseño de arquitectura y estrategia de IA** — diagrama de flujo + KPIs de evaluación (LLMOps).
2. **Implementación técnica** — agente con function calling, RAG con metadata filtering, API FastAPI con streaming.
3. **Integración y seguridad enterprise** — guardrail de prompt injection/PII, diseño de despliegue Azure.
4. **Gestión de incidentes y liderazgo** — respuesta escrita a un escenario de drift de modelo y a una queja de latencia.

## Stack elegido

| Capa | Elección | Justificación |
|---|---|---|
| Orquestación | LangGraph (sobre LangChain) | La rúbrica exige razonamiento iterativo (ReAct) y manejo de estados explícito, no un prompt lineal. |
| LLM | `BaseChatModel` de LangChain apuntando a Azure OpenAI (gpt-4o) | Model-agnostic: el agente no queda acoplado a un proveedor; calza con el despliegue Azure de la Parte 3. |
| RAG / vectorstore | Chroma local + metadata filtering (`year: 2024`) | Simple de levantar, cumple el requisito explícito de filtrar por metadata. |
| "SQL Server" mock | SQLite vía SQLAlchemy, queries parametrizadas | El enunciado permite mock, pero la rúbrica penaliza SQL no parametrizado incluso simulado. |
| API | FastAPI + `StreamingResponse` (SSE) | Streaming de tokens pedido explícitamente. |
| Seguridad | Middleware de rol + detección de intento de fuga de PII/salarios | Parte 3.1. |
| Infra | Bicep (nativo Azure, más simple que Terraform para Container Apps) con VNet integration / Private Endpoint | Parte 3.2 — tráfico no sale de la red privada. |
| Evaluación LLMOps | Script con Ragas (Faithfulness, Answer Relevancy) | Parte 1.2. |

## Alcance de SDD (Spec-Driven Development)

No todas las partes ameritan el mismo tratamiento — se reserva SDD (proposal →
spec → design → tasks) solo donde hay ambigüedad de diseño real a resolver
antes de codear:

- **Parte 1** (diagrama + estrategia LLMOps) → documento directo, sin spec/tasks.
- **Parte 2** (agente + tools + RAG + API) → **vía SDD** — es el core con decisiones de arquitectura.
- **Parte 3.1** (middleware de seguridad) → **vía SDD** — lógica no trivial.
- **Parte 3.2** (script Bicep + explicación) → documento/script directo.
- **Parte 4** (incidentes/liderazgo) → documento directo, es una respuesta escrita.

## Estructura del repo

```
Logistics-erp-agent/
  docs/
    00-planning.md            (este archivo)
    01-arquitectura-agentica.md  (diagrama Mermaid + guardrails + memoria)
    01-estrategia-llmops.md      (KPIs, Ragas/Phoenix)
    03-despliegue-azure.md       (+ infra/main.bicep)
    04-incidentes-liderazgo.md
  app/
    agent/        (grafo LangGraph)
    tools/         (get_erp_data, calculate_tax_discrepancy)
    rag/           (índice Chroma + metadata filter)
    security/      (middleware PII/rol)
    api/           (FastAPI)
  infra/
    main.bicep
  tests/
  README.md
```

## Orden de trabajo propuesto

1. Parte 1 — diagrama + estrategia LLMOps (documento).
2. Parte 2 — agente + tools + RAG + API (SDD: propuesta → spec → design → tasks → apply).
3. Parte 3.1 — middleware de seguridad (SDD).
4. Parte 3.2 — despliegue Azure (documento + script Bicep).
5. Parte 4 — incidentes/liderazgo (documento).
6. README final + video de 5 min.
