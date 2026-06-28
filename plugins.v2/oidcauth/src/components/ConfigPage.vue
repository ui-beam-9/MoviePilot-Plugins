<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'OidcAuth' },
})

defineEmits(['close'])

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const status = ref({ public: {} })

const config = ref({
  enabled: false,
  provider_name: 'OIDC 登录',
  issuer: '',
  client_id: '',
  client_secret: '',
  scopes: 'openid profile email',
  redirect_uri: '',
  username_claim: 'preferred_username',
  email_claim: 'email',
  allow_auto_bind_by_username: false,
})



const pluginBase = computed(() => `plugin/${props.pluginId || 'OidcAuth'}`)

const displayRedirectUri = computed(() => {
  const raw = status.value.public?.redirect_uri || ''
  if (!raw) return ''
  if (/^https?:\/\//i.test(raw)) return raw
  return `${window.location.origin}${raw}`
})



function unwrap(response) {
  if (response && Object.prototype.hasOwnProperty.call(response, 'data')) {
    return response.data
  }
  return response
}

function clearMessages() {
  errorMessage.value = ''
  successMessage.value = ''
}

async function loadStatus() {
  loading.value = true
  clearMessages()
  try {
    const response = await props.api.get(`${pluginBase.value}/status`)
    status.value = unwrap(response) || status.value
    if (status.value.config) {
      config.value = { ...config.value, ...status.value.config }
    }
  } catch (error) {
    errorMessage.value = error?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  clearMessages()
  try {
    const response = await props.api.post(`${pluginBase.value}/config`, config.value)
    const data = unwrap(response) || {}
    if (data.config) {
      config.value = { ...config.value, ...data.config }
    }
    await loadStatus()
    successMessage.value = '配置已保存，即将刷新页面...'
    setTimeout(() => window.location.reload(), 1000)
  } catch (error) {
    errorMessage.value = error?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  clearMessages()
  try {
    const response = await props.api.post(`${pluginBase.value}/test`, config.value)
    if (response?.success) {
      successMessage.value = response.message || '连接正常'
    } else {
      errorMessage.value = response?.message || '连接失败'
    }
  } catch (error) {
    errorMessage.value = error?.message || '连接失败'
  } finally {
    testing.value = false
  }
}

onMounted(loadStatus)

onUnmounted(() => {
})
</script>

<template>
  <div class="oidc-auth-config pa-4">
    <VCard :loading="loading">
      <VCardItem>
        <VCardTitle>OIDC Provider 配置</VCardTitle>
      </VCardItem>
      <VCardText>
        <VSwitch v-model="config.enabled" label="启用 OIDC 登录" color="primary" class="mb-2" />
        <template v-if="config.enabled">
          <VRow>
            <VCol cols="12" md="6">
              <VTextField v-model="config.provider_name" label="入口名称" prepend-inner-icon="mdi-openid" />
            </VCol>
            <VCol cols="12">
              <VTextField v-model="config.issuer" label="Issuer" placeholder="https://idp.example.com" prepend-inner-icon="mdi-web" />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model="config.client_id" label="Client ID" prepend-inner-icon="mdi-identifier" />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model="config.client_secret" label="Client Secret" type="password" prepend-inner-icon="mdi-key" />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model="config.scopes" label="Scopes" placeholder="openid profile email" prepend-inner-icon="mdi-format-list-checks" />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model="config.redirect_uri" label="回调地址覆盖" placeholder="留空自动生成" prepend-inner-icon="mdi-call-made" />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model="config.username_claim" label="用户名 Claim" prepend-inner-icon="mdi-account" />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model="config.email_claim" label="邮箱 Claim" prepend-inner-icon="mdi-email" />
            </VCol>
            <VCol cols="12">
              <VSwitch v-model="config.allow_auto_bind_by_username" label="允许按用户名 Claim 自动绑定已有用户" color="primary" />
            </VCol>
          </VRow>

          <!-- 使用指南 -->
          <div class="rounded-lg border pa-4 mt-4">
            <div class="d-flex align-center gap-2 mb-3">
              <VIcon size="20" color="primary">mdi-information-outline</VIcon>
              <span class="text-subtitle-2 font-weight-medium">使用指南</span>
            </div>
            <div class="d-flex gap-3 mb-2">
              <div class="text-medium-emphasis" style="min-width: 16px">1.</div>
              <div class="text-body-2">在您的 OIDC 提供商（如 Keycloak、Authentik、Okta 等）中创建一个客户端，协议类型选择 "OAuth2/OpenID Provider"，授权流程使用 "Authorize Application"。</div>
            </div>
            <div class="d-flex gap-3 mb-2">
              <div class="text-medium-emphasis" style="min-width: 16px">2.</div>
              <div class="text-body-2 d-flex flex-column gap-1">
                将回调地址设置为：
                <span v-if="displayRedirectUri" class="oidc-callback-uri">{{ displayRedirectUri }}</span>
                <span v-else class="text-medium-emphasis">加载中...</span>
              </div>
            </div>
            <div class="d-flex gap-3 mb-2">
              <div class="text-medium-emphasis" style="min-width: 16px">3.</div>
              <div class="text-body-2">
                填写签发者 URL、客户端 ID 和客户端密钥，保存设置。
                <div class="text-medium-emphasis text-caption mt-1">
                  如果 IdP 与 MoviePilot 不在同一网络、需要指定不同的回调地址，可在「回调地址覆盖」中手动填写完整地址（如 <code class="text-caption">https://another-domain.com/api/v1/plugin/OidcAuth/callback</code>），正常情况下留空即可。
                </div>
              </div>
            </div>
            <div class="d-flex gap-3 mb-2">
              <div class="text-medium-emphasis" style="min-width: 16px">4.</div>
              <div class="text-body-2">保存后登录页面将显示 OIDC 登录按钮。</div>
            </div>
            <div class="d-flex gap-3">
              <div class="text-medium-emphasis" style="min-width: 16px">5.</div>
              <div class="text-body-2">已登录用户可在左侧菜单「OIDC 认证」中绑定/解绑 OIDC 账号。</div>
            </div>
          </div>
        </template>

        <div class="d-flex flex-wrap gap-3 mt-4">
          <VBtn color="primary" prepend-icon="mdi-content-save" :loading="saving" @click="saveConfig">保存</VBtn>
          <VBtn v-if="config.enabled" color="info" variant="tonal" prepend-icon="mdi-connection" :loading="testing" @click="testConnection">测试连接</VBtn>
        </div>

        <VAlert v-if="errorMessage" type="error" variant="tonal" class="mt-4">{{ errorMessage }}</VAlert>
        <VAlert v-if="successMessage" type="success" variant="tonal" class="mt-4">{{ successMessage }}</VAlert>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.oidc-callback-uri {
  display: inline-block;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgb(var(--v-theme-on-surface));
  padding: 6px 12px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.85rem;
  word-break: break-all;
  user-select: all;
}
</style>
