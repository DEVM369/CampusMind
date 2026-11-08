import * as api from '../api.js'
import { ref, typedRef } from '../vue.js'

export const ToolsView = {
  setup() {
    const tab = typedRef<'course' | 'research' | 'library'>('course')
    const query = ref('')
    const busy = ref(false)
    const error = ref('')
    const result = typedRef<Record<string, unknown> | null>(null)

    async function run() {
      const text = query.value.trim()
      if (!text) return
      busy.value = true
      error.value = ''
      result.value = null
      try {
        if (tab.value === 'course') result.value = await api.courseQuery(text)
        else if (tab.value === 'research') result.value = await api.researchQuery(text)
        else result.value = await api.librarySearch(text)
      } catch (exc) {
        error.value = exc instanceof Error ? exc.message : String(exc)
      } finally {
        busy.value = false
      }
    }

    return { tab, query, busy, error, result, run }
  },
  template: `
  <section class="page">
    <header class="page-header"><div><span class="eyebrow">CAMPUS TOOLS</span><h1>校园业务工具</h1><p>直接调用结构化只读工具；写操作仍由 Agent + HITL 管控。</p></div></header>
    <div class="panel-card tool-console"><div class="tabs"><button :class="{active:tab==='course'}" @click="tab='course'">课程</button><button :class="{active:tab==='research'}" @click="tab='research'">科研</button><button :class="{active:tab==='library'}" @click="tab='library'">图书</button></div><div v-if="error" class="alert error page-feedback">{{error}}</div><textarea v-model="query" rows="4" :placeholder="tab==='course'?'例如：机器学习有哪些先修课程？':tab==='research'?'例如：有哪些人工智能方向的教师？':'例如：机器学习相关图书'"></textarea><div class="tool-actions"><button class="btn primary" :disabled="busy || !query.trim()" @click="run">{{busy?'查询中…':'执行查询'}}</button></div><pre v-if="result" class="json-preview large">{{JSON.stringify(result,null,2)}}</pre></div>
  </section>`
}
