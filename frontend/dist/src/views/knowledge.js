import * as api from '../api.js';
import { reactive, ref, typedRef } from '../vue.js';
export const KnowledgeView = {
    setup() {
        const fileInput = typedRef(null);
        const form = reactive({
            knowledgeBaseCode: 'campus-service', documentType: 'policy', version: '1.0',
            title: '', department: '', permissionLevel: 'campus',
        });
        const uploadBusy = ref(false);
        const inspectBusy = ref(false);
        const error = ref('');
        const notice = ref('');
        const uploadResult = typedRef(null);
        const documentId = ref('');
        const documentDetail = typedRef(null);
        const documentChunks = typedRef([]);
        async function upload() {
            const file = fileInput.value?.files?.[0];
            if (!file) {
                error.value = '请选择一个文件后再上传';
                return;
            }
            uploadBusy.value = true;
            error.value = '';
            notice.value = '';
            try {
                const payload = new FormData();
                payload.append('file', file);
                payload.append('knowledge_base_code', form.knowledgeBaseCode);
                payload.append('document_type', form.documentType);
                payload.append('version', form.version);
                payload.append('permission_level', form.permissionLevel);
                if (form.title)
                    payload.append('title', form.title);
                if (form.department)
                    payload.append('department', form.department);
                uploadResult.value = await api.uploadDocument(payload);
                documentId.value = String(uploadResult.value.document_id || '');
                notice.value = '文档已提交，解析结果已返回。';
            }
            catch (exc) {
                error.value = exc instanceof Error ? exc.message : String(exc);
            }
            finally {
                uploadBusy.value = false;
            }
        }
        async function inspect() {
            const id = documentId.value.trim();
            if (!id)
                return;
            inspectBusy.value = true;
            error.value = '';
            try {
                documentDetail.value = await api.getDocument(id);
                documentChunks.value = (await api.getDocumentChunks(id)).chunks || [];
            }
            catch (exc) {
                error.value = exc instanceof Error ? exc.message : String(exc);
            }
            finally {
                inspectBusy.value = false;
            }
        }
        return { fileInput, form, uploadBusy, inspectBusy, error, notice, uploadResult, documentId, documentDetail, documentChunks, upload, inspect };
    },
    template: `
  <section class="page">
    <header class="page-header"><div><span class="eyebrow">KNOWLEDGE BASE</span><h1>知识库管理</h1><p>上传文档并查看切片与版本信息。</p></div></header>
    <div v-if="error" class="alert error page-feedback">{{error}}</div>
    <div v-if="notice" class="alert success page-feedback">{{notice}}</div>
    <div class="two-column-grid">
      <div class="panel-card"><h3>文档入库</h3><label>文件<input ref="fileInput" class="file-input" type="file"></label><label>知识库代码<input v-model="form.knowledgeBaseCode"></label><label>文档类型<input v-model="form.documentType"></label><div class="form-grid"><label>版本<input v-model="form.version"></label><label>权限<select v-model="form.permissionLevel"><option>campus</option><option>public</option><option>private</option></select></label></div><label>标题（可选）<input v-model="form.title"></label><label>部门（可选）<input v-model="form.department"></label><button class="btn primary" :disabled="uploadBusy" @click="upload">{{uploadBusy?'上传中…':'上传并解析'}}</button><pre v-if="uploadResult" class="json-preview">{{JSON.stringify(uploadResult,null,2)}}</pre></div>
      <div class="panel-card"><h3>文档检查</h3><div class="lookup-row"><input v-model="documentId" placeholder="Document UUID"><button class="btn secondary" :disabled="inspectBusy || !documentId.trim()" @click="inspect">{{inspectBusy?'查询中…':'查询'}}</button></div><template v-if="documentDetail"><div class="document-meta"><b>{{documentDetail.title}}</b><span>{{documentDetail.status}} · {{documentDetail.document_type}}</span><small>{{documentDetail.object_key}}</small></div><h3>Chunks · {{documentChunks.length}}</h3><div class="chunk-list"><article v-for="chunk in documentChunks" class="chunk-card"><div><strong>#{{chunk.chunk_index}}</strong><span>{{chunk.section||chunk.chapter||'正文'}}</span></div><p>{{chunk.content}}</p></article></div></template><div v-else class="empty-state">输入 Document UUID 查看详情</div></div>
    </div>
  </section>`
};
