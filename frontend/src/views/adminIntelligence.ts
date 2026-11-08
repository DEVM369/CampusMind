import {
  computed,
  onMounted,
  ref,
  typedRef,
  watch,
} from '../vue.js'

import {
  getAdminAgents,
  getAdminPrompts,
  getAdminTools,
} from '../api.js'


type IntelligenceSection =
  | 'agents'
  | 'tools'
  | 'prompts'


export const AdminIntelligencePanel = {
  name: 'AdminIntelligencePanel',

  props: {
    actorUserId: {
      type: String,
      required: true,
    },

    section: {
      type: String as () => IntelligenceSection,
      required: true,
    },
  },

  setup(props: any) {
    const loading = ref(false)
    const error = ref('')
    const data = typedRef<Record<string, any>>({})

    const title = computed(() => {
      if (props.section === 'agents') {
        return '\u667a\u80fd\u4f53\u7ba1\u7406'
      }

      if (props.section === 'tools') {
        return '\u5de5\u5177\u4e0e\u8c03\u7528'
      }

      return '\u63d0\u793a\u8bcd\u6e05\u5355'
    })

    const eyebrow = computed(() => {
      if (props.section === 'agents') {
        return 'AGENT RUNTIME'
      }

      if (props.section === 'tools') {
        return 'TOOL REGISTRY'
      }

      return 'PROMPT CATALOG'
    })

    const agents = computed(
      () =>
        Array.isArray(data.value.agents)
          ? data.value.agents
          : [],
    )

    const recentRuns = computed(
      () =>
        Array.isArray(data.value.recent_runs)
          ? data.value.recent_runs
          : [],
    )

    const serviceTools = computed(
      () =>
        Array.isArray(
          data.value.service_catalog,
        )
          ? data.value.service_catalog
          : [],
    )

    const observedTools = computed(
      () =>
        Array.isArray(
          data.value.observed_tools,
        )
          ? data.value.observed_tools
          : [],
    )

    const prompts = computed(
      () =>
        Array.isArray(data.value.prompts)
          ? data.value.prompts
          : [],
    )

    const runtime = computed(
      () => data.value.runtime || {},
    )

    async function load() {
      const actor =
        props.actorUserId.trim()

      if (!actor) {
        data.value = {}
        error.value =
          '\u7f3a\u5c11\u7ba1\u7406\u5458\u8eab\u4efd\u3002'
        return
      }

      loading.value = true
      error.value = ''

      try {
        if (props.section === 'agents') {
          data.value =
            await getAdminAgents(actor)
        } else if (
          props.section === 'tools'
        ) {
          data.value =
            await getAdminTools(actor)
        } else {
          data.value =
            await getAdminPrompts(actor)
        }
      } catch (exc: any) {
        data.value = {}
        error.value =
          exc?.message
          || '\u52a0\u8f7d\u5931\u8d25'
      } finally {
        loading.value = false
      }
    }

    onMounted(load)

    watch(
      () => [
        props.actorUserId,
        props.section,
      ],
      load,
    )

    return {
      loading,
      error,
      data,
      title,
      eyebrow,
      agents,
      recentRuns,
      serviceTools,
      observedTools,
      prompts,
      runtime,
      load,
    }
  },

  template: `
    <section class="admin-intelligence">
      <div class="admin-section-heading">
        <div>
          <div class="admin-eyebrow">
            {{eyebrow}}
          </div>
          <h2>{{title}}</h2>
        </div>

        <button
          class="admin-secondary-button"
          type="button"
          :disabled="loading"
          @click="load"
        >
          {{loading
            ? '\u52a0\u8f7d\u4e2d...'
            : '\u5237\u65b0'}}
        </button>
      </div>

      <div
        v-if="error"
        class="admin-inline-message admin-inline-message-error"
      >
        {{error}}
      </div>

      <template v-if="section === 'agents'">
        <div class="admin-stat-grid admin-intelligence-stats">
          <article class="admin-stat-card">
            <span>Agent Catalog</span>
            <strong>{{agents.length}}</strong>
            <small>
              \u5f53\u524d\u6ce8\u518c\u667a\u80fd\u4f53
            </small>
          </article>

          <article class="admin-stat-card">
            <span>Agent Runs</span>
            <strong>
              {{runtime.run_count ?? 0}}
            </strong>
            <small>
              \u5df2\u8bb0\u5f55\u8fd0\u884c
            </small>
          </article>

          <article class="admin-stat-card">
            <span>Agent Steps</span>
            <strong>
              {{runtime.step_count ?? 0}}
            </strong>
            <small>
              \u6267\u884c\u6b65\u9aa4
            </small>
          </article>

          <article class="admin-stat-card">
            <span>Completed</span>
            <strong>
              {{
                runtime.status_counts
                  ?.completed
                ?? 0
              }}
            </strong>
            <small>
              \u5df2\u5b8c\u6210\u8fd0\u884c
            </small>
          </article>
        </div>

        <div class="admin-table-wrap">
          <table class="admin-table admin-wide-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Type</th>
                <th>Class</th>
                <th>Status</th>
                <th>Management</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="item in agents"
                :key="item.code"
              >
                <td>
                  <strong>{{item.name}}</strong>
                  <div class="admin-muted">
                    {{item.description}}
                  </div>
                </td>

                <td>{{item.kind}}</td>

                <td>
                  <code>
                    {{item.class_name || '-'}}
                  </code>
                </td>

                <td>
                  <span class="admin-status-chip">
                    {{item.status}}
                  </span>
                </td>

                <td>
                  {{item.management_mode}}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="admin-subsection-heading">
          <div>
            <div class="admin-eyebrow">
              RECENT RUNS
            </div>
            <h3>
              \u6700\u8fd1 Agent \u8fd0\u884c
            </h3>
          </div>
        </div>

        <div class="admin-table-wrap">
          <table class="admin-table admin-wide-table">
            <thead>
              <tr>
                <th>Intent</th>
                <th>Strategy</th>
                <th>Status</th>
                <th>Validation</th>
                <th>Latency</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="item in recentRuns"
                :key="item.run_id"
              >
                <td>{{item.intent || '-'}}</td>
                <td>
                  {{item.retrieval_strategy || '-'}}
                </td>
                <td>{{item.status}}</td>
                <td>
                  {{
                    item.validation_score
                    ?? '-'
                  }}
                </td>
                <td>
                  {{
                    item.latency_ms != null
                      ? item.latency_ms + ' ms'
                      : '-'
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-else-if="section === 'tools'">
        <div class="admin-stat-grid admin-intelligence-stats">
          <article class="admin-stat-card">
            <span>Tool Services</span>
            <strong>
              {{serviceTools.length}}
            </strong>
            <small>
              \u5de5\u5177\u670d\u52a1\u7c7b\u578b
            </small>
          </article>

          <article class="admin-stat-card">
            <span>Tool Calls</span>
            <strong>
              {{data.total_tool_calls ?? 0}}
            </strong>
            <small>
              \u5386\u53f2\u5de5\u5177\u8c03\u7528
            </small>
          </article>

          <article class="admin-stat-card">
            <span>HITL</span>
            <strong>
              {{
                data.approval_required_calls
                ?? 0
              }}
            </strong>
            <small>
              \u9700\u8981\u4eba\u5de5\u786e\u8ba4
            </small>
          </article>
        </div>

        <div class="admin-card-grid">
          <article
            v-for="item in serviceTools"
            :key="item.code"
            class="admin-info-card"
          >
            <div class="admin-eyebrow">
              {{item.code}}
            </div>

            <h3>{{item.name}}</h3>

            <p class="admin-muted">
              {{item.module}}
            </p>

            <div class="admin-inline-meta">
              <span>
                Risk: {{item.risk}}
              </span>
              <span>
                {{item.status}}
              </span>
            </div>
          </article>
        </div>

        <div class="admin-subsection-heading">
          <div>
            <div class="admin-eyebrow">
              OBSERVED CALLS
            </div>
            <h3>
              \u5b9e\u9645\u5de5\u5177\u8c03\u7528
            </h3>
          </div>
        </div>

        <div class="admin-table-wrap">
          <table class="admin-table admin-wide-table">
            <thead>
              <tr>
                <th>Tool</th>
                <th>Calls</th>
                <th>Completed</th>
                <th>Failed</th>
                <th>Approval</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="item in observedTools"
                :key="item.tool_name"
              >
                <td>
                  <code>{{item.tool_name}}</code>
                </td>
                <td>{{item.call_count}}</td>
                <td>
                  {{item.completed_count}}
                </td>
                <td>{{item.failed_count}}</td>
                <td>
                  {{
                    item.approval_required_count
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-else>
        <div class="admin-inline-message">
          <strong>
            \u5f53\u524d\u63d0\u793a\u8bcd\u4e3a\u6e90\u7801\u7ba1\u7406\u3002
          </strong>
          <span>
            \u7ba1\u7406\u7aef\u53ea\u5c55\u793a\u7528\u9014\u548c\u72b6\u6001\uff0c
            \u4e0d\u66b4\u9732\u5b8c\u6574 System Prompt\uff0c
            \u4e5f\u4e0d\u63d0\u4f9b\u5728\u7ebf\u4fee\u6539\u3002
          </span>
        </div>

        <div class="admin-card-grid">
          <article
            v-for="item in prompts"
            :key="item.code"
            class="admin-info-card"
          >
            <div class="admin-eyebrow">
              {{item.code}}
            </div>

            <h3>{{item.name}}</h3>

            <p>
              {{item.purpose}}
            </p>

            <p class="admin-muted">
              {{item.module}}
            </p>

            <div class="admin-inline-meta">
              <span>
                {{item.status}}
              </span>
              <span>
                {{item.management_mode}}
              </span>
            </div>
          </article>
        </div>
      </template>
    </section>
  `,
}
