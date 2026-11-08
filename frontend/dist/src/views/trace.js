import { computed, onMounted, ref, typedRef, watch, } from '../vue.js';
import { getExecutionTrace, getExecutionTraces, } from '../api.js';
function safeJson(value) {
    try {
        return JSON.stringify(value ?? {}, null, 2);
    }
    catch {
        return String(value ?? '');
    }
}
export const TraceView = {
    props: {
        actorUserId: {
            type: String,
            default: '',
        },
    },
    emits: ['request-settings'],
    setup(props, context) {
        const loading = ref(false);
        const detailLoading = ref(false);
        const error = ref('');
        const traces = typedRef([]);
        const selectedTraceId = ref('');
        const detail = typedRef({});
        const completedCount = computed(() => traces.value.filter(item => String(item.status || '').toLowerCase()
            === 'completed').length);
        const hitlCount = computed(() => traces.value.filter(item => item.requires_approval
            === true).length);
        const averageLatency = computed(() => {
            const values = traces.value
                .map(item => Number(item.latency_ms))
                .filter(value => Number.isFinite(value));
            if (!values.length) {
                return 0;
            }
            return Math.round(values.reduce((sum, value) => sum + value, 0)
                / values.length);
        });
        const selectedTrace = computed(() => detail.value.trace
            || traces.value.find(item => item.trace_id
                === selectedTraceId.value)
            || null);
        const steps = computed(() => Array.isArray(detail.value.steps)
            ? detail.value.steps
            : []);
        const toolCalls = computed(() => Array.isArray(detail.value.tool_calls)
            ? detail.value.tool_calls
            : []);
        function requestSettings() {
            context.emit('request-settings');
        }
        function statusLabel(value) {
            const key = String(value || '').toLowerCase();
            const map = {
                completed: '\u5df2\u5b8c\u6210',
                success: '\u6210\u529f',
                running: '\u8fd0\u884c\u4e2d',
                pending: '\u5f85\u5904\u7406',
                paused: '\u5df2\u6682\u505c',
                failed: '\u5931\u8d25',
                error: '\u5f02\u5e38',
                rejected: '\u5df2\u62d2\u7edd',
                cancelled: '\u5df2\u53d6\u6d88',
                canceled: '\u5df2\u53d6\u6d88',
            };
            return map[key]
                || String(value || '-');
        }
        function statusTone(value) {
            const key = String(value || '').toLowerCase();
            if ([
                'completed',
                'success',
            ].includes(key)) {
                return 'success';
            }
            if ([
                'failed',
                'error',
                'rejected',
                'cancelled',
                'canceled',
            ].includes(key)) {
                return 'danger';
            }
            return 'pending';
        }
        function routeLabel(value) {
            const key = String(value || '').toLowerCase();
            const map = {
                rag: 'RAG',
                graph: 'GraphRAG',
                hybrid: 'Hybrid',
                sql: 'SQL',
                tool: 'Tool',
                agent: 'Agent',
            };
            return map[key]
                || String(value || '-');
        }
        function formatLatency(value) {
            const number = Number(value);
            if (!Number.isFinite(number)) {
                return '-';
            }
            if (number < 1000) {
                return (Math.round(number)
                    + ' ms');
            }
            return ((number / 1000)
                .toFixed(2)
                + ' s');
        }
        function formatTime(value) {
            if (!value)
                return '-';
            const parsed = new Date(String(value));
            if (Number.isNaN(parsed.getTime())) {
                return String(value);
            }
            return parsed.toLocaleString('zh-CN', {
                hour12: false,
            });
        }
        async function loadDetail(traceId) {
            const actor = String(props.actorUserId
                || '').trim();
            if (!actor
                || !traceId) {
                return;
            }
            selectedTraceId.value =
                traceId;
            detailLoading.value = true;
            error.value = '';
            try {
                detail.value =
                    await getExecutionTrace(traceId, actor);
            }
            catch (exc) {
                error.value =
                    exc instanceof Error
                        ? exc.message
                        : String(exc);
            }
            finally {
                detailLoading.value =
                    false;
            }
        }
        async function loadTraces() {
            const actor = String(props.actorUserId
                || '').trim();
            error.value = '';
            detail.value = {};
            selectedTraceId.value = '';
            if (!actor) {
                traces.value = [];
                return;
            }
            loading.value = true;
            try {
                const result = await getExecutionTraces(actor, 30);
                traces.value =
                    Array.isArray(result.traces)
                        ? result.traces
                        : [];
                if (traces.value.length) {
                    await loadDetail(String(traces.value[0]
                        .trace_id));
                }
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
        watch(() => props.actorUserId, () => {
            loadTraces();
        });
        onMounted(() => {
            loadTraces();
        });
        return {
            loading,
            detailLoading,
            error,
            traces,
            selectedTraceId,
            selectedTrace,
            steps,
            toolCalls,
            completedCount,
            hitlCount,
            averageLatency,
            requestSettings,
            loadTraces,
            loadDetail,
            statusLabel,
            statusTone,
            routeLabel,
            formatLatency,
            formatTime,
            safeJson,
        };
    },
    template: `
  <section class="page trace-page">
    <header class="page-header trace-header">
      <div>
        <span class="eyebrow">
          AGENT OBSERVABILITY
        </span>

        <h1>
          &#25191;&#34892;&#36861;&#36394;
        </h1>

        <p>
          &#26597;&#30475; Agent &#36335;&#30001;&#12289;&#25191;&#34892;&#27493;&#39588;&#12289;&#24037;&#20855;&#35843;&#29992;&#12289;&#20154;&#24037;&#30830;&#35748;&#19982;&#24615;&#33021;&#32791;&#26102;
        </p>
      </div>

      <button
        class="btn secondary"
        :disabled="
          loading
          || !actorUserId
        "
        @click="loadTraces"
      >
        {{
          loading
            ? '\u5237\u65b0\u4e2d...'
            : '\u5237\u65b0\u8ffd\u8e2a'
        }}
      </button>
    </header>

    <div
      v-if="!actorUserId"
      class="trace-auth-card"
    >
      <div class="trace-auth-icon">
        T
      </div>

      <h2>
        &#35831;&#20808;&#30331;&#24405;&#26597;&#30475;&#25191;&#34892;&#35760;&#24405;
      </h2>

      <p>
        &#30331;&#24405;&#21518;&#21487;&#26597;&#30475;&#24403;&#21069;&#36134;&#21495;&#30340; Agent &#36816;&#34892;&#21644;&#23457;&#35745;&#32447;&#32034;&#12290;
      </p>

      <button
        class="btn primary"
        @click="requestSettings"
      >
        &#30331;&#24405;&#26597;&#30475;
      </button>
    </div>

    <template v-else>
      <div
        v-if="error"
        class="alert error trace-error"
      >
        {{error}}
      </div>

      <div class="trace-stat-grid">
        <article class="trace-stat-card">
          <span>
            &#26368;&#36817;&#36816;&#34892;
          </span>

          <strong>
            {{traces.length}}
          </strong>

          <small>
            latest traces
          </small>
        </article>

        <article class="trace-stat-card">
          <span>
            &#24050;&#23436;&#25104;
          </span>

          <strong>
            {{completedCount}}
          </strong>

          <small>
            completed
          </small>
        </article>

        <article class="trace-stat-card">
          <span>
            HITL &#25191;&#34892;
          </span>

          <strong>
            {{hitlCount}}
          </strong>

          <small>
            requires approval
          </small>
        </article>

        <article class="trace-stat-card">
          <span>
            &#24179;&#22343;&#32791;&#26102;
          </span>

          <strong>
            {{
              formatLatency(
                averageLatency
              )
            }}
          </strong>

          <small>
            average latency
          </small>
        </article>
      </div>

      <div class="trace-workspace">
        <article class="panel-card trace-list-card">
          <div class="trace-section-head">
            <div>
              <span class="eyebrow">
                RUN HISTORY
              </span>

              <h3>
                &#25191;&#34892;&#35760;&#24405;
              </h3>
            </div>

            <span class="trace-count-chip">
              {{traces.length}}
            </span>
          </div>

          <div
            v-if="traces.length"
            class="trace-run-list"
          >
            <button
              v-for="item in traces"
              :key="item.trace_id"
              class="trace-run-item"
              :class="{
                active:
                  selectedTraceId
                  === item.trace_id
              }"
              @click="
                loadDetail(
                  item.trace_id
                )
              "
            >
              <div class="trace-run-top">
                <span
                  class="trace-status"
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

                <span class="trace-route-chip">
                  {{
                    routeLabel(
                      item.retrieval_strategy
                    )
                  }}
                </span>

                <span
                  v-if="
                    item.requires_approval
                  "
                  class="trace-hitl-chip"
                >
                  HITL
                </span>
              </div>

              <strong>
                {{item.query}}
              </strong>

              <div class="trace-run-meta">
                <span>
                  {{
                    formatLatency(
                      item.latency_ms
                    )
                  }}
                </span>

                <span>
                  {{item.step_count}}
                  steps
                </span>

                <span>
                  {{item.tool_call_count}}
                  tools
                </span>
              </div>

              <small>
                {{
                  formatTime(
                    item.started_at
                  )
                }}
              </small>
            </button>
          </div>

          <div
            v-else-if="!loading"
            class="trace-empty"
          >
            &#24403;&#21069;&#29992;&#25143;&#36824;&#27809;&#26377;&#21487;&#26597;&#30475;&#30340; Agent &#25191;&#34892;&#35760;&#24405;
          </div>
        </article>

        <div class="trace-detail-stack">
          <article class="panel-card trace-summary-card">
            <div class="trace-section-head">
              <div>
                <span class="eyebrow">
                  TRACE DETAIL
                </span>

                <h3>
                  &#36816;&#34892;&#25688;&#35201;
                </h3>
              </div>

              <span
                v-if="selectedTrace"
                class="trace-status"
                :class="
                  statusTone(
                    selectedTrace.status
                  )
                "
              >
                {{
                  statusLabel(
                    selectedTrace.status
                  )
                }}
              </span>
            </div>

            <template v-if="selectedTrace">
              <div class="trace-summary-query">
                {{selectedTrace.query}}
              </div>

              <div class="trace-summary-grid">
                <div>
                  <span>
                    Trace ID
                  </span>

                  <strong>
                    {{
                      selectedTrace.trace_id
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    &#26816;&#32034;&#31574;&#30053;
                  </span>

                  <strong>
                    {{
                      routeLabel(
                        selectedTrace
                          .retrieval_strategy
                      )
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    &#24847;&#22270;
                  </span>

                  <strong>
                    {{
                      selectedTrace.intent
                      || '-'
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    &#22797;&#26434;&#24230;
                  </span>

                  <strong>
                    {{
                      selectedTrace.complexity
                      || '-'
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    &#39118;&#38505;&#31561;&#32423;
                  </span>

                  <strong>
                    {{
                      selectedTrace.risk_level
                      || '-'
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    &#24635;&#32791;&#26102;
                  </span>

                  <strong>
                    {{
                      formatLatency(
                        selectedTrace
                          .latency_ms
                      )
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    &#39564;&#35777;&#24471;&#20998;
                  </span>

                  <strong>
                    {{
                      selectedTrace
                        .validation_score
                      ?? '-'
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    HITL
                  </span>

                  <strong>
                    {{
                      selectedTrace
                        .requires_approval
                        ? '\u662f'
                        : '\u5426'
                    }}
                  </strong>
                </div>
              </div>
            </template>

            <div
              v-else
              class="trace-empty compact"
            >
              &#36873;&#25321;&#19968;&#26465;&#25191;&#34892;&#35760;&#24405;&#26597;&#30475;&#35814;&#24773;
            </div>
          </article>

          <article class="panel-card trace-timeline-card">
            <div class="trace-section-head">
              <div>
                <span class="eyebrow">
                  EXECUTION TIMELINE
                </span>

                <h3>
                  &#25191;&#34892;&#27493;&#39588;
                </h3>
              </div>

              <span class="trace-count-chip">
                {{steps.length}}
              </span>
            </div>

            <div
              v-if="steps.length"
              class="trace-timeline"
            >
              <div
                v-for="item in steps"
                :key="item.step_id"
                class="trace-step"
              >
                <div class="trace-step-rail">
                  <div class="trace-step-number">
                    {{item.sequence_no}}
                  </div>
                </div>

                <div class="trace-step-body">
                  <div class="trace-step-head">
                    <div>
                      <strong>
                        {{item.step_name}}
                      </strong>

                      <span>
                        {{item.step_type}}
                      </span>
                    </div>

                    <div>
                      <span
                        class="trace-status"
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
                          formatLatency(
                            item.latency_ms
                          )
                        }}
                      </small>
                    </div>
                  </div>

                  <details
                    class="trace-json-details"
                  >
                    <summary>
                      Input / Output
                    </summary>

                    <div class="trace-json-grid">
                      <div>
                        <span>INPUT</span>
                        <pre>{{safeJson(item.input_json)}}</pre>
                      </div>

                      <div>
                        <span>OUTPUT</span>
                        <pre>{{safeJson(item.output_json)}}</pre>
                      </div>
                    </div>
                  </details>
                </div>
              </div>
            </div>

            <div
              v-else-if="
                !detailLoading
              "
              class="trace-empty compact"
            >
              &#24403;&#21069; Trace &#27809;&#26377;&#27493;&#39588;&#35760;&#24405;
            </div>
          </article>
        </div>
      </div>

      <article class="panel-card trace-tools-card">
        <div class="trace-section-head">
          <div>
            <span class="eyebrow">
              TOOL CALLS
            </span>

            <h3>
              &#24037;&#20855;&#35843;&#29992;
            </h3>
          </div>

          <span class="trace-count-chip">
            {{toolCalls.length}}
          </span>
        </div>

        <div
          v-if="toolCalls.length"
          class="trace-tool-grid"
        >
          <div
            v-for="item in toolCalls"
            :key="item.tool_call_id"
            class="trace-tool-item"
          >
            <div class="trace-tool-head">
              <div>
                <strong>
                  {{item.tool_name}}
                </strong>

                <span
                  v-if="
                    item.requires_approval
                  "
                  class="trace-hitl-chip"
                >
                  HITL
                </span>
              </div>

              <span
                class="trace-status"
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

            <details
              class="trace-json-details"
            >
              <summary>
                Arguments / Result
              </summary>

              <div class="trace-json-grid">
                <div>
                  <span>
                    ARGUMENTS
                  </span>

                  <pre>{{safeJson(item.arguments_json)}}</pre>
                </div>

                <div>
                  <span>
                    RESULT
                  </span>

                  <pre>{{safeJson(item.result_json)}}</pre>
                </div>
              </div>
            </details>
          </div>
        </div>

        <div
          v-else-if="
            !detailLoading
          "
          class="trace-empty compact"
        >
          &#24403;&#21069; Trace &#27809;&#26377;&#24037;&#20855;&#35843;&#29992;&#35760;&#24405;
        </div>
      </article>
    </template>
  </section>`
};
