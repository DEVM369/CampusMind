import {
  computed,
  onMounted,
  ref,
  typedRef,
} from '../vue.js'

import { AdminGraphBrowser } from './adminGraphBrowser.js'

import {
  getGraphOntology,
  getGraphStats,
} from '../api.js'


export const AdminGraphPanel = {
  components: {
    AdminGraphBrowser,
  },

  props: {
    actorUserId: {
      type: String,
      default: '',
    },
  },

  setup() {
    const loading = ref(false)
    const error = ref('')

    const stats =
      typedRef<Record<string, any>>({})

    const ontology =
      typedRef<Record<string, any>>({})

    const nodeTypes = computed(
      () => {
        const counts =
          stats.value.nodes_by_type
          || {}

        const definitions =
          Array.isArray(
            ontology.value.entities,
          )
            ? ontology.value.entities
            : []

        return definitions
          .map(
            (item: any) => ({
              type: item.type,
              description:
                item.description || '',
              count:
                Number(
                  counts[item.type]
                  || 0,
                ),
            }),
          )
          .sort(
            (a: any, b: any) =>
              b.count - a.count
              || String(a.type)
                .localeCompare(
                  String(b.type),
                ),
          )
      },
    )

    const relationTypes = computed(
      () => {
        const counts =
          stats.value.relations_by_type
          || {}

        const definitions =
          Array.isArray(
            ontology.value.relations,
          )
            ? ontology.value.relations
            : []

        return definitions
          .map(
            (item: any) => ({
              type: item.type,
              description:
                item.description || '',
              source_types:
                Array.isArray(
                  item.source_types,
                )
                  ? item.source_types
                  : [],
              target_types:
                Array.isArray(
                  item.target_types,
                )
                  ? item.target_types
                  : [],
              count:
                Number(
                  counts[item.type]
                  || 0,
                ),
            }),
          )
          .sort(
            (a: any, b: any) =>
              b.count - a.count
              || String(a.type)
                .localeCompare(
                  String(b.type),
                ),
          )
      },
    )

    const populatedEntityTypes = computed(
      () =>
        nodeTypes.value.filter(
          (item: any) =>
            item.count > 0,
        ).length,
    )

    const populatedRelationTypes = computed(
      () =>
        relationTypes.value.filter(
          (item: any) =>
            item.count > 0,
        ).length,
    )

    const entityCoverage = computed(
      () => {
        const total = Number(
          ontology.value.entity_count
          || 0,
        )

        if (!total) {
          return 0
        }

        return Math.round(
          (
            populatedEntityTypes.value
            / total
          )
          * 1000,
        ) / 10
      },
    )

    const relationCoverage = computed(
      () => {
        const total = Number(
          ontology.value.relation_count
          || 0,
        )

        if (!total) {
          return 0
        }

        return Math.round(
          (
            populatedRelationTypes.value
            / total
          )
          * 1000,
        ) / 10
      },
    )

    function formatTypes(
      value: unknown,
    ): string {
      return Array.isArray(value)
        ? value.join(', ')
        : '-'
    }

    async function load() {
      loading.value = true
      error.value = ''

      const results =
        await Promise.allSettled([
          getGraphStats(),
          getGraphOntology(),
        ])

      if (
        results[0].status
        === 'fulfilled'
      ) {
        stats.value =
          results[0].value
      }

      if (
        results[1].status
        === 'fulfilled'
      ) {
        ontology.value =
          results[1].value
      }

      if (
        results.some(
          item =>
            item.status === 'rejected',
        )
      ) {
        error.value =
          '\u90e8\u5206\u56fe\u8c31\u7ba1\u7406\u6570\u636e\u52a0\u8f7d\u5931\u8d25\u3002'
      }

      loading.value = false
    }

    onMounted(load)

    return {
      loading,
      error,
      stats,
      ontology,
      nodeTypes,
      relationTypes,
      populatedEntityTypes,
      populatedRelationTypes,
      entityCoverage,
      relationCoverage,
      formatTypes,
      load,
    }
  },

  template: `
    <section class="admin-graph-page">
      <div class="admin-section-heading">
        <div>
          <div class="admin-eyebrow">
            KNOWLEDGE GRAPH
          </div>

          <h2>
            \u77e5\u8bc6\u56fe\u8c31\u7ba1\u7406
          </h2>

          <p class="admin-muted">
            \u53ea\u8bfb\u67e5\u770b Neo4j \u5b9e\u4f53\u3001
            \u5173\u7cfb\u3001Ontology \u53ca\u5f53\u524d\u6570\u636e\u8986\u76d6\u60c5\u51b5\u3002
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
              : '\u5237\u65b0\u56fe\u8c31'
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
          <span>Nodes</span>

          <strong>
            {{stats.node_count ?? 0}}
          </strong>

          <small>
            \u5b9e\u4f53\u8282\u70b9
          </small>
        </article>

        <article class="admin-stat-card">
          <span>Relations</span>

          <strong>
            {{stats.relation_count ?? 0}}
          </strong>

          <small>
            \u56fe\u8c31\u5173\u7cfb
          </small>
        </article>

        <article class="admin-stat-card">
          <span>Entity Coverage</span>

          <strong>
            {{
              populatedEntityTypes
            }}
            /
            {{
              ontology.entity_count
              ?? 0
            }}
          </strong>

          <small>
            {{entityCoverage}}%
            Ontology
          </small>
        </article>

        <article class="admin-stat-card">
          <span>Relation Coverage</span>

          <strong>
            {{
              populatedRelationTypes
            }}
            /
            {{
              ontology.relation_count
              ?? 0
            }}
          </strong>

          <small>
            {{relationCoverage}}%
            Ontology
          </small>
        </article>
      </div>

      <div class="admin-graph-grid">
        <article class="panel-card">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                ENTITY DISTRIBUTION
              </span>

              <h3>
                \u5b9e\u4f53\u7c7b\u578b\u5206\u5e03
              </h3>
            </div>
          </div>

          <div class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>Entity Type</th>
                  <th>Nodes</th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in nodeTypes"
                  :key="item.type"
                >
                  <td>
                    <strong>
                      {{item.type}}
                    </strong>

                    <div class="admin-muted">
                      {{item.description}}
                    </div>
                  </td>

                  <td>
                    {{item.count}}
                  </td>

                  <td>
                    <span
                      class="admin-status"
                      :class="
                        item.count > 0
                          ? 'success'
                          : 'pending'
                      "
                    >
                      {{
                        item.count > 0
                          ? '\u5df2\u8986\u76d6'
                          : '\u672a\u5165\u56fe'
                      }}
                    </span>
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
                RELATION DISTRIBUTION
              </span>

              <h3>
                \u5173\u7cfb\u7c7b\u578b\u5206\u5e03
              </h3>
            </div>
          </div>

          <div class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>Relation</th>
                  <th>Edges</th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in relationTypes"
                  :key="item.type"
                >
                  <td>
                    <strong>
                      {{item.type}}
                    </strong>

                    <div class="admin-muted">
                      {{item.description}}
                    </div>
                  </td>

                  <td>
                    {{item.count}}
                  </td>

                  <td>
                    <span
                      class="admin-status"
                      :class="
                        item.count > 0
                          ? 'success'
                          : 'pending'
                      "
                    >
                      {{
                        item.count > 0
                          ? '\u5df2\u8986\u76d6'
                          : '\u672a\u5165\u56fe'
                      }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <AdminGraphBrowser
        :actor-user-id="actorUserId"
      />

      <article class="panel-card">
        <div class="admin-section-head">
          <div>
            <span class="eyebrow">
              RELATION ONTOLOGY
            </span>

            <h3>
              \u5173\u7cfb Schema
            </h3>
          </div>

          <span class="admin-count-chip">
            {{
              ontology.relation_count
              ?? relationTypes.length
            }}
          </span>
        </div>

        <div class="admin-table-wrap">
          <table class="admin-table admin-wide-table">
            <thead>
              <tr>
                <th>Relation</th>
                <th>Source</th>
                <th>Target</th>
                <th>Current Edges</th>
                <th>Description</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="item in relationTypes"
                :key="item.type"
              >
                <td>
                  <strong>
                    {{item.type}}
                  </strong>
                </td>

                <td>
                  {{
                    formatTypes(
                      item.source_types
                    )
                  }}
                </td>

                <td>
                  {{
                    formatTypes(
                      item.target_types
                    )
                  }}
                </td>

                <td>
                  {{item.count}}
                </td>

                <td>
                  {{item.description}}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <div class="admin-system-note">
        <strong>
          \u5f53\u524d\u8303\u56f4
        </strong>

        <span>
          \u672c\u9875\u4ec5\u8bfb\u53d6 /graph/stats
          \u4e0e /graph/ontology\uff0c
          \u4e0d\u8c03\u7528 bootstrap\u3001
          entity upsert \u6216 relation upsert\u3002
        </span>
      </div>
    </section>
  `,
}
