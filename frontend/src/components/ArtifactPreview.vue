<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { showFailToast } from 'vant'
import { api, getArtifactPreview } from '../api'
import type { Artifact, ArtifactPreview as Preview } from '../types'

const props = defineProps<{ taskId: string; artifact: Artifact }>()
const emit = defineEmits<{ close: [] }>()
const metadata = ref<Preview | null>(null)
const text = ref('')
const html = ref('')
const rows = ref<string[][]>([])
const loading = ref(true)
const frameLoading = ref(false)
const frameError = ref(false)
let loadGeneration = 0

const inlineApiPath = computed(() => `/tasks/${props.taskId}/artifacts/${props.artifact.id}/inline`)
const inlineUrl = computed(() => `/api${inlineApiPath.value}`)
const downloadUrl = computed(() => `/api/tasks/${props.taskId}/artifacts/${props.artifact.id}/download`)
const frameUrl = computed(() => `${inlineUrl.value}#toolbar=1&navpanes=0&view=FitH`)

function sandboxHtml(source: string) {
  const policy = [
    "default-src 'none'",
    "img-src data: blob: https: http:",
    "media-src data: blob: https: http:",
    "style-src 'unsafe-inline' https: http:",
    "font-src data: https: http:",
    "script-src 'unsafe-inline'",
    "connect-src 'none'",
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
  ].join('; ')
  const guard = `<meta http-equiv="Content-Security-Policy" content="${policy}"><meta name="referrer" content="no-referrer">`
  const slideCount = (source.match(/class=["'][^"']*\bslide\b[^"']*["']/gi) || []).length
  const safeScrollStyle = slideCount > 1
    ? ''
    : `<style id="miniswarm-safe-scroll">html,body{min-height:100%!important;overflow-y:auto!important;overscroll-behavior:auto!important}</style>`
  const head = /<head(?:\s[^>]*)?>/i
  if (head.test(source)) {
    const guarded = source.replace(head, match => `${match}${guard}`)
    return /<\/head>/i.test(guarded)
      ? guarded.replace(/<\/head>/i, `${safeScrollStyle}</head>`)
      : `${guarded}${safeScrollStyle}`
  }
  return `<!doctype html><html><head>${guard}${safeScrollStyle}</head><body>${source}</body></html>`
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function officeLabel() {
  const suffix = props.artifact.filename.split('.').pop()?.toLowerCase()
  if (suffix === 'docx') return 'Word 文档已由服务器转换为 PDF 预览'
  if (suffix === 'pptx') return 'PowerPoint 已按幻灯片转换为 PDF 预览'
  if (suffix === 'xlsx') return 'Excel 已按打印区域转换为 PDF 预览'
  return 'Office 文件已转换为 PDF 预览'
}

async function load() {
  const generation = ++loadGeneration
  const taskId = props.taskId
  const artifactId = props.artifact.id
  const inlinePath = `/tasks/${taskId}/artifacts/${artifactId}/inline`
  loading.value = true
  frameLoading.value = false
  frameError.value = false
  metadata.value = null
  text.value = ''
  html.value = ''
  rows.value = []
  try {
    const nextMetadata = await getArtifactPreview(taskId, artifactId)
    if (generation !== loadGeneration) return
    metadata.value = nextMetadata
    if (nextMetadata.kind === 'text' || nextMetadata.kind === 'html') {
      const { data } = await api.get<string>(inlinePath, { responseType: 'text' })
      if (generation !== loadGeneration) return
      if (nextMetadata.kind === 'html') html.value = sandboxHtml(data)
      else text.value = data
    } else if (nextMetadata.kind === 'csv') {
      const { data } = await api.get<{ rows: string[][] }>(inlinePath)
      if (generation !== loadGeneration) return
      rows.value = data.rows
    } else if (nextMetadata.kind === 'pdf' || nextMetadata.kind === 'office') {
      frameLoading.value = true
    }
  } catch (error: any) {
    if (generation === loadGeneration) {
      showFailToast(error?.response?.data?.detail || '文件预览失败')
    }
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

watch(() => [props.taskId, props.artifact.id], load, { immediate: true })
</script>

<template>
  <section class="artifact-preview-pane">
    <header class="preview-header">
      <div>
        <strong>{{ artifact.filename }}</strong>
        <small>{{ formatSize(artifact.size) }} · {{ artifact.mime_type }} · {{ artifact.inspection_status === 'VERIFIED' ? 'Reviewer 已验证' : '结构预览' }}</small>
      </div>
      <div>
        <a class="subtle-button" :href="downloadUrl">下载</a>
        <button class="icon-button" type="button" aria-label="关闭预览" @click="emit('close')">×</button>
      </div>
    </header>

    <div v-if="loading" class="workbench-empty compact">正在准备预览…</div>
    <template v-else-if="metadata">
      <pre v-if="metadata.kind === 'text'" class="text-preview">{{ text }}</pre>

      <div v-else-if="metadata.kind === 'csv'" class="csv-preview">
        <table>
          <tbody>
            <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
              <th>{{ rowIndex + 1 }}</th>
              <td v-for="(cell, columnIndex) in row" :key="columnIndex">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else-if="metadata.kind === 'image'" class="image-preview">
        <img :src="inlineUrl" :alt="artifact.filename" />
      </div>

      <div v-else-if="metadata.kind === 'html'" class="html-preview">
        <div class="html-preview-notice">隔离交互预览 · 文件内翻页已启用，工作台权限仍隔离</div>
        <iframe sandbox="allow-scripts" scrolling="yes" referrerpolicy="no-referrer" :srcdoc="html" :title="artifact.filename" />
      </div>

      <div v-else-if="metadata.kind === 'pdf' || metadata.kind === 'office'" class="document-frame-preview">
        <div v-if="metadata.kind === 'office'" class="office-preview-notice">
          <strong>{{ officeLabel() }}</strong>
          <span>预览文件缓存在当前任务的私有 workspace，不会替换或修改原文件。</span>
        </div>
        <div v-if="frameLoading" class="frame-loading">正在渲染页面…</div>
        <div v-if="frameError" class="frame-error">
          <strong>当前浏览器无法内嵌显示该文件</strong>
          <a class="primary-inline-button" :href="downloadUrl">下载原文件</a>
        </div>
        <iframe
          v-show="!frameError"
          :key="`${taskId}:${artifact.id}`"
          class="pdf-preview"
          :src="frameUrl"
          :title="artifact.filename"
          @load="frameLoading = false"
          @error="frameLoading = false; frameError = true"
        />
      </div>

      <div v-else class="office-preview">
        <div class="file-glyph">{{ artifact.filename.split('.').pop()?.toUpperCase() }}</div>
        <h2>{{ artifact.filename }}</h2>
        <p>该文件暂不支持在线渲染，可以下载原文件查看。</p>
        <dl>
          <template v-for="(value, key) in metadata.metadata" :key="key">
            <dt>{{ key }}</dt><dd>{{ Array.isArray(value) ? value.join('、') : value }}</dd>
          </template>
        </dl>
        <a class="primary-inline-button" :href="downloadUrl">下载原文件</a>
      </div>
    </template>
  </section>
</template>

<style scoped>
.document-frame-preview { position: relative; display: flex; min-height: 0; flex: 1; flex-direction: column; overflow: hidden; }
.office-preview-notice { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 9px 14px; border-bottom: 1px solid var(--ws-line); color: var(--ws-muted); background: var(--ws-soft); font-size: 10px; }
.office-preview-notice strong { color: var(--ws-text); font-size: 10px; }
.frame-error { display: grid; min-height: 220px; place-content: center; justify-items: center; gap: 14px; color: var(--ws-muted); background: var(--ws-bg); font-size: 12px; }
.frame-loading { position: absolute; z-index: 2; inset: 42px 0 0; display: grid; place-items: center; color: var(--ws-muted); background: var(--ws-bg); font-size: 12px; pointer-events: none; }
.document-frame-preview .pdf-preview { width: 100%; min-height: 0; flex: 1; border: 0; background: #ececea; }
@media (max-width: 700px) {
  .office-preview-notice { align-items: flex-start; flex-direction: column; gap: 3px; }
}
</style>
