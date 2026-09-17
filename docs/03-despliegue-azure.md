# F-A3 — Despliegue en Azure

Script de referencia: [`infra/main.bicep`](../infra/main.bicep). Es el diseño de la infraestructura — no se ejecutó ningún despliegue real, es la propuesta de cómo se llevaría este prototipo a producción.

## Por qué Container Apps + Azure OpenAI

- **Azure Container Apps**: corre el contenedor de la API del agente sin gestionar Kubernetes directamente, con autoescalado e integración nativa a la red virtual (VNet) — suficiente para un portal interno, sin la complejidad de administrar un clúster de Kubernetes completo (AKS).
- **Azure OpenAI Service** (no OpenAI público): mismo modelo, pero el tráfico queda dentro del perímetro de red de la empresa y bajo su nivel de servicio — requisito explícito de la prueba.

## Cómo se garantiza que el tráfico no sale de la red privada

Tres controles, no uno solo:

1. **Azure OpenAI con acceso público deshabilitado** — el recurso no acepta ninguna conexión desde internet, sin importar si alguien tiene las credenciales correctas.
2. **Conexión privada (Private Endpoint) más una zona DNS privada** — el Container App resuelve la dirección de Azure OpenAI a una IP privada dentro de la red interna, nunca a la IP pública del servicio.
3. **Entorno de Container Apps configurado como interno** — el agente no tiene salida a internet; solo se puede acceder desde dentro de la red de la empresa.

Los tres controles son necesarios porque cada uno cierra una puerta distinta: sin el primero, alguien con la clave de acceso podría llamar directamente a la API pública de OpenAI. Sin el segundo, un error de configuración de DNS podría igual resolver a la dirección pública. Sin el tercero, cualquiera en internet podría llegar al agente mismo, aunque el modelo esté bien aislado.

## Identidad sin claves de acceso

El Container App usa una identidad administrada por Azure, con permiso únicamente para usar el servicio de Azure OpenAI, en lugar de guardar una clave de API en variables de entorno. Es la práctica recomendada por Microsoft para este tipo de despliegue: una clave puede filtrarse en un log o quedar expuesta por error en el código; una identidad administrada por la propia plataforma elimina ese riesgo de raíz.

## Qué falta para un despliegue real

Esto queda fuera del alcance de la prueba, pero para que quede claro qué es diseño y qué sería trabajo adicional:

- Reemplazar la imagen de ejemplo del script por la imagen real del agente, publicada en un registro de contenedores privado de Azure.
- Una conexión de red (VPN o similar) para que el portal interno sea alcanzable desde la red de la empresa — no se incluye en el script porque depende de la infraestructura ya existente de cada empresa, no de este proyecto.
- Un archivo de parámetros con los valores reales de suscripción y región, que nunca deben quedar escritos directamente en el script de infraestructura.
