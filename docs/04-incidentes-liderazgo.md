# F-A4 — Gestión de incidentes y liderazgo

## Escenario: drift de modelo (GPT-4 → GPT-4o) aprobando notas de crédito erróneas

### Investigación de causa raíz

1. **Congelar el blast radius primero, investigar después.** Ver rollback abajo — no se investiga con el sistema todavía aprobando ajustes incorrectos en producción.
2. **Tracing (Arize Phoenix/LangSmith, ver `docs/01-estrategia-llmops.md`):** comparar, para los casos fallidos, la traza completa contra casos equivalentes pre-actualización. La pregunta concreta: ¿el guardrail dejó pasar algo que antes bloqueaba, o el orquestador está llamando mal a `calculate_tax_discrepancy` (argumentos distintos, tool skip, formato de salida distinto que rompe el parsing aguas abajo)?
3. **Diffear el comportamiento del modelo, no asumir "el modelo es peor".** GPT-4o cambia formato de tool-calling, tono, y sensibilidad a instrucciones respecto a GPT-4 — la causa más probable no es "el modelo alucina más" sino que el prompt/parsing estaba implícitamente afinado para el formato de respuesta de GPT-4 y GPT-4o rompe ese supuesto no documentado.
4. **Correlacionar con el golden dataset (abajo):** si el dataset ya existía, correrlo contra GPT-4o aísla inmediatamente si es un problema de prompt/parsing (el dataset ya lo hubiera detectado antes de producción) o algo nuevo específico de los datos reales en producción.

### Rollback

1. Revertir el alias/versión del modelo a GPT-4 de inmediato — es la mitigación de menor riesgo y más rápida, no requiere entender la causa raíz primero.
2. Si el sistema tiene *feature flag* de modelo (recomendado, ver Arquitectura model-agnostic en `CLAUDE.md`), el rollback es un cambio de config, no un deploy.
3. Poner en cuarentena manual (no auto-revertir en el ERP) cualquier ajuste ya aprobado automáticamente desde que se desplegó GPT-4o hasta el rollback — necesitan revisión humana uno por uno, porque ya hubo confianza depositada en una decisión potencialmente errónea.

### Golden Dataset — para que no se repita

- Un dataset versionado (en el repo, no en una hoja de cálculo aparte) de casos reales: prompt, contexto esperado, tool calls esperadas con sus argumentos, y el resultado correcto (ajuste vs. escalar).
- Cada incidente de producción confirmado (como este) se agrega como caso de regresión permanente — el dataset crece con el tiempo, no se escribe una sola vez al inicio.
- Se corre en **CI, como gate bloqueante, antes de cualquier cambio de modelo o de prompt** — no solo cuando alguien se acuerda de correrlo. Un upgrade de modelo (GPT-4 → GPT-4o) es exactamente el tipo de cambio que debe disparar esta corrida, igual que un cambio de código dispara la suite de tests.
- Métrica de aceptación explícita: 0 regresiones en exactitud numérica financiera (ver KPI en `docs/01-estrategia-llmops.md`) — este KPI específico no admite tolerancia, a diferencia de Faithfulness/Relevancy donde un pequeño margen es aceptable.

## Liderazgo técnico: Frontend se queja de 15-20s de latencia

No se ataca con "hacer el modelo más rápido" — se ataca con percepción y con paralelismo real:

1. **Streaming de tokens** (ya en el diseño de la API, `docs/00-planning.md` F-B6) — el usuario ve texto apareciendo en ~1-2s en vez de esperar 15-20s de pantalla en blanco. Esto solo resuelve percepción, no el tiempo real.
2. **Paralelizar tool calls independientes.** Si el orquestador necesita `get_erp_data` y el RAG normativo para la misma pregunta, no hay razón de negocio para llamarlos en serie — correrlos concurrentemente puede recortar varios segundos reales, no solo percibidos.
3. **Estado intermedio explícito en el streaming** — emitir eventos tipo "Consultando ERP...", "Revisando normativa..." en vez de silencio hasta el token final. Reduce ansiedad de espera sin tocar el modelo.
4. **Cachear la capa RAG** (embeddings + resultados de metadata filtering) para preguntas normativas recurrentes — no todo el tráfico necesita re-embeddear la pregunta y re-buscar contra el índice.
5. **Lo que NO se propone:** cambiar a un modelo más chico/barato para ganar velocidad — eso compromete precisión en un dominio financiero, y el enunciado pide explícitamente no sacrificarla.
