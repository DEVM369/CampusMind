import * as api from '../api.js';
import { onMounted, ref, typedRef } from '../vue.js';
export const SystemView = {
    setup() {
        const health = typedRef(null);
        const database = typedRef(null);
        const rag = typedRef(null);
        const model = typedRef(null);
        const busy = ref(false);
        const modelBusy = ref(false);
        const error = ref('');
        async function refresh() {
            busy.value = true;
            error.value = '';
            try {
                const [h, d, r] = await Promise.all([api.getHealth(), api.getDatabaseStatus(), api.getRagStatus()]);
                health.value = h;
                database.value = d;
                rag.value = r;
            }
            catch (exc) {
                error.value = exc instanceof Error ? exc.message : String(exc);
            }
            finally {
                busy.value = false;
            }
        }
        async function checkModel() {
            modelBusy.value = true;
            error.value = '';
            try {
                model.value = await api.modelCheck();
            }
            catch (exc) {
                error.value = exc instanceof Error ? exc.message : String(exc);
            }
            finally {
                modelBusy.value = false;
            }
        }
        onMounted(refresh);
        return { health, database, rag, model, busy, modelBusy, error, refresh, checkModel };
    },
    template: `
  <section class="page">
    <header class="page-header"><div><span class="eyebrow">OPERATIONS</span><h1>系统状态</h1><p>基础设施、数据库 Schema 与模型链路。</p></div><button class="btn secondary" :disabled="busy" @click="refresh">{{busy?'刷新中…':'刷新状态'}}</button></header>
    <div v-if="error" class="alert error page-feedback">{{error}}</div><div class="health-grid"><div v-for="(item,name) in health?.components||{}" class="health-card"><div class="health-head"><strong>{{name}}</strong><span class="status-dot" :class="item.status"></span></div><div class="health-status">{{item.status}}</div><p>{{item.message}}</p><small>{{Math.round(item.latency_ms)}} ms</small></div></div>
    <div class="two-column-grid system-grid"><div class="panel-card"><h3>模型配置</h3><div v-if="rag" class="kv-list"><div><span>LLM</span><b>{{rag.llm_model}}</b></div><div><span>Provider</span><b>{{rag.llm_provider}}</b></div><div><span>Embedding</span><b>{{rag.embedding_model}}</b></div><div><span>Dimensions</span><b>{{rag.embedding_dimensions}}</b></div></div><button class="btn primary" :disabled="modelBusy" @click="checkModel">{{modelBusy?'检查中…':'执行模型检查'}}</button><div v-if="model" class="model-results"><div class="alert" :class="model.embedding?.ok?'success':'error'">Embedding · {{model.embedding?.detail||'-'}}</div><div class="alert" :class="model.llm?.ok?'success':'error'">LLM · {{model.llm?.detail||'-'}}</div></div></div><div class="panel-card"><h3>PostgreSQL Schema</h3><pre v-if="database" class="json-preview">{{JSON.stringify(database,null,2)}}</pre><div v-else class="empty-state">暂无数据</div></div></div>
  </section>`
};
