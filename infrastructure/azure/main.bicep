// ─────────────────────────────────────────────────────────────────────────────
// Enterprise Multi-Agent AI — Azure Infrastructure (Bicep)
// Deploys: Container Apps, Azure OpenAI, AI Search, Redis, PostgreSQL, App Insights
// ─────────────────────────────────────────────────────────────────────────────

@description('Environment name: dev | staging | prod')
param environment string = 'prod'

@description('Azure region')
param location string = resourceGroup().location

@description('Unique suffix to avoid naming collisions')
param suffix string = uniqueString(resourceGroup().id)

var prefix = 'entai-${environment}'

// ── Log Analytics + App Insights ─────────────────────────────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${prefix}-law-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 90
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-ai-${suffix}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ── Azure OpenAI ──────────────────────────────────────────────────────────────
resource openAI 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: '${prefix}-oai-${suffix}'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    publicNetworkAccess: 'Enabled'
    customSubDomainName: '${prefix}-oai-${suffix}'
  }
}

resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: openAI
  name: 'gpt-4o'
  sku: { name: 'Standard', capacity: 120 }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-4o', version: '2024-05-13' }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: openAI
  name: 'text-embedding-ada-002'
  sku: { name: 'Standard', capacity: 120 }
  properties: {
    model: { format: 'OpenAI', name: 'text-embedding-ada-002', version: '2' }
  }
  dependsOn: [gpt4oDeployment]
}

// ── Azure AI Search ────────────────────────────────────────────────────────────
resource aiSearch 'Microsoft.Search/searchServices@2023-11-01' = {
  name: '${prefix}-search-${suffix}'
  location: location
  sku: { name: 'standard' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    publicNetworkAccess: 'enabled'
    semanticSearch: 'standard'
  }
}

// ── Azure Cache for Redis ────────────────────────────────────────────────────
resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: '${prefix}-redis-${suffix}'
  location: location
  properties: {
    sku: { name: 'Basic', family: 'C', capacity: 1 }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
  }
}

// ── Azure Database for PostgreSQL ─────────────────────────────────────────────
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: '${prefix}-pg-${suffix}'
  location: location
  sku: { name: 'Standard_D2s_v3', tier: 'GeneralPurpose' }
  properties: {
    administratorLogin: 'pgadmin'
    administratorLoginPassword: 'CHANGE_ME_BEFORE_DEPLOY!'
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    version: '15'
  }
}

// ── Container Apps Environment ────────────────────────────────────────────────
resource containerEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${prefix}-cae-${suffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ── API Container App ─────────────────────────────────────────────────────────
resource apiApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${prefix}-api'
  location: location
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
      secrets: [
        { name: 'openai-key', value: openAI.listKeys().key1 }
        { name: 'search-key', value: aiSearch.listAdminKeys().primaryKey }
        { name: 'redis-key', value: redis.listKeys().primaryKey }
        { name: 'appinsights-key', value: appInsights.properties.InstrumentationKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: 'YOUR_ACR.azurecr.io/enterprise-ai-api:latest'
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'openai-key' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: openAI.properties.endpoint }
            { name: 'AZURE_SEARCH_ENDPOINT', value: 'https://${aiSearch.name}.search.windows.net' }
            { name: 'AZURE_SEARCH_API_KEY', secretRef: 'search-key' }
            { name: 'AZURE_APP_INSIGHTS_KEY', secretRef: 'appinsights-key' }
            { name: 'REDIS_URL', value: 'rediss://:${redis.listKeys().primaryKey}@${redis.properties.hostName}:6380' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 10
        rules: [
          { name: 'http-scaling', http: { metadata: { concurrentRequests: '30' } } }
        ]
      }
    }
  }
}

// ── Frontend Container App ────────────────────────────────────────────────────
resource frontendApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${prefix}-frontend'
  location: location
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: { external: true, targetPort: 80, transport: 'http' }
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: 'YOUR_ACR.azurecr.io/enterprise-ai-frontend:latest'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'VITE_API_URL', value: 'https://${apiApp.properties.configuration.ingress.fqdn}' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────
output apiUrl string = 'https://${apiApp.properties.configuration.ingress.fqdn}'
output frontendUrl string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'
output openAIEndpoint string = openAI.properties.endpoint
output searchEndpoint string = 'https://${aiSearch.name}.search.windows.net'
output appInsightsKey string = appInsights.properties.InstrumentationKey
