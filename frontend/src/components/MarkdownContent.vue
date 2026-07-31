<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function inlineMarkdown(value: string) {
  return value
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
}

const html = computed(() => {
  const escaped = escapeHtml(props.content || '')
  const codeBlocks: string[] = []
  const withoutCode = escaped.replace(/```([\w-]*)\n?([\s\S]*?)```/g, (_match, language, code) => {
    const normalizedLanguage = language || 'text'
    const index = codeBlocks.push(
      `<div class="code-block"><div class="code-block-header"><span>${normalizedLanguage}</span></div>` +
      `<pre><code data-language="${normalizedLanguage}">${code.replace(/^\n|\n$/g, '')}</code></pre></div>`,
    ) - 1
    return `@@CODE_BLOCK_${index}@@`
  })
  const lines = withoutCode.split('\n')
  const rendered: string[] = []
  let listType: 'ul' | 'ol' | '' = ''
  const closeList = () => {
    if (listType) rendered.push(`</${listType}>`)
    listType = ''
  }
  for (const line of lines) {
    const codePlaceholder = /^@@CODE_BLOCK_(\d+)@@$/.exec(line.trim())
    if (codePlaceholder) {
      closeList()
      rendered.push(codeBlocks[Number(codePlaceholder[1])] || '')
      continue
    }
    const unordered = /^[-*] (.+)$/.exec(line)
    const ordered = /^\d+\. (.+)$/.exec(line)
    if (unordered || ordered) {
      const nextType = unordered ? 'ul' : 'ol'
      if (listType && listType !== nextType) closeList()
      if (!listType) {
        listType = nextType
        rendered.push(`<${nextType}>`)
      }
      rendered.push(`<li>${inlineMarkdown((unordered || ordered)?.[1] || '')}</li>`)
      continue
    }
    closeList()
    const heading = /^(#{1,3})\s+(.+)$/.exec(line)
    if (heading) {
      const level = heading[1].length + 2
      rendered.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`)
    } else if (/^>\s?/.test(line)) {
      rendered.push(`<blockquote>${inlineMarkdown(line.replace(/^>\s?/, ''))}</blockquote>`)
    } else if (/^\s*(?:---+|___+)\s*$/.test(line)) {
      rendered.push('<hr>')
    } else if (line.trim()) {
      rendered.push(`<p>${inlineMarkdown(line)}</p>`)
    } else {
      rendered.push('<br>')
    }
  }
  closeList()
  return rendered.join('')
})
</script>

<template>
  <!-- 原始 HTML 在解析前全部转义，v-html 只接收本组件生成的白名单标签。 -->
  <div class="markdown-content" v-html="html" />
</template>
