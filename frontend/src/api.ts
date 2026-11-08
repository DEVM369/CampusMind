import type { ChatMode, ChatResult, HealthResponse } from './types.js'

const API_BASE = location.port === '5173'
  ? 'http://127.0.0.1:8000/api/v1'
  : '/api/v1'

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {})
  const isForm = init.body instanceof FormData
  if (!isForm && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 120_000)
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: init.credentials ?? 'include',
      headers,
      signal: controller.signal,
    })
    const contentType = response.headers.get('content-type') || ''
    const payload = contentType.includes('application/json') ? await response.json() : await response.text()
    if (!response.ok) {
      const detail = typeof payload === 'object' && payload && 'detail' in payload
        ? (payload as { detail: unknown }).detail
        : payload
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    }
    return payload as T
  } finally {
    clearTimeout(timeout)
  }
}

export async function chat(mode: ChatMode, query: string, actorUserId?: string): Promise<ChatResult> {
  const actor_user_id = actorUserId?.trim() || null
  const post = (path: string, body: unknown) => request<ChatResult>(path, { method: 'POST', body: JSON.stringify(body) })
  if (mode === 'rag') return post('/rag/chat', { query, top_k: 5 })
  if (mode === 'graph') return post('/graph-rag/chat', { query, max_paths: 12 })
  if (mode === 'hybrid') return post('/hybrid-rag/chat', { query, top_k: 6, max_paths: 12 })
  if (mode === 'agent') return post('/agent/chat', {
    query, actor_user_id, top_k: 6, max_paths: 12,
    max_retries: 1, max_answer_rewrites: 1, persist_trace: false,
  })
  if (mode === 'multi') return post('/multi-agent/chat', { query, actor_user_id, persist_trace: false })
  return post('/chat', { query, top_k: 6, max_paths: 12, actor_user_id })
}

export function routeQuery(query: string, actorUserId?: string) {
  return request<Record<string, unknown>>('/adaptive-rag/route', {
    method: 'POST',
    body: JSON.stringify({ query, top_k: 6, max_paths: 12, actor_user_id: actorUserId?.trim() || null }),
  })
}

export function resumeAgent(payload: { approval_id: string; actor_user_id: string; approved: boolean; resource_id?: string }) {
  return request<Record<string, unknown>>('/agent/resume', {
    method: 'POST',
    body: JSON.stringify({
      approval_id: payload.approval_id,
      actor_user_id: payload.actor_user_id,
      approved: payload.approved,
      room_id: payload.resource_id || null,
      book_id: payload.resource_id || null,
      resource_id: payload.resource_id || null,
    }),
  })
}

export const getHealth = () => request<HealthResponse>('/system/health')

export const getSystemReadiness = () =>
  request<Record<string, any>>(
    '/system/readiness'
  )
export const getDatabaseStatus = () => request<Record<string, unknown>>('/system/database')
export const getRagStatus = () => request<Record<string, unknown>>('/rag/status')
export const modelCheck = () => request<Record<string, unknown>>('/rag/model-check', { method: 'POST' })

export const uploadDocument = (form: FormData) => request<Record<string, unknown>>('/documents/upload', { method: 'POST', body: form })
export const getDocument = (id: string) => request<Record<string, unknown>>(`/documents/${encodeURIComponent(id)}`)
export const getDocumentChunks = (id: string) => request<{ chunks: Array<Record<string, unknown>> }>(`/documents/${encodeURIComponent(id)}/chunks`)

export const courseQuery = (query: string) => request<Record<string, unknown>>('/tools/course/query', { method: 'POST', body: JSON.stringify({ query }) })
export const researchQuery = (query: string) => request<Record<string, unknown>>('/tools/research/query', { method: 'POST', body: JSON.stringify({ query }) })
export const librarySearch = (query: string) => request<Record<string, unknown>>('/tools/library/search', { method: 'POST', body: JSON.stringify({ query, available_only: false, limit: 8 }) })


// student_portal_api_v1

function actorQuery(
  actorUserId: string,
): string {
  return encodeURIComponent(
    actorUserId.trim(),
  )
}

export const getStudentProfile = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/tools/student/profile?actor_user_id=${actorQuery(actorUserId)}`
  )

export const getStudentCredits = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/tools/student/credits?actor_user_id=${actorQuery(actorUserId)}`
  )

export const getStudentCourses = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/tools/student/courses?actor_user_id=${actorQuery(actorUserId)}`
  )

export const getStudentGraduation = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/tools/student/graduation-progress?actor_user_id=${actorQuery(actorUserId)}`
  )

export const getLibraryReservations = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/tools/library/reservations?actor_user_id=${actorQuery(actorUserId)}`
  )

export const getClassroomReservations = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/tools/classroom/reservations?actor_user_id=${actorQuery(actorUserId)}`
  )


// graph_visualization_api_v1

export const getGraphStats = () =>
  request<Record<string, any>>(
    '/graph/stats'
  )

export const getGraphOntology = () =>
  request<Record<string, any>>(
    '/graph/ontology'
  )

export const searchGraph = (
  query: string,
  maxPaths = 12,
) =>
  request<Record<string, any>>(
    '/graph-rag/search',
    {
      method: 'POST',
      body: JSON.stringify({
        query,
        max_paths: maxPaths,
      }),
    },
  )


// execution_trace_api_v1

export const getExecutionTraces = (
  actorUserId: string,
  limit = 30,
) =>
  request<Record<string, any>>(
    `/agent/traces?actor_user_id=${encodeURIComponent(actorUserId.trim())}&limit=${limit}`
  )

export const getExecutionTrace = (
  traceId: string,
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/agent/traces/${encodeURIComponent(traceId)}?actor_user_id=${encodeURIComponent(actorUserId.trim())}`
  )


// admin_dashboard_api_v1

export const getAdminDashboard = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/admin/dashboard?actor_user_id=${encodeURIComponent(actorUserId.trim())}&recent_limit=8`
  )

export const getAdminSystemHealth = () =>
  request<Record<string, any>>(
    '/system/health'
  )


// admin_dashboard_api_v2

export const getAdminUsers = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/admin/users?actor_user_id=${encodeURIComponent(actorUserId.trim())}&limit=200`
  )

export const getAdminKnowledge = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/admin/knowledge?actor_user_id=${encodeURIComponent(actorUserId.trim())}&document_limit=50`
  )

export const getAdminEvaluations = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/admin/evaluations?actor_user_id=${encodeURIComponent(actorUserId.trim())}&result_limit=40`
  )

export const getAdminAudits = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/admin/audits?actor_user_id=${encodeURIComponent(actorUserId.trim())}&limit=50`
  )


// evaluation_runner_api_v1

export const runAdminEvaluation = (
  datasetId: string,
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/admin/evaluations/${encodeURIComponent(datasetId)}/run?actor_user_id=${encodeURIComponent(actorUserId.trim())}`,
    {
      method: 'POST',
    },
  )

export const getAdminAgents = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/admin/agents?actor_user_id=${encodeURIComponent(actorUserId.trim())}`,
  )

export const getAdminTools = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/admin/tools?actor_user_id=${encodeURIComponent(actorUserId.trim())}`,
  )

export const getAdminPrompts = (
  actorUserId: string,
) =>
  request<Record<string, any>>(
    `/admin/prompts?actor_user_id=${encodeURIComponent(actorUserId.trim())}`,
  )



export const getAdminGraphEntities = (
  actorUserId: string,
  entityType = '',
  keyword = '',
  offset = 0,
  limit = 50,
) => {
  const query = [
    `actor_user_id=${encodeURIComponent(actorUserId.trim())}`,
    `offset=${encodeURIComponent(String(offset))}`,
    `limit=${encodeURIComponent(String(limit))}`,
  ]

  if (entityType.trim()) {
    query.push(
      `entity_type=${encodeURIComponent(entityType.trim())}`
    )
  }

  if (keyword.trim()) {
    query.push(
      `keyword=${encodeURIComponent(keyword.trim())}`
    )
  }

  return request<Record<string, any>>(
    `/admin/graph/entities?${query.join('&')}`,
  )
}


export const getAdminGraphRelations = (
  actorUserId: string,
  relationType = '',
  keyword = '',
  offset = 0,
  limit = 50,
) => {
  const query = [
    `actor_user_id=${encodeURIComponent(actorUserId.trim())}`,
    `offset=${encodeURIComponent(String(offset))}`,
    `limit=${encodeURIComponent(String(limit))}`,
  ]

  if (relationType.trim()) {
    query.push(
      `relation_type=${encodeURIComponent(relationType.trim())}`
    )
  }

  if (keyword.trim()) {
    query.push(
      `keyword=${encodeURIComponent(keyword.trim())}`
    )
  }

  return request<Record<string, any>>(
    `/admin/graph/relations?${query.join('&')}`,
  )
}

export const getAdminGraphEntityContext = (
  actorUserId: string,
  entityId: string,
  limit = 100,
) =>
  request<Record<string, any>>(
    `/admin/graph/entity-context?actor_user_id=${encodeURIComponent(actorUserId.trim())}&entity_id=${encodeURIComponent(entityId.trim())}&limit=${encodeURIComponent(String(limit))}`,
  )

export const getAdminDocumentGraphStatus = (
  actorUserId: string,
  documentId: string,
) =>
  request<Record<string, any>>(
    `/admin/documents/${encodeURIComponent(documentId.trim())}/graph-status?actor_user_id=${encodeURIComponent(actorUserId.trim())}`,
  )

export const getSourceChunkGraph = (
  chunkId: string,
) =>
  request<Record<string, any>>(
    `/graph/ingest/chunks/${encodeURIComponent(chunkId.trim())}`,
  )




// auth_conversation_v1

export interface AuthUser {
  user_id: string
  username: string
  full_name: string
  status: string
  is_superuser: boolean
  roles: string[]
}

export interface AuthLoginResponse {
  status: string
  user: AuthUser
}

export interface ConversationSummary {
  id: string
  title: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface ConversationMessageRecord {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Array<Record<string, any>>
  metadata_json: Record<string, any>
  created_at: string
}

export interface ConversationDetail
  extends ConversationSummary {
  messages: ConversationMessageRecord[]
}

export interface ConversationMessageWrite {
  role: 'user' | 'assistant'
  content: string
  citations?: Array<Record<string, any>>
  metadata_json?: Record<string, any>
}

export const authLogin = (
  username: string,
  password: string,
) =>
  request<AuthLoginResponse>(
    '/auth/login',
    {
      method: 'POST',
      body: JSON.stringify({
        username,
        password,
      }),
    },
  )

export const authMe = () =>
  request<AuthUser>(
    '/auth/me',
  )

export const authLogout = () =>
  request<{ status: string }>(
    '/auth/logout',
    {
      method: 'POST',
    },
  )

export const getConversations = () =>
  request<ConversationSummary[]>(
    '/conversations',
  )

export const createConversation = (
  title?: string,
) =>
  request<ConversationSummary>(
    '/conversations',
    {
      method: 'POST',
      body: JSON.stringify({
        title: title || null,
      }),
    },
  )

export const getConversation = (
  conversationId: string,
) =>
  request<ConversationDetail>(
    `/conversations/${
      encodeURIComponent(
        conversationId,
      )
    }`,
  )

export const deleteConversation = (
  conversationId: string,
) =>
  request<void>(
    `/conversations/${
      encodeURIComponent(
        conversationId,
      )
    }`,
    {
      method: 'DELETE',
    },
  )

export const conversationChat = (
  conversationId: string,
  query: string,
) =>
  request<ChatResult>(
    `/conversations/${
      encodeURIComponent(
        conversationId,
      )
    }/chat`,
    {
      method: 'POST',
      body: JSON.stringify({
        query,
        top_k: 6,
        max_paths: 12,
      }),
    },
  )

export const appendConversationMessages = (
  conversationId: string,
  messages: ConversationMessageWrite[],
) =>
  request<{
    status: string
    appended: number
  }>(
    `/conversations/${
      encodeURIComponent(
        conversationId,
      )
    }/messages`,
    {
      method: 'POST',
      body: JSON.stringify({
        messages,
      }),
    },
  )
