import { computed, ref, typedRef, watch, } from '../vue.js';
import { getAdminDocumentGraphStatus, getDocument, getDocumentChunks, getSourceChunkGraph, } from '../api.js';
export const AdminDocumentInspector = {
    props: {
        documents: {
            type: Array,
            default: () => [],
        },
        actorUserId: {
            type: String,
            default: '',
        },
    },
    setup(props) {
        const selectedDocumentId = ref('');
        const loading = ref(false);
        const error = ref('');
        const detail = typedRef({});
        const chunkData = typedRef({});
        const graphStatus = typedRef({});
        const graphStatusError = ref('');
        const chunkGraph = typedRef({});
        const selectedGraphChunkId = ref('');
        const chunkGraphLoading = ref(false);
        const chunkGraphError = ref('');
        const selectedChunk = typedRef({});
        const chunkDisplayLimit = ref(20);
        const documentOptions = computed(() => Array.isArray(props.documents)
            ? props.documents
            : []);
        const versions = computed(() => Array.isArray(detail.value.versions)
            ? detail.value.versions
            : []);
        const chunks = computed(() => Array.isArray(chunkData.value.chunks)
            ? chunkData.value.chunks
            : []);
        const chunkGraphRelations = computed(() => Array.isArray(chunkGraph.value.relations)
            ? chunkGraph.value.relations
            : []);
        const chunkEvidenceGaps = computed(() => Array.isArray(chunkGraph.value.evidence_gaps)
            ? chunkGraph.value.evidence_gaps
            : []);
        const graphChunks = computed(() => Array.isArray(graphStatus.value.chunks)
            ? graphStatus.value.chunks
            : []);
        const relationTypeEntries = computed(() => Object.entries(graphStatus.value
            .relation_type_counts
            || {})
            .map(([type, count]) => ({
            type,
            count: Number(count || 0),
        }))
            .sort((a, b) => b.count - a.count
            || a.type.localeCompare(b.type)));
        const provenanceMethodEntries = computed(() => Object.entries(graphStatus.value
            .provenance_method_counts
            || {})
            .map(([method, count]) => ({
            method,
            count: Number(count || 0),
        }))
            .sort((a, b) => b.count - a.count
            || a.method.localeCompare(b.method)));
        const visibleChunks = computed(() => chunks.value.slice(0, chunkDisplayLimit.value));
        const hasMoreChunks = computed(() => chunks.value.length
            > chunkDisplayLimit.value);
        function resetDetail() {
            detail.value = {};
            chunkData.value = {};
            graphStatus.value = {};
            graphStatusError.value = '';
            chunkGraph.value = {};
            selectedGraphChunkId.value = '';
            chunkGraphError.value = '';
            selectedChunk.value = {};
            chunkDisplayLimit.value = 20;
            error.value = '';
        }
        function formatValue(value) {
            if (value === null
                || value === undefined
                || value === '') {
                return '-';
            }
            return String(value);
        }
        function formatTime(value) {
            if (!value) {
                return '-';
            }
            const date = new Date(String(value));
            if (Number.isNaN(date.getTime())) {
                return String(value);
            }
            return date.toLocaleString();
        }
        function closeChunkGraph() {
            chunkGraph.value = {};
            selectedGraphChunkId.value = '';
            chunkGraphError.value = '';
        }
        async function openChunkGraph(chunkId) {
            const id = String(chunkId || '').trim();
            if (!id) {
                return;
            }
            selectedGraphChunkId.value = id;
            chunkGraphLoading.value = true;
            chunkGraphError.value = '';
            try {
                chunkGraph.value =
                    await getSourceChunkGraph(id);
            }
            catch (exc) {
                chunkGraph.value = {};
                chunkGraphError.value =
                    exc instanceof Error
                        ? exc.message
                        : String(exc);
            }
            finally {
                chunkGraphLoading.value = false;
            }
        }
        function selectChunk(item) {
            selectedChunk.value = item;
        }
        function showMoreChunks() {
            chunkDisplayLimit.value += 20;
        }
        async function loadDocument() {
            const id = selectedDocumentId.value.trim();
            if (!id) {
                resetDetail();
                return;
            }
            loading.value = true;
            error.value = '';
            selectedChunk.value = {};
            chunkGraph.value = {};
            selectedGraphChunkId.value = '';
            chunkGraphError.value = '';
            chunkDisplayLimit.value = 20;
            try {
                const actor = String(props.actorUserId
                    || '').trim();
                const graphRequest = actor
                    ? getAdminDocumentGraphStatus(actor, id)
                    : Promise.resolve({});
                const results = await Promise.allSettled([
                    getDocument(id),
                    getDocumentChunks(id),
                    graphRequest,
                ]);
                if (results[0].status
                    === 'fulfilled') {
                    detail.value =
                        results[0].value;
                }
                else {
                    throw results[0].reason;
                }
                if (results[1].status
                    === 'fulfilled') {
                    chunkData.value =
                        results[1].value;
                }
                else {
                    throw results[1].reason;
                }
                if (results[2].status
                    === 'fulfilled') {
                    graphStatus.value =
                        results[2].value;
                    graphStatusError.value = '';
                }
                else {
                    graphStatus.value = {};
                    graphStatusError.value =
                        results[2].reason
                            instanceof Error
                            ? results[2].reason.message
                            : String(results[2].reason);
                }
            }
            catch (exc) {
                detail.value = {};
                chunkData.value = {};
                graphStatus.value = {};
                error.value =
                    exc instanceof Error
                        ? exc.message
                        : String(exc);
            }
            finally {
                loading.value = false;
            }
        }
        watch(documentOptions, (value) => {
            if (!selectedDocumentId.value
                && value.length) {
                selectedDocumentId.value =
                    String(value[0].document_id
                        || '');
                loadDocument();
            }
        }, {
            immediate: true,
        });
        return {
            selectedDocumentId,
            loading,
            error,
            detail,
            chunkData,
            graphStatus,
            graphStatusError,
            graphChunks,
            relationTypeEntries,
            provenanceMethodEntries,
            chunkGraph,
            selectedGraphChunkId,
            chunkGraphLoading,
            chunkGraphError,
            chunkGraphRelations,
            chunkEvidenceGaps,
            selectedChunk,
            documentOptions,
            versions,
            chunks,
            visibleChunks,
            hasMoreChunks,
            formatValue,
            formatTime,
            selectChunk,
            showMoreChunks,
            openChunkGraph,
            closeChunkGraph,
            loadDocument,
        };
    },
    template: `
    <article class="panel-card admin-document-inspector">
      <div class="admin-section-head">
        <div>
          <span class="eyebrow">
            DOCUMENT INSPECTOR
          </span>

          <h3>
            \u6587\u6863\u8be6\u60c5
          </h3>
        </div>

        <span
          v-if="chunkData.total !== undefined"
          class="admin-count-chip"
        >
          {{chunkData.total}}
          chunks
        </span>
      </div>

      <p class="admin-muted">
        \u53ea\u8bfb\u67e5\u770b\u6587\u6863\u57fa\u672c\u4fe1\u606f\u3001
        \u7248\u672c\u3001\u6d3b\u52a8 Chunk \u53ca\u5411\u91cf\u5316\u5143\u6570\u636e\u3002
      </p>

      <div class="admin-document-selector">
        <select
          v-model="selectedDocumentId"
          class="admin-graph-control"
          @change="loadDocument"
        >
          <option value="">
            \u9009\u62e9\u6587\u6863
          </option>

          <option
            v-for="item in documentOptions"
            :key="item.document_id"
            :value="item.document_id"
          >
            {{item.title}}
            ·
            {{item.knowledge_base_name || '-'}}
          </option>
        </select>

        <button
          class="btn secondary"
          type="button"
          :disabled="
            loading
            || !selectedDocumentId
          "
          @click="loadDocument"
        >
          {{
            loading
              ? '\u52a0\u8f7d\u4e2d...'
              : '\u5237\u65b0\u8be6\u60c5'
          }}
        </button>
      </div>

      <div
        v-if="error"
        class="alert error"
      >
        {{error}}
      </div>

      <div
        v-if="
          !loading
          && detail.id
        "
        class="admin-document-detail-body"
      >
        <div class="admin-document-summary">
          <div class="admin-document-title">
            <span
              class="admin-status success"
            >
              {{detail.status}}
            </span>

            <h4>
              {{detail.title}}
            </h4>

            <code>
              {{detail.id}}
            </code>
          </div>

          <div class="admin-document-summary-grid">
            <div>
              <span>Document Type</span>
              <strong>
                {{
                  formatValue(
                    detail.document_type
                  )
                }}
              </strong>
            </div>

            <div>
              <span>MIME</span>
              <strong>
                {{
                  formatValue(
                    detail.mime_type
                  )
                }}
              </strong>
            </div>

            <div>
              <span>Versions</span>
              <strong>
                {{versions.length}}
              </strong>
            </div>

            <div>
              <span>Active Chunks</span>
              <strong>
                {{chunkData.total ?? 0}}
              </strong>
            </div>

            <div>
              <span>Checksum SHA256</span>
              <code>
                {{
                  formatValue(
                    detail.checksum_sha256
                  )
                }}
              </code>
            </div>

            <div>
              <span>Object Key</span>
              <code>
                {{
                  formatValue(
                    detail.object_key
                  )
                }}
              </code>
            </div>
          </div>
        </div>

        <div class="admin-document-section admin-document-graph-status">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                GRAPH EXTRACTION
              </span>

              <h4>
                \u56fe\u8c31\u5173\u7cfb\u72b6\u6001
              </h4>
            </div>

            <span
              v-if="graphStatus.read_only"
              class="admin-status success"
            >
              READ ONLY
            </span>
          </div>

          <div
            v-if="graphStatusError"
            class="alert error"
          >
            {{graphStatusError}}
          </div>

          <template
            v-if="
              graphStatus.document_id
            "
          >
            <div class="admin-document-graph-metrics">
              <div>
                <span>
                  Active Chunks
                </span>

                <strong>
                  {{
                    graphStatus.chunk_count
                    ?? 0
                  }}
                </strong>
              </div>

              <div>
                <span>
                  Relation-backed Chunks
                </span>

                <strong>
                  {{
                    graphStatus
                      .relation_backed_chunk_count
                    ?? 0
                  }}
                </strong>
              </div>

              <div>
                <span>
                  Graph Relations
                </span>

                <strong>
                  {{
                    graphStatus.relation_count
                    ?? 0
                  }}
                </strong>
              </div>

              <div>
                <span>
                  Evidence Gaps
                </span>

                <strong>
                  {{
                    graphStatus
                      .evidence_gap_count
                    ?? 0
                  }}
                </strong>
              </div>
            </div>

            <div
              v-if="relationTypeEntries.length"
              class="admin-document-relation-types"
            >
              <span
                v-for="item in relationTypeEntries"
                :key="item.type"
                class="admin-status success"
              >
                {{item.type}}
                ·
                {{item.count}}
              </span>
            </div>

            <div
              v-if="provenanceMethodEntries.length"
              class="admin-document-provenance"
            >
              <span
                class="admin-document-provenance-label"
              >
                Provenance
              </span>

              <span
                v-for="item in provenanceMethodEntries"
                :key="item.method"
                class="admin-status pending"
              >
                {{item.method}}
                ·
                {{item.count}}
              </span>
            </div>

            <div class="admin-system-note admin-document-graph-note">
              <strong>
                \u72b6\u6001\u8bf4\u660e
              </strong>

              <span>
                \u201c\u5df2\u5f62\u6210\u56fe\u8c31\u5173\u7cfb\u7684 Chunk\u201d
                \u6307\u5f53\u524d CampusMind \u56fe\u8c31\u4e2d\u5b58\u5728
                campusmind_graph=true
                \u4e14 source_chunk_id
                \u53ef\u8ffd\u6eaf\u5230\u8be5 Chunk \u7684\u5173\u7cfb\u3002
                extraction_method
                \u7f3a\u5931\u65f6\u663e\u793a
                &lt;unspecified&gt;\uff0c
                \u4e0d\u63a8\u65ad\u5176\u6765\u6e90\u4e3a LLM\u3001
                seed \u6216 structured ingestion\u3002
                0 \u6761\u5173\u7cfb\u4e0d\u80fd\u5355\u72ec\u8bc1\u660e Chunk
                \u672a\u6267\u884c\u8fc7\u56fe\u8c31\u5904\u7406\u3002
              </span>
            </div>

            <div
              v-if="graphChunks.length"
              class="admin-table-wrap"
            >
              <table class="admin-table admin-wide-table">
                <thead>
                  <tr>
                    <th>Chunk</th>
                    <th>Location</th>
                    <th>Relations</th>
                    <th>Relation Types</th>
                    <th>Provenance</th>
                    <th>Evidence Gaps</th>
                    <th>Status</th>
                    <th>关系详情</th>
                  </tr>
                </thead>

                <tbody>
                  <tr
                    v-for="item in graphChunks"
                    :key="item.chunk_id"
                  >
                    <td>
                      <strong>
                        #{{item.chunk_index}}
                      </strong>

                      <small>
                        {{item.chunk_id}}
                      </small>
                    </td>

                    <td>
                      <small>
                        page:
                        {{
                          formatValue(
                            item.page
                          )
                        }}
                      </small>

                      <small>
                        {{
                          formatValue(
                            item.section
                          )
                        }}
                      </small>
                    </td>

                    <td>
                      <strong>
                        {{item.relation_count}}
                      </strong>
                    </td>

                    <td>
                      {{
                        Array.isArray(
                          item.relation_types
                        )
                        && item
                          .relation_types
                          .length
                          ? item
                              .relation_types
                              .join(', ')
                          : '-'
                      }}
                    </td>

                    <td>
                      {{
                        Array.isArray(
                          item.extraction_methods
                        )
                        && item
                          .extraction_methods
                          .length
                          ? item
                              .extraction_methods
                              .join(', ')
                          : '-'
                      }}
                    </td>

                    <td>
                      <span
                        class="admin-status"
                        :class="
                          item.evidence_gap_count
                            > 0
                            ? 'pending'
                            : 'success'
                        "
                      >
                        {{
                          item.evidence_gap_count
                          ?? 0
                        }}
                      </span>
                    </td>

                    <td>
                      <span
                        class="admin-status"
                        :class="
                          item.has_relations
                            ? 'success'
                            : 'pending'
                        "
                      >
                        {{
                          item.has_relations
                            ? '\u5df2\u5f62\u6210\u5173\u7cfb'
                            : '\u6682\u65e0\u5173\u7cfb'
                        }}
                      </span>
                    </td>

                    <td>
                      <button
                        v-if="item.has_relations"
                        class="btn secondary admin-chunk-graph-button"
                        type="button"
                        :disabled="
                          chunkGraphLoading
                          && selectedGraphChunkId
                             === item.chunk_id
                        "
                        @click="
                          openChunkGraph(
                            item.chunk_id
                          )
                        "
                      >
                        {{
                          chunkGraphLoading
                          && selectedGraphChunkId
                             === item.chunk_id
                            ? '\u52a0\u8f7d\u4e2d...'
                            : '\u67e5\u770b\u5173\u7cfb'
                        }}
                      </button>

                      <span
                        v-else
                        class="admin-muted"
                      >
                        -
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              v-if="
                chunkGraphLoading
                || chunkGraphError
                || selectedGraphChunkId
              "
              class="admin-chunk-graph-detail"
            >
              <div class="admin-section-head">
                <div>
                  <span class="eyebrow">
                    CHUNK GRAPH EVIDENCE
                  </span>

                  <h4>
                    Chunk \u56fe\u8c31\u5173\u7cfb\u4e0e Evidence
                  </h4>
                </div>

                <button
                  class="btn secondary"
                  type="button"
                  @click="closeChunkGraph"
                >
                  \u5173\u95ed
                </button>
              </div>

              <div
                v-if="chunkGraphError"
                class="alert error"
              >
                {{chunkGraphError}}
              </div>

              <div
                v-else-if="chunkGraphLoading"
                class="admin-empty"
              >
                \u6b63\u5728\u8bfb\u53d6 Chunk \u56fe\u8c31\u5173\u7cfb...
              </div>

              <template v-else>
                <div class="admin-chunk-graph-summary">
                  <div>
                    <span>Chunk ID</span>
                    <code>
                      {{selectedGraphChunkId}}
                    </code>
                  </div>

                  <div>
                    <span>Relations</span>
                    <strong>
                      {{
                        chunkGraph.relation_count
                        ?? chunkGraphRelations.length
                      }}
                    </strong>
                  </div>

                  <div>
                    <span>Evidence Gaps</span>
                    <strong>
                      {{chunkEvidenceGaps.length}}
                    </strong>
                  </div>
                </div>

                <div
                  v-if="chunkEvidenceGaps.length"
                  class="admin-chunk-evidence-gaps"
                >
                  <strong>
                    Evidence Gaps
                  </strong>

                  <code
                    v-for="item in chunkEvidenceGaps"
                    :key="item"
                  >
                    {{item}}
                  </code>
                </div>

                <div
                  v-if="chunkGraphRelations.length"
                  class="admin-table-wrap"
                >
                  <table class="admin-table admin-wide-table">
                    <thead>
                      <tr>
                        <th>Source</th>
                        <th>Relation</th>
                        <th>Target</th>
                        <th>Confidence</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>

                    <tbody>
                      <tr
                        v-for="item in chunkGraphRelations"
                        :key="item.relation_id"
                      >
                        <td>
                          <strong>
                            {{item.source_name}}
                          </strong>

                          <small>
                            {{item.source_type}}
                          </small>

                          <code class="admin-graph-id">
                            {{item.source_id}}
                          </code>
                        </td>

                        <td>
                          <span class="admin-status success">
                            {{item.relation_type}}
                          </span>

                          <code class="admin-graph-id">
                            {{item.relation_id}}
                          </code>
                        </td>

                        <td>
                          <strong>
                            {{item.target_name}}
                          </strong>

                          <small>
                            {{item.target_type}}
                          </small>

                          <code class="admin-graph-id">
                            {{item.target_id}}
                          </code>
                        </td>

                        <td>
                          {{
                            item.confidence
                            === null
                            || item.confidence
                               === undefined
                              ? '-'
                              : Number(
                                  item.confidence
                                ).toFixed(2)
                          }}
                        </td>

                        <td>
                          <small>
                            document:
                          </small>

                          <code class="admin-graph-evidence">
                            {{
                              item.source_document_id
                              || '-'
                            }}
                          </code>

                          <small>
                            chunk:
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
                  \u8be5 Chunk \u5f53\u524d\u6ca1\u6709\u53ef\u5c55\u793a\u7684\u56fe\u8c31\u5173\u7cfb
                </div>
              </template>
            </div>

          </template>

          <div
            v-else-if="
              !graphStatusError
            "
            class="admin-empty"
          >
            \u5f53\u524d\u6682\u65e0\u6587\u6863\u56fe\u8c31\u72b6\u6001
          </div>
        </div>

        <div class="admin-document-section">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                VERSIONS
              </span>

              <h4>
                \u7248\u672c\u4fe1\u606f
              </h4>
            </div>

            <span class="admin-count-chip">
              {{versions.length}}
            </span>
          </div>

          <div
            v-if="versions.length"
            class="admin-table-wrap"
          >
            <table class="admin-table admin-wide-table">
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Status</th>
                  <th>Department</th>
                  <th>Effective</th>
                  <th>Published</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in versions"
                  :key="item.id"
                >
                  <td>
                    <strong>
                      {{item.version}}
                    </strong>

                    <small>
                      {{item.id}}
                    </small>
                  </td>

                  <td>
                    <span
                      class="admin-status"
                      :class="
                        item.status === 'active'
                          ? 'success'
                          : 'pending'
                      "
                    >
                      {{item.status}}
                    </span>
                  </td>

                  <td>
                    {{
                      formatValue(
                        item.department
                      )
                    }}
                  </td>

                  <td>
                    <small>
                      {{
                        formatValue(
                          item.effective_from
                        )
                      }}
                    </small>

                    <small>
                      →
                      {{
                        formatValue(
                          item.effective_to
                        )
                      }}
                    </small>
                  </td>

                  <td>
                    {{
                      formatTime(
                        item.published_at
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
            \u5f53\u524d\u6587\u6863\u6ca1\u6709\u7248\u672c\u6570\u636e
          </div>
        </div>

        <div class="admin-document-section">
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                ACTIVE CHUNKS
              </span>

              <h4>
                Chunk \u6d4f\u89c8
              </h4>
            </div>

            <span class="admin-count-chip">
              {{chunkData.total ?? 0}}
            </span>
          </div>

          <div
            v-if="visibleChunks.length"
            class="admin-table-wrap"
          >
            <table class="admin-table admin-wide-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Location</th>
                  <th>Tokens</th>
                  <th>Embedding</th>
                  <th>Content</th>
                  <th>\u8be6\u60c5</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in visibleChunks"
                  :key="item.id"
                >
                  <td>
                    <strong>
                      {{item.chunk_index}}
                    </strong>
                  </td>

                  <td>
                    <small>
                      page:
                      {{
                        formatValue(
                          item.page
                        )
                      }}
                    </small>

                    <small>
                      section:
                      {{
                        formatValue(
                          item.section
                        )
                      }}
                    </small>

                    <small>
                      chapter:
                      {{
                        formatValue(
                          item.chapter
                        )
                      }}
                    </small>
                  </td>

                  <td>
                    {{
                      formatValue(
                        item.token_count
                      )
                    }}
                  </td>

                  <td>
                    <small>
                      {{
                        formatValue(
                          item.embedding_model
                        )
                      }}
                    </small>

                    <small>
                      dim:
                      {{
                        formatValue(
                          item.embedding_dimensions
                        )
                      }}
                    </small>
                  </td>

                  <td class="admin-document-content-preview">
                    {{
                      String(
                        item.content
                        || ''
                      ).slice(
                        0,
                        120,
                      )
                    }}
                    {{
                      String(
                        item.content
                        || ''
                      ).length > 120
                        ? '…'
                        : ''
                    }}
                  </td>

                  <td>
                    <button
                      class="btn secondary"
                      type="button"
                      @click="
                        selectChunk(
                          item
                        )
                      "
                    >
                      \u67e5\u770b
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
            \u5f53\u524d\u6587\u6863\u6ca1\u6709\u6d3b\u52a8 Chunk
          </div>

          <div
            v-if="hasMoreChunks"
            class="admin-document-more"
          >
            <button
              class="btn secondary"
              type="button"
              @click="showMoreChunks"
            >
              \u518d\u663e\u793a 20 \u6761
            </button>

            <span>
              \u5df2\u663e\u793a
              {{visibleChunks.length}}
              /
              {{chunks.length}}
            </span>
          </div>
        </div>

        <div
          v-if="selectedChunk.id"
          class="admin-document-chunk-detail"
        >
          <div class="admin-section-head">
            <div>
              <span class="eyebrow">
                CHUNK DETAIL
              </span>

              <h4>
                Chunk
                #{{selectedChunk.chunk_index}}
              </h4>
            </div>

            <button
              class="btn secondary"
              type="button"
              @click="
                selectedChunk = {}
              "
            >
              \u5173\u95ed
            </button>
          </div>

          <div class="admin-document-chunk-meta">
            <div>
              <span>Chunk ID</span>
              <code>
                {{selectedChunk.id}}
              </code>
            </div>

            <div>
              <span>Version ID</span>
              <code>
                {{
                  selectedChunk
                    .document_version_id
                }}
              </code>
            </div>

            <div>
              <span>Tokens</span>
              <strong>
                {{
                  formatValue(
                    selectedChunk
                      .token_count
                  )
                }}
              </strong>
            </div>

            <div>
              <span>Page</span>
              <strong>
                {{
                  formatValue(
                    selectedChunk.page
                  )
                }}
              </strong>
            </div>
          </div>

          <pre class="admin-document-chunk-content">{{selectedChunk.content}}</pre>
        </div>
      </div>

      <div
        v-else-if="
          !loading
          && !selectedDocumentId
        "
        class="admin-empty"
      >
        \u8bf7\u9009\u62e9\u4e00\u4e2a\u6587\u6863\u67e5\u770b\u8be6\u60c5
      </div>
    </article>
  `,
};
