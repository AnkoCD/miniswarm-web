<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { showFailToast, showSuccessToast } from 'vant'
import { installSkill, listSkills } from '../api'
import { useAuthStore } from '../stores/auth'
import type { Skill, SkillInstallResult } from '../types'

const auth = useAuthStore()
const skills = ref<Skill[]>([])
const loading = ref(true)
const installing = ref(false)
const skillUrl = ref('')
const installResult = ref<SkillInstallResult | null>(null)

async function refresh() {
  skills.value = await listSkills()
}

async function submitInstall() {
  const url = skillUrl.value.trim()
  if (!url) return
  installing.value = true
  installResult.value = null
  try {
    installResult.value = await installSkill(url)
    await refresh()
    skillUrl.value = ''
    showSuccessToast(`Skill ${installResult.value.name} 已安全安装`)
    window.dispatchEvent(new CustomEvent('miniswarm:refresh-navigation'))
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || 'SkillSpector 扫描或安装未通过')
  } finally {
    installing.value = false
  }
}

onMounted(async () => {
  try { await refresh() }
  catch { showFailToast('Skills 加载失败') }
  finally { loading.value = false }
})
</script>

<template>
  <section class="content-page">
    <header class="content-page-header"><div><p class="page-kicker">能力中心</p><h1>Skills</h1><p>已安装 Skill 默认只读挂载给 Agent；新 Skill 必须先通过 NVIDIA SkillSpector 扫描。</p></div></header>
    <section v-if="auth.user?.role === 'admin'" class="content-card skill-installer-card">
      <div class="card-heading">
        <div>
          <h2>安全添加 Skill</h2>
          <p>粘贴公开 GitHub 仓库或精确的 /tree/ref/path 地址。系统会锁定提交、限制下载大小、拒绝链接文件，扫描通过后自动安装，已有 Skill 不会被覆盖。</p>
        </div>
      </div>
      <div class="filter-bar">
        <input
          v-model="skillUrl"
          type="url"
          inputmode="url"
          placeholder="https://github.com/owner/repo 或 /tree/ref/path"
          :disabled="installing"
          @keyup.enter="submitInstall"
        />
        <button class="primary-inline-button" type="button" :disabled="installing || !skillUrl.trim()" @click="submitInstall">
          {{ installing ? '正在扫描…' : '扫描并自动安装' }}
        </button>
      </div>
      <div v-if="installResult" class="scan-result">
        <strong>{{ installResult.name }} 已安装</strong>
        <span>风险 {{ installResult.risk_score }}/100 · {{ installResult.risk_severity }}</span>
        <span>{{ installResult.finding_count }} 项发现 · {{ installResult.scan_mode }}</span>
        <small>固定提交：{{ installResult.source_ref }}</small>
      </div>
    </section>
    <div v-if="loading" class="workbench-empty compact">正在读取 Skills…</div>
    <div class="skills-catalog">
      <article v-for="skill in skills" :key="skill.name">
        <div class="skill-icon">◇</div>
        <div><h2>{{ skill.display_name }}</h2><p>{{ skill.description }}</p><div><span>{{ skill.supports_auto ? '支持自主判断' : '仅手动' }}</span><span>{{ skill.source || '本地固定来源' }}</span></div><small v-if="skill.source_ref">版本：{{ skill.source_ref }}</small></div>
      </article>
    </div>
  </section>
</template>
