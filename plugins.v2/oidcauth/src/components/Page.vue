<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'OidcAuth' },
})

const emit = defineEmits(['close', 'switch'])

const loading = ref(false)
const binding = ref(false)
const bindErrorMessage = ref('')
const bindSuccessMessage = ref('')
const status = ref({ public: {}, binding: {} })

let bindPopupTimer = null
let bindMessageReceived = false
let bindPollingLock = false

const pluginBase = computed(() => `plugin/${props.pluginId || 'OidcAuth'}`)
const isBound = computed(() => Boolean(status.value.binding?.bound))
const isAdmin = computed(() => status.value.is_superuser)

function unwrap(response) {
  if (response && Object.prototype.hasOwnProperty.call(response, 'data')) {
    return response.data
  }
  return response
}

async function loadStatus() {
  loading.value = true
  try {
    const response = await props.api.get(`${pluginBase.value}/status`)
    status.value = unwrap(response) || status.value
  } catch (error) {
    bindErrorMessage.value = error?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function clearBindPopupTimer() {
  if (bindPopupTimer) {
    clearInterval(bindPopupTimer)
    bindPopupTimer = null
  }
}

async function handleBindMessage(event) {
  if (event.origin !== window.location.origin) return
  if (event.data?.type !== 'oidcauth_bind_callback') return
  bindMessageReceived = true
  window.removeEventListener('message', handleBindMessage)
  clearBindPopupTimer()
  binding.value = false
  if (event.data.success) {
    await loadStatus()
    bindSuccessMessage.value = 'OIDC 账号已绑定'
    bindErrorMessage.value = ''
  } else {
    bindErrorMessage.value = event.data?.message || '绑定失败'
  }
}

async function bindAccount() {
  binding.value = true
  bindErrorMessage.value = ''
  bindSuccessMessage.value = ''
  bindMessageReceived = false
  bindPollingLock = false
  try {
    const response = await props.api.post(`${pluginBase.value}/bind/start`, {})
    const authorizeUrl = response?.data?.authorize_url
    if (!response?.success || !authorizeUrl) {
      throw new Error(response?.message || '无法发起绑定')
    }
    window.addEventListener('message', handleBindMessage)
    const popup = window.open(authorizeUrl, 'moviepilot_oidc_bind', 'width=600,height=720,left=200,top=80')
    if (!popup) {
      window.removeEventListener('message', handleBindMessage)
      throw new Error('浏览器阻止了认证弹窗')
    }
    bindPopupTimer = setInterval(async () => {
      // 防止上一次轮询还未完成
      if (bindPollingLock) return
      bindPollingLock = true
      try {
        // 弹窗未关闭时，偷偷检查绑定状态（PostMessage 可能因 opener 丢失而失效）
        if (!popup.closed && !bindMessageReceived) {
          await loadStatus()
          if (isBound.value) {
            // 绑定已生效，关闭弹窗并标记成功
            bindMessageReceived = true
            clearBindPopupTimer()
            window.removeEventListener('message', handleBindMessage)
            binding.value = false
            bindSuccessMessage.value = 'OIDC 账号已绑定'
            bindErrorMessage.value = ''
            try { popup.close() } catch (_) { /* 忽略跨域关闭错误 */ }
            return
          }
          return
        }
        if (!popup.closed) return
        // 弹窗已关闭
        clearBindPopupTimer()
        window.removeEventListener('message', handleBindMessage)
        if (!binding.value) return
        binding.value = false
        if (bindMessageReceived) return
        // postMessage 丢失，重试轮询状态（最多 6 次，每次间隔 1.5 秒）
        for (let attempt = 0; attempt < 6; attempt++) {
          await loadStatus()
          if (isBound.value) {
            bindSuccessMessage.value = 'OIDC 账号已绑定'
            bindErrorMessage.value = ''
            return
          }
          if (attempt < 5) {
            await new Promise(r => setTimeout(r, 1500))
          }
        }
        bindErrorMessage.value = '绑定失败：未检测到绑定状态，请重试'
      } finally {
        bindPollingLock = false
      }
    }, 1000)
  } catch (error) {
    binding.value = false
    bindErrorMessage.value = error?.message || '绑定失败'
  }
}

async function unbindAccount() {
  binding.value = true
  bindErrorMessage.value = ''
  bindSuccessMessage.value = ''
  try {
    const response = await props.api.post(`${pluginBase.value}/unbind`, {})
    if (response?.success) {
      await loadStatus()
      bindSuccessMessage.value = 'OIDC 账号已解绑'
      bindErrorMessage.value = ''
    } else {
      bindErrorMessage.value = response?.message || '解绑失败'
    }
  } catch (error) {
    bindErrorMessage.value = error?.message || '解绑失败'
  } finally {
    binding.value = false
  }
}

onMounted(loadStatus)

onUnmounted(() => {
  clearBindPopupTimer()
  window.removeEventListener('message', handleBindMessage)
})
</script>

<template>
  <div class="oidc-auth-page pa-4">
    <!-- OIDC 已启用：显示绑定卡片 -->
    <VCard v-if="status.public?.enabled" :loading="loading" class="mb-4">
      <VCardItem>
        <template #prepend>
          <VAvatar color="primary" size="40">
            <svg viewBox="0 0 1024 1024" width="24" height="24" fill="white" xmlns="http://www.w3.org/2000/svg">
              <path d="M468.064 866.08v91.616c-81.408-7.168-155.328-25.376-221.792-54.656-66.432-29.28-118.752-66.496-156.96-111.68C51.104 746.176 32 697.536 32 645.408c0-50.016 17.952-97.056 53.856-141.184 35.904-44.096 84.992-80.8 147.328-110.08s132.224-48.576 209.728-57.856v92.128c-77.504 13.568-141.152 40.352-190.976 80.352-49.824 40-74.72 85.536-74.72 136.64 0 54.272 27.584 101.952 82.752 143.04 55.168 41.056 124.544 66.944 208.096 77.632zM992 587.008l-19.808-208.928-75.008 42.304c-72.864-44.288-158.752-72.32-257.696-84.096v92.128c57.504 10.368 107.488 28.032 150.016 53.056l-78.752 44.48L992 587.008z" />
              <path d="M613.792 889.152l-145.728 68.576V137.536l145.728-71.264v822.88z" />
            </svg>
          </VAvatar>
        </template>
        <VCardTitle>OIDC 账号绑定</VCardTitle>
        <VCardSubtitle>
          <span v-if="isBound" class="text-success">
            <VIcon size="14" color="success" class="mr-1">mdi-check-circle</VIcon>
            已绑定 {{ status.binding?.sub || status.binding?.masked_sub }}
          </span>
          <span v-else class="text-medium-emphasis">当前账号尚未绑定 OIDC</span>
        </VCardSubtitle>
      </VCardItem>
      <VCardText>
        <div class="d-flex flex-wrap gap-3 align-center">
          <VBtn v-if="!isBound" color="primary" :loading="binding" @click="bindAccount">
            <template #prepend>
              <svg viewBox="0 0 1024 1024" width="20" height="20" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                <path d="M468.064 866.08v91.616c-81.408-7.168-155.328-25.376-221.792-54.656-66.432-29.28-118.752-66.496-156.96-111.68C51.104 746.176 32 697.536 32 645.408c0-50.016 17.952-97.056 53.856-141.184 35.904-44.096 84.992-80.8 147.328-110.08s132.224-48.576 209.728-57.856v92.128c-77.504 13.568-141.152 40.352-190.976 80.352-49.824 40-74.72 85.536-74.72 136.64 0 54.272 27.584 101.952 82.752 143.04 55.168 41.056 124.544 66.944 208.096 77.632zM992 587.008l-19.808-208.928-75.008 42.304c-72.864-44.288-158.752-72.32-257.696-84.096v92.128c57.504 10.368 107.488 28.032 150.016 53.056l-78.752 44.48L992 587.008z" />
                <path d="M613.792 889.152l-145.728 68.576V137.536l145.728-71.264v822.88z" />
              </svg>
            </template>
            绑定 OIDC 账号
          </VBtn>
          <VBtn v-else color="error" variant="tonal" prepend-icon="mdi-link-off" :loading="binding" @click="unbindAccount">
            解绑 OIDC 账号
          </VBtn>
          <VBtn v-if="isAdmin" color="primary" variant="tonal" prepend-icon="mdi-cog" @click="emit('switch')">
            配置
          </VBtn>
        </div>
        <VAlert v-if="bindErrorMessage" type="error" variant="tonal" class="mt-3">{{ bindErrorMessage }}</VAlert>
        <VAlert v-if="bindSuccessMessage" type="success" variant="tonal" class="mt-3">{{ bindSuccessMessage }}</VAlert>
      </VCardText>
    </VCard>

    <!-- OIDC 未启用：显示提示 -->
    <VCard v-else class="mb-4">
      <VCardItem>
        <template #prepend>
          <VAvatar color="grey-lighten-2" size="40">
            <svg viewBox="0 0 1024 1024" width="24" height="24" fill="#9E9E9E" xmlns="http://www.w3.org/2000/svg">
              <path d="M468.064 866.08v91.616c-81.408-7.168-155.328-25.376-221.792-54.656-66.432-29.28-118.752-66.496-156.96-111.68C51.104 746.176 32 697.536 32 645.408c0-50.016 17.952-97.056 53.856-141.184 35.904-44.096 84.992-80.8 147.328-110.08s132.224-48.576 209.728-57.856v92.128c-77.504 13.568-141.152 40.352-190.976 80.352-49.824 40-74.72 85.536-74.72 136.64 0 54.272 27.584 101.952 82.752 143.04 55.168 41.056 124.544 66.944 208.096 77.632zM992 587.008l-19.808-208.928-75.008 42.304c-72.864-44.288-158.752-72.32-257.696-84.096v92.128c57.504 10.368 107.488 28.032 150.016 53.056l-78.752 44.48L992 587.008z" />
              <path d="M613.792 889.152l-145.728 68.576V137.536l145.728-71.264v822.88z" />
            </svg>
          </VAvatar>
        </template>
        <VCardTitle>OIDC 认证</VCardTitle>
        <VCardSubtitle class="text-medium-emphasis">OIDC 认证尚未启用</VCardSubtitle>
      </VCardItem>
      <VCardText>
        <p class="text-body-2 text-medium-emphasis">请联系管理员在插件设置中配置 OIDC Provider。</p>
      </VCardText>
    </VCard>
  </div>
</template>
