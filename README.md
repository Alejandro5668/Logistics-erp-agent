# Logistics-erp-agent

Prototipo de agente autónomo para conciliar facturas de logística vs. ERP —
prueba técnica Senior AI Backend (Castor).

Ver [`docs/00-planning.md`](docs/00-planning.md) para la planeación completa
(stack, alcance por parte, estructura del repo).

---

## Variables de entorno

| Variable | Uso | Ejemplo | Requerida |
|---|---|---|---|
| `AGENT_MODEL` | Modelo del proveedor que usa `build_agent()`. String con formato `provider:model`, resuelto vía `init_chat_model` de LangChain. Si se omite, cae a `DEFAULT_MODEL` (`"azure_openai:gpt-4o"`) en `app/agent/core.py`. | `AGENT_MODEL=azure_openai:gpt-4o` o `AGENT_MODEL=openai:gpt-4` | No (solo para levantar el agente contra un proveedor real; los tests no la necesitan) |
| `ERP_DB_PATH` | Ruta del SQLite mock del ERP. | `data/erp_mock.db` (default) | No |
| `CHROMA_DB_PATH` | Ruta del índice Chroma de normativa. | `data/chroma` (default) | No |

Cambiar de proveedor es un edit de entorno, no de código: `app/agent/core.py`
nunca hardcodea un proveedor (`model` acepta un string `provider:model`, una
instancia `BaseChatModel` ya construida, o `None`).

## Herramientas mockeadas (no mutan estado real)

`create_erp_adjustment` y `notify_human` (`app/tools/actions.py`) son mocks
deterministas:

- `create_erp_adjustment` **nunca** escribe en la tabla `erp_orders`; devuelve
  un recibo simulado con `applied: false`.
- `notify_human` **nunca** envía una notificación real; devuelve un ticket
  simulado con `notified: false`.

Ambas son literales (`False`) a propósito, para que el mock sea legible tanto
para el modelo como para quien revisa el código y los tests. Ningún flujo del
agente puede dejar el ERP en un estado inconsistente porque ninguna de las
dos tools tiene un efecto real.

## Qué prueba la suite de tests (y qué no prueba)

Los tests de integración (`tests/test_agent_flow.py`, niveles L2-L4) corren
el grafo real de `create_agent` — SQLite, Chroma y el guardrail de seguridad
(F-B4) se ejecutan de verdad — pero el modelo es un `ScriptedChatModel`
(`tests/scripted_model.py`): un `BaseChatModel` de prueba que emite una
secuencia de mensajes prescrita por el test, sin red ni credenciales.

Esto prueba el **cableado** (orden de tool calls, intercepción del
guardrail, reuso de memoria vía checkpointer) de forma determinista y
offline. **No prueba la calidad del razonamiento de un LLM real** — la
decisión de ajustar vs. escalar según la política del `SYSTEM_PROMPT` la
toma el modelo real en producción, no el test double. Verificar eso (ej.
correr el agente con `AGENT_MODEL` apuntando a un proveedor real y
credenciales válidas) es un paso manual de demo, fuera del alcance de
`pytest`.

## Memoria de sesión

El checkpointer por defecto es `InMemorySaver` (LangGraph), inyectable vía
`build_agent(checkpointer=...)`. Es **solo en proceso**: el estado de la
conversación (`thread_id`) se pierde al reiniciar el proceso. No hay
persistencia durable en este prototipo — queda fuera de alcance (ver F-B6 en
`docs/00-planning.md`).

## API HTTP (F-B6)

`app/api/` expone el agente por HTTP vía FastAPI: `POST /chat` (streaming
SSE) y `POST /chat/sync` (JSON, sin streaming). Ambos endpoints comparten
un único pipeline guardado (`app/api/service.py`'s `run_turn()`) — ningún
byte llega al cliente sin pasar antes por `inspect_output` (F-B4).

### Levantar el servidor

```
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Por defecto levanta en `http://127.0.0.1:8000`. Requiere `AGENT_MODEL`
configurada (o el `DEFAULT_MODEL` de `app/agent/core.py`) y credenciales
válidas del proveedor — a diferencia de `pytest`, esto SÍ toca un LLM real
en el primer request (`get_agent()` construye y cachea el agente vía
`build_agent()`, sin `model=` override).

### `POST /chat` — streaming SSE

```
curl -N -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "reconcile ORD-1001", "thread_id": "demo-1", "role": "ADMIN"}'
```

Salida (frames `text/event-stream`; el protocolo completo de eventos está
documentado en `openspec/changes/f-b6-fastapi/design.md`'s Interfaces /
Contracts):

```
event: progress
data: {"label":"Looking up ERP order data..."}

event: content
data: {"text":"Ajuste simulado para ORD-1001."}

event: done
data: {"thread_id":"demo-1","status":"ok"}
```

Un `role="EMPLOYEE"` sobre un campo restringido (p. ej. `salary`,
`bank_account`) termina el stream con un evento `blocked` en vez de
`done` — el mismo request con `role="ADMIN"` completa normalmente
(spec: "Role and Thread_id Propagation").

### `POST /chat/sync` — JSON, sin streaming

```
curl -X POST http://127.0.0.1:8000/chat/sync \
  -H "Content-Type: application/json" \
  -d '{"message": "reconcile ORD-1001", "thread_id": "demo-1", "role": "ADMIN"}'
```

Respuesta:

```json
{"content": "Ajuste simulado para ORD-1001.", "thread_id": "demo-1", "status": "ok"}
```

### Manejo de errores (dos ventanas)

- Un fallo del proveedor (timeout, rate limit, auth, red) **antes** del
  primer byte responde HTTP `502`/`503` con un cuerpo JSON genérico
  (`{"code", "message", "replace"}`), sin abrir el stream.
- Un fallo **después** de que las cabeceras SSE ya se enviaron termina el
  stream con un evento `error` — el código de estado ya no puede cambiar
  a esa altura (`app/api/routes/chat.py`'s `_sse_body`, design.md
  "Decision: Two error windows").

Ningún caso filtra detalles del proveedor, stack traces, ni filas del ERP
al cliente.

## Tests

```
pip install -r requirements.txt
pytest -v
```

Suite completa offline: ninguna prueba requiere red, credenciales de
proveedor LLM, ni `AGENT_MODEL` configurada. Los tests de `app/api/`
(`tests/test_api_service.py`, `tests/test_api_endpoints.py`) usan
`app.dependency_overrides` + `ScriptedChatModel` (F-B5) para sustituir
`get_agent()` — nunca tocan un proveedor real.
