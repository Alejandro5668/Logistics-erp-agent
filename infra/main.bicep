// Despliegue del agente de conciliación ERP: Container Apps + Azure OpenAI,
// sin salida de tráfico a redes públicas para el modelo.
targetScope = 'resourceGroup'

@description('Prefijo corto para nombrar recursos, p.ej. "erpagent"')
param environmentName string

@description('Región de despliegue')
param location string = resourceGroup().location

@description('Modelo de Azure OpenAI a desplegar')
param openAiModelName string = 'gpt-4o'

@description('Nombre del deployment del modelo')
param openAiDeploymentName string = 'gpt-4o-erp-agent'

var vnetName = '${environmentName}-vnet'
var infraSubnetName = 'container-apps-infra'
var peSubnetName = 'private-endpoints'
var logAnalyticsName = '${environmentName}-logs'
var containerAppsEnvName = '${environmentName}-cae'
var containerAppName = '${environmentName}-agent'
var openAiName = '${environmentName}-openai'
var privateDnsZoneName = 'privatelink.openai.azure.com'

// --- Red privada: 2 subnets, una para el Container Apps Environment
//     (delegada), otra para los private endpoints. Nada de esto tiene
//     salida pública por diseño.
resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: { addressPrefixes: ['10.0.0.0/16'] }
    subnets: [
      {
        name: infraSubnetName
        properties: {
          addressPrefix: '10.0.0.0/23'
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: { serviceName: 'Microsoft.App/environments' }
            }
          ]
        }
      }
      {
        name: peSubnetName
        properties: {
          addressPrefix: '10.0.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: { sku: { name: 'PerGB2018' } }
}

// --- Container Apps Environment integrado a la VNet, sin exponer ingress
//     público — el portal interno solo se alcanza dentro de la red privada.
resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppsEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: vnet.properties.subnets[0].id
      internal: true
    }
  }
}

// --- Azure OpenAI sin acceso público — solo alcanzable vía private endpoint.
resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAiName
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: openAiName
    publicNetworkAccess: 'Disabled'
    networkAcls: { defaultAction: 'Deny' }
  }
}

resource openAiDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: openAiDeploymentName
  properties: {
    model: { format: 'OpenAI', name: openAiModelName, version: '2024-08-06' }
  }
  sku: { name: 'Standard', capacity: 10 }
}

resource privateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: privateDnsZoneName
  location: 'global'
}

resource privateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZone
  name: '${vnetName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}

resource openAiPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: '${openAiName}-pe'
  location: location
  properties: {
    subnet: { id: vnet.properties.subnets[1].id }
    privateLinkServiceConnections: [
      {
        name: '${openAiName}-plsc'
        properties: {
          privateLinkServiceId: openAi.id
          groupIds: ['account']
        }
      }
    ]
  }
}

resource privateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: openAiPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'openai-config', properties: { privateDnsZoneId: privateDnsZone.id } }
    ]
  }
}

// --- La app del agente: identidad administrada, sin API keys en el env.
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      ingress: {
        external: false // portal interno: solo alcanzable dentro de la VNet
        targetPort: 8000
      }
    }
    template: {
      containers: [
        {
          name: 'erp-agent'
          image: 'mcr.microsoft.com/k8se/quickstart:latest' // placeholder — reemplazar con la imagen real del agente
          env: [
            { name: 'AZURE_OPENAI_ENDPOINT', value: openAi.properties.endpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAiDeploymentName }
          ]
          resources: { cpu: json('1.0'), memory: '2Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [openAiPrivateEndpoint]
}

// --- RBAC: el Container App llama a Azure OpenAI vía managed identity,
//     nunca con una API key.
resource openAiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAi.id, containerApp.id, 'Cognitive Services OpenAI User')
  scope: openAi
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User
    )
  }
}

output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output openAiEndpoint string = openAi.properties.endpoint
