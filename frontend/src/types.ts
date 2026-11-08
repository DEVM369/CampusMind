export type ChatMode = 'smart' | 'rag' | 'graph' | 'hybrid' | 'agent' | 'multi'
export type ViewName = 'chat' | 'student' | 'knowledge' | 'graph' | 'trace' | 'admin' | 'tools' | 'system'

export interface Citation {
  chunk_id: string
  document_id: string
  title: string
  page?: number | null
  section?: string | null
  chapter?: string | null
  object_key: string
  quote: string
}

export interface GraphPath {
  source_name: string
  source_type: string
  relation_type: string
  target_name: string
  target_type: string
  path_id?: string | null
  hop_index?: number
  text?: string
}

export interface RouteDecision {
  route: string
  intent: string
  complexity: string
  confidence: number
  reasons: string[]
  executable: boolean
  requires_agent: boolean
  source: string
}

export interface ChatResult {
  trace_id?: string
  query?: string
  answer: string
  citations?: Citation[]
  graph_paths?: GraphPath[]
  diagnostics?: string[]
  raw_path_count?: number
  recovered_evidence_count?: number
  decision?: RouteDecision
  planned_route?: string
  active_route?: string
  executed_route?: string | null
  fallback_reason?: string | null
  deferred_capability?: string | null
  structured_data?: Record<string, unknown> | null
  pending_approval?: boolean
  status?: string
  elapsed_ms?: number
  steps?: Array<Record<string, unknown>>
  child_results?: Array<Record<string, unknown>>
  evidence?: Array<Record<string, unknown>>
  retrieval?: Record<string, unknown> | null
  [key: string]: unknown
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: number
  mode?: ChatMode
  result?: ChatResult
  error?: string
}

export interface HealthComponent {
  status: 'healthy' | 'unhealthy'
  message: string
  latency_ms: number
  details: Record<string, unknown>
}

export interface HealthResponse {
  service: string
  status: 'healthy' | 'degraded'
  checked_at: string
  components: Record<string, HealthComponent>
}
