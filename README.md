# Logistics-erp-agent

Agente de inteligencia artificial que revisa facturas de logística contra los
datos del ERP de una empresa y detecta si hay una discrepancia en el monto de
impuestos cobrado. Es un prototipo hecho para una prueba técnica (Senior AI
Backend Engineer — Castor), no un sistema en producción.

## Qué hace exactamente

1. Un usuario escribe una pregunta en lenguaje natural, por ejemplo: "¿por
   qué hay una discrepancia en la orden ORD-1004?".
2. El agente busca el pedido en una base de datos que simula el ERP, calcula
   si el impuesto cobrado coincide con lo que debería ser según la región de
   esa orden, y busca en un conjunto de normativas si hay algo que
   justifique la diferencia.
3. Con esa información, el agente decide una de dos cosas: generar un ajuste
   automático en el ERP (simulado — no escribe nada real en ninguna base de
   datos) o escalar el caso a un humano para que lo revise.
4. Antes de que cualquier respuesta salga, un filtro de seguridad revisa dos
   cosas: que no se esté filtrando información restringida (salarios, datos
   personales) a alguien sin el rol adecuado, y que el usuario no esté
   intentando manipular al agente con instrucciones escondidas en su
   mensaje.

Todo esto corre local, en tu máquina. No hay nada desplegado en un servidor
real ni en Azure — el despliegue en Azure es solo un diseño (explicado más
abajo).

---

## Cómo probarlo tú mismo

Dos caminos: con Docker (un solo comando, recomendado) o instalando Python
directo en tu máquina. Cualquiera de los dos requiere una clave de API de
algún proveedor de IA (Azure OpenAI, OpenAI o Anthropic) — sin eso, el
agente no puede correr de verdad (los tests sí corren sin clave, ver abajo).

### Opción A — Con Docker (recomendado, un solo comando)

```
cp .env.example .env
```

Abre `.env` y descomenta UNA sección (Azure OpenAI, Anthropic u OpenAI),
con tu clave y el modelo que quieras usar (por ejemplo
`AGENT_MODEL=anthropic:claude-haiku-4-5-20251001`). Después:

```
docker compose up --build
```

Eso construye la imagen (ya incluye los tres paquetes de proveedor, así
funciona sin importar cuál elegiste en `.env`) y deja todo corriendo en
`http://localhost:8000`. No hay que instalar Python, ni pip, ni nada más
a mano.

### Opción B — Con Python instalado en tu máquina

Necesitas Python 3.12. Desde la carpeta del proyecto:

```
pip install -r requirements.txt
```

Para correr los tests (no necesita ninguna clave de API):

```
pytest -v
```

Debe terminar en "332 passed". Esto prueba que todo el código funciona bien
— la base de datos, la búsqueda de normativa, el filtro de seguridad, el
armado del agente, la API — sin necesidad de conectarse a ningún proveedor
de IA real. Para los tests se usa un modelo de lenguaje falso que responde
con mensajes ya escritos de antemano, así se puede probar el flujo completo
sin gastar dinero en llamadas a una IA real ni necesitar internet.

Para levantar la API de verdad:

```
cp .env.example .env
```

Edita `.env` igual que en la Opción A, e instala el paquete del proveedor
que elegiste. `requirements.txt` los deja afuera a propósito: el agente no
depende de un proveedor específico (`AGENT_MODEL` decide cuál en tiempo de
ejecución), así que el paquete del cliente se instala aparte, según cuál
uses:

```
pip install langchain-openai      # Azure OpenAI u OpenAI
pip install langchain-anthropic   # Anthropic
```

Luego:

```
uvicorn app.main:app --reload
```

Esto lo deja corriendo en `http://127.0.0.1:8000` (con Docker o sin él).

### Probarlo desde el navegador (más fácil para una demo)

Con la API corriendo (cualquiera de las dos opciones), abre:

```
http://localhost:8000/demo/
```

Es una interfaz de chat mínima (`web/`, no forma parte de lo que pide la
prueba técnica, es solo una ayuda visual): tiene botones con los casos de
prueba típicos ya armados (una discrepancia real, una orden sin problemas,
una orden que no existe, un intento de pedir un dato restringido, un
intento de manipular al agente), un selector de rol, y un botón "Nueva
sesión" para reiniciar la conversación.

### Probarlo con curl (sin interfaz)

**Con streaming** (la respuesta va llegando en pedazos, como en un chat):

```
curl -N -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "reconcile ORD-1001", "thread_id": "demo-1", "role": "ADMIN"}'
```

**Sin streaming** (una sola respuesta completa en JSON):

```
curl -X POST http://127.0.0.1:8000/chat/sync \
  -H "Content-Type: application/json" \
  -d '{"message": "reconcile ORD-1001", "thread_id": "demo-1", "role": "ADMIN"}'
```

`thread_id` identifica la conversación (para que el agente recuerde
preguntas anteriores en la misma sesión). `role` es el rol del usuario que
pregunta (`EMPLOYEE`, `FINANCE_MANAGER` o `ADMIN`) — si preguntas por un
dato restringido con el rol `EMPLOYEE`, el agente lo bloquea; con `ADMIN`
lo permite.

---

## Cómo está organizado el código

```
app/
  tools/      → funciones que el agente puede llamar: consultar el ERP,
                calcular el impuesto esperado, aprobar un ajuste, avisar
                a un humano
  rag/        → búsqueda de normativa (el "RAG")
  security/   → el filtro de seguridad (guardrail)
  agent/      → arma el agente completo, uniendo todo lo de arriba
  api/        → expone el agente como una API web (FastAPI)
web/          → interfaz de chat mínima para probar la API desde el
                navegador (/demo) — no es parte de lo que pide la prueba
                técnica, es solo una ayuda visual, sin build ni dependencias
docs/         → toda la documentación pedida en la prueba: diagrama,
                estrategia de evaluación, diseño de Azure, respuestas del
                escenario de incidentes
infra/        → diseño de la infraestructura de Azure (nunca desplegado)
tests/        → pruebas automáticas de cada parte del proyecto
openspec/     → historial completo de decisiones de diseño (ver siguiente
                sección)
Dockerfile, docker-compose.yml → arrancar todo con un solo comando
                (`docker compose up --build`), ver arriba
```

---

## Cómo se construyó este proyecto

Se hizo con Claude Code, usando dos formas de trabajo distintas según la
parte:

- **La documentación** (diagrama, estrategia de evaluación, diseño de
  Azure, respuestas del escenario de incidentes) se escribió directo, sin
  ningún proceso formal — son documentos de texto, no había una decisión
  de diseño real que resolver antes de escribirlos.

- **El código** (el agente, las herramientas, la API) se hizo con un
  proceso llamado **SDD (Spec-Driven Development)**. Esto significa que
  antes de escribir cualquier línea de código, se escribía primero:

  1. Una **propuesta**: qué se va a hacer y por qué.
  2. Una **especificación**: qué debe cumplir exactamente el código, con
     casos de uso concretos.
  3. Un **diseño técnico**: cómo se va a construir, qué archivos, qué
     decisiones de arquitectura y por qué.
  4. Una lista de **tareas** concretas y chequeables.
  5. Recién ahí se implementaba el código.
  6. Después se **verificaba** que el código cumpliera exactamente con lo
     que decía la especificación, con una revisión aparte.
  7. Al final se **archivaba** el cambio, guardando el historial completo
     de esas cinco etapas.

  Ese historial completo quedó guardado en la carpeta
  `openspec/changes/archive/` — ahí se puede ver, por ejemplo, por qué se
  usó SQLite en vez de una base de datos real, o por qué el filtro de
  seguridad terminó dividido en dos partes en vez de una.

---

## Cómo se dividió el trabajo (features)

El proyecto se partió en piezas pequeñas e independientes, para poder
trabajar cada una por separado sin que una rompiera a otra:

| Pieza | Qué hace | Dónde está el código |
|---|---|---|
| F-B1 | Consulta simulada al ERP | `app/tools/erp_data.py` |
| F-B2 | Calcula si el impuesto cobrado está bien | `app/tools/tax_discrepancy.py` |
| F-B3 | Busca normativa relevante (RAG) | `app/rag/` |
| F-B4 | Filtro de seguridad (datos restringidos, intentos de manipulación) | `app/security/` |
| F-B5 | Arma el agente completo uniendo las 4 piezas de arriba | `app/agent/` |
| F-B6 | Expone el agente como API web | `app/api/` |

Las primeras cuatro piezas (F-B1 a F-B4) no dependen entre sí — se podían
hacer en cualquier orden. F-B5 necesita que las primeras tres ya existan,
porque las une en un solo agente. F-B6 necesita F-B5 y F-B4 terminados,
porque los expone al mundo a través de la API.

Cada pieza se entregó como su propio Pull Request en GitHub, y cada una
pasó por el proceso completo de SDD (propuesta → especificación → diseño →
tareas → código → verificación) antes de mergearse a la rama principal.
Dos piezas grandes (el filtro de seguridad y la API) se dividieron además
en dos Pull Requests cada una, porque el cambio era demasiado grande para
revisar de una sola vez.

---

## Guías de calidad (skills) usadas para generar el código

Además del proceso SDD, se usaron guías específicas de buenas prácticas
("skills" de Claude Code) para que el código generado siguiera un estándar
concreto, no genérico:

| Skill | Para qué se usó |
|---|---|
| `architecture-patterns` | Decidir cómo estructurar cada módulo nuevo antes de escribirlo |
| `solid-principles` | Que cada función o clase tenga una sola responsabilidad clara |
| `fastapi-backend-architecture` | Estructura correcta de la API (rutas, dependencias, streaming) |
| `api-contract-first` | Definir primero qué recibe y qué devuelve cada endpoint, antes de programarlo |
| `pytest` | Que cada pieza de código tenga al menos un test que falle si la lógica se rompe |
| `azure-deploy` (de Microsoft) | Diseño correcto del despliegue en Azure: identidad sin contraseñas, red privada |
| `diagram-design` | Generar el diagrama de arquitectura de forma clara y profesional |

---

## Sobre el despliegue en Azure

`infra/main.bicep` es solo el **diseño** de cómo se desplegaría este
proyecto en Azure (Container Apps + Azure OpenAI, con la red configurada
para que el tráfico no salga a internet). Ese script nunca se ejecutó — no
hay nada corriendo en Azure ahora mismo. La explicación completa de esa
decisión está en `docs/03-despliegue-azure.md`.

---

## Dónde está la respuesta a cada parte de la prueba técnica

| Parte de la prueba | Dónde está |
|---|---|
| Diagrama de arquitectura | `docs/assets/arquitectura-agentica.png` |
| Estrategia de evaluación (LLMOps) | `docs/01-estrategia-llmops.md` |
| Diseño de despliegue en Azure | `docs/03-despliegue-azure.md` |
| Gestión de incidentes y liderazgo | `docs/04-incidentes-liderazgo.md` |
| Planeación completa del proyecto | `docs/00-planning.md` |

---

## Herramientas que no hacen nada real (mocks)

`create_erp_adjustment` y `notify_human` (en `app/tools/actions.py`) son
simulaciones deterministas, a propósito:

- `create_erp_adjustment` **nunca** escribe en la base de datos del ERP;
  devuelve un recibo simulado con `applied: false`.
- `notify_human` **nunca** envía una notificación real; devuelve un ticket
  simulado con `notified: false`.

Así, ningún flujo del agente puede dejar datos en un estado inconsistente,
porque ninguna de las dos acciones tiene un efecto real fuera del proceso.

## Memoria de sesión

El agente recuerda la conversación dentro de un mismo `thread_id` mientras
el proceso esté corriendo (usando un componente de LangGraph llamado
`InMemorySaver`). Si reinicias el servidor, esa memoria se pierde — no hay
una base de datos persistente para esto en este prototipo.

## Manejo de errores en la API

- Si el proveedor de IA falla (tiempo de espera agotado, límite de
  peticiones, credenciales inválidas) **antes** de que empiece a responder,
  la API devuelve un error HTTP 502 o 503 con un mensaje genérico.
- Si el proveedor falla **después** de que ya empezó a enviar la respuesta
  en streaming, la conexión termina con un mensaje de error dentro del
  mismo stream (ya no se puede cambiar el código de estado HTTP a esa
  altura).

En ningún caso se filtran detalles internos del proveedor, ni un stack
trace, ni datos del ERP al usuario final.
