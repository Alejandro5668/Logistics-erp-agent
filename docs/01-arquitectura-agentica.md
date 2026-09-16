# F-A1 — Arquitectura agéntica

Diagrama: [`assets/arquitectura-agentica.html`](assets/arquitectura-agentica.html) (ábrelo en el navegador).

## Flujo

1. **Usuario** envía un prompt en lenguaje natural (ej: "¿Por qué hay una discrepancia en el envío #4402?").
2. **Orquestador ReAct** (LangGraph) razona en bucle: decide qué herramienta llamar, la ejecuta, evalúa el resultado, y repite hasta tener suficiente información — no es un prompt lineal de un solo paso.
3. Herramientas disponibles para el orquestador:
   - **ERP Data (mock)** — `get_erp_data(order_id)`, consulta parametrizada contra SQLite.
   - **Discrepancia fiscal** — `calculate_tax_discrepancy(amount, region)`, lógica de negocio en Python.
   - **RAG normativo** — busca en el manual PDF de normativas, con *metadata filtering* (`year: 2024`) para no traer ruido de años anteriores.
4. Con el resultado combinado, el orquestador redacta una respuesta/acción propuesta y la pasa al **guardrail de seguridad**.
5. El guardrail valida dos cosas antes de dejar pasar cualquier salida:
   - Que no se exponga PII/salarios fuera del rol del usuario que preguntó.
   - Que el prompt original no sea un intento de prompt injection para forzar esa fuga.
6. Nodo de decisión final: si la discrepancia calculada está dentro de un umbral y no hay ambigüedad normativa → **ajuste automático en el ERP**. Si supera el umbral, hay ambigüedad, o el guardrail bloqueó algo → **notifica a un humano** para revisión manual.

## Memoria de sesión

El estado (historial de la conversación + resultados de tools ya invocadas) vive en el grafo de LangGraph entre turnos — el orquestador lee ese estado antes de decidir el siguiente paso y lo actualiza después de cada tool call. Así una pregunta de seguimiento ("¿y si fuera la región norte?") no repite llamadas ya resueltas.

## Guardrails de seguridad

- Está **desacoplado del orquestador** — corre siempre antes de que cualquier respuesta llegue al usuario o cualquier acción llegue al ERP, sin excepción, sin importar qué tool se haya usado.
- Dos disparadores de bloqueo/escalación: fuga de datos restringidos por rol, e intento de instrucción-en-el-prompt que intente forzar esa fuga.
- Implementación detallada → F-B4 en [`00-planning.md`](00-planning.md).

## Por qué esta arquitectura y no un prompt lineal

Un solo prompt con todo el contexto (context stuffing) no permite: (a) decidir dinámicamente qué herramienta usar según la pregunta, (b) encadenar resultados de una tool como input de la siguiente, ni (c) aplicar un guardrail independiente del modelo. El ReAct loop + guardrail desacoplado es lo que la rúbrica de la prueba pide explícitamente como diferenciador senior.
