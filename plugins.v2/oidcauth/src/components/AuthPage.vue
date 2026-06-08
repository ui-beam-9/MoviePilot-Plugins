<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  provider: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'OidcAuth' },
})

const emit = defineEmits(['authenticated', 'error', 'close'])

const checking = ref(true)
const loading = ref(false)
const errorMessage = ref('')
let popupTimer = null
let messageReceived = false

const pluginBase = computed(() => `plugin/${props.pluginId || 'OidcAuth'}`)
const providerName = computed(() => props.provider?.name || 'OIDC 登录')

/** 拼接 API 路径为可用于 window.open 的 URL。 */
function buildApiUrl(path) {
  const base = props.api?.defaults?.baseURL || '/api/v1/'
  const normalizedBase = base.endsWith('/') ? base : `${base}/`
  const normalizedPath = String(path || '').replace(/^\/+/, '')
  return `${normalizedBase}${normalizedPath}`
}

/** 关闭弹窗轮询并清理状态。 */
function clearPopupTimer() {
  if (popupTimer) {
    clearInterval(popupTimer)
    popupTimer = null
  }
}

/** 处理 OIDC 回调窗口发回的认证消息。 */
function handleOidcMessage(event) {
  if (event.origin !== window.location.origin) return
  if (event.data?.type !== 'oidcauth_callback') return
  messageReceived = true
  window.removeEventListener('message', handleOidcMessage)
  clearPopupTimer()
  loading.value = false
  if (event.data.success && event.data.data?.ticket) {
    emit('authenticated', { ticket: event.data.data.ticket })
    return
  }
  const message = event.data?.message || 'OIDC 认证失败'
  errorMessage.value = message
  emit('error', { message })
}

/** 先自检 OIDC 是否已启用，再决定是否发起授权弹窗。 */
async function checkAndStart() {
  checking.value = true
  errorMessage.value = ''
  try {
    const response = await props.api.get(`${pluginBase.value}/public/status`)
    const data = response?.data !== undefined ? response.data : response
    if (!data?.enabled) {
      errorMessage.value = '管理员未启用OIDC认证，请联系管理员开启'
      emit('error', { message: errorMessage.value })
      return
    }
    startLogin()
  } catch {
    errorMessage.value = '无法连接到认证服务'
    emit('error', { message: errorMessage.value })
  } finally {
    checking.value = false
  }
}

/** 发起 OIDC 登录授权弹窗。 */
function startLogin() {
  errorMessage.value = ''
  loading.value = true
  messageReceived = false
  window.addEventListener('message', handleOidcMessage)
  const popup = window.open(
    buildApiUrl(`${pluginBase.value}/authorize`),
    'moviepilot_oidc_login',
    'width=600,height=720,left=200,top=80',
  )
  if (!popup) {
    loading.value = false
    window.removeEventListener('message', handleOidcMessage)
    errorMessage.value = '浏览器阻止了认证弹窗'
    emit('error', { message: errorMessage.value })
    return
  }
  popupTimer = setInterval(() => {
    if (!popup.closed) return
    clearPopupTimer()
    window.removeEventListener('message', handleOidcMessage)
    if (loading.value && !messageReceived) {
      loading.value = false
      errorMessage.value = '认证窗口已关闭'
      emit('error', { message: errorMessage.value })
    }
  }, 500)
}

/** 组件挂载后自检，通过后自动发起登录。 */
onMounted(() => {
  checkAndStart()
})

/** 组件卸载时清理监听器和定时器。 */
onUnmounted(() => {
  clearPopupTimer()
  window.removeEventListener('message', handleOidcMessage)
})
</script>

<template>
  <div class="oidc-auth-page text-center">
    <VProgressCircular v-if="checking" key="checking" indeterminate color="primary" class="mb-4" />
    <div v-if="checking" key="checking-text" class="text-body-2 text-medium-emphasis mb-2">正在检查认证服务状态...</div>
    <VProgressCircular v-if="!checking && loading" key="loading" indeterminate color="primary" class="mb-4" />
    <div v-if="!checking && loading" key="loading-text" class="text-body-2 text-medium-emphasis mb-2">正在打开 {{ providerName }} 授权页面...</div>
    <VAlert v-if="!loading && !checking && errorMessage" type="error" variant="tonal" class="mb-2">
      {{ errorMessage }}
    </VAlert>
    <VBtn v-if="!loading && !checking" block color="primary" @click="checkAndStart">重试</VBtn>
    <VBtn v-if="!loading && !checking" block variant="text" class="mt-2" @click="emit('close')">取消</VBtn>
  </div>
</template>
