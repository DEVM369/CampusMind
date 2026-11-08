const API_BASE = location.port === '5173'
    ? 'http://127.0.0.1:8000/api/v1'
    : '/api/v1';
async function request(path, init = {}) {
    const headers = new Headers(init.headers || {});
    const isForm = init.body instanceof FormData;
    if (!isForm && !headers.has('Content-Type'))
        headers.set('Content-Type', 'application/json');
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 120_000);
    try {
        const response = await fetch(`${API_BASE}${path}`, {
            ...init,
            credentials: init.credentials ?? 'include',
            headers,
            signal: controller.signal,
        });
        const contentType = response.headers.get('content-type') || '';
        const payload = contentType.includes('application/json') ? await response.json() : await response.text();
        if (!response.ok) {
            const detail = typeof payload === 'object' && payload && 'detail' in payload
                ? payload.detail
                : payload;
            throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        }
        return payload;
    }
    finally {
        clearTimeout(timeout);
    }
}
export async function chat(mode, query, actorUserId) {
    const actor_user_id = actorUserId?.trim() || null;
    const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) });
    if (mode === 'rag')
        return post('/rag/chat', { query, top_k: 5 });
    if (mode === 'graph')
        return post('/graph-rag/chat', { query, max_paths: 12 });
    if (mode === 'hybrid')
        return post('/hybrid-rag/chat', { query, top_k: 6, max_paths: 12 });
    if (mode === 'agent')
        return post('/agent/chat', {
            query, actor_user_id, top_k: 6, max_paths: 12,
            max_retries: 1, max_answer_rewrites: 1, persist_trace: false,
        });
    if (mode === 'multi')
        return post('/multi-agent/chat', { query, actor_user_id, persist_trace: false });
    return post('/chat', { query, top_k: 6, max_paths: 12, actor_user_id });
}
export function routeQuery(query, actorUserId) {
    return request('/adaptive-rag/route', {
        method: 'POST',
        body: JSON.stringify({ query, top_k: 6, max_paths: 12, actor_user_id: actorUserId?.trim() || null }),
    });
}
export function resumeAgent(payload) {
    return request('/agent/resume', {
        method: 'POST',
        body: JSON.stringify({
            approval_id: payload.approval_id,
            actor_user_id: payload.actor_user_id,
            approved: payload.approved,
            room_id: payload.resource_id || null,
            book_id: payload.resource_id || null,
            resource_id: payload.resource_id || null,
        }),
    });
}
export const getHealth = () => request('/system/health');
export const getSystemReadiness = () => request('/system/readiness');
export const getDatabaseStatus = () => request('/system/database');
export const getRagStatus = () => request('/rag/status');
export const modelCheck = () => request('/rag/model-check', { method: 'POST' });
export const uploadDocument = (form) => request('/documents/upload', { method: 'POST', body: form });
export const getDocument = (id) => request(`/documents/${encodeURIComponent(id)}`);
export const getDocumentChunks = (id) => request(`/documents/${encodeURIComponent(id)}/chunks`);
export const courseQuery = (query) => request('/tools/course/query', { method: 'POST', body: JSON.stringify({ query }) });
export const researchQuery = (query) => request('/tools/research/query', { method: 'POST', body: JSON.stringify({ query }) });
export const librarySearch = (query) => request('/tools/library/search', { method: 'POST', body: JSON.stringify({ query, available_only: false, limit: 8 }) });
// student_portal_api_v1
function actorQuery(actorUserId) {
    return encodeURIComponent(actorUserId.trim());
}
export const getStudentProfile = (actorUserId) => request(`/tools/student/profile?actor_user_id=${actorQuery(actorUserId)}`);
export const getStudentCredits = (actorUserId) => request(`/tools/student/credits?actor_user_id=${actorQuery(actorUserId)}`);
export const getStudentCourses = (actorUserId) => request(`/tools/student/courses?actor_user_id=${actorQuery(actorUserId)}`);
export const getStudentGraduation = (actorUserId) => request(`/tools/student/graduation-progress?actor_user_id=${actorQuery(actorUserId)}`);
export const getLibraryReservations = (actorUserId) => request(`/tools/library/reservations?actor_user_id=${actorQuery(actorUserId)}`);
export const getClassroomReservations = (actorUserId) => request(`/tools/classroom/reservations?actor_user_id=${actorQuery(actorUserId)}`);
// graph_visualization_api_v1
export const getGraphStats = () => request('/graph/stats');
export const getGraphOntology = () => request('/graph/ontology');
export const searchGraph = (query, maxPaths = 12) => request('/graph-rag/search', {
    method: 'POST',
    body: JSON.stringify({
        query,
        max_paths: maxPaths,
    }),
});
// execution_trace_api_v1
export const getExecutionTraces = (actorUserId, limit = 30) => request(`/agent/traces?actor_user_id=${encodeURIComponent(actorUserId.trim())}&limit=${limit}`);
export const getExecutionTrace = (traceId, actorUserId) => request(`/agent/traces/${encodeURIComponent(traceId)}?actor_user_id=${encodeURIComponent(actorUserId.trim())}`);
// admin_dashboard_api_v1
export const getAdminDashboard = (actorUserId) => request(`/admin/dashboard?actor_user_id=${encodeURIComponent(actorUserId.trim())}&recent_limit=8`);
export const getAdminSystemHealth = () => request('/system/health');
// admin_dashboard_api_v2
export const getAdminUsers = (actorUserId) => request(`/admin/users?actor_user_id=${encodeURIComponent(actorUserId.trim())}&limit=200`);
export const getAdminKnowledge = (actorUserId) => request(`/admin/knowledge?actor_user_id=${encodeURIComponent(actorUserId.trim())}&document_limit=50`);
export const getAdminEvaluations = (actorUserId) => request(`/admin/evaluations?actor_user_id=${encodeURIComponent(actorUserId.trim())}&result_limit=40`);
export const getAdminAudits = (actorUserId) => request(`/admin/audits?actor_user_id=${encodeURIComponent(actorUserId.trim())}&limit=50`);
// evaluation_runner_api_v1
export const runAdminEvaluation = (datasetId, actorUserId) => request(`/admin/evaluations/${encodeURIComponent(datasetId)}/run?actor_user_id=${encodeURIComponent(actorUserId.trim())}`, {
    method: 'POST',
});
export const getAdminAgents = (actorUserId) => request(`/admin/agents?actor_user_id=${encodeURIComponent(actorUserId.trim())}`);
export const getAdminTools = (actorUserId) => request(`/admin/tools?actor_user_id=${encodeURIComponent(actorUserId.trim())}`);
export const getAdminPrompts = (actorUserId) => request(`/admin/prompts?actor_user_id=${encodeURIComponent(actorUserId.trim())}`);
export const getAdminGraphEntities = (actorUserId, entityType = '', keyword = '', offset = 0, limit = 50) => {
    const query = [
        `actor_user_id=${encodeURIComponent(actorUserId.trim())}`,
        `offset=${encodeURIComponent(String(offset))}`,
        `limit=${encodeURIComponent(String(limit))}`,
    ];
    if (entityType.trim()) {
        query.push(`entity_type=${encodeURIComponent(entityType.trim())}`);
    }
    if (keyword.trim()) {
        query.push(`keyword=${encodeURIComponent(keyword.trim())}`);
    }
    return request(`/admin/graph/entities?${query.join('&')}`);
};
export const getAdminGraphRelations = (actorUserId, relationType = '', keyword = '', offset = 0, limit = 50) => {
    const query = [
        `actor_user_id=${encodeURIComponent(actorUserId.trim())}`,
        `offset=${encodeURIComponent(String(offset))}`,
        `limit=${encodeURIComponent(String(limit))}`,
    ];
    if (relationType.trim()) {
        query.push(`relation_type=${encodeURIComponent(relationType.trim())}`);
    }
    if (keyword.trim()) {
        query.push(`keyword=${encodeURIComponent(keyword.trim())}`);
    }
    return request(`/admin/graph/relations?${query.join('&')}`);
};
export const getAdminGraphEntityContext = (actorUserId, entityId, limit = 100) => request(`/admin/graph/entity-context?actor_user_id=${encodeURIComponent(actorUserId.trim())}&entity_id=${encodeURIComponent(entityId.trim())}&limit=${encodeURIComponent(String(limit))}`);
export const getAdminDocumentGraphStatus = (actorUserId, documentId) => request(`/admin/documents/${encodeURIComponent(documentId.trim())}/graph-status?actor_user_id=${encodeURIComponent(actorUserId.trim())}`);
export const getSourceChunkGraph = (chunkId) => request(`/graph/ingest/chunks/${encodeURIComponent(chunkId.trim())}`);
export const authLogin = (username, password) => request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({
        username,
        password,
    }),
});
export const authMe = () => request('/auth/me');
export const authLogout = () => request('/auth/logout', {
    method: 'POST',
});
export const getConversations = () => request('/conversations');
export const createConversation = (title) => request('/conversations', {
    method: 'POST',
    body: JSON.stringify({
        title: title || null,
    }),
});
export const getConversation = (conversationId) => request(`/conversations/${encodeURIComponent(conversationId)}`);
export const deleteConversation = (conversationId) => request(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'DELETE',
});
export const conversationChat = (conversationId, query) => request(`/conversations/${encodeURIComponent(conversationId)}/chat`, {
    method: 'POST',
    body: JSON.stringify({
        query,
        top_k: 6,
        max_paths: 12,
    }),
});
export const appendConversationMessages = (conversationId, messages) => request(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: 'POST',
    body: JSON.stringify({
        messages,
    }),
});
