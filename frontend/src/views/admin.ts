import {
  computed,
  onMounted,
  ref,
  typedRef,
  watch,
} from '../vue.js'

import {
  getAdminAudits,
  getAdminDashboard,
  getAdminEvaluations,
  runAdminEvaluation,
  getAdminKnowledge,
  getAdminSystemHealth,
  getAdminUsers,
  getGraphStats,
} from '../api.js'

import { AdminIntelligencePanel } from './adminIntelligence.js'
import { AdminGraphPanel } from './adminGraph.js'
import { AdminDocumentInspector } from './adminDocumentInspector.js'
import { AdminSystemPanel } from './adminSystem.js'


type AdminTab =
  | 'overview'
  | 'users'
  | 'knowledge'
  | 'graph'
  | 'agents'
  | 'tools'
  | 'prompts'
  | 'evaluation'
  | 'system'
  | 'audit'


export const AdminView = {
  components: {
    AdminIntelligencePanel,
    AdminGraphPanel,
    AdminDocumentInspector,
    AdminSystemPanel,
  },

  props: {
    actorUserId: {
      type: String,
      default: '',
    },
  },

  emits: ['request-settings'],

  setup(
    props: any,
    context: any,
  ) {
    const loading = ref(false)
    const error = ref('')
    const forbidden = ref(false)
    const runningDatasetId = ref('')
    const evaluationRunMessage = ref('')

    const activeTab =
      typedRef<AdminTab>(
        'overview',
      )

    const dashboard =
      typedRef<Record<string, any>>({})

    const health =
      typedRef<Record<string, any>>({})

    const graph =
      typedRef<Record<string, any>>({})

    const usersData =
      typedRef<Record<string, any>>({})

    const knowledgeData =
      typedRef<Record<string, any>>({})

    const evaluationData =
      typedRef<Record<string, any>>({})

    const auditData =
      typedRef<Record<string, any>>({})

    const tabs = [
      {
        value: 'overview',
        label: '\u603b\u89c8',
      },
      {
        value: 'users',
        label: '\u7528\u6237\u4e0e\u89d2\u8272',
      },
      {
        value: 'knowledge',
        label: '\u77e5\u8bc6\u5e93\u4e0e\u6587\u6863',
      },
      {
        value: 'graph',
        label: '\u56fe\u8c31',
      },
      {
        value: 'agents',
        label: '\u667a\u80fd\u4f53',
      },
      {
        value: 'tools',
        label: '\u5de5\u5177',
      },
      {
        value: 'prompts',
        label: '\u63d0\u793a\u8bcd',
      },
      {
        value: 'evaluation',
        label: '\u8bc4\u4f30',
      },
      {
        value: 'system',
        label: '\u7cfb\u7edf',
      },
      {
        value: 'audit',
        label: '\u5ba1\u8ba1\u65e5\u5fd7',
      },
    ]

    const counts = computed(
      () =>
        dashboard.value.counts
        || {},
    )

    const recentRuns = computed(
      () =>
        Array.isArray(
          dashboard.value
            .recent_runs,
        )
          ? dashboard.value
              .recent_runs
          : [],
    )

    const recentAudits = computed(
      () =>
        Array.isArray(
          dashboard.value
            .recent_audits,
        )
          ? dashboard.value
              .recent_audits
          : [],
    )

    const healthComponents = computed(
      () => {
        const value =
          health.value.components

        if (
          !value
          || typeof value !== 'object'
        ) {
          return []
        }

        return Object.entries(value)
          .map(
            ([name, item]) => ({
              name,
              ...(
                item
                && typeof item
                   === 'object'
                  ? item as Record<
                      string,
                      any
                    >
                  : {}
              ),
            }),
          )
      },
    )

    const users = computed(
      () =>
        Array.isArray(
          usersData.value.users,
        )
          ? usersData.value.users
          : [],
    )

    const roles = computed(
      () =>
        Array.isArray(
          usersData.value.roles,
        )
          ? usersData.value.roles
          : [],
    )

    const knowledgeBases = computed(
      () =>
        Array.isArray(
          knowledgeData.value
            .knowledge_bases,
        )
          ? knowledgeData.value
              .knowledge_bases
          : [],
    )

    const documents = computed(
      () =>
        Array.isArray(
          knowledgeData.value.documents,
        )
          ? knowledgeData.value.documents
          : [],
    )

    const datasets = computed(
      () =>
        Array.isArray(
          evaluationData.value.datasets,
        )
          ? evaluationData.value.datasets
          : [],
    )

    const evaluationResults = computed(
      () =>
        Array.isArray(
          evaluationData.value.results,
        )
          ? evaluationData.value.results
          : [],
    )

    const auditLogs = computed(
      () =>
        Array.isArray(
          auditData.value.logs,
        )
          ? auditData.value.logs
          : [],
    )

    function requestSettings() {
      context.emit(
        'request-settings',
      )
    }

    function statusLabel(
      value: unknown,
    ): string {
      const key = String(
        value || '',
      ).toLowerCase()

      const map:
        Record<string, string> = {
          healthy: '\u5065\u5eb7',
          ready: '\u5c31\u7eea',
          completed: '\u5df2\u5b8c\u6210',
          active: '\u6b63\u5e38',
          running: '\u8fd0\u884c\u4e2d',
          draft: '\u8349\u7a3f',
          uploaded: '\u5df2\u4e0a\u4f20',
          indexed: '\u5df2\u7d22\u5f15',
          degraded: '\u964d\u7ea7',
          unhealthy: '\u5f02\u5e38',
          failed: '\u5931\u8d25',
        }

      return map[key]
        || String(value || '-')
    }

    function statusTone(
      value: unknown,
    ): string {
      const key = String(
        value || '',
      ).toLowerCase()

      if (
        [
          'healthy',
          'ready',
          'completed',
          'active',
          'indexed',
        ].includes(key)
      ) {
        return 'success'
      }

      if (
        [
          'unhealthy',
          'failed',
          'error',
        ].includes(key)
      ) {
        return 'danger'
      }

      return 'pending'
    }

    function formatTime(
      value: unknown,
    ): string {
      if (!value) return '-'

      const parsed =
        new Date(
          String(value),
        )

      if (
        Number.isNaN(
          parsed.getTime(),
        )
      ) {
        return String(value)
      }

      return parsed.toLocaleString(
        'zh-CN',
        {
          hour12: false,
        },
      )
    }

    function formatLatency(
      value: unknown,
    ): string {
      const number =
        Number(value)

      if (
        !Number.isFinite(number)
      ) {
        return '-'
      }

      return number < 1000
        ? Math.round(number)
          + ' ms'
        : (
            number / 1000
          ).toFixed(2)
          + ' s'
    }

    function percent(
      value: unknown,
    ): string {
      if (
        value === null
        || value === undefined
      ) {
        return '-'
      }

      const number =
        Number(value)

      if (
        !Number.isFinite(number)
      ) {
        return '-'
      }

      return (
        number * 100
      ).toFixed(1)
        + '%'
    }

    function roleText(
      value: unknown,
    ): string {
      if (!Array.isArray(value)) {
        return '-'
      }

      const codes =
        value.map(
          item =>
            String(
              item?.code
              || item?.name
              || '',
            ),
        )
        .filter(Boolean)

      return codes.length
        ? codes.join(', ')
        : '-'
    }

    async function runEvaluation(
      datasetId: string,
    ) {
      const actor =
        String(
          props.actorUserId
          || '',
        ).trim()

      if (
        !actor
        || !datasetId
        || runningDatasetId.value
      ) {
        return
      }

      runningDatasetId.value =
        datasetId

      evaluationRunMessage.value = ''
      error.value = ''

      try {
        const result =
          await runAdminEvaluation(
            datasetId,
            actor,
          )

        evaluationRunMessage.value =
          '\u8bc4\u4f30\u5b8c\u6210\uff1a'
          + String(
              result.passed_count
              ?? 0
            )
          + '/'
          + String(
              result.case_count
              ?? 0
            )
          + '\u901a\u8fc7\uff0c\u901a\u8fc7\u7387 '
          + percent(
              result.pass_rate
            )

        evaluationData.value =
          await getAdminEvaluations(
            actor,
          )

        dashboard.value =
          await getAdminDashboard(
            actor,
          )

      } catch (exc) {
        error.value =
          exc instanceof Error
            ? exc.message
            : String(exc)

      } finally {
        runningDatasetId.value = ''
      }
    }

    async function loadDashboard() {
      const actor =
        String(
          props.actorUserId
          || '',
        ).trim()

      error.value = ''
      forbidden.value = false

      if (!actor) return

      loading.value = true

      try {
        dashboard.value =
          await getAdminDashboard(
            actor,
          )

        const results =
          await Promise.allSettled([
            getAdminSystemHealth(),
            getGraphStats(),
            getAdminUsers(actor),
            getAdminKnowledge(actor),
            getAdminEvaluations(actor),
            getAdminAudits(actor),
          ])

        if (
          results[0].status
          === 'fulfilled'
        ) {
          health.value =
            results[0].value
        }

        if (
          results[1].status
          === 'fulfilled'
        ) {
          graph.value =
            results[1].value
        }

        if (
          results[2].status
          === 'fulfilled'
        ) {
          usersData.value =
            results[2].value
        }

        if (
          results[3].status
          === 'fulfilled'
        ) {
          knowledgeData.value =
            results[3].value
        }

        if (
          results[4].status
          === 'fulfilled'
        ) {
          evaluationData.value =
            results[4].value
        }

        if (
          results[5].status
          === 'fulfilled'
        ) {
          auditData.value =
            results[5].value
        }
      } catch (exc) {
        const message =
          exc instanceof Error
            ? exc.message
            : String(exc)

        if (
          message.includes('403')
          || message.includes(
            'RBAC deny'
          )
          || message.includes(
            'not authorized'
          )
        ) {
          forbidden.value = true
        } else {
          error.value = message
        }
      } finally {
        loading.value = false
      }
    }

    watch(
      () => props.actorUserId,
      () => {
        loadDashboard()
      },
    )

    onMounted(
      () => {
        loadDashboard()
      },
    )

    return {
      loading,
      error,
      forbidden,
      runningDatasetId,
      evaluationRunMessage,
      activeTab,
      tabs,
      dashboard,
      health,
      graph,
      counts,
      recentRuns,
      recentAudits,
      healthComponents,
      usersData,
      users,
      roles,
      knowledgeData,
      knowledgeBases,
      documents,
      evaluationData,
      datasets,
      evaluationResults,
      auditData,
      auditLogs,
      requestSettings,
      runEvaluation,
      loadDashboard,
      statusLabel,
      statusTone,
      formatTime,
      formatLatency,
      percent,
      roleText,
    }
  },

  template: `
  <section class="page admin-page">
    <header class="page-header admin-header">
      <div>
        <span class="eyebrow">
          ADMIN CONTROL CENTER
        </span>

        <h1>
          &#31649;&#29702;&#21518;&#21488;
        </h1>

        <p>
          &#31995;&#32479;&#36164;&#28304;&#12289;&#30693;&#35782;&#24211;&#12289;Agent &#36816;&#34892;&#12289;&#35780;&#20272;&#19982;&#23457;&#35745;&#24635;&#35272;
        </p>
      </div>

      <button
        class="btn secondary"
        :disabled="
          loading
          || !actorUserId
        "
        @click="loadDashboard"
      >
        {{
          loading
            ? '\u5237\u65b0\u4e2d...'
            : '\u5237\u65b0\u540e\u53f0'
        }}
      </button>
    </header>

    <div
      v-if="!actorUserId"
      class="admin-access-card"
    >
      <div class="admin-access-icon">
        A
      </div>

      <h2>
        &#35831;&#20808;&#30331;&#24405;&#31649;&#29702;&#21592;&#36134;&#21495;
      </h2>

      <p>
        &#31649;&#29702;&#21592;&#36134;&#21495;&#21487;&#26597;&#30475;&#24182;&#31649;&#29702;&#31995;&#32479;&#36816;&#34892;&#36164;&#28304;&#12290;
      </p>

      <button
        class="btn primary"
        @click="requestSettings"
      >
        &#30331;&#24405;&#31649;&#29702;&#21592;&#36134;&#21495;
      </button>
    </div>

    <div
      v-else-if="forbidden"
      class="admin-access-card"
    >
      <div class="admin-access-icon denied">
        !
      </div>

      <h2>
        &#24403;&#21069;&#29992;&#25143;&#26080;&#31649;&#29702;&#21518;&#21488;&#26435;&#38480;
      </h2>

      <p>
        RBAC &#24050;&#38459;&#27490;&#35775;&#38382;&#12290;&#27492;&#39029;&#38754;&#20165;&#21521; system_admin / admin &#25110;&#26174;&#24335;&#25480;&#26435;&#36134;&#21495;&#24320;&#25918;&#12290;
      </p>
    </div>

    <template v-else>
      <div
        v-if="error"
        class="alert error admin-error"
      >
        {{error}}
      </div>

      <div class="admin-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          :class="{
            active:
              activeTab === tab.value
          }"
          @click="
            activeTab = tab.value
          "
        >
          {{tab.label}}
        </button>
      </div>

      <template
        v-if="
          activeTab === 'overview'
        "
      >
        <div class="admin-stat-grid">
          <article class="admin-stat-card">
            <span>
              &#29992;&#25143;
            </span>
            <strong>
              {{counts.users ?? '-'}}
            </strong>
            <small>
              {{counts.active_users ?? 0}}
              active
            </small>
          </article>

          <article class="admin-stat-card">
            <span>
              &#30693;&#35782;&#24211; / &#25991;&#26723;
            </span>
            <strong>
              {{
                counts.knowledge_bases
                ?? '-'
              }}
            </strong>
            <small>
              {{counts.documents ?? 0}}
              documents
            </small>
          </article>

          <article class="admin-stat-card">
            <span>
              Agent Runs
            </span>
            <strong>
              {{counts.agent_runs ?? '-'}}
            </strong>
            <small>
              {{
                counts.completed_agent_runs
                ?? 0
              }}
              completed
            </small>
          </article>

          <article class="admin-stat-card">
            <span>
              Audit Logs
            </span>
            <strong>
              {{counts.audit_logs ?? '-'}}
            </strong>
            <small>
              system audit
            </small>
          </article>
        </div>

        <div class="admin-overview-grid">
          <article class="panel-card">
            <div class="admin-section-head">
              <div>
                <span class="eyebrow">
                  INFRASTRUCTURE
                </span>
                <h3>
                  &#31995;&#32479;&#20581;&#24247;
                </h3>
              </div>

              <span
                class="admin-status"
                :class="
                  statusTone(
                    health.status
                  )
                "
              >
                {{
                  statusLabel(
                    health.status
                  )
                }}
              </span>
            </div>

            <div class="admin-health-grid">
              <div
                v-for="item in healthComponents"
                :key="item.name"
                class="admin-health-item"
              >
                <div>
                  <strong>
                    {{item.name}}
                  </strong>
                  <small>
                    {{item.message || ''}}
                  </small>
                </div>

                <span
                  class="admin-status"
                  :class="
                    statusTone(
                      item.status
                    )
                  "
                >
                  {{
                    statusLabel(
                      item.status
                    )
                  }}
                </span>
              </div>
            </div>
          </article>

          <article class="panel-card">
            <div class="admin-section-head">
              <div>
                <span class="eyebrow">
                  KNOWLEDGE GRAPH
                </span>
                <h3>
                  Neo4j &#22270;&#35889;
                </h3>
              </div>
            </div>

            <div class="admin-mini-metrics">
              <div>
                <strong>
                  {{graph.node_count ?? '-'}}
                </strong>
                <span>
                  &#33410;&#28857;
                </span>
              </div>

              <div>
                <strong>
                  {{
                    graph.relation_count
                    ?? '-'
                  }}
                </strong>
                <span>
                  &#20851;&#31995;
                </span>
              </div>

              <div>
                <strong>
                  {{
                    Object.keys(
                      graph.nodes_by_type
                      || {}
                    ).length
                  }}
                </strong>
                <span>
                  &#24050;&#36733;&#20837;&#31867;&#22411;
                </span>
              </div>
            </div>

            <div class="admin-ops-grid">
              <div>
                <span>Tool Calls</span>
                <strong>
                  {{counts.tool_calls ?? 0}}
                </strong>
              </div>

              <div>
                <span>HITL</span>
                <strong>
                  {{
                    counts.hitl_tool_calls
                    ?? 0
                  }}
                </strong>
              </div>

              <div>
                <span>Evaluation</span>
                <strong>
                  {{
                    counts.evaluation_results
                    ?? 0
                  }}
                </strong>
              </div>

              <div>
                <span>Pass Rate</span>
                <strong>
                  {{
                    percent(
                      dashboard
                        .evaluation_pass_rate
                    )
                  }}
                </strong>
              </div>
            </div>
          </article>
        </div>

        <div class="admin-table-grid">
          <article class="panel-card">
            <div class="admin-section-head">
              <div>
                <span class="eyebrow">
                  RECENT AGENT RUNS
                </span>
                <h3>
                  &#26368;&#36817; Agent &#36816;&#34892;
                </h3>
              </div>
            </div>

            <div
              v-if="recentRuns.length"
              class="admin-table-wrap"
            >
              <table class="admin-table">
                <thead>
                  <tr>
                    <th>Query</th>
                    <th>Strategy</th>
                    <th>Status</th>
                    <th>Latency</th>
                  </tr>
                </thead>

                <tbody>
                  <tr
                    v-for="item in recentRuns"
                    :key="item.trace_id"
                  >
                    <td>
                      <strong>
                        {{item.query}}
                      </strong>
                      <small>
                        {{
                          formatTime(
                            item.started_at
                          )
                        }}
                      </small>
                    </td>

                    <td>
                      {{
                        item.retrieval_strategy
                        || '-'
                      }}
                    </td>

                    <td>
                      <span
                        class="admin-status"
                        :class="
                          statusTone(
                            item.status
                          )
                        "
                      >
                        {{
                          statusLabel(
                            item.status
                          )
                        }}
                      </span>
                    </td>

                    <td>
                      {{
                        formatLatency(
                          item.latency_ms
                        )
                      }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>

          <article class="panel-card">
            <div class="admin-section-head">
              <div>
                <span class="eyebrow">
                  RECENT AUDIT
                </span>
                <h3>
                  &#26368;&#36817;&#23457;&#35745;&#26085;&#24535;
                </h3>
              </div>
            </div>

            <div class="admin-audit-list">
              <div
                v-for="item in recentAudits"
                :key="item.audit_id"
                class="admin-audit-item"
              >
                <div>
                  <strong>
                    {{item.action}}
                  </strong>
                  <span>
                    {{
                      item.resource_type
                      || '-'
                    }}
                  </span>
                </div>

                <small>
                  {{
                    formatTime(
                      item.created_at
                    )
                  }}
                </small>
              </div>
            </div>
          </article>
        </div>
      </template>

      <template
        v-else-if="
          activeTab === 'users'
        "
      >
        <div class="admin-role-grid">
          <article
            v-for="item in roles"
            :key="item.role_id"
            class="panel-card admin-role-card"
          >
            <span class="eyebrow">
              ROLE
            </span>
            <strong>
              {{item.code}}
            </strong>
            <small>
              {{item.name}}
            </small>
            <b>
              {{item.user_count}}
              users
            </b>
          </article>
        </div>

        <article class="panel-card">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                USERS
              </span>
              <h3>
                &#29992;&#25143;&#19982;&#35282;&#33394;
              </h3>
            </div>

            <span class="admin-count-chip">
              {{usersData.total ?? users.length}}
            </span>
          </div>

          <div class="admin-table-wrap">
            <table class="admin-table admin-wide-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>&#22995;&#21517;</th>
                  <th>Email</th>
                  <th>&#35282;&#33394;</th>
                  <th>&#29366;&#24577;</th>
                  <th>Superuser</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in users"
                  :key="item.user_id"
                >
                  <td>
                    <strong>
                      {{item.username}}
                    </strong>
                    <small>
                      {{item.user_id}}
                    </small>
                  </td>

                  <td>
                    {{item.full_name}}
                  </td>

                  <td>
                    {{item.email || '-'}}
                  </td>

                  <td>
                    {{roleText(item.roles)}}
                  </td>

                  <td>
                    <span
                      class="admin-status"
                      :class="
                        statusTone(
                          item.status
                        )
                      "
                    >
                      {{
                        statusLabel(
                          item.status
                        )
                      }}
                    </span>
                  </td>

                  <td>
                    {{
                      item.is_superuser
                      ? '\u662f'
                      : '\u5426'
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </template>

      <template
        v-else-if="
          activeTab === 'knowledge'
        "
      >
        <div class="admin-kb-grid">
          <article
            v-for="item in knowledgeBases"
            :key="item.knowledge_base_id"
            class="panel-card admin-kb-card"
          >
            <div class="admin-kb-head">
              <div>
                <span class="eyebrow">
                  {{item.code}}
                </span>
                <h3>
                  {{item.name}}
                </h3>
              </div>

              <span
                class="admin-status"
                :class="
                  statusTone(
                    item.status
                  )
                "
              >
                {{
                  statusLabel(
                    item.status
                  )
                }}
              </span>
            </div>

            <p>
              {{item.description || '-'}}
            </p>

            <div class="admin-kb-meta">
              <span>
                {{item.domain}}
              </span>
              <span>
                {{item.visibility}}
              </span>
              <strong>
                {{item.document_count}}
                docs
              </strong>
            </div>
          </article>
        </div>

        <article class="panel-card">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                DOCUMENTS
              </span>
              <h3>
                &#26368;&#36817;&#25991;&#26723;
              </h3>
            </div>

            <span class="admin-count-chip">
              {{
                knowledgeData
                  .total_documents
                ?? 0
              }}
            </span>
          </div>

          <div class="admin-table-wrap">
            <table class="admin-table admin-wide-table">
              <thead>
                <tr>
                  <th>&#25991;&#26723;</th>
                  <th>&#30693;&#35782;&#24211;</th>
                  <th>&#31867;&#22411;</th>
                  <th>MIME</th>
                  <th>&#29366;&#24577;</th>
                  <th>&#26102;&#38388;</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in documents"
                  :key="item.document_id"
                >
                  <td>
                    <strong>
                      {{item.title}}
                    </strong>
                    <small>
                      {{item.document_id}}
                    </small>
                  </td>

                  <td>
                    {{
                      item.knowledge_base_name
                      || '-'
                    }}
                  </td>

                  <td>
                    {{
                      item.document_type
                      || '-'
                    }}
                  </td>

                  <td>
                    {{item.mime_type || '-'}}
                  </td>

                  <td>
                    <span
                      class="admin-status"
                      :class="
                        statusTone(
                          item.status
                        )
                      "
                    >
                      {{
                        statusLabel(
                          item.status
                        )
                      }}
                    </span>
                  </td>

                  <td>
                    {{
                      formatTime(
                        item.created_at
                      )
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>

        <AdminDocumentInspector
          :documents="documents"
          :actor-user-id="actorUserId"
        />

      </template>

      <AdminGraphPanel
        v-else-if="activeTab === 'graph'"
        :actor-user-id="actorUserId"
      />

      <AdminIntelligencePanel
        v-else-if="activeTab === 'agents'"
        :actor-user-id="actorUserId"
        section="agents"
      />

      <AdminIntelligencePanel
        v-else-if="activeTab === 'tools'"
        :actor-user-id="actorUserId"
        section="tools"
      />

      <AdminIntelligencePanel
        v-else-if="activeTab === 'prompts'"
        :actor-user-id="actorUserId"
        section="prompts"
      />

      <template
        v-else-if="
          activeTab === 'evaluation'
        "
      >
        <article class="panel-card">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                EVALUATION DATASETS
              </span>
              <h3>
                &#35780;&#20272;&#25968;&#25454;&#38598;
              </h3>
            </div>

            <span class="admin-count-chip">
              {{datasets.length}}
            </span>
          </div>

          <div
            v-if="evaluationRunMessage"
            class="admin-eval-run-message"
          >
            {{evaluationRunMessage}}
          </div>

          <div
            v-if="datasets.length"
            class="admin-table-wrap"
          >
            <table class="admin-table admin-wide-table">
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Version</th>
                  <th>Cases</th>
                  <th>Results</th>
                  <th>Passed</th>
                  <th>Pass Rate</th>
                  <th>Avg Score</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in datasets"
                  :key="item.dataset_id"
                >
                  <td>
                    <strong>
                      {{item.name}}
                    </strong>
                  </td>
                  <td>
                    {{item.version}}
                  </td>
                  <td>
                    {{item.case_count}}
                  </td>
                  <td>
                    {{item.result_count}}
                  </td>
                  <td>
                    {{item.passed_count}}
                  </td>
                  <td>
                    {{percent(item.pass_rate)}}
                  </td>
                  <td>
                    {{
                      item.average_score
                      ?? '-'
                    }}
                  </td>
                  <td>
                    <span
                      class="admin-status"
                      :class="
                        statusTone(
                          item.status
                        )
                      "
                    >
                      {{
                        statusLabel(
                          item.status
                        )
                      }}
                    </span>
                  </td>

                  <td>
                    <button
                      class="admin-run-eval-button"
                      :disabled="
                        item.status !== 'active'
                        || !!runningDatasetId
                      "
                      @click="
                        runEvaluation(
                          item.dataset_id
                        )
                      "
                    >
                      {{
                        runningDatasetId
                          === item.dataset_id
                          ? '运行中...'
                          : '运行评估'
                      }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-else
            class="admin-empty"
          >
            &#24403;&#21069;&#27809;&#26377;&#35780;&#20272;&#25968;&#25454;&#38598;
          </div>
        </article>

        <article
          class="panel-card admin-eval-results"
        >
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                EVALUATION RESULTS
              </span>
              <h3>
                &#26368;&#36817;&#35780;&#20272;&#32467;&#26524;
              </h3>
            </div>

            <span class="admin-count-chip">
              {{evaluationResults.length}}
            </span>
          </div>

          <div
            v-if="evaluationResults.length"
            class="admin-table-wrap"
          >
            <table class="admin-table">
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Score</th>
                  <th>Passed</th>
                  <th>Time</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in evaluationResults"
                  :key="item.result_id"
                >
                  <td>
                    {{
                      item.dataset_name
                      || item.dataset_id
                    }}
                  </td>

                  <td>
                    {{item.score ?? '-'}}
                  </td>

                  <td>
                    {{
                      item.passed === null
                      ? '-'
                      : (
                          item.passed
                          ? '\u662f'
                          : '\u5426'
                        )
                    }}
                  </td>

                  <td>
                    {{
                      formatTime(
                        item.created_at
                      )
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-else
            class="admin-empty"
          >
            &#24403;&#21069;&#36824;&#27809;&#26377;&#35780;&#20272;&#32467;&#26524;
          </div>
        </article>
      </template>

      <AdminSystemPanel
        v-else-if="activeTab === 'system'"
        :actor-user-id="actorUserId"
      />

      <template v-else>
        <article class="panel-card">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                AUDIT LOGS
              </span>
              <h3>
                &#23457;&#35745;&#26085;&#24535;
              </h3>
            </div>

            <span class="admin-count-chip">
              {{
                auditData.total
                ?? auditLogs.length
              }}
            </span>
          </div>

          <div class="admin-table-wrap">
            <table class="admin-table admin-wide-table">
              <thead>
                <tr>
                  <th>&#25805;&#20316;</th>
                  <th>&#36164;&#28304;</th>
                  <th>&#29992;&#25143;</th>
                  <th>Resource ID</th>
                  <th>Request ID</th>
                  <th>&#26102;&#38388;</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in auditLogs"
                  :key="item.audit_id"
                >
                  <td>
                    <strong>
                      {{item.action}}
                    </strong>
                  </td>

                  <td>
                    {{
                      item.resource_type
                      || '-'
                    }}
                  </td>

                  <td>
                    {{
                      item.actor_username
                      || item.actor_full_name
                      || item.actor_user_id
                      || '-'
                    }}
                  </td>

                  <td>
                    {{
                      item.resource_id
                      || '-'
                    }}
                  </td>

                  <td>
                    {{
                      item.request_id
                      || '-'
                    }}
                  </td>

                  <td>
                    {{
                      formatTime(
                        item.created_at
                      )
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </template>
    </template>
  </section>`
}
