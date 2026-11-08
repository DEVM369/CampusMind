import { computed, onMounted, ref, typedRef, } from '../vue.js';
import { getGraphOntology, getGraphStats, searchGraph, } from '../api.js';
function textValue(value, fallback = '-') {
    if (value === null
        || value === undefined
        || value === '') {
        return fallback;
    }
    return String(value);
}
function diagnosticText(value) {
    const key = String(value || '');
    const map = {
        graph_edges_failed_source_evidence_validation: '\u56fe\u4e2d\u5b58\u5728\u5019\u9009\u5173\u7cfb\uff0c\u4f46\u5176\u6765\u6e90\u8bc1\u636e\u672a\u901a\u8fc7\u5f53\u524d\u6709\u6548\u77e5\u8bc6\u5e93\u6821\u9a8c\uff0c\u56e0\u6b64 GraphRAG \u672a\u8fd4\u56de\u8fd9\u4e9b\u5173\u7cfb\u3002',
        entity_not_linked: '\u672a\u5728\u5f53\u524d\u77e5\u8bc6\u56fe\u8c31\u4e2d\u5339\u914d\u5230\u8be5\u5b9e\u4f53\u3002',
        no_graph_edge_for_plan: '\u5df2\u627e\u5230\u5b9e\u4f53\uff0c\u4f46\u5f53\u524d\u68c0\u7d22\u8ba1\u5212\u4e0b\u6ca1\u6709\u5339\u914d\u5173\u7cfb\u3002',
    };
    return map[key] || key;
}
function nodeTypeLabel(value) {
    const key = String(value || '');
    const map = {
        Student: '\u5b66\u751f',
        Teacher: '\u6559\u5e08',
        College: '\u5b66\u9662',
        Department: '\u9662\u7cfb',
        Major: '\u4e13\u4e1a',
        Course: '\u8bfe\u7a0b',
        KnowledgePoint: '\u77e5\u8bc6\u70b9',
        Policy: '\u653f\u7b56',
        Procedure: '\u6d41\u7a0b',
        Requirement: '\u8981\u6c42',
        ResearchArea: '\u7814\u7a76\u65b9\u5411',
        Paper: '\u8bba\u6587',
        Project: '\u9879\u76ee',
        Lab: '\u5b9e\u9a8c\u5ba4',
        Book: '\u56fe\u4e66',
        LibraryResource: '\u56fe\u4e66\u9986\u8d44\u6e90',
        Building: '\u5efa\u7b51',
        Classroom: '\u6559\u5ba4',
        Activity: '\u6d3b\u52a8',
    };
    return map[key] || key || '-';
}
function relationLabel(value) {
    const key = String(value || '');
    const map = {
        ENROLLED_IN: '\u5c31\u8bfb\u4e8e',
        BELONGS_TO: '\u96b6\u5c5e\u4e8e',
        REQUIRES: '\u8981\u6c42',
        PREREQUISITE_OF: '\u5148\u4fee\u4e8e',
        TEACHES: '\u6388\u8bfe',
        RESEARCHES: '\u7814\u7a76',
        AUTHORED: '\u8457\u4f5c',
        RELATED_TO: '\u76f8\u5173\u4e8e',
        USES: '\u4f7f\u7528',
        APPLIES_TO: '\u9002\u7528\u4e8e',
        HAS_REQUIREMENT: '\u5305\u542b\u8981\u6c42',
        MEMBER_OF: '\u6210\u5458\u4e8e',
        LOCATED_IN: '\u4f4d\u4e8e',
        OFFERS: '\u5f00\u8bbe',
        HAS_KNOWLEDGE_POINT: '\u5305\u542b\u77e5\u8bc6\u70b9',
        PARTICIPATES_IN: '\u53c2\u4e0e',
        WORKS_ON: '\u53c2\u4e0e\u9879\u76ee',
    };
    return map[key] || key || '-';
}
function circularLayout(rawNodes) {
    const count = rawNodes.length;
    if (!count)
        return [];
    const cx = 450;
    const cy = 235;
    const radiusX = count <= 4
        ? 210
        : 330;
    const radiusY = count <= 4
        ? 125
        : 175;
    return rawNodes.map((item, index) => {
        if (count === 1) {
            return {
                id: String(item.id),
                name: String(item.name),
                type: String(item.type || ''),
                x: cx,
                y: cy,
                data: item.data || item,
            };
        }
        const angle = (Math.PI * 2 * index
            / count)
            - Math.PI / 2;
        return {
            id: String(item.id),
            name: String(item.name),
            type: String(item.type || ''),
            x: cx
                + Math.cos(angle)
                    * radiusX,
            y: cy
                + Math.sin(angle)
                    * radiusY,
            data: item.data || item,
        };
    });
}
export const GraphView = {
    setup() {
        const loading = ref(false);
        const searching = ref(false);
        const error = ref('');
        const mode = typedRef('ontology');
        const query = ref('');
        const stats = typedRef({});
        const ontology = typedRef({});
        const searchResult = typedRef({});
        const selectedNode = typedRef(null);
        const quickQueries = [
            '\u673a\u5668\u5b66\u4e60\u7684\u5148\u4fee\u8bfe\u7a0b\u662f\u4ec0\u4e48\uff1f',
            '\u674e\u660e\u7814\u7a76\u54ea\u4e9b\u65b9\u5411\uff1f',
            '\u54ea\u4e9b\u6559\u5e08\u7814\u7a76\u77e5\u8bc6\u56fe\u8c31\uff1f',
        ];
        const nodesByType = computed(() => {
            const value = stats.value.nodes_by_type;
            if (!value
                || typeof value !== 'object') {
                return [];
            }
            return Object.entries(value)
                .map(([key, count]) => ({
                type: key,
                count: Number(count || 0),
            }))
                .sort((a, b) => b.count - a.count);
        });
        const relationsByType = computed(() => {
            const value = stats.value.relations_by_type;
            if (!value
                || typeof value !== 'object') {
                return [];
            }
            return Object.entries(value)
                .map(([key, count]) => ({
                type: key,
                count: Number(count || 0),
            }))
                .sort((a, b) => b.count - a.count);
        });
        const ontologyNodes = computed(() => {
            const entities = Array.isArray(ontology.value.entities)
                ? ontology.value.entities
                : [];
            const raw = entities.map((item) => ({
                id: 'ontology:'
                    + String(item.type),
                name: nodeTypeLabel(item.type),
                type: String(item.type || ''),
                data: item,
            }));
            return circularLayout(raw);
        });
        const ontologyEdges = computed(() => {
            const relations = Array.isArray(ontology.value.relations)
                ? ontology.value.relations
                : [];
            const result = [];
            for (const relation of relations) {
                const sources = Array.isArray(relation.source_types)
                    ? relation.source_types
                    : [];
                const targets = Array.isArray(relation.target_types)
                    ? relation.target_types
                    : [];
                for (const source of sources) {
                    for (const target of targets) {
                        result.push({
                            id: String(relation.type)
                                + ':'
                                + String(source)
                                + ':'
                                + String(target),
                            source: 'ontology:'
                                + String(source),
                            target: 'ontology:'
                                + String(target),
                            label: String(relation.type || ''),
                            data: relation,
                        });
                    }
                }
            }
            return result;
        });
        const entityGraph = computed(() => {
            const linked = Array.isArray(searchResult.value
                .linked_entities)
                ? searchResult.value
                    .linked_entities
                : [];
            const paths = Array.isArray(searchResult.value.paths)
                ? searchResult.value.paths
                : [];
            const nodeMap = new Map();
            for (const item of linked) {
                const id = String(item.entity_id
                    || item.name
                    || item.query_name
                    || '');
                if (!id)
                    continue;
                nodeMap.set(id, {
                    id,
                    name: String(item.name
                        || item.query_name
                        || id),
                    type: String(item.entity_type
                        || ''),
                    data: item,
                });
            }
            const edges = [];
            for (let index = 0; index < paths.length; index += 1) {
                const path = paths[index];
                const sourceId = String(path.source_id
                    || path.anchor_id
                    || '');
                const targetId = String(path.target_id
                    || '');
                if (sourceId
                    && !nodeMap.has(sourceId)) {
                    nodeMap.set(sourceId, {
                        id: sourceId,
                        name: String(path.source_name
                            || sourceId),
                        type: String(path.source_type
                            || ''),
                        data: {
                            entity_id: sourceId,
                            name: path.source_name
                                || sourceId,
                            entity_type: path.source_type,
                        },
                    });
                }
                if (targetId
                    && !nodeMap.has(targetId)) {
                    nodeMap.set(targetId, {
                        id: targetId,
                        name: String(path.target_name
                            || targetId),
                        type: String(path.target_type
                            || ''),
                        data: {
                            entity_id: targetId,
                            name: path.target_name
                                || targetId,
                            entity_type: path.target_type,
                        },
                    });
                }
                if (sourceId
                    && targetId) {
                    edges.push({
                        id: String(path.path_id
                            || 'path')
                            + ':'
                            + String(path.hop_index
                                ?? index),
                        source: sourceId,
                        target: targetId,
                        label: String(path.relation_type
                            || ''),
                        data: path,
                    });
                }
            }
            return {
                nodes: circularLayout(Array.from(nodeMap.values())),
                edges,
            };
        });
        const visibleNodes = computed(() => mode.value === 'ontology'
            ? ontologyNodes.value
            : entityGraph.value.nodes);
        const visibleEdges = computed(() => mode.value === 'ontology'
            ? ontologyEdges.value
            : entityGraph.value.edges);
        const nodeLookup = computed(() => {
            const map = new Map();
            for (const item of visibleNodes.value) {
                map.set(item.id, item);
            }
            return map;
        });
        const drawableEdges = computed(() => visibleEdges.value
            .map((edge) => ({
            ...edge,
            sourceNode: nodeLookup.value.get(edge.source),
            targetNode: nodeLookup.value.get(edge.target),
        }))
            .filter((edge) => edge.sourceNode
            && edge.targetNode));
        const paths = computed(() => Array.isArray(searchResult.value.paths)
            ? searchResult.value.paths
            : []);
        const citations = computed(() => Array.isArray(searchResult.value.citations)
            ? searchResult.value.citations
            : []);
        const diagnostics = computed(() => Array.isArray(searchResult.value.diagnostics)
            ? searchResult.value.diagnostics
            : []);
        async function loadOverview() {
            loading.value = true;
            error.value = '';
            try {
                const [statsResult, ontologyResult,] = await Promise.all([
                    getGraphStats(),
                    getGraphOntology(),
                ]);
                stats.value =
                    statsResult || {};
                ontology.value =
                    ontologyResult || {};
                mode.value = 'ontology';
            }
            catch (exc) {
                error.value =
                    exc instanceof Error
                        ? exc.message
                        : String(exc);
            }
            finally {
                loading.value = false;
            }
        }
        async function runSearch(value) {
            const next = String(value
                ?? query.value
                ?? '').trim();
            if (!next)
                return;
            query.value = next;
            searching.value = true;
            error.value = '';
            selectedNode.value = null;
            try {
                searchResult.value =
                    await searchGraph(next, 12);
                mode.value = 'entity';
                const first = entityGraph.value.nodes[0];
                if (first) {
                    selectedNode.value = first;
                }
            }
            catch (exc) {
                error.value =
                    exc instanceof Error
                        ? exc.message
                        : String(exc);
            }
            finally {
                searching.value = false;
            }
        }
        function showOntology() {
            mode.value = 'ontology';
            selectedNode.value = null;
        }
        function showEntity() {
            mode.value = 'entity';
            selectedNode.value =
                entityGraph.value.nodes[0]
                    || null;
        }
        function selectNode(node) {
            selectedNode.value = node;
        }
        function citationName(item, index) {
            return textValue(item.source_name
                || item.document_name
                || item.title
                || item.document_id, 'Evidence '
                + String(index + 1));
        }
        function citationMeta(item) {
            return textValue(item.chunk_id
                || item.source_chunk_id
                || item.document_id, '');
        }
        onMounted(() => {
            loadOverview();
        });
        return {
            loading,
            searching,
            error,
            mode,
            query,
            stats,
            ontology,
            searchResult,
            selectedNode,
            quickQueries,
            nodesByType,
            relationsByType,
            visibleNodes,
            visibleEdges,
            drawableEdges,
            paths,
            citations,
            diagnostics,
            loadOverview,
            runSearch,
            showOntology,
            showEntity,
            selectNode,
            diagnosticText,
            nodeTypeLabel,
            relationLabel,
            textValue,
            citationName,
            citationMeta,
        };
    },
    template: `
  <section class="page graph-page">
    <header class="page-header graph-header">
      <div>
        <span class="eyebrow">
          KNOWLEDGE GRAPH
        </span>

        <h1>
          &#30693;&#35782;&#22270;&#35889;
        </h1>

        <p>
          &#22522;&#20110; Neo4j &#19982; GraphRAG &#30340;&#26657;&#22253;&#23454;&#20307;&#12289;&#20851;&#31995;&#19982;&#35777;&#25454;&#21487;&#35270;&#21270;
        </p>
      </div>

      <button
        class="btn secondary"
        :disabled="loading"
        @click="loadOverview"
      >
        {{
          loading
            ? '\u5237\u65b0\u4e2d...'
            : '\u5237\u65b0\u56fe\u8c31'
        }}
      </button>
    </header>

    <div
      v-if="error"
      class="alert error graph-error"
    >
      {{error}}
    </div>

    <div class="graph-stat-grid">
      <article class="graph-stat-card">
        <span>
          &#22270;&#35889;&#33410;&#28857;
        </span>
        <strong>
          {{stats.node_count ?? '-'}}
        </strong>
        <small>
          Neo4j CampusEntity
        </small>
      </article>

      <article class="graph-stat-card">
        <span>
          &#22270;&#35889;&#20851;&#31995;
        </span>
        <strong>
          {{stats.relation_count ?? '-'}}
        </strong>
        <small>
          CampusMind relations
        </small>
      </article>

      <article class="graph-stat-card">
        <span>
          &#23454;&#20307;&#31867;&#22411;
        </span>
        <strong>
          {{ontology.entity_count ?? '-'}}
        </strong>
        <small>
          ontology entity types
        </small>
      </article>

      <article class="graph-stat-card">
        <span>
          &#20851;&#31995;&#31867;&#22411;
        </span>
        <strong>
          {{ontology.relation_count ?? '-'}}
        </strong>
        <small>
          ontology relations
        </small>
      </article>
    </div>

    <article class="panel-card graph-search-panel">
      <form
        class="graph-search-form"
        @submit.prevent="runSearch()"
      >
        <div class="graph-search-input-wrap">
          <span class="graph-search-icon">
            &#9906;
          </span>

          <input
            v-model="query"
            placeholder="&#36755;&#20837;&#35838;&#31243;&#12289;&#25945;&#24072;&#25110;&#30740;&#31350;&#26041;&#21521;&#65292;&#20363;&#22914;&#65306;&#26426;&#22120;&#23398;&#20064;"
          >
        </div>

        <button
          class="btn primary"
          type="submit"
          :disabled="
            searching
            || !query.trim()
          "
        >
          {{
            searching
              ? '\u68c0\u7d22\u4e2d...'
              : '\u68c0\u7d22\u56fe\u8c31'
          }}
        </button>
      </form>

      <div class="graph-quick-row">
        <span>
          &#24555;&#36895;&#26597;&#35810;
        </span>

        <button
          v-for="item in quickQueries"
          :key="item"
          @click="runSearch(item)"
        >
          {{item}}
        </button>
      </div>
    </article>

    <div class="graph-workspace">
      <article class="panel-card graph-canvas-card">
        <div class="graph-toolbar">
          <div>
            <span class="eyebrow">
              GRAPH VIEW
            </span>

            <h3>
              {{
                mode === 'ontology'
                  ? '\u672c\u4f53\u7ed3\u6784'
                  : '\u5b9e\u4f53\u5173\u7cfb'
              }}
            </h3>
          </div>

          <div class="graph-mode-switch">
            <button
              :class="{
                active:
                  mode === 'ontology'
              }"
              @click="showOntology"
            >
              &#26412;&#20307;&#32467;&#26500;
            </button>

            <button
              :class="{
                active:
                  mode === 'entity'
              }"
              :disabled="
                !searchResult.query
              "
              @click="showEntity"
            >
              &#23454;&#20307;&#20851;&#31995;
            </button>
          </div>
        </div>

        <div
          v-if="
            mode === 'entity'
            && searchResult.query
          "
          class="graph-query-summary"
        >
          <div>
            <span>
              &#26597;&#35810;
            </span>
            <strong>
              {{searchResult.query}}
            </strong>
          </div>

          <div>
            <span>
              &#21407;&#22987;&#20505;&#36873;&#20851;&#31995;
            </span>
            <strong>
              {{
                searchResult.raw_path_count
                ?? 0
              }}
            </strong>
          </div>

          <div>
            <span>
              &#35777;&#25454;&#39564;&#35777;&#36890;&#36807;
            </span>
            <strong>
              {{paths.length}}
            </strong>
          </div>
        </div>

        <div
          v-if="
            mode === 'entity'
            && searchResult.query
            && visibleNodes.length
            && paths.length === 0
            && searchResult.raw_path_count > 0
          "
          class="graph-trust-empty"
        >
          <div class="graph-trust-node">
            <div class="graph-trust-node-ring">
              {{
                visibleNodes[0].name
                  .slice(0,1)
              }}
            </div>

            <strong>
              {{visibleNodes[0].name}}
            </strong>

            <span>
              {{
                nodeTypeLabel(
                  visibleNodes[0].type
                )
              }}
            </span>
          </div>

          <div class="graph-trust-connector"></div>

          <div class="graph-trust-summary">
            <span class="eyebrow">
              EVIDENCE VALIDATION
            </span>

            <h3>
              &#20505;&#36873;&#20851;&#31995;&#23578;&#26410;&#36890;&#36807;&#35777;&#25454;&#26657;&#39564;
            </h3>

            <div class="graph-trust-metrics">
              <div>
                <strong>
                  {{
                    searchResult.raw_path_count
                    || 0
                  }}
                </strong>
                <span>
                  &#21407;&#22987;&#20505;&#36873;&#20851;&#31995;
                </span>
              </div>

              <div>
                <strong>
                  {{paths.length}}
                </strong>
                <span>
                  &#35777;&#25454;&#39564;&#35777;&#36890;&#36807;
                </span>
              </div>
            </div>

            <p>
              &#26410;&#36890;&#36807;&#24403;&#21069;&#26377;&#25928;&#26469;&#28304;&#35777;&#25454;&#26657;&#39564;&#30340;&#20851;&#31995;&#65292;&#19981;&#20250;&#20316;&#20026;&#21487;&#20449;&#22270;&#36335;&#24452;&#23637;&#31034;&#12290;
            </p>
          </div>
        </div>

        <div
          v-else-if="visibleNodes.length"
          class="graph-svg-wrap"
        >
          <svg
            class="graph-svg"
            viewBox="0 0 900 470"
            role="img"
          >
            <defs>
              <marker
                id="campusGraphArrow"
                markerWidth="10"
                markerHeight="10"
                refX="18"
                refY="5"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path
                  d="M 0 0 L 10 5 L 0 10 z"
                  class="graph-arrow-head"
                />
              </marker>
            </defs>

            <g class="graph-edges">
              <g
                v-for="edge in drawableEdges"
                :key="edge.id"
              >
                <line
                  :x1="edge.sourceNode.x"
                  :y1="edge.sourceNode.y"
                  :x2="edge.targetNode.x"
                  :y2="edge.targetNode.y"
                  class="graph-edge-line"
                  marker-end="url(#campusGraphArrow)"
                />

                <text
                  v-if="
                    visibleNodes.length <= 10
                  "
                  :x="
                    (
                      edge.sourceNode.x
                      + edge.targetNode.x
                    ) / 2
                  "
                  :y="
                    (
                      edge.sourceNode.y
                      + edge.targetNode.y
                    ) / 2 - 7
                  "
                  class="graph-edge-label"
                  text-anchor="middle"
                >
                  {{
                    relationLabel(
                      edge.label
                    )
                  }}
                </text>
              </g>
            </g>

            <g class="graph-nodes">
              <g
                v-for="node in visibleNodes"
                :key="node.id"
                class="graph-node"
                :class="{
                  selected:
                    selectedNode
                    && selectedNode.id
                       === node.id
                }"
                :transform="
                  'translate('
                  + node.x
                  + ','
                  + node.y
                  + ')'
                "
                @click="selectNode(node)"
              >
                <circle
                  r="34"
                  class="graph-node-circle"
                />

                <text
                  y="-3"
                  class="graph-node-title"
                  text-anchor="middle"
                >
                  {{
                    node.name.length > 8
                      ? node.name.slice(0,8)
                        + '\u2026'
                      : node.name
                  }}
                </text>

                <text
                  y="14"
                  class="graph-node-type"
                  text-anchor="middle"
                >
                  {{
                    nodeTypeLabel(
                      node.type
                    )
                  }}
                </text>
              </g>
            </g>
          </svg>
        </div>

        <div
          v-else
          class="graph-empty"
        >
          &#24403;&#21069;&#27809;&#26377;&#21487;&#26174;&#31034;&#30340;&#22270;&#20851;&#31995;
        </div>

        <div
          v-if="
            mode === 'entity'
            && diagnostics.length
          "
          class="graph-diagnostic-list"
        >
          <div
            v-for="item in diagnostics"
            :key="item"
            class="graph-diagnostic"
          >
            <strong>
              &#26816;&#32034;&#35786;&#26029;
            </strong>
            <span>
              {{diagnosticText(item)}}
            </span>
          </div>
        </div>
      </article>

      <aside class="graph-side-stack">
        <article class="panel-card graph-detail-card">
          <div class="graph-section-head">
            <div>
              <span class="eyebrow">
                NODE DETAIL
              </span>

              <h3>
                &#33410;&#28857;&#35814;&#24773;
              </h3>
            </div>
          </div>

          <template v-if="selectedNode">
            <div class="graph-selected-title">
              <div class="graph-selected-icon">
                {{
                  selectedNode.name
                    .slice(0,1)
                }}
              </div>

              <div>
                <strong>
                  {{selectedNode.name}}
                </strong>

                <span>
                  {{
                    nodeTypeLabel(
                      selectedNode.type
                    )
                  }}
                </span>
              </div>
            </div>

            <div class="graph-detail-kv">
              <div>
                <span>
                  &#23454;&#20307; ID
                </span>
                <strong>
                  {{
                    textValue(
                      selectedNode.data
                        .entity_id
                      || selectedNode.id
                    )
                  }}
                </strong>
              </div>

              <div>
                <span>
                  &#23454;&#20307;&#31867;&#22411;
                </span>
                <strong>
                  {{selectedNode.type}}
                </strong>
              </div>

              <div
                v-if="
                  selectedNode.data
                    .confidence
                  != null
                "
              >
                <span>
                  &#21305;&#37197;&#32622;&#20449;&#24230;
                </span>
                <strong>
                  {{
                    Number(
                      selectedNode.data
                        .confidence
                    ).toFixed(2)
                  }}
                </strong>
              </div>

              <div
                v-if="
                  selectedNode.data
                    .description
                "
              >
                <span>
                  &#35828;&#26126;
                </span>
                <strong>
                  {{
                    selectedNode.data
                      .description
                  }}
                </strong>
              </div>
            </div>
          </template>

          <div
            v-else
            class="graph-side-empty"
          >
            &#28857;&#20987;&#22270;&#20013;&#33410;&#28857;&#26597;&#30475;&#35814;&#24773;
          </div>
        </article>

        <article class="panel-card graph-type-card">
          <div class="graph-section-head">
            <div>
              <span class="eyebrow">
                LIVE DATA
              </span>

              <h3>
                &#24403;&#21069;&#22270;&#35889;&#32479;&#35745;
              </h3>
            </div>
          </div>

          <div class="graph-type-list">
            <div
              v-for="item in nodesByType"
              :key="item.type"
            >
              <span>
                {{nodeTypeLabel(item.type)}}
              </span>
              <strong>
                {{item.count}}
              </strong>
            </div>
          </div>

          <div class="graph-type-divider"></div>

          <div class="graph-type-list">
            <div
              v-for="item in relationsByType"
              :key="item.type"
            >
              <span>
                {{relationLabel(item.type)}}
              </span>
              <strong>
                {{item.count}}
              </strong>
            </div>
          </div>
        </article>
      </aside>
    </div>

    <div class="graph-bottom-grid">
      <article class="panel-card">
        <div class="graph-section-head">
          <div>
            <span class="eyebrow">
              VERIFIED PATHS
            </span>

            <h3>
              &#20851;&#31995;&#36335;&#24452;
            </h3>
          </div>

          <span class="graph-count-chip">
            {{paths.length}}
          </span>
        </div>

        <div
          v-if="paths.length"
          class="graph-path-list"
        >
          <div
            v-for="(item,index) in paths"
            :key="
              String(
                item.path_id
                || index
              )
              + ':'
              + String(
                item.hop_index
                || 0
              )
            "
            class="graph-path-item"
          >
            <div class="graph-path-index">
              {{index + 1}}
            </div>

            <div>
              <strong>
                {{
                  item.text
                  || (
                    textValue(
                      item.source_name,
                      item.source_id
                    )
                    + ' '
                    + relationLabel(
                      item.relation_type
                    )
                    + ' '
                    + textValue(
                      item.target_name,
                      item.target_id
                    )
                  )
                }}
              </strong>

              <span>
                {{
                  item.path_id
                  ? 'Path '
                    + item.path_id
                  : ''
                }}
                {{
                  item.hop_index
                  ? ' / Hop '
                    + item.hop_index
                  : ''
                }}
              </span>
            </div>
          </div>
        </div>

        <div
          v-else
          class="graph-side-empty"
        >
          {{
            searchResult.query
              ? '\u5f53\u524d\u67e5\u8be2\u6ca1\u6709\u901a\u8fc7\u6765\u6e90\u8bc1\u636e\u6821\u9a8c\u7684\u5173\u7cfb\u8def\u5f84'
              : '\u641c\u7d22\u5b9e\u4f53\u540e\u5c06\u5728\u8fd9\u91cc\u663e\u793a\u53ef\u4fe1\u5173\u7cfb\u8def\u5f84'
          }}
        </div>
      </article>

      <article class="panel-card">
        <div class="graph-section-head">
          <div>
            <span class="eyebrow">
              EVIDENCE
            </span>

            <h3>
              &#26469;&#28304;&#35777;&#25454;
            </h3>
          </div>

          <span class="graph-count-chip">
            {{citations.length}}
          </span>
        </div>

        <div
          v-if="citations.length"
          class="graph-evidence-list"
        >
          <div
            v-for="(item,index) in citations"
            :key="
              citationMeta(item)
              || index
            "
            class="graph-evidence-item"
          >
            <strong>
              {{
                citationName(
                  item,
                  index
                )
              }}
            </strong>

            <span>
              {{citationMeta(item)}}
            </span>
          </div>
        </div>

        <div
          v-else
          class="graph-side-empty"
        >
          {{
            searchResult.query
              ? '\u5f53\u524d\u672a\u6709\u901a\u8fc7\u6821\u9a8c\u7684\u6765\u6e90\u8bc1\u636e'
              : '\u901a\u8fc7 GraphRAG \u6821\u9a8c\u7684\u8bc1\u636e\u5c06\u5728\u8fd9\u91cc\u663e\u793a'
          }}
        </div>
      </article>
    </div>
  </section>`
};
