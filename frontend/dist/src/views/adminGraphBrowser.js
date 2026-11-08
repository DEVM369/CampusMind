import { computed, onMounted, ref, typedRef, watch, } from '../vue.js';
import { getAdminGraphEntities, getAdminGraphRelations, getAdminGraphEntityContext, getGraphStats, } from '../api.js';
export const AdminGraphBrowser = {
    props: {
        actorUserId: {
            type: String,
            default: '',
        },
    },
    setup(props) {
        const stats = typedRef({});
        const entityData = typedRef({});
        const relationData = typedRef({});
        const entityContext = typedRef({});
        const selectedEntityId = ref('');
        const entityContextLoading = ref(false);
        const entityContextError = ref('');
        const entityType = ref('');
        const relationType = ref('');
        const entityKeyword = ref('');
        const relationKeyword = ref('');
        const entityOffset = ref(0);
        const relationOffset = ref(0);
        const pageSize = 50;
        const entityLoading = ref(false);
        const relationLoading = ref(false);
        const entityError = ref('');
        const relationError = ref('');
        const entities = computed(() => Array.isArray(entityData.value.entities)
            ? entityData.value.entities
            : []);
        const relations = computed(() => Array.isArray(relationData.value.relations)
            ? relationData.value.relations
            : []);
        const entityPage = computed(() => Math.floor(entityOffset.value
            / pageSize) + 1);
        const entityPageCount = computed(() => Math.max(1, Math.ceil(Number(entityData.value.total
            || 0)
            / pageSize)));
        const relationPage = computed(() => Math.floor(relationOffset.value
            / pageSize) + 1);
        const relationPageCount = computed(() => Math.max(1, Math.ceil(Number(relationData.value.total
            || 0)
            / pageSize)));
        const entityHasPrevious = computed(() => entityOffset.value > 0);
        const entityHasNext = computed(() => entityOffset.value
            + pageSize
            < Number(entityData.value.total
                || 0));
        const relationHasPrevious = computed(() => relationOffset.value > 0);
        const relationHasNext = computed(() => relationOffset.value
            + pageSize
            < Number(relationData.value.total
                || 0));
        const selectedEntity = computed(() => {
            const value = entityContext.value.entity;
            return (value
                && typeof value === 'object')
                ? value
                : null;
        });
        const selectedRelations = computed(() => Array.isArray(entityContext.value.relations)
            ? entityContext.value.relations
            : []);
        const selectedProperties = computed(() => {
            const value = selectedEntity.value
                ?.properties;
            if (!value
                || typeof value !== 'object') {
                return [];
            }
            return Object.entries(value)
                .map(([key, item]) => ({
                key,
                value: item === null
                    || item === undefined
                    ? '-'
                    : String(item),
            }));
        });
        const entityTypes = computed(() => Object.entries(stats.value.nodes_by_type
            || {})
            .map(([type, count]) => ({
            type,
            count: Number(count || 0),
        }))
            .filter(item => item.count > 0)
            .sort((a, b) => b.count - a.count
            || a.type.localeCompare(b.type)));
        const relationTypes = computed(() => Object.entries(stats.value.relations_by_type
            || {})
            .map(([type, count]) => ({
            type,
            count: Number(count || 0),
        }))
            .filter(item => item.count > 0)
            .sort((a, b) => b.count - a.count
            || a.type.localeCompare(b.type)));
        function formatAliases(value) {
            return (Array.isArray(value)
                && value.length)
                ? value.join(', ')
                : '-';
        }
        function formatConfidence(value) {
            if (value === null
                || value === undefined) {
                return '-';
            }
            const number = Number(value);
            return Number.isFinite(number)
                ? number.toFixed(2)
                : '-';
        }
        function connectedName(item) {
            return (item.direction === 'outgoing'
                ? item.target_name
                : item.source_name) || '-';
        }
        function connectedType(item) {
            return (item.direction === 'outgoing'
                ? item.target_type
                : item.source_type) || '-';
        }
        function connectedId(item) {
            return (item.direction === 'outgoing'
                ? item.target_id
                : item.source_id) || '-';
        }
        function directionLabel(value) {
            return value === 'outgoing'
                ? '\u2192 \u51fa\u5411'
                : '\u2190 \u5165\u5411';
        }
        function clearEntityContext() {
            selectedEntityId.value = '';
            entityContext.value = {};
            entityContextError.value = '';
        }
        async function openEntityContext(entityId) {
            const actor = String(props.actorUserId
                || '').trim();
            const target = String(entityId || '').trim();
            if (!actor
                || !target) {
                return;
            }
            selectedEntityId.value = target;
            entityContextLoading.value = true;
            entityContextError.value = '';
            try {
                entityContext.value =
                    await getAdminGraphEntityContext(actor, target, 100);
            }
            catch (exc) {
                entityContext.value = {};
                entityContextError.value =
                    exc instanceof Error
                        ? exc.message
                        : String(exc);
            }
            finally {
                entityContextLoading.value = false;
            }
        }
        async function loadEntities() {
            const actor = String(props.actorUserId
                || '').trim();
            if (!actor)
                return;
            entityLoading.value = true;
            entityError.value = '';
            try {
                entityData.value =
                    await getAdminGraphEntities(actor, entityType.value, entityKeyword.value, entityOffset.value, pageSize);
            }
            catch (exc) {
                entityError.value =
                    exc instanceof Error
                        ? exc.message
                        : String(exc);
            }
            finally {
                entityLoading.value = false;
            }
        }
        async function loadRelations() {
            const actor = String(props.actorUserId
                || '').trim();
            if (!actor)
                return;
            relationLoading.value = true;
            relationError.value = '';
            try {
                relationData.value =
                    await getAdminGraphRelations(actor, relationType.value, relationKeyword.value, relationOffset.value, pageSize);
            }
            catch (exc) {
                relationError.value =
                    exc instanceof Error
                        ? exc.message
                        : String(exc);
            }
            finally {
                relationLoading.value = false;
            }
        }
        async function loadAll() {
            const actor = String(props.actorUserId
                || '').trim();
            if (!actor)
                return;
            try {
                stats.value =
                    await getGraphStats();
            }
            catch {
                stats.value = {};
            }
            await Promise.allSettled([
                loadEntities(),
                loadRelations(),
            ]);
        }
        function applyEntityFilters() {
            clearEntityContext();
            entityOffset.value = 0;
            loadEntities();
        }
        function applyRelationFilters() {
            relationOffset.value = 0;
            loadRelations();
        }
        function previousEntityPage() {
            clearEntityContext();
            if (!entityHasPrevious.value) {
                return;
            }
            entityOffset.value =
                Math.max(0, entityOffset.value
                    - pageSize);
            loadEntities();
        }
        function nextEntityPage() {
            clearEntityContext();
            if (!entityHasNext.value) {
                return;
            }
            entityOffset.value += pageSize;
            loadEntities();
        }
        function previousRelationPage() {
            if (!relationHasPrevious.value) {
                return;
            }
            relationOffset.value =
                Math.max(0, relationOffset.value
                    - pageSize);
            loadRelations();
        }
        function nextRelationPage() {
            if (!relationHasNext.value) {
                return;
            }
            relationOffset.value += pageSize;
            loadRelations();
        }
        function resetEntityFilter() {
            clearEntityContext();
            entityType.value = '';
            entityKeyword.value = '';
            entityOffset.value = 0;
            loadEntities();
        }
        function resetRelationFilter() {
            relationType.value = '';
            relationKeyword.value = '';
            relationOffset.value = 0;
            loadRelations();
        }
        onMounted(loadAll);
        watch(() => props.actorUserId, () => {
            loadAll();
        });
        return {
            entityData,
            relationData,
            entityContext,
            selectedEntityId,
            entityContextLoading,
            entityContextError,
            selectedEntity,
            selectedRelations,
            selectedProperties,
            entityType,
            relationType,
            entityKeyword,
            relationKeyword,
            entityOffset,
            relationOffset,
            entityPage,
            entityPageCount,
            relationPage,
            relationPageCount,
            entityHasPrevious,
            entityHasNext,
            relationHasPrevious,
            relationHasNext,
            entityLoading,
            relationLoading,
            entityError,
            relationError,
            entities,
            relations,
            entityTypes,
            relationTypes,
            formatAliases,
            formatConfidence,
            connectedName,
            connectedType,
            connectedId,
            directionLabel,
            openEntityContext,
            clearEntityContext,
            loadEntities,
            loadRelations,
            applyEntityFilters,
            applyRelationFilters,
            previousEntityPage,
            nextEntityPage,
            previousRelationPage,
            nextRelationPage,
            resetEntityFilter,
            resetRelationFilter,
        };
    },
    template: `
    <div class="admin-graph-browser">
      <article
        class="panel-card admin-graph-browser-card"
      >
        <div class="admin-section-head">
          <div>
            <span class="eyebrow">
              ENTITY BROWSER
            </span>

            <h3>
              \u5b9e\u4f53\u6d4f\u89c8
            </h3>
          </div>

          <span class="admin-count-chip">
            {{
              entityData.total
              ?? entities.length
            }}
          </span>
        </div>

        <p class="admin-muted">
          \u67e5\u770b\u5f53\u524d Neo4j \u4e2d\u7684\u771f\u5b9e\u5b9e\u4f53\u8282\u70b9\uff0c
          \u652f\u6301\u6309\u7c7b\u578b\u548c\u5173\u952e\u8bcd\u8fc7\u6ee4\u3002
        </p>

        <div
          class="admin-graph-browser-toolbar"
        >
          <select
            v-model="entityType"
            class="admin-graph-control"
            @change="applyEntityFilters"
          >
            <option value="">
              \u5168\u90e8\u5b9e\u4f53\u7c7b\u578b
            </option>

            <option
              v-for="item in entityTypes"
              :key="item.type"
              :value="item.type"
            >
              {{item.type}}
              ({{item.count}})
            </option>
          </select>

          <input
            v-model="entityKeyword"
            class="admin-graph-control"
            type="search"
            placeholder="\u641c\u7d22\u540d\u79f0\u3001Entity ID\u3001\u522b\u540d"
            @keyup.enter="applyEntityFilters"
          />

          <button
            class="btn secondary"
            type="button"
            :disabled="entityLoading"
            @click="applyEntityFilters"
          >
            {{
              entityLoading
                ? '\u67e5\u8be2\u4e2d...'
                : '\u67e5\u8be2'
            }}
          </button>

          <button
            class="btn secondary"
            type="button"
            :disabled="entityLoading"
            @click="resetEntityFilter"
          >
            \u91cd\u7f6e
          </button>
        </div>

        <div
          v-if="entityError"
          class="alert error"
        >
          {{entityError}}
        </div>

        <div
          v-if="entities.length"
          class="admin-table-wrap"
        >
          <table
            class="admin-table admin-wide-table"
          >
            <thead>
              <tr>
                <th>Type</th>
                <th>Name</th>
                <th>Entity ID</th>
                <th>Aliases</th>
                <th>Evidence</th>
                <th>详情</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="item in entities"
                :key="item.entity_id"
              >
                <td>
                  <span
                    class="admin-status success"
                  >
                    {{item.entity_type}}
                  </span>
                </td>

                <td>
                  <strong>
                    {{item.name}}
                  </strong>

                  <small
                    v-if="item.description"
                  >
                    {{item.description}}
                  </small>
                </td>

                <td>
                  <code
                    class="admin-graph-id"
                  >
                    {{item.entity_id}}
                  </code>
                </td>

                <td>
                  {{
                    formatAliases(
                      item.aliases
                    )
                  }}
                </td>

                <td>
                  <small>
                    confidence:
                    {{
                      formatConfidence(
                        item.confidence
                      )
                    }}
                  </small>

                  <code
                    class="admin-graph-evidence"
                  >
                    {{
                      item.source_chunk_id
                      || '-'
                    }}
                  </code>
                </td>

                <td>
                  <button
                    class="btn secondary admin-graph-detail-button"
                    type="button"
                    :disabled="
                      entityContextLoading
                      && selectedEntityId
                         === item.entity_id
                    "
                    @click="
                      openEntityContext(
                        item.entity_id
                      )
                    "
                  >
                    {{
                      entityContextLoading
                      && selectedEntityId
                         === item.entity_id
                        ? '加载中...'
                        : '查看'
                    }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          v-else-if="!entityLoading"
          class="admin-empty"
        >
          \u5f53\u524d\u6761\u4ef6\u4e0b\u6ca1\u6709\u5b9e\u4f53\u6570\u636e
        </div>

        <div class="admin-graph-pagination">
          <div class="admin-graph-browser-foot">
            \u5171
            <strong>
              {{entityData.total ?? 0}}
            </strong>
            \u6761\uff0c\u6bcf\u9875 50 \u6761
          </div>

          <div class="admin-graph-page-controls">
            <button
              class="btn secondary"
              type="button"
              :disabled="
                !entityHasPrevious
                || entityLoading
              "
              @click="previousEntityPage"
            >
              \u4e0a\u4e00\u9875
            </button>

            <span>
              \u7b2c
              <strong>{{entityPage}}</strong>
              /
              <strong>{{entityPageCount}}</strong>
              \u9875
            </span>

            <button
              class="btn secondary"
              type="button"
              :disabled="
                !entityHasNext
                || entityLoading
              "
              @click="nextEntityPage"
            >
              \u4e0b\u4e00\u9875
            </button>
          </div>
        </div>
      </article>

      <article
        v-if="
          entityContextLoading
          || entityContextError
          || selectedEntity
        "
        class="panel-card admin-graph-context-card"
      >
        <div class="admin-section-head">
          <div>
            <span class="eyebrow">
              ENTITY CONTEXT
            </span>

            <h3>
              \u5b9e\u4f53\u8be6\u60c5\u4e0e\u76f4\u63a5\u5173\u7cfb
            </h3>
          </div>

          <button
            class="btn secondary"
            type="button"
            @click="clearEntityContext"
          >
            \u5173\u95ed
          </button>
        </div>

        <div
          v-if="entityContextError"
          class="alert error"
        >
          {{entityContextError}}
        </div>

        <div
          v-else-if="entityContextLoading"
          class="admin-empty"
        >
          \u6b63\u5728\u8bfb\u53d6\u5b9e\u4f53\u76f4\u63a5\u5173\u7cfb...
        </div>

        <template v-else-if="selectedEntity">
          <div class="admin-graph-context-head">
            <div>
              <span class="admin-status success">
                {{selectedEntity.entity_type}}
              </span>

              <h4>
                {{selectedEntity.name}}
              </h4>

              <code class="admin-graph-id">
                {{selectedEntity.entity_id}}
              </code>
            </div>

            <div class="admin-graph-context-count">
              <strong>
                {{
                  entityContext.relation_count
                  ?? selectedRelations.length
                }}
              </strong>
              <span>
                \u76f4\u63a5\u5173\u7cfb
              </span>
            </div>
          </div>

          <div class="admin-graph-context-meta">
            <div>
              <span>Confidence</span>
              <strong>
                {{
                  formatConfidence(
                    selectedEntity.confidence
                  )
                }}
              </strong>
            </div>

            <div>
              <span>Aliases</span>
              <strong>
                {{
                  formatAliases(
                    selectedEntity.aliases
                  )
                }}
              </strong>
            </div>

            <div>
              <span>Source Document</span>
              <code>
                {{
                  selectedEntity.source_document_id
                  || '-'
                }}
              </code>
            </div>

            <div>
              <span>Source Chunk</span>
              <code>
                {{
                  selectedEntity.source_chunk_id
                  || '-'
                }}
              </code>
            </div>
          </div>

          <div
            v-if="selectedProperties.length"
            class="admin-graph-property-list"
          >
            <div
              v-for="item in selectedProperties"
              :key="item.key"
            >
              <span>
                {{item.key}}
              </span>
              <strong>
                {{item.value}}
              </strong>
            </div>
          </div>

          <div
            v-if="selectedRelations.length"
            class="admin-table-wrap admin-graph-context-relations"
          >
            <table class="admin-table admin-wide-table">
              <thead>
                <tr>
                  <th>\u65b9\u5411</th>
                  <th>Relation</th>
                  <th>\u5173\u8054\u5b9e\u4f53</th>
                  <th>Entity ID</th>
                  <th>Evidence</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in selectedRelations"
                  :key="item.relation_id"
                >
                  <td>
                    <span
                      class="admin-graph-direction"
                      :class="item.direction"
                    >
                      {{
                        directionLabel(
                          item.direction
                        )
                      }}
                    </span>
                  </td>

                  <td>
                    <strong>
                      {{item.relation_type}}
                    </strong>
                  </td>

                  <td>
                    <strong>
                      {{
                        connectedName(
                          item
                        )
                      }}
                    </strong>

                    <small>
                      {{
                        connectedType(
                          item
                        )
                      }}
                    </small>
                  </td>

                  <td>
                    <code class="admin-graph-id">
                      {{
                        connectedId(
                          item
                        )
                      }}
                    </code>
                  </td>

                  <td>
                    <small>
                      confidence:
                      {{
                        formatConfidence(
                          item.confidence
                        )
                      }}
                    </small>

                    <code class="admin-graph-evidence">
                      {{
                        item.source_chunk_id
                        || '-'
                      }}
                    </code>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-else
            class="admin-empty"
          >
            \u8be5\u5b9e\u4f53\u5f53\u524d\u6ca1\u6709 CampusMind \u76f4\u63a5\u5173\u7cfb
          </div>
        </template>
      </article>

      <article
        class="panel-card admin-graph-browser-card"
      >
        <div class="admin-section-head">
          <div>
            <span class="eyebrow">
              RELATION BROWSER
            </span>

            <h3>
              \u5173\u7cfb\u6d4f\u89c8
            </h3>
          </div>

          <span class="admin-count-chip">
            {{
              relationData.total
              ?? relations.length
            }}
          </span>
        </div>

        <p class="admin-muted">
          \u4ec5\u5c55\u793a CampusMind \u7ba1\u7406\u7684\u56fe\u8c31\u5173\u7cfb\uff0c
          \u652f\u6301\u6309\u5173\u7cfb\u7c7b\u578b\u548c\u8d77\u6b62\u5b9e\u4f53\u641c\u7d22\u3002
        </p>

        <div
          class="admin-graph-browser-toolbar"
        >
          <select
            v-model="relationType"
            class="admin-graph-control"
            @change="applyRelationFilters"
          >
            <option value="">
              \u5168\u90e8\u5173\u7cfb\u7c7b\u578b
            </option>

            <option
              v-for="item in relationTypes"
              :key="item.type"
              :value="item.type"
            >
              {{item.type}}
              ({{item.count}})
            </option>
          </select>

          <input
            v-model="relationKeyword"
            class="admin-graph-control"
            type="search"
            placeholder="\u641c\u7d22\u8d77\u70b9\u3001\u7ec8\u70b9\u3001Relation ID"
            @keyup.enter="applyRelationFilters"
          />

          <button
            class="btn secondary"
            type="button"
            :disabled="relationLoading"
            @click="applyRelationFilters"
          >
            {{
              relationLoading
                ? '\u67e5\u8be2\u4e2d...'
                : '\u67e5\u8be2'
            }}
          </button>

          <button
            class="btn secondary"
            type="button"
            :disabled="relationLoading"
            @click="resetRelationFilter"
          >
            \u91cd\u7f6e
          </button>
        </div>

        <div
          v-if="relationError"
          class="alert error"
        >
          {{relationError}}
        </div>

        <div
          v-if="relations.length"
          class="admin-table-wrap"
        >
          <table
            class="admin-table admin-wide-table"
          >
            <thead>
              <tr>
                <th>Source</th>
                <th>Relation</th>
                <th>Target</th>
                <th>Relation ID</th>
                <th>Evidence</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="item in relations"
                :key="
                  item.relation_id
                  || (
                    item.source_id
                    + ':'
                    + item.relation_type
                    + ':'
                    + item.target_id
                  )
                "
              >
                <td>
                  <strong>
                    {{item.source_name}}
                  </strong>

                  <small>
                    {{item.source_type}}
                  </small>

                  <code
                    class="admin-graph-id"
                  >
                    {{item.source_id}}
                  </code>
                </td>

                <td>
                  <span
                    class="admin-status success"
                  >
                    {{item.relation_type}}
                  </span>
                </td>

                <td>
                  <strong>
                    {{item.target_name}}
                  </strong>

                  <small>
                    {{item.target_type}}
                  </small>

                  <code
                    class="admin-graph-id"
                  >
                    {{item.target_id}}
                  </code>
                </td>

                <td>
                  <code
                    class="admin-graph-id"
                  >
                    {{
                      item.relation_id
                      || '-'
                    }}
                  </code>
                </td>

                <td>
                  <small>
                    confidence:
                    {{
                      formatConfidence(
                        item.confidence
                      )
                    }}
                  </small>

                  <code
                    class="admin-graph-evidence"
                  >
                    {{
                      item.source_chunk_id
                      || '-'
                    }}
                  </code>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          v-else-if="!relationLoading"
          class="admin-empty"
        >
          \u5f53\u524d\u6761\u4ef6\u4e0b\u6ca1\u6709\u5173\u7cfb\u6570\u636e
        </div>

        <div class="admin-graph-pagination">
          <div class="admin-graph-browser-foot">
            \u5171
            <strong>
              {{relationData.total ?? 0}}
            </strong>
            \u6761\uff0c\u6bcf\u9875 50 \u6761
          </div>

          <div class="admin-graph-page-controls">
            <button
              class="btn secondary"
              type="button"
              :disabled="
                !relationHasPrevious
                || relationLoading
              "
              @click="previousRelationPage"
            >
              \u4e0a\u4e00\u9875
            </button>

            <span>
              \u7b2c
              <strong>{{relationPage}}</strong>
              /
              <strong>{{relationPageCount}}</strong>
              \u9875
            </span>

            <button
              class="btn secondary"
              type="button"
              :disabled="
                !relationHasNext
                || relationLoading
              "
              @click="nextRelationPage"
            >
              \u4e0b\u4e00\u9875
            </button>
          </div>
        </div>
      </article>
    </div>
  `,
};
