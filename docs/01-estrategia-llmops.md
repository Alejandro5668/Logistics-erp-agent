# F-A2 — Estrategia de evaluación (LLMOps)

## KPIs

| KPI | Qué mide | Cómo se calcula |
|---|---|---|
| **Faithfulness** | Que la respuesta no invente nada que no esté soportado por el contexto recuperado (RAG) o el resultado de una tool. | Ragas, contra el contexto real devuelto por `RAG normativo` / `get_erp_data`. |
| **Answer Relevancy** | Que la respuesta conteste lo que se preguntó, no un tema adyacente. | Ragas. |
| **Context Precision / Recall** | Que el metadata filtering (`year: 2024`) esté trayendo los chunks correctos y no ruido de años anteriores. | Ragas, contra un set de preguntas con el chunk esperado etiquetado. |
| **Exactitud numérica financiera** | Que cualquier monto/discrepancia citado en la respuesta coincida *exactamente* con lo que devolvió `calculate_tax_discrepancy`/`get_erp_data` — no un número "parecido" generado por el LLM. | Comparación determinística string/float contra el valor real de la tool, no un juicio del LLM. Esta es la métrica que más importa para este dominio — una alucinación aquí es dinero mal ajustado en el ERP. |
| **Tasa de falsa aprobación** | Cuántos ajustes automáticos en el ERP resultan incorrectos tras revisión posterior. | Muestreo humano periódico sobre ajustes ya aplicados (ver Golden Dataset, `docs/04-incidentes-liderazgo.md`). Es el KPI de mayor severidad: un objetivo de negocio, no solo de calidad de texto. |
| **Tasa de escalación** | % de casos que el agente manda a revisión humana vs. resuelve solo. | Conteo sobre logs de producción. Ni 0% (no hay guardrail real) ni 100% (el agente no aporta nada) es saludable — se vigila la tendencia, no un número absoluto. |
| **Efectividad del guardrail** | % de intentos de fuga de PII/prompt injection correctamente bloqueados. | Suite de ataques conocidos (red-team set) corrida en cada release, no solo en producción. |
| **Latencia (p50/p95)** | Percepción de velocidad del usuario. | Tracing de producción (ver framework). |

## Framework

- **Ragas** — evaluación offline, batch, contra un **golden dataset** versionado (preguntas + contexto esperado + respuesta esperada + valores de tool esperados). Corre como *gate* en CI antes de cualquier cambio de prompt o de modelo — igual que un test suite, no un dashboard que se mira después.
- **Arize Phoenix** (o LangSmith, equivalente) — tracing en producción: cada ejecución del grafo LangGraph queda registrada (qué tool se llamó, con qué input/output, qué decidió el guardrail, cuánto tardó). Esto es lo que permite investigar un caso puntual reportado por un usuario y detectar drift de modelo (ver `docs/04-incidentes-liderazgo.md`).

## Por qué esto evita alucinar con datos financieros

La defensa real no es "pedirle al LLM que no invente" — es **nunca dejar que el LLM sea la fuente de un número**. Todo monto que aparece en la respuesta final debe poder trazarse a un valor literal devuelto por `get_erp_data` o `calculate_tax_discrepancy`; el LLM solo redacta la explicación alrededor de ese número, no lo calcula ni lo recuerda. El guardrail (F-B4) valida esta trazabilidad antes de dejar pasar cualquier ajuste automático — si un número en la respuesta no matchea ningún valor de tool, se bloquea y escala a humano en vez de aprobarse.

## Cadencia

1. **Pre-deploy (bloqueante):** Ragas contra el golden dataset en CI — cualquier caída de Faithfulness o exactitud numérica frena el merge.
2. **Producción (continuo):** tracing de cada request + muestreo periódico de ajustes auto-aprobados por un humano.
3. **Post-incidente:** cualquier caso de falsa aprobación se agrega al golden dataset como regresión permanente (ver Golden Dataset en `docs/04-incidentes-liderazgo.md`).
