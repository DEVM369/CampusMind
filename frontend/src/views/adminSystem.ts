import {
  computed,
  onMounted,
  ref,
  typedRef,
  watch,
} from '../vue.js'

import {
  getAdminDashboard,
  getAdminSystemHealth,
  getDatabaseStatus,
  getGraphStats,
  getSystemReadiness,
} from '../api.js'


export const AdminSystemPanel = {
  props: {
    actorUserId: {
      type: String,
      required: true,
    },
  },

  setup(props: any) {
    const loading = ref(false)
    const error = ref('')

    const health =
      typedRef<Record<string, any>>({})

    const readiness =
      typedRef<Record<string, any>>({})

    const database =
      typedRef<Record<string, any>>({})

    const graph =
      typedRef<Record<string, any>>({})

    const dashboard =
      typedRef<Record<string, any>>({})

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
                && typeof item === 'object'
                  ? item
                  : {}
              ),
            }),
          )
      },
    )

    const seedCounts = computed(
      () => {
        const value =
          database.value.seed_counts

        if (
          !value
          || typeof value !== 'object'
        ) {
          return []
        }

        return Object.entries(value)
          .map(
            ([name, count]) => ({
              name,
              count,
            }),
          )
      },
    )

    const counts = computed(
      () =>
        dashboard.value.counts
        || {},
    )

    function statusLabel(
      value: unknown,
    ): string {
      const key = String(
        value || '',
      ).toLowerCase()

      const labels:
        Record<string, string> = {
          healthy: '\u5065\u5eb7',
          ready: '\u5c31\u7eea',
          degraded: '\u964d\u7ea7',
          unhealthy: '\u5f02\u5e38',
          incomplete: '\u4e0d\u5b8c\u6574',
          active: '\u6b63\u5e38',
        }

      return labels[key]
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
          'active',
        ].includes(key)
      ) {
        return 'success'
      }

      if (
        [
          'unhealthy',
          'failed',
          'error',
          'incomplete',
        ].includes(key)
      ) {
        return 'danger'
      }

      return 'pending'
    }

    async function load() {
      const actor =
        props.actorUserId.trim()

      if (!actor) {
        error.value =
          '\u7f3a\u5c11\u7ba1\u7406\u5458\u8eab\u4efd\u3002'
        return
      }

      loading.value = true
      error.value = ''

      const results =
        await Promise.allSettled([
          getAdminSystemHealth(),
          getSystemReadiness(),
          getDatabaseStatus(),
          getGraphStats(),
          getAdminDashboard(actor),
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
        readiness.value =
          results[1].value
      } else {
        readiness.value = {
          status: 'degraded',
        }
      }

      if (
        results[2].status
        === 'fulfilled'
      ) {
        database.value =
          results[2].value
      }

      if (
        results[3].status
        === 'fulfilled'
      ) {
        graph.value =
          results[3].value
      }

      if (
        results[4].status
        === 'fulfilled'
      ) {
        dashboard.value =
          results[4].value
      }

      if (
        results.every(
          item =>
            item.status === 'rejected',
        )
      ) {
        error.value =
          '\u7cfb\u7edf\u72b6\u6001\u63a5\u53e3\u5747\u65e0\u6cd5\u8bbf\u95ee\u3002'
      }

      loading.value = false
    }

    onMounted(load)

    watch(
      () => props.actorUserId,
      load,
    )

    return {
      loading,
      error,
      health,
      readiness,
      database,
      graph,
      dashboard,
      counts,
      healthComponents,
      seedCounts,
      statusLabel,
      statusTone,
      load,
    }
  },

  template: `
    <section class="admin-system-page">
      <div class="admin-section-heading">
        <div>
          <div class="admin-eyebrow">
            SYSTEM OPERATIONS
          </div>

          <h2>
            \u7cfb\u7edf\u8fd0\u884c\u72b6\u6001
          </h2>

          <p class="admin-muted">
            \u53ea\u8bfb\u67e5\u770b CampusMind \u57fa\u7840\u8bbe\u65bd\u3001
            \u6570\u636e\u5e93\u3001\u56fe\u8c31\u4e0e\u6838\u5fc3\u8fd0\u884c\u6307\u6807\u3002
          </p>
        </div>

        <button
          class="btn secondary"
          type="button"
          :disabled="loading"
          @click="load"
        >
          {{
            loading
              ? '\u5237\u65b0\u4e2d...'
              : '\u5237\u65b0\u72b6\u6001'
          }}
        </button>
      </div>

      <div
        v-if="error"
        class="alert error"
      >
        {{error}}
      </div>

      <div class="admin-stat-grid">
        <article class="admin-stat-card">
          <span>Health</span>

          <strong>
            {{
              statusLabel(
                health.status
              )
            }}
          </strong>

          <small>
            \u7cfb\u7edf\u7efc\u5408\u5065\u5eb7\u5ea6
          </small>
        </article>

        <article class="admin-stat-card">
          <span>Readiness</span>

          <strong>
            {{
              statusLabel(
                readiness.status
              )
            }}
          </strong>

          <small>
            \u670d\u52a1\u662f\u5426\u5c31\u7eea
          </small>
        </article>

        <article class="admin-stat-card">
          <span>Database</span>

          <strong>
            {{
              statusLabel(
                database.status
              )
            }}
          </strong>

          <small>
            {{
              database.revision
              || 'revision -'
            }}
          </small>
        </article>

        <article class="admin-stat-card">
          <span>Knowledge Graph</span>

          <strong>
            {{
              graph.node_count
              ?? '-'
            }}
          </strong>

          <small>
            {{
              graph.relation_count
              ?? graph.edge_count
              ?? '-'
            }}
            relations
          </small>
        </article>
      </div>

      <div class="admin-system-grid">
        <article class="panel-card">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                INFRASTRUCTURE
              </span>

              <h3>
                \u57fa\u7840\u8bbe\u65bd\u5065\u5eb7
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
                  {{item.message || '-'}}
                </small>
              </div>

              <div class="admin-health-side">
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

                <small>
                  {{
                    item.latency_ms != null
                      ? item.latency_ms
                        + ' ms'
                      : '-'
                  }}
                </small>
              </div>
            </div>
          </div>
        </article>

        <article class="panel-card">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                DATABASE SCHEMA
              </span>

              <h3>
                PostgreSQL \u7ed3\u6784
              </h3>
            </div>

            <span
              class="admin-status"
              :class="
                statusTone(
                  database.status
                )
              "
            >
              {{
                statusLabel(
                  database.status
                )
              }}
            </span>
          </div>

          <div class="admin-mini-metrics">
            <div>
              <strong>
                {{
                  database.table_count
                  ?? '-'
                }}
              </strong>

              <small>
                \u5df2\u6709\u8868
              </small>
            </div>

            <div>
              <strong>
                {{
                  database.expected_table_count
                  ?? '-'
                }}
              </strong>

              <small>
                \u9884\u671f\u8868
              </small>
            </div>

            <div>
              <strong>
                {{
                  database.revision
                  || '-'
                }}
              </strong>

              <small>
                Alembic
              </small>
            </div>
          </div>

          <div
            v-if="
              Array.isArray(
                database.missing_tables
              )
              && database.missing_tables.length
            "
            class="admin-system-warning"
          >
            <strong>
              \u7f3a\u5931\u6570\u636e\u8868\uff1a
            </strong>

            {{
              database.missing_tables
                .join(', ')
            }}
          </div>

          <div
            v-else
            class="admin-system-ok"
          >
            \u672a\u68c0\u6d4b\u5230\u7f3a\u5931\u7684\u9884\u671f\u6570\u636e\u8868\u3002
          </div>
        </article>
      </div>

      <div class="admin-system-grid">
        <article class="panel-card">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                DATA BASELINE
              </span>

              <h3>
                \u57fa\u7840\u6570\u636e
              </h3>
            </div>
          </div>

          <div class="admin-system-list">
            <div
              v-for="item in seedCounts"
              :key="item.name"
              class="admin-system-list-row"
            >
              <span>{{item.name}}</span>
              <strong>{{item.count}}</strong>
            </div>
          </div>
        </article>

        <article class="panel-card">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                APPLICATION
              </span>

              <h3>
                CampusMind \u4e1a\u52a1\u8fd0\u884c
              </h3>
            </div>
          </div>

          <div class="admin-mini-metrics">
            <div>
              <strong>
                {{counts.users ?? '-'}}
              </strong>

              <small>
                Users
              </small>
            </div>

            <div>
              <strong>
                {{
                  counts.knowledge_bases
                  ?? '-'
                }}
              </strong>

              <small>
                Knowledge Bases
              </small>
            </div>

            <div>
              <strong>
                {{
                  counts.agent_runs
                  ?? '-'
                }}
              </strong>

              <small>
                Agent Runs
              </small>
            </div>

            <div>
              <strong>
                {{
                  counts.tool_calls
                  ?? '-'
                }}
              </strong>

              <small>
                Tool Calls
              </small>
            </div>
          </div>
        </article>
      </div>

      <div class="admin-system-note">
        <strong>
          \u5b89\u5168\u8fb9\u754c
        </strong>

        <span>
          \u672c\u9875\u4e0d\u5c55\u793a\u6570\u636e\u5e93\u8fde\u63a5\u4e32\u3001
          API Key\u3001\u5bc6\u7801\u6216\u5176\u4ed6\u654f\u611f\u914d\u7f6e\uff0c
          \u4e5f\u4e0d\u63d0\u4f9b\u5728\u7ebf\u4fee\u6539\u548c\u670d\u52a1\u91cd\u542f\u3002
        </span>
      </div>
    </section>
  `,
}
