<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'OidcAuth' },
})

const loading = ref(false)
const binding = ref(false)
const bindErrorMessage = ref('')
const bindSuccessMessage = ref('')
const showUnbindConfirm = ref(false)
const status = ref({
  public: {},
  binding: {},
  config: null,
  plugin_version: '0.3.4',
})

let bindPopupTimer = null
let bindMessageReceived = false
let bindPollingLock = false
let idpLoadTimer = null

// 步骤状态: 'pending' | 'loading' | 'done' | 'error'
const step1State = ref('pending')
const step2State = ref('pending')
const step3State = ref('pending')

const pluginBase = computed(() => `plugin/${props.pluginId || 'OidcAuth'}`)
const isBound = computed(() => Boolean(status.value.binding?.bound))
const isEnabled = computed(() => Boolean(status.value?.public?.enabled))

const step1Title = computed(() => {
  const map = { loading: '正在跳转到 IdP', done: '已跳转至 IdP', error: '跳转失败' }
  return map[step1State.value] || '跳转至 IdP 认证'
})
const step1Desc = computed(() => {
  const map = { loading: '正在打开认证提供商的登录页面...', done: '已成功跳转至身份提供商', error: '请尝试重新发起绑定' }
  return map[step1State.value] || '点击下方按钮，跳转至身份提供商进行认证授权'
})
const step2Title = computed(() => {
  const map = { loading: '等待身份认证', done: '身份认证完成', error: '认证已中断' }
  return map[step2State.value] || '完成身份认证'
})
const step2Desc = computed(() => {
  const map = { loading: '请在弹窗中登录并完成授权...', done: '已通过 IdP 身份认证', error: '窗口已关闭，请重试' }
  return map[step2State.value] || '在 IdP 页面登录并完成授权确认'
})
const step3Title = computed(() => {
  const map = { loading: '正在完成绑定', done: '账号绑定成功', error: '绑定失败' }
  return map[step3State.value] || '自动完成绑定'
})
const step3Desc = computed(() => {
  const map = { loading: '正在将 OIDC 账号与本地用户关联...', done: 'OIDC 账号已成功绑定', error: '绑定过程中发生错误' }
  return map[step3State.value] || '授权完成后自动返回 MoviePilot 并完成绑定'
})

const shortSub = computed(() => {
  const sub = status.value?.binding?.sub || status.value?.binding?.masked_sub
  if (!sub) return ''
  if (sub.length <= 16) return sub
  return sub.slice(0, 16) + '…'
})

const isLight = ref(false)

function detectTheme() {
  const html = document.documentElement
  const cls = html.className || ''
  const dataset = html.dataset || {}
  if (cls.includes('v-theme--light')) { isLight.value = true; return }
  if (cls.includes('v-theme--dark')) { isLight.value = false; return }
  if (dataset.theme === 'light') { isLight.value = true; return }
  if (dataset.theme === 'dark') { isLight.value = false; return }
  if (cls.includes('dark')) { isLight.value = false; return }
  if (cls.includes('light')) { isLight.value = true; return }
  isLight.value = false
}

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
  if (idpLoadTimer) {
    clearTimeout(idpLoadTimer)
    idpLoadTimer = null
  }
}

async function handleBindMessage(event) {
  if (event.origin !== window.location.origin) return
  if (event.data?.type !== 'oidcauth_bind_callback') return
  bindMessageReceived = true
  window.removeEventListener('message', handleBindMessage)
  clearBindPopupTimer()
  step1State.value = 'done'
  step2State.value = 'done'
  if (event.data.success) {
    step3State.value = 'loading'
    for (let attempt = 0; attempt < 10; attempt++) {
      await loadStatus()
      if (isBound.value) {
        step3State.value = 'done'
        bindSuccessMessage.value = 'OIDC 账号已绑定'
        bindErrorMessage.value = ''
        binding.value = false
        return
      }
      await new Promise(r => setTimeout(r, 1500))
    }
    step3State.value = 'error'
    bindErrorMessage.value = '绑定失败：未检测到绑定状态，请重试'
    binding.value = false
  } else {
    step3State.value = 'error'
    bindErrorMessage.value = event.data?.message || '绑定失败'
    binding.value = false
  }
}

async function bindAccount() {
  binding.value = true
  bindErrorMessage.value = ''
  bindSuccessMessage.value = ''
  bindMessageReceived = false
  bindPollingLock = false
  step1State.value = 'pending'
  step2State.value = 'pending'
  step3State.value = 'pending'
  try {
    const response = await props.api.post(`${pluginBase.value}/bind/start`, {})
    const authorizeUrl = response?.data?.authorize_url
    if (!response?.success || !authorizeUrl) {
      throw new Error(response?.message || '无法发起绑定')
    }
    step1State.value = 'loading'
    window.addEventListener('message', handleBindMessage)
    const popup = window.open(authorizeUrl, 'moviepilot_oidc_bind', 'width=600,height=720,left=200,top=80')
    if (!popup) {
      window.removeEventListener('message', handleBindMessage)
      step1State.value = 'error'
      throw new Error('浏览器阻止了认证弹窗')
    }
    // 3 秒后假设 IdP 页面已加载完成
    idpLoadTimer = setTimeout(() => {
      if (popup && !popup.closed && step1State.value === 'loading' && !bindMessageReceived) {
        step1State.value = 'done'
        step2State.value = 'loading'
      }
    }, 3000)
    bindPopupTimer = setInterval(async () => {
      if (bindPollingLock) return
      bindPollingLock = true
      try {
        if (!popup.closed && !bindMessageReceived) {
          await loadStatus()
          if (isBound.value) {
            bindMessageReceived = true
            clearBindPopupTimer()
            window.removeEventListener('message', handleBindMessage)
            step1State.value = 'done'
            step2State.value = 'done'
            step3State.value = 'done'
            bindSuccessMessage.value = 'OIDC 账号已绑定'
            bindErrorMessage.value = ''
            binding.value = false
            try { popup.close() } catch (_) { }
            return
          }
          return
        }
        if (!popup.closed) return
        // 弹窗关闭
        clearBindPopupTimer()
        window.removeEventListener('message', handleBindMessage)
        if (!binding.value) return
        binding.value = false
        if (bindMessageReceived) return
        if (step1State.value === 'loading') {
          step1State.value = 'done'
        }
        step2State.value = 'error'
        bindErrorMessage.value = '窗口已关闭，请重试'
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
      showUnbindConfirm.value = false
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

let themeObserver = null

onMounted(() => {
  loadStatus()
  document.documentElement.style.overflow = 'hidden'
  document.body.style.overflow = 'hidden'
  detectTheme()
  themeObserver = new MutationObserver(detectTheme)
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] })
})

onUnmounted(() => {
  clearBindPopupTimer()
  if (idpLoadTimer) clearTimeout(idpLoadTimer)
  window.removeEventListener('message', handleBindMessage)
  if (themeObserver) { themeObserver.disconnect(); themeObserver = null }
  document.documentElement.style.overflow = ''
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="oidc-page" :class="{ 'oidc-light': isLight }">
    <!-- 背景装饰层 -->
    <div class="oidc-bg-decor">
      <div class="oidc-bg-blob oidc-bg-blob-1"></div>
      <div class="oidc-bg-blob oidc-bg-blob-2"></div>
      <div class="oidc-bg-grid"></div>
      <div class="oidc-bg-orb oidc-bg-orb-1"></div>
      <div class="oidc-bg-orb oidc-bg-orb-2"></div>
      <div class="oidc-bg-orb oidc-bg-orb-3"></div>
    </div>

    <!-- 主内容区：双栏 -->
    <div class="oidc-main">
      <!-- 左侧：品牌信息 -->
      <div class="oidc-card oidc-left">
        <div class="oidc-left-header">
          <svg class="oidc-left-icon" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
            <path d="M0 0 C1.7159774 -0.00571094 3.43195101 -0.01267798 5.1479187 -0.02079773 C9.78440331 -0.03866516 14.420698 -0.03757278 19.05720663 -0.03185534 C22.93867373 -0.02875392 26.82010485 -0.03486658 30.70156682 -0.04089409 C39.86422633 -0.0549169 49.02679256 -0.05339698 58.18945312 -0.04199219 C67.61781236 -0.03051545 77.04588698 -0.04458433 86.47420871 -0.07138866 C94.59174844 -0.09359587 102.70919916 -0.10017168 110.82676709 -0.09431225 C115.66502586 -0.0909532 120.50310229 -0.09328739 125.3413353 -0.11056328 C129.8936731 -0.12611042 134.44559166 -0.12199135 138.99791336 -0.10325813 C140.66026483 -0.09959353 142.32264791 -0.10261797 143.98497009 -0.11314392 C159.71978438 -0.20510452 173.23259887 3.06255643 185.08642578 14.02905273 C197.16983172 26.84626875 199.35371432 40.68318478 199.30297852 57.50512695 C199.30868945 59.22110435 199.3156565 60.93707796 199.32377625 62.65304565 C199.34164368 67.28953027 199.34055129 71.92582495 199.33483386 76.56233358 C199.33173243 80.44380068 199.3378451 84.32523181 199.34387261 88.20669377 C199.35789542 97.36935328 199.3563755 106.53191952 199.3449707 115.69458008 C199.33349396 125.12293931 199.34756284 134.55101393 199.37436718 143.97933567 C199.39657439 152.09687539 199.4031502 160.21432611 199.39729077 168.33189404 C199.39393171 173.17015282 199.39626591 178.00822924 199.41354179 182.84646225 C199.42908894 187.39880005 199.42496987 191.95071861 199.40623665 196.50304031 C199.40257205 198.16539178 199.40559649 199.82777486 199.41612244 201.49009705 C199.51072605 217.6771408 195.8756987 230.92781239 184.71142578 243.15405273 C172.1196704 254.89882906 158.19775869 256.8575684 141.79785156 256.80810547 C140.08187416 256.81381641 138.36590055 256.82078345 136.64993286 256.8289032 C132.01344825 256.84677063 127.37715356 256.84567825 122.74064493 256.83996081 C118.85917783 256.83685939 114.97774671 256.84297205 111.09628475 256.84899956 C101.93362523 256.86302237 92.771059 256.86150245 83.60839844 256.85009766 C74.18003921 256.83862091 64.75196458 256.85268979 55.32364285 256.87949413 C47.20610312 256.90170134 39.0886524 256.90827715 30.97108448 256.90241772 C26.1328257 256.89905867 21.29474927 256.90139286 16.45651627 256.91866875 C11.90417847 256.93421589 7.35225991 256.93009682 2.7999382 256.9113636 C1.13758673 256.907699 -0.52479635 256.91072344 -2.18711853 256.92124939 C-18.37416229 257.015853 -31.62483387 253.38082565 -43.85107422 242.21655273 C-55.59585054 229.62479735 -57.55458988 215.70288564 -57.50512695 199.30297852 C-57.51083789 197.58700111 -57.51780494 195.87102751 -57.52592468 194.15505981 C-57.54379212 189.5185752 -57.54269973 184.88228052 -57.5369823 180.24577188 C-57.53388087 176.36430479 -57.53999354 172.48287366 -57.54602104 168.6014117 C-57.56004385 159.43875219 -57.55852393 150.27618595 -57.54711914 141.11352539 C-57.5356424 131.68516616 -57.54971128 122.25709154 -57.57651561 112.8287698 C-57.59872283 104.71123007 -57.60529863 96.59377936 -57.5994392 88.47621143 C-57.59608015 83.63795265 -57.59841435 78.79987623 -57.61569023 73.96164322 C-57.63123737 69.40930542 -57.62711831 64.85738686 -57.60838509 60.30506516 C-57.60472048 58.64271368 -57.60774492 56.98033061 -57.61827087 55.31800842 C-57.71023147 39.58319413 -54.44257052 26.07037965 -43.47607422 14.21655273 C-30.65885821 2.1331468 -16.82194217 -0.05073581 0 0 Z" fill="#4A4A4A" transform="translate(57.10107421875,-0.404052734375)" />
            <path d="M0 0 C0 34.32 0 68.64 0 104 C-16.13020644 112.06510322 -22.35605626 114.39798452 -38.27734375 109.390625 C-53.56383724 103.68024548 -66.1826518 96.46574615 -73.3125 81.1875 C-75.50841113 71.0064575 -73.61355923 63.74057544 -68 55 C-61.24777412 45.63691345 -46.34487157 37.73869339 -35.11572266 35.64941406 C-30.75915717 34.95508322 -26.38923748 34.44477606 -22 34 C-22 37.96 -22 41.92 -22 46 C-23.753125 46.37125 -25.50625 46.7425 -27.3125 47.125 C-38.37872077 49.94043426 -46.14023219 54.82918742 -53 64 C-55.33496753 68.66993506 -54.70556739 75.43275479 -53.3515625 80.359375 C-49.570809 88.69642117 -42.36239176 92.59291409 -34.55078125 96.703125 C-29.57356032 98.52098787 -24.22671084 99.12888153 -19 100 C-19 69.64 -19 39.28 -19 8 C-2 0 -2 0 0 0 Z" fill="#F8A420" transform="translate(141,72)" />
            <path d="M0 0 C0 3.96 0 7.92 0 12 C-1.753125 12.37125 -3.50625 12.7425 -5.3125 13.125 C-16.37872077 15.94043426 -24.14023219 20.82918742 -31 30 C-33.33496753 34.66993506 -32.70556739 41.43275479 -31.3515625 46.359375 C-27.10773037 55.71756892 -18.12465664 60.25059563 -9 64 C-5.01277631 65.20838675 -1.08007601 66.125698 3 67 C3 70.63 3 74.26 3 78 C-12.36372613 79.05956732 -29.48013877 71.8793015 -41.1875 62 C-47.86202659 55.50380045 -51.89653202 48.24886937 -52.5 38.875 C-52.33221166 30.66455741 -48.41696623 23.31479679 -43 17.25 C-31.73510393 7.03416299 -15.205855 0 0 0 Z" fill="#B4B4B4" transform="translate(119,106)" />
            <path d="M0 0 C6.9283588 0.22349545 12.90919374 1.74921905 19.4375 3.9375 C20.23075684 4.20256348 21.02401367 4.46762695 21.84130859 4.74072266 C25.26913827 5.92346706 27.95243761 6.96829174 31 9 C35.00586131 8.68374779 37.63682532 7.0906221 41 5 C41.66 5 42.32 5 43 5 C43.66 13.58 44.32 22.16 45 31 C37.82460361 30.20273373 31.13505374 29.09987112 24.125 27.5625 C23.09375 27.34529297 22.0625 27.12808594 21 26.90429688 C20.01257813 26.68966797 19.02515625 26.47503906 18.0078125 26.25390625 C17.11723145 26.06127197 16.22665039 25.8686377 15.30908203 25.67016602 C13 25 13 25 10 23 C12.64 21.35 15.28 19.7 18 18 C16.12855305 17.17934931 14.25265664 16.3688416 12.375 15.5625 C11.33085937 15.11003906 10.28671875 14.65757813 9.2109375 14.19140625 C6.11314749 13.04198295 3.26789946 12.42688777 0 12 C0 8.04 0 4.08 0 0 Z" fill="#B4B4B4" transform="translate(144,106)" />
          </svg>
          <div class="oidc-left-titles">
            <h2 class="oidc-left-title">OIDC 认证</h2>
            <p class="oidc-left-sub">OpenID Connect 账号绑定</p>
          </div>
        </div>
        <p class="oidc-left-desc">
          通过绑定 OIDC 账号，你可以使用组织内的统一身份系统直接登录 MoviePilot，无需记忆额外密码，享受更安全便捷的认证体验。
        </p>
        <div class="oidc-left-tags">
          <span class="oidc-left-tag">OAuth 2.0</span>
          <div class="oidc-left-tag-sep"></div>
          <span class="oidc-left-tag">OpenID Connect</span>
          <div class="oidc-left-tag-sep"></div>
          <span class="oidc-left-tag">PKCE</span>
        </div>
        <div class="oidc-features">
          <div class="feature-card feature-violet">
            <div class="feature-icon feature-purple">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                <polyline points="10 17 15 12 10 7" />
                <line x1="15" y1="12" x2="3" y2="12" />
              </svg>
            </div>
            <div class="feature-text">
              <div class="feature-title">单点登录</div>
              <div class="feature-desc">一次认证，畅享全部服务，无需反复输入密码</div>
            </div>
          </div>
          <div class="feature-card feature-blue">
            <div class="feature-icon feature-blue-bg">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </div>
            <div class="feature-text">
              <div class="feature-title">免密认证</div>
              <div class="feature-desc">通过 IdP 安全授权，无需在本站存储密码</div>
            </div>
          </div>
          <div class="feature-card feature-green">
            <div class="feature-icon feature-green-bg">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <div class="feature-text">
              <div class="feature-title">统一账号</div>
              <div class="feature-desc">与组织内其他服务共享同一套用户身份体系</div>
            </div>
          </div>
          <div class="feature-card feature-amber">
            <div class="feature-icon feature-yellow-bg">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
            </div>
            <div class="feature-text">
              <div class="feature-title">安全可靠</div>
              <div class="feature-desc">基于 OAuth 2.0 / OpenID Connect 标准协议</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：绑定/解绑 -->
      <div class="oidc-card oidc-right">
        <div class="oidc-right-top">
          <div class="oidc-right-bigicon">
            <svg viewBox="0 0 1025 1024" xmlns="http://www.w3.org/2000/svg">
              <path fill="white" d="M406.766493 519.191123C402.472299 519.191123 398.112041 518.365316 393.916945 516.581574 294.159525 474.432413 229.71359 377.185445 229.71359 268.872671 229.71359 120.623897 350.347396-0.00991 498.59617-0.00991 646.844945-0.00991 767.445719 120.623897 767.445719 268.872671 767.445719 373.849187 705.741461 469.873961 610.245203 513.509574 593.629977 521.073961 574.041848 513.806865 566.444428 497.224671 558.880041 480.609445 566.18017 461.021316 582.795396 453.456929 654.838751 420.523768 701.381203 348.050994 701.381203 268.872671 701.381203 157.025445 610.410364 66.054606 498.59617 66.054606 386.781977 66.054606 295.778106 157.025445 295.778106 268.872671 295.778106 350.594477 344.40159 423.92609 419.649074 455.736155 436.429461 462.83809 444.32417 482.228026 437.189203 499.041445 431.871009 511.626735 419.649074 519.191123 406.766493 519.191123" />
              <path fill="white" d="M673.71999 996.54689 673.686957 996.54689 103.087732 996.018374C67.148635 995.95231 34.413667 978.147923 15.519215 948.385858-2.714591 919.680826-4.960785 884.171148 9.44128 853.385084 59.485151 746.525729 190.623215 566.532955 506.708893 561.644181 831.614183 555.698374 949.803603 748.474632 991.325151 863.327794 1002.225796 893.486245 997.832506 925.989987 979.202312 952.547923 959.878441 980.096826 927.936248 996.54689 893.780893 996.54689L811.365409 996.54689C793.131603 996.54689 778.333151 981.781471 778.333151 963.514632 778.333151 945.247794 793.131603 930.482374 811.365409 930.482374L893.780893 930.482374C906.432248 930.482374 918.125667 924.536568 925.128506 914.62689 928.69599 909.50689 933.981151 899.002632 929.191474 885.756697 885.787086 765.750503 776.351215 623.282374 507.765925 627.708697 241.59199 631.837729 122.411603 767.930632 69.295732 881.396439 64.406957 891.768568 65.166699 903.296826 71.310699 912.975277 78.04928 923.578632 89.973925 929.920826 103.186828 929.953858L673.753022 930.482374C691.986828 930.515406 706.752248 945.280826 706.752248 963.547665 706.752248 981.781471 691.953796 996.54689 673.71999 996.54689" />
            </svg>
          </div>
          <h2 class="oidc-right-title">{{ isBound ? 'OIDC 账号' : '绑定 OIDC 账号' }}</h2>
          <p v-if="!isBound" class="oidc-right-sub">点击下方按钮跳转至 IdP 完成授权和绑定</p>
          <div v-else class="oidc-bound-badge">
            <span class="oidc-dot"></span> 已绑定
          </div>
        </div>

        <div v-if="!isEnabled" class="oidc-disabled-banner">
          <svg class="oidc-disabled-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span>OIDC 认证已关闭，绑定与解绑功能不可用</span>
        </div>

        <div class="oidc-right-body">
          <!-- 未绑定：显示 3 步骤 -->
          <div v-if="!isBound" class="oidc-steps">
            <div class="oidc-step" :class="{ 'oidc-step-active': step1State !== 'pending', 'oidc-step-done-step': step1State === 'done' }">
              <div class="oidc-step-left">
                <div class="oidc-step-num" :class="{ 'oidc-num-done': step1State === 'done', 'oidc-num-loading': step1State === 'loading', 'oidc-num-error': step1State === 'error' }">
                  <svg v-if="step1State === 'done'" class="oidc-step-check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span v-else-if="step1State === 'loading'" class="oidc-spinner"></span>
                  <svg v-else-if="step1State === 'error'" class="oidc-step-x-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                  <template v-else>1</template>
                </div>
              </div>
              <div class="oidc-step-right">
                <div class="oidc-step-title">{{ step1Title }}</div>
                <div class="oidc-step-desc">{{ step1Desc }}</div>
              </div>
            </div>
            <div class="oidc-step" :class="{ 'oidc-step-active': step2State !== 'pending', 'oidc-step-done-step': step2State === 'done', 'oidc-step-error-step': step2State === 'error' }">
              <div class="oidc-step-left">
                <div class="oidc-step-num" :class="{ 'oidc-num-done': step2State === 'done', 'oidc-num-loading': step2State === 'loading', 'oidc-num-error': step2State === 'error' }">
                  <svg v-if="step2State === 'done'" class="oidc-step-check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span v-else-if="step2State === 'loading'" class="oidc-spinner"></span>
                  <svg v-else-if="step2State === 'error'" class="oidc-step-x-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                  <template v-else>2</template>
                </div>
              </div>
              <div class="oidc-step-right">
                <div class="oidc-step-title">{{ step2Title }}</div>
                <div class="oidc-step-desc">{{ step2Desc }}</div>
              </div>
            </div>
            <div class="oidc-step" :class="{ 'oidc-step-active': step3State !== 'pending', 'oidc-step-done-step': step3State === 'done', 'oidc-step-error-step': step3State === 'error' }">
              <div class="oidc-step-left">
                <div class="oidc-step-num" :class="{ 'oidc-num-done': step3State === 'done', 'oidc-num-loading': step3State === 'loading', 'oidc-num-error': step3State === 'error' }">
                  <svg v-if="step3State === 'done'" class="oidc-step-check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span v-else-if="step3State === 'loading'" class="oidc-spinner"></span>
                  <svg v-else-if="step3State === 'error'" class="oidc-step-x-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                  <template v-else>3</template>
                </div>
              </div>
              <div class="oidc-step-right">
                <div class="oidc-step-title">{{ step3Title }}</div>
                <div class="oidc-step-desc">{{ step3Desc }}</div>
              </div>
            </div>
          </div>

          <!-- 已绑定：显示信息行 -->
          <template v-else>
            <div class="oidc-info-rows">
              <div class="oidc-info-row">
                <span class="oidc-info-row-label">
                  <svg class="oidc-row-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                  绑定用户
                </span>
                <span class="oidc-info-row-value">{{ status.binding?.local_username || status.binding?.username || status.binding?.sub || status.binding?.masked_sub || '用户' }}</span>
              </div>
              <div class="oidc-info-row">
                <span class="oidc-info-row-label">
                  <svg class="oidc-row-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="2" y1="12" x2="22" y2="12" />
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                  </svg>
                  OIDC Subject
                </span>
                <span class="oidc-info-row-value" :title="status.binding?.sub || status.binding?.masked_sub">{{ shortSub }}</span>
              </div>
              <div class="oidc-info-row">
                <span class="oidc-info-row-label">
                  <svg class="oidc-row-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  认证状态
                </span>
                <span class="oidc-info-row-status"><span class="oidc-status-dot"></span> 有效</span>
              </div>
            </div>
            <p class="oidc-bound-desc">
              已通过 OIDC 绑定，可直接使用 {{ status.binding?.local_username || status.binding?.username || status.binding?.sub || status.binding?.masked_sub || 'admin' }} 的身份登录 MoviePilot
            </p>
          </template>
        </div>

        <div class="oidc-right-footer">
          <button v-if="!isBound" class="oidc-btn oidc-btn-primary" :disabled="binding || !isEnabled" @click="bindAccount">
            {{ isEnabled ? '绑定 OIDC 账号' : '认证功能已关闭' }}
          </button>
          <template v-else>
            <template v-if="showUnbindConfirm">
              <p class="oidc-unbind-confirm-text">确认解绑？解绑后将无法使用 OIDC 登录。</p>
              <div class="oidc-unbind-actions">
                <button class="oidc-btn oidc-btn-outline" :disabled="binding || !isEnabled" @click="showUnbindConfirm = false">取消</button>
                <button class="oidc-btn oidc-btn-danger" :disabled="binding || !isEnabled" @click="unbindAccount">确认解绑</button>
              </div>
            </template>
            <button v-else class="oidc-btn oidc-btn-unbind" :disabled="!isEnabled" @click="showUnbindConfirm = true">
              <svg class="oidc-btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
              解绑 OIDC 账号
            </button>
          </template>
        </div>

        <Transition name="oidc-fade">
          <div v-if="bindErrorMessage" class="oidc-alert oidc-alert-error">{{ bindErrorMessage }}</div>
        </Transition>
        <Transition name="oidc-fade">
          <div v-if="bindSuccessMessage" class="oidc-alert oidc-alert-success">{{ bindSuccessMessage }}</div>
        </Transition>
      </div>
    </div>

    <!-- 底部 -->
    <div class="oidc-bottom">
      <div class="oidc-bottom-line"></div>
      <div class="oidc-bottom-content">
        <div class="oidc-bottom-left">
          <svg class="oidc-warn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          请注意保管 OIDC 资料，以免信息泄露
        </div>
        <div class="oidc-bottom-right">OIDCAuth v{{ status.plugin_version || '0.3.0' }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.oidc-page {
  position: relative;
  height: 100vh;
  max-height: 100vh;
  box-sizing: border-box;
  padding: 24px 32px 16px;
  color: #e4e4e7;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #0c0c10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

/* 背景装饰层 */
.oidc-bg-decor {
  pointer-events: none;
  position: absolute;
  inset: 0;
  overflow: hidden;
  z-index: 0;
}

/* 大光斑 */
.oidc-bg-blob {
  position: absolute;
  border-radius: 50%;
}
.oidc-bg-blob-1 {
  top: -160px;
  left: -160px;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(109, 40, 217, 0.18) 0%, transparent 70%);
  filter: blur(120px);
}
.oidc-bg-blob-2 {
  bottom: -160px;
  right: -80px;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(79, 70, 229, 0.14) 0%, transparent 70%);
  filter: blur(100px);
}

/* 网格 */
.oidc-bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.14) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.14) 1px, transparent 1px);
  background-size: 48px 48px;
}

/* 浮动光点 */
.oidc-bg-orb {
  position: absolute;
  border-radius: 50%;
  animation: orb-float var(--orb-dur, 6s) ease-in-out infinite;
  animation-delay: var(--orb-delay, 0s);
}
.oidc-bg-orb-1 {
  --orb-dur: 6s;
  --orb-delay: 0s;
  top: 25%;
  left: 10%;
  width: 8px;
  height: 8px;
  background: rgba(167, 139, 250, 0.4);
}
.oidc-bg-orb-2 {
  --orb-dur: 8s;
  --orb-delay: 1s;
  top: 33%;
  right: 12%;
  width: 6px;
  height: 6px;
  background: rgba(129, 140, 248, 0.4);
}
.oidc-bg-orb-3 {
  --orb-dur: 7s;
  --orb-delay: 2.5s;
  bottom: 33%;
  left: 20%;
  width: 4px;
  height: 4px;
  background: rgba(196, 181, 253, 0.5);
}
@keyframes orb-float {
  0%, 100% { transform: translateY(0); opacity: 0.4; }
  50% { transform: translateY(var(--orb-range, -20px)); opacity: 0.7; }
}
.oidc-bg-orb-1 { --orb-range: -20px; }
.oidc-bg-orb-2 { --orb-range: 16px; }
.oidc-bg-orb-3 { --orb-range: -12px; }

/* 主内容区 */
.oidc-main {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 28px;
  width: 100%;
  max-width: 1024px;
  align-items: stretch;
}
@media (max-width: 900px) {
  .oidc-main {
    grid-template-columns: 1fr;
  }
}

/* 卡片通用 */
.oidc-card {
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 18px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

/* 左侧 */
.oidc-left-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.oidc-left-icon {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  object-fit: cover;
  flex-shrink: 0;
  box-shadow: 0 0 28px rgba(124, 58, 237, 0.3);
}
.oidc-left-titles {
  min-width: 0;
}
.oidc-left-title {
  font-size: 22px;
  font-weight: 600;
  color: #fff;
  margin: 0;
  line-height: 1.2;
  letter-spacing: -0.02em;
}
.oidc-left-sub {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.35);
  margin: 4px 0 0;
  line-height: 1.3;
}
.oidc-left-desc {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.45);
  line-height: 1.7;
  margin: 0 0 16px;
  max-width: 420px;
}
.oidc-left-tags {
  display: flex;
  align-items: center;
  gap: 0;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.oidc-left-tag {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 6px;
  padding: 5px 12px;
  line-height: 1;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.oidc-left-tag-sep {
  width: 20px;
  height: 1px;
  background: rgba(255, 255, 255, 0.15);
  margin: 0 8px;
}

/* 特性卡片 */
.oidc-features {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 16px;
}
.feature-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border-radius: 14px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(255, 255, 255, 0.015);
}
.feature-card.feature-violet {
  background: rgba(124, 58, 237, 0.06);
  border-color: rgba(124, 58, 237, 0.15);
}
.feature-card.feature-blue {
  background: rgba(59, 130, 246, 0.06);
  border-color: rgba(59, 130, 246, 0.15);
}
.feature-card.feature-green {
  background: rgba(16, 185, 129, 0.06);
  border-color: rgba(16, 185, 129, 0.15);
}
.feature-card.feature-amber {
  background: rgba(234, 179, 8, 0.06);
  border-color: rgba(234, 179, 8, 0.15);
}
.feature-icon {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.feature-icon svg {
  width: 16px;
  height: 16px;
}
.feature-purple {
  background: rgba(124, 58, 237, 0.12);
  color: #a78bfa;
}
.feature-blue-bg {
  background: rgba(59, 130, 246, 0.12);
  color: #60a5fa;
}
.feature-green-bg {
  background: rgba(16, 185, 129, 0.12);
  color: #34d399;
}
.feature-yellow-bg {
  background: rgba(234, 179, 8, 0.12);
  color: #facc15;
}
.feature-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.feature-title {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.8);
  line-height: 1.4;
}
.feature-desc {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.35);
  line-height: 1.6;
}

/* 右侧 */
.oidc-right {
  display: flex;
  flex-direction: column;
}
.oidc-right-top {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  margin-bottom: 16px;
}
.oidc-right-bigicon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-bottom: 14px;
  box-shadow: 0 4px 20px rgba(124, 58, 237, 0.3);
}
.oidc-right-bigicon svg {
  width: 26px;
  height: 26px;
}
.oidc-right-title {
  font-size: 18px;
  font-weight: 600;
  color: #f1f1f5;
  margin: 0 0 8px;
  line-height: 1.3;
}
.oidc-right-sub {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.35);
  margin: 0;
  line-height: 1.3;
}

/* 中间内容区 */
.oidc-right-body {
  flex: 1;
}

/* 未启用警告 */
.oidc-disabled-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 10px;
  background: rgba(234, 179, 8, 0.08);
  border: 1px solid rgba(234, 179, 8, 0.15);
  color: #eab308;
  font-size: 13px;
  font-weight: 500;
}
.oidc-disabled-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* 步骤流程卡片 */
.oidc-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.oidc-step {
  display: flex;
  gap: 0;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  transition: background 0.2s ease, border-color 0.2s ease;
}
.oidc-step:hover {
  background: rgba(255, 255, 255, 0.035);
  border-color: rgba(255, 255, 255, 0.08);
}
.oidc-step-active {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.08);
}
.oidc-step-done-step {
  border-color: rgba(16, 185, 129, 0.15);
  background: rgba(16, 185, 129, 0.04);
}
.oidc-step-error-step {
  border-color: rgba(239, 68, 68, 0.15);
  background: rgba(239, 68, 68, 0.04);
}
.oidc-step-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-right: 14px;
  flex-shrink: 0;
  padding-top: 2px;
}
.oidc-step-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(124, 58, 237, 0.25);
  transition: background 0.3s ease, box-shadow 0.3s ease;
}
.oidc-num-done {
  background: #10b981 !important;
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25) !important;
}
.oidc-num-loading {
  background: rgba(124, 58, 237, 0.4) !important;
  box-shadow: none !important;
}
.oidc-num-error {
  background: #ef4444 !important;
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.25) !important;
}

/* 转圈 spinner */
.oidc-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: #fff;
  border-radius: 50%;
  animation: oidc-spin 0.7s linear infinite;
}
@keyframes oidc-spin {
  to { transform: rotate(360deg); }
}

/* 打勾 / 打叉 图标 */
.oidc-step-check-icon {
  width: 14px;
  height: 14px;
  color: #fff;
}
.oidc-step-x-icon {
  width: 12px;
  height: 12px;
  color: #fff;
}
.oidc-step-right {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 4px;
}
.oidc-step-title {
  font-size: 14px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.75);
  line-height: 1.4;
  transition: color 0.2s ease;
}
.oidc-step-desc {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.35);
  line-height: 1.5;
  transition: color 0.2s ease;
}

/* 已绑定 */
.oidc-bound-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #10b981;
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.12);
  border-radius: 999px;
  padding: 4px 12px;
  margin-top: 2px;
}
.oidc-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 5px rgba(16, 185, 129, 0.4);
  flex-shrink: 0;
}
.oidc-info-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}
.oidc-info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 10px;
}
.oidc-info-row-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: rgba(255, 255, 255, 0.4);
  white-space: nowrap;
  flex-shrink: 0;
}
.oidc-row-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  opacity: 0.5;
}
.oidc-info-row-value {
  color: rgba(255, 255, 255, 0.75);
  font-weight: 500;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: right;
  margin-left: 12px;
  flex: 1;
  min-width: 0;
}
.oidc-info-row-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #10b981;
  font-weight: 500;
  margin-left: 12px;
}
.oidc-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 4px rgba(16, 185, 129, 0.4);
}
.oidc-bound-desc {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.35);
  margin: 0;
  line-height: 1.6;
}

/* 底部按钮区 */
.oidc-right-footer {
  margin-top: auto;
  padding-top: 12px;
}

/* 按钮 */
.oidc-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 44px;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;
  line-height: 1;
}
.oidc-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.oidc-btn-primary {
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  color: #fff;
  box-shadow: 0 4px 14px rgba(124, 58, 237, 0.25);
}
.oidc-btn-primary:hover:not(:disabled) {
  box-shadow: 0 6px 20px rgba(124, 58, 237, 0.4);
  transform: translateY(-1px);
}
.oidc-btn-primary:active:not(:disabled) {
  transform: translateY(0);
}
.oidc-btn-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

/* 解绑 */
.oidc-btn-unbind {
  background: rgba(239, 68, 68, 0.08);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.15);
}
.oidc-btn-unbind:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.14);
  border-color: rgba(239, 68, 68, 0.25);
}
.oidc-unbind-confirm-text {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.4);
  margin: 0 0 12px;
  text-align: center;
}
.oidc-unbind-actions {
  display: flex;
  gap: 10px;
}
.oidc-unbind-actions .oidc-btn {
  width: auto;
  flex: 1;
}
.oidc-btn-outline {
  background: transparent;
  color: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.oidc-btn-outline:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.18);
}
.oidc-btn-danger {
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.2);
}
.oidc-btn-danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.35);
}

/* 提示 */
.oidc-alert {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13px;
  text-align: left;
  line-height: 1.5;
}
.oidc-alert-error {
  background: rgba(239, 68, 68, 0.1);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.15);
}
.oidc-alert-success {
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.15);
}

/* 底部 */
.oidc-bottom {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1024px;
  margin-top: 16px;
}
.oidc-bottom-line {
  height: 1px;
  background: rgba(255, 255, 255, 0.06);
  margin-bottom: 12px;
}
.oidc-bottom-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.2);
}
.oidc-bottom-left {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.oidc-warn-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: rgba(234, 179, 8, 0.6);
}
.oidc-bottom-right {
  color: rgba(255, 255, 255, 0.2);
  font-size: 11px;
}

/* 过渡 */
.oidc-fade-enter-active,
.oidc-fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.oidc-fade-enter-from,
.oidc-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ===== 浅色主题 ===== */
.oidc-page.oidc-light {
  color: #1f2937;
  background: #f1f5f9;
}
.oidc-page.oidc-light .oidc-bg-blob-1 {
  background: radial-gradient(circle, rgba(124, 58, 237, 0.08) 0%, transparent 70%);
}
.oidc-page.oidc-light .oidc-bg-blob-2 {
  background: radial-gradient(circle, rgba(79, 70, 229, 0.06) 0%, transparent 70%);
}
.oidc-page.oidc-light .oidc-bg-grid {
  background-image:
    linear-gradient(rgba(0, 0, 0, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.05) 1px, transparent 1px);
}
.oidc-page.oidc-light .oidc-bg-orb-1 { background: rgba(124, 58, 237, 0.12); }
.oidc-page.oidc-light .oidc-bg-orb-2 { background: rgba(79, 70, 229, 0.1); }
.oidc-page.oidc-light .oidc-bg-orb-3 { background: rgba(139, 92, 246, 0.14); }

/* 浅色卡片 */
.oidc-page.oidc-light .oidc-card {
  background: #ffffff;
  border-color: rgba(0, 0, 0, 0.06);
}

/* 浅色左侧 */
.oidc-page.oidc-light .oidc-left-title { color: #111827; }
.oidc-page.oidc-light .oidc-left-sub { color: rgba(0, 0, 0, 0.45); }
.oidc-page.oidc-light .oidc-left-desc { color: rgba(0, 0, 0, 0.55); }
.oidc-page.oidc-light .oidc-left-tag {
  color: rgba(0, 0, 0, 0.5);
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.07);
}
.oidc-page.oidc-light .oidc-left-tag-sep { background: rgba(0, 0, 0, 0.12); }

/* 浅色特性 */
.oidc-page.oidc-light .feature-card {
  background: rgba(0, 0, 0, 0.015);
  border-color: rgba(0, 0, 0, 0.06);
}
.oidc-page.oidc-light .feature-card.feature-violet {
  background: rgba(124, 58, 237, 0.04);
  border-color: rgba(124, 58, 237, 0.1);
}
.oidc-page.oidc-light .feature-card.feature-blue {
  background: rgba(59, 130, 246, 0.04);
  border-color: rgba(59, 130, 246, 0.1);
}
.oidc-page.oidc-light .feature-card.feature-green {
  background: rgba(16, 185, 129, 0.04);
  border-color: rgba(16, 185, 129, 0.1);
}
.oidc-page.oidc-light .feature-card.feature-amber {
  background: rgba(234, 179, 8, 0.04);
  border-color: rgba(234, 179, 8, 0.1);
}
.oidc-page.oidc-light .feature-title { color: rgba(0, 0, 0, 0.8); }
.oidc-page.oidc-light .feature-desc { color: rgba(0, 0, 0, 0.45); }

/* 浅色右侧 */
.oidc-page.oidc-light .oidc-right-title { color: #111827; }
.oidc-page.oidc-light .oidc-right-sub { color: rgba(0, 0, 0, 0.45); }

/* 浅色步骤 */
.oidc-page.oidc-light .oidc-step {
  background: #f8fafc;
  border-color: rgba(0, 0, 0, 0.06);
}
.oidc-page.oidc-light .oidc-step:hover {
  background: #f1f5f9;
  border-color: rgba(0, 0, 0, 0.1);
}
.oidc-page.oidc-light .oidc-step-active {
  background: #f1f5f9;
  border-color: rgba(0, 0, 0, 0.1);
}
.oidc-page.oidc-light .oidc-step-done-step {
  border-color: rgba(16, 185, 129, 0.15);
  background: rgba(16, 185, 129, 0.04);
}
.oidc-page.oidc-light .oidc-step-error-step {
  border-color: rgba(239, 68, 68, 0.15);
  background: rgba(239, 68, 68, 0.04);
}
.oidc-page.oidc-light .oidc-step-title { color: rgba(0, 0, 0, 0.8); }
.oidc-page.oidc-light .oidc-step-desc { color: rgba(0, 0, 0, 0.45); }
.oidc-page.oidc-light .oidc-disabled-banner {
  background: rgba(234, 179, 8, 0.06);
  border-color: rgba(234, 179, 8, 0.2);
  color: #b45309;
}

/* 浅色信息行 */
.oidc-page.oidc-light .oidc-info-row {
  background: #f8fafc;
  border-color: rgba(0, 0, 0, 0.05);
}
.oidc-page.oidc-light .oidc-info-row-label { color: rgba(0, 0, 0, 0.45); }
.oidc-page.oidc-light .oidc-info-row-value { color: rgba(0, 0, 0, 0.75); }
.oidc-page.oidc-light .oidc-bound-desc { color: rgba(0, 0, 0, 0.45); }

/* 浅色按钮 */
.oidc-page.oidc-light .oidc-btn-outline {
  color: rgba(0, 0, 0, 0.5);
  border-color: rgba(0, 0, 0, 0.1);
}
.oidc-page.oidc-light .oidc-btn-outline:hover:not(:disabled) {
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.18);
}
.oidc-page.oidc-light .oidc-unbind-confirm-text { color: rgba(0, 0, 0, 0.45); }

/* 浅色底部 */
.oidc-page.oidc-light .oidc-bottom-line { background: rgba(0, 0, 0, 0.08); }
.oidc-page.oidc-light .oidc-bottom-content { color: rgba(0, 0, 0, 0.25); }
.oidc-page.oidc-light .oidc-bottom-right { color: rgba(0, 0, 0, 0.25); }

/* spinner - 浅色下保持可读 */
.oidc-page.oidc-light .oidc-spinner {
  border-color: rgba(0, 0, 0, 0.15);
  border-top-color: #7c3aed;
}
</style>
