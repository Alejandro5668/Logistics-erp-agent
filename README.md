# Logistics-erp-agent

Agente de IA que revisa facturas de logística contra el ERP de una empresa y
detecta si el impuesto cobrado en una orden es correcto. Prototipo para una
prueba técnica (Senior AI Backend Engineer — Castor), no un sistema en
producción.

## Qué hace

1. El usuario pregunta en lenguaje natural, por ejemplo: "¿por qué hay una
   discrepancia en la orden ORD-1004?".
2. El agente busca la orden en una base de datos que simula el ERP, calcula
   si el impuesto cobrado coincide con lo esperado según la región, y
   revisa si existe alguna normativa que justifique la diferencia.
3. Decide entre generar un ajuste automático (simulado, no escribe nada
   real) o escalar el caso a una persona.
4. Antes de responder, un filtro de seguridad revisa que no se filtre
   información restringida a alguien sin el rol adecuado, y que el mensaje
   no intente manipular al agente.

Todo corre en local. El despliegue en Azure es solo un diseño (ver más
abajo), nunca se ejecutó.

---

## Cómo levantarlo

Necesita una clave de API de un proveedor de IA (Azure OpenAI, OpenAI o
Anthropic) — sin eso el agente no responde de verdad. Los tests sí corren
sin ninguna clave.

**Con Docker (recomendado, un solo comando):**

```
cp .env.example .env        # completar con tu clave y el modelo elegido
docker compose up --build
```

Deja todo corriendo en `http://localhost:8000`, sin instalar nada más.

**Con Python instalado en tu máquina:**

```
pip install -r requirements.txt
pip install langchain-openai      # o langchain-anthropic, según tu proveedor
cp .env.example .env              # completar con tu clave
uvicorn app.main:app --reload
```

**Tests** (no necesitan ninguna clave de API):

```
pytest -v
```

Debe terminar en "332 passed".

**Probarlo:**

- Desde el navegador: `http://localhost:8000/demo/` — interfaz de chat con
  los casos de prueba típicos ya armados en botones.
- Con curl, streaming:
  ```
  curl -N -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
    -d '{"message": "reconcile ORD-1001", "thread_id": "demo-1", "role": "ADMIN"}'
  ```
- Con curl, sin streaming: el mismo request a `/chat/sync`.

`role` puede ser `EMPLOYEE`, `FINANCE_MANAGER` o `ADMIN` — determina qué
información restringida puede pedir. `thread_id` identifica la
conversación, para que el agente recuerde el contexto entre preguntas.

---

## Cómo está organizado

```
app/tools/    → consultar el ERP, calcular el impuesto esperado, aprobar un ajuste, avisar a un humano
app/rag/      → búsqueda de normativa
app/security/ → filtro de seguridad (guardrail)
app/agent/    → arma el agente completo
app/api/      → expone el agente como API (FastAPI)
web/          → interfaz de demo en el navegador (/demo), no es parte de la prueba técnica
docs/         → toda la documentación pedida en la prueba
infra/        → diseño de infraestructura de Azure (nunca desplegado)
tests/        → pruebas automáticas
openspec/     → historial de decisiones de diseño (ver abajo)
```

## Cómo se construyó

La documentación (arquitectura, LLMOps, Azure, incidentes) se escribió
directo. El código (agente, herramientas, API) siguió un proceso de diseño
por especificación: antes de programar cada parte, se definió por escrito
qué debía cumplir, cómo se iba a construir y por qué, y solo después se
implementó y se verificó contra esa definición. El historial completo de
esas decisiones queda en `openspec/changes/archive/`.

## Piezas del proyecto

| Pieza | Qué hace | Código |
|---|---|---|
| F-B1 | Consulta simulada al ERP | `app/tools/erp_data.py` |
| F-B2 | Calcula si el impuesto cobrado está bien | `app/tools/tax_discrepancy.py` |
| F-B3 | Busca normativa relevante (RAG) | `app/rag/` |
| F-B4 | Filtro de seguridad | `app/security/` |
| F-B5 | Arma el agente completo | `app/agent/` |
| F-B6 | Expone el agente como API | `app/api/` |

F-B1 a F-B4 son independientes entre sí. F-B5 los une en un solo agente.
F-B6 expone ese agente al mundo.

---

## Dónde está cada parte de la prueba técnica

| Parte | Dónde está |
|---|---|
| Diagrama de arquitectura | `docs/assets/arquitectura-agentica.png` |
| Estrategia de evaluación (LLMOps) | `docs/01-estrategia-llmops.md` |
| Diseño de despliegue en Azure | `docs/03-despliegue-azure.md` |
| Gestión de incidentes y liderazgo | `docs/04-incidentes-liderazgo.md` |
| Planeación completa del proyecto | `docs/00-planning.md` |

---

## Detalles que vale la pena saber

- **Las acciones son simuladas.** `create_erp_adjustment` y `notify_human`
  (`app/tools/actions.py`) nunca escriben ni notifican nada real — devuelven
  un resultado simulado, así ningún flujo puede dejar datos en un estado
  inconsistente durante una prueba.
- **La memoria de sesión vive en el proceso.** El agente recuerda la
  conversación dentro de un mismo `thread_id` mientras el servidor esté
  corriendo; se pierde si se reinicia.
- **Manejo de errores:** si el proveedor de IA falla antes de responder, la
  API devuelve un error HTTP genérico (502/503). Si falla después de
  empezar a responder en streaming, el error llega dentro del mismo stream.
  En ningún caso se exponen detalles internos ni datos del ERP.
