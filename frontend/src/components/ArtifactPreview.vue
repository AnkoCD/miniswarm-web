<script setup lang="ts">
import { onMounted, ref } from 'vue'
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
const inlineApiPath = `/tasks/${props.taskId}/artifacts/${props.artifact.id}/inline`
const inlineUrl = `/api/tasks/${props.taskId}/artifacts/${props.artifact.id}/inline`
const downloadUrl = `/api/tasks/${props.taskId}/artifacts/${props.artifact.id}/download`

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
  // 演示文稿型 HTML 依赖自己的滚轮/键盘/触摸脚本翻页，不能覆盖 deck/slide 布局。
  // 普通静态网页仍补上可滚动兜底，避免作者误设 overflow:hidden。
  const safeScrollStyle = slideCount > 1
    ? ''
    : `<style id="miniswarm-safe-scroll">
        html, body {
          min-height: 100% !important;
          overflow-y: auto !important;
          overscroll-behavior: auto !important;
        }
      </style>`
  const head = /<head(?:\s[^>]*)?>/i
  if (head.test(source)) {
    const guarded = source.replace(head, match => `${match}${guard}`)
    if (/<\/head>/i.test(guarded)) {
      return guarded.replace(/<\/head>/i, `${safeScrollStyle}</head>`)
    }
    return `${guarded}${safeScrollStyle}`
  }
  return `<!doctype html><html><head>${guard}${safeScrollStyle}</head><body>${source}</body></html>`
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function load() {
  loading.value = true
  try {
    metadata.value = await getArtifactPreview(props.taskId, props.artifact.id)
    if (metadata.value.kind === 'text' || metadata.value.kind === 'html') {
      const { data } = await api.get<string>(inlineApiPath, { responseType: 'text' })
      if (metadata.value.kind === 'html') html.value = sandboxHtml(data)
      else text.value = data
    } else if (metadata.value.kind === 'csv') {
      const { data } = await api.get<{ rows: string[][] }>(inlineApiPath)
      rows.value = data.rows
    }
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || '文件预览失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
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
        <iframe
          sandbox="allow-scripts"
          scrolling="yes"
          referrerpolicy="no-referrer"
          :srcdoc="html"
          :title="artifact.filename"
        />
      </div>
      <iframe v-else-if="metadata.kind === 'pdf'" class="pdf-preview" :src="inlineUrl" :title="artifact.filename" />
      <div v-else class="office-preview">
        <div class="file-glyph">{{ artifact.filename.split('.').pop()?.toUpperCase() }}</div>
        <h2>{{ artifact.filename }}</h2>
        <p>服务器已完成安全结构检查，不使用第三方在线预览服务。</p>
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
