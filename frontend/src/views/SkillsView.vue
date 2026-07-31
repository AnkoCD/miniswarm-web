<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { showConfirmDialog, showFailToast, showSuccessToast } from 'vant'
import { installSkill, listSkills, removeSkill } from '../api'
import { useAuthStore } from '../stores/auth'
import type { Skill } from '../types'

const auth = useAuthStore()
const skills = ref<Skill[]>([])
const loading = ref(true)
const installing = ref(false)
const removing = ref('')
const skillUrl = ref('')

async function refresh() {
  skills.value = await listSkills()
}

async function submitInstall() {
  const url = skillUrl.value.trim()
  if (!url) return
  installing.value = true
  try {
    const result = await installSkill(url)
    await refresh()
    skillUrl.value = ''
    showSuccessToast(`Skill ${result.name} 已添加`)
    window.dispatchEvent(new CustomEvent('miniswarm:refresh-navigation'))
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || 'Skill 添加失败')
  } finally {
    installing.value = false
  }
}

async function removeInstalledSkill(skill: Skill) {
  try {
    await showConfirmDialog({
      title: `删除 ${skill.display_name}？`,
      message: '该 Skill 将立即从可用列表移出并放入服务器回收区，不会永久删除。',
      confirmButtonText: '删除 Skill',
      cancelButtonText: '取消',
      confirmButtonColor: '#b42318',
    })
  } catch {
    return
  }

  removing.value = skill.name
  try {
    await removeSkill(skill.name)
    await refresh()
    showSuccessToast(`${skill.display_name} 已移入回收区`)
    window.dispatchEvent(new CustomEvent('miniswarm:refresh-navigation'))
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || 'Skill 删除失败')
  } finally {
    removing.value = ''
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
    <header class="content-page-header"><div><p class="page-kicker">能力中心</p><h1>Skills</h1><p>为 MiniSwarm 添加需要的能力，或移除不再使用的 Skill。</p></div></header>
    <section v-if="auth.user?.role === 'admin'" class="content-card skill-installer-card">
      <div class="card-heading">
        <div>
          <h2>添加 Skill</h2>
          <p>粘贴公开 GitHub 仓库或精确的 /tree/ref/path 地址即可添加。同名 Skill 不会被覆盖。</p>
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
          {{ installing ? '正在添加…' : '添加 Skill' }}
        </button>
      </div>
    </section>
    <div v-if="loading" class="workbench-empty compact">正在读取 Skills…</div>
    <div class="skills-catalog">
      <article v-for="skill in skills" :key="skill.name">
        <div class="skill-icon">◇</div>
        <div>
          <h2>{{ skill.display_name }}</h2>
          <p>{{ skill.description }}</p>
          <div><span>{{ skill.supports_auto ? '支持自主判断' : '仅手动' }}</span><span>{{ skill.source || '本地固定来源' }}</span></div>
          <small v-if="skill.source_ref">版本：{{ skill.source_ref }}</small>
          <button
            v-if="auth.user?.role === 'admin'"
            class="skill-remove-button"
            type="button"
            :disabled="Boolean(removing)"
            @click="removeInstalledSkill(skill)"
          >
            {{ removing === skill.name ? '正在删除…' : '删除' }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>
