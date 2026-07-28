<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showFailToast } from 'vant'
import { useAuthStore } from '../stores/auth'

const username = ref('')
const password = ref('')
const submitting = ref(false)
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const expired = route.query.expired === '1' || sessionStorage.getItem('miniswarm:session-expired') === 'true'

async function submit() {
  if (!username.value || password.value.length < 8) {
    showFailToast('请输入账号和密码')
    return
  }
  submitting.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    sessionStorage.removeItem('miniswarm:session-expired')
    const next = typeof route.query.next === 'string' ? route.query.next : '/'
    await router.replace(next)
  } catch {
    showFailToast('用户名或密码错误')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="login-page">
    <div class="login-card">
      <p class="eyebrow">个人云端 AI 工作站</p>
      <h1>MiniSwarm Web</h1>
      <p class="muted">提交任务、查看 Agent 进度并领取服务器生成的文件。</p>
      <p v-if="expired" class="session-expired-note">登录已过期，请重新登录。登录后会自动返回刚才的任务。</p>
      <form class="form-stack" @submit.prevent="submit">
        <label>
          <span>账号</span>
          <input v-model="username" autocomplete="username" maxlength="64" />
        </label>
        <label>
          <span>密码</span>
          <input v-model="password" type="password" autocomplete="current-password" maxlength="256" />
        </label>
        <button class="primary-button" type="submit" :disabled="submitting">
          {{ submitting ? '登录中…' : '登录' }}
        </button>
      </form>
    </div>
  </section>
</template>
