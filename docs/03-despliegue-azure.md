# F-A3 — Despliegue en Azure

Script: [`infra/main.bicep`](../infra/main.bicep). Nota: no se validó con `az bicep build` (sin Azure CLI disponible en este entorno) — es el diseño de la infraestructura, no un deploy ejecutado.

## Por qué Container Apps + Azure OpenAI

- **Azure Container Apps**: corre el contenedor de la API FastAPI del agente sin gestionar Kubernetes directamente, con scale-to-N e integración nativa a VNet — suficiente para un portal interno, sin el overhead de AKS.
- **Azure OpenAI Service** (no OpenAI público): mismo modelo (gpt-4o), pero el tráfico queda dentro del perímetro de red de Azure de la empresa y bajo su cumplimiento/SLA — requisito explícito de la prueba.

## Cómo se garantiza que el tráfico no sale de la red privada

Tres controles, no uno solo:

1. **Azure OpenAI con `publicNetworkAccess: Disabled`** — el recurso ni siquiera acepta conexiones desde internet, sin importar credenciales.
2. **Private Endpoint + Private DNS Zone** (`privatelink.openai.azure.com`) — el Container App resuelve el endpoint de OpenAI a una IP privada dentro de la VNet, no a la IP pública del servicio.
3. **Container Apps Environment con `vnetConfiguration.internal: true`** — el propio agente (portal interno) no tiene ingress público; solo se alcanza desde dentro de la red de la empresa (VPN/ExpressRoute/bastion, según la infraestructura ya existente de la empresa).

Sin los tres, cualquiera de los siguientes escapes sigue siendo posible: alguien con la API key podría llamar a la API pública de OpenAI directamente (control 1), un DNS mal configurado podría resolver a la IP pública igual (control 2), o cualquiera en internet podría llegar al agente mismo así el modelo esté bien aislado (control 3).

## Identidad — sin API keys

El Container App usa **managed identity** (system-assigned) con el rol `Cognitive Services OpenAI User` sobre el recurso de Azure OpenAI, en vez de una API key en variables de entorno. Esto es lo que recomienda la skill `azure-deploy` instalada en este repo (`auth-best-practices.md`) — una key filtrada en logs o en el propio código es una superficie de fuga que la managed identity elimina por diseño.

## Qué falta para un deploy real (fuera de alcance de esta prueba)

- Reemplazar la imagen placeholder (`mcr.microsoft.com/k8se/quickstart`) por la imagen real del agente, publicada en Azure Container Registry (con su propio private endpoint).
- VPN Gateway o ExpressRoute para que el portal interno sea alcanzable desde la red corporativa — no se modela aquí porque depende de infraestructura ya existente de la empresa, no de este proyecto.
- `main.parameters.json` con los valores reales de suscripción/región (nunca hardcodeados en `main.bicep`).
