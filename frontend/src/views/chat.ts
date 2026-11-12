import * as api from '../api.js'
import {
  nextTick,
  onMounted,
  ref,
  typedReactive,
  typedRef,
  watch,
} from '../vue.js'
import type {
  ChatMessage,
  ChatMode,
  ChatResult,
} from '../types.js'


const modes:
  Array<{
    value: ChatMode
    label: string
    hint: string
  }> = [
    {
      value: 'smart',
      label: '\u667a\u80fd\u8def\u7531',
      hint: '\u81ea\u52a8\u9009\u62e9 RAG / Graph / Tool / Agent',
    },
    {
      value: 'rag',
      label: 'RAG',
      hint: '\u539f\u59cb\u6587\u6863\u68c0\u7d22\uff08public scope\uff09',
    },
    {
      value: 'graph',
      label: 'GraphRAG',
      hint: '\u539f\u59cb\u56fe\u8c31\u68c0\u7d22\uff08public scope\uff09',
    },
    {
      value: 'hybrid',
      label: 'Hybrid',
      hint: '\u539f\u59cb\u6587\u6863 + \u56fe\u8c31\u878d\u5408\uff08public scope\uff09',
    },
    {
      value: 'agent',
      label: 'Agent',
      hint: '\u590d\u6742\u4efb\u52a1\u4e0e\u53d7\u63a7\u5de5\u5177',
    },
    {
      value: 'multi',
      label: 'Multi-Agent',
      hint: '\u591a\u57df\u534f\u540c\u4efb\u52a1',
    },
  ]


function uid(): string {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
}


function validMode(
  value: unknown,
): value is ChatMode {
  return [
    'smart',
    'rag',
    'graph',
    'hybrid',
    'agent',
    'multi',
  ].includes(
    String(value)
  )
}


function storedMessageToChat(
  item: api.ConversationMessageRecord,
): ChatMessage {
  const metadata =
    item.metadata_json
    && typeof item.metadata_json === 'object'
      ? item.metadata_json
      : {}

  const mode =
    validMode(
      metadata.mode
    )
      ? metadata.mode
      : undefined

  const storedResult =
    metadata.result
    && typeof metadata.result === 'object'
      ? metadata.result as ChatResult
      : undefined

  const fallbackResult =
    (
      !storedResult
      && item.role === 'assistant'
      && Array.isArray(
        item.citations
      )
      && item.citations.length
    )
      ? {
          answer: item.content,
          citations: item.citations,
        } as ChatResult
      : undefined

  return {
    id: item.id,
    role: item.role,
    content: item.content,
    createdAt:
      Date.parse(
        item.created_at
      )
      || Date.now(),
    mode,
    result:
      storedResult
      || fallbackResult,
  }
}


export const ChatView = {
  props: {
    actorUserId: {
      type: String,
      default: '',
    },
  },

  emits: [
    'request-settings',
  ],

  setup(
    props: any,
    context: any,
  ) {
    const conversations =
      typedRef<
        api.ConversationSummary[]
      >(
        []
      )

    const activeConversationId =
      ref('')

    const messages =
      typedRef<ChatMessage[]>(
        []
      )

    const chatMode =
      typedRef<ChatMode>(
        'smart'
      )

    const prompt =
      ref('')

    const chatBusy =
      ref(false)

    const historyBusy =
      ref(false)

    const historyError =
      ref('')

    const interactionError =
      ref('')

    const routeBusy =
      ref(false)

    const routePreview =
      typedRef<
        Record<string, any>
        | null
      >(
        null
      )

    const messageList =
      typedRef<
        HTMLElement
        | null
      >(
        null
      )

    const approvalOpen =
      ref(false)

    const approvalBusy =
      ref(false)

    const approvalId =
      ref('')

    const approvalResourceId =
      ref('')

    let historyGeneration = 0


    async function scrollBottom() {
      await nextTick()

      if (
        messageList.value
      ) {
        messageList.value.scrollTop =
          messageList.value.scrollHeight
      }
    }


    function resetConversationUi() {
      prompt.value = ''
      routePreview.value = null
      interactionError.value = ''
      approvalOpen.value = false
      approvalId.value = ''
      approvalResourceId.value = ''
    }


    async function loadConversationDetail(
      conversationId: string,
      generation:
        number = historyGeneration,
    ) {
      const detail =
        await api.getConversation(
          conversationId
        )

      if (
        generation
        !== historyGeneration
      ) {
        return
      }

      activeConversationId.value =
        detail.id

      messages.value =
        detail.messages.map(
          storedMessageToChat
        )

      resetConversationUi()

      await scrollBottom()
    }


    async function reloadHistory(
      preferredId: string = '',
    ) {
      const generation =
        ++historyGeneration

      if (
        !props.actorUserId
      ) {
        conversations.value = []
        activeConversationId.value = ''
        messages.value = []
        historyError.value = ''
        return
      }

      historyBusy.value = true
      historyError.value = ''

      try {
        const rows =
          await api.getConversations()

        if (
          generation
          !== historyGeneration
        ) {
          return
        }

        conversations.value =
          rows

        if (
          !rows.length
        ) {
          activeConversationId.value =
            ''

          messages.value = []
          resetConversationUi()
          return
        }

        const nextId =
          (
            preferredId
            && rows.some(
              item =>
                item.id
                === preferredId
            )
          )
            ? preferredId
            : rows[0].id

        await loadConversationDetail(
          nextId,
          generation,
        )
      } catch (error) {
        if (
          generation
          !== historyGeneration
        ) {
          return
        }

        conversations.value = []
        activeConversationId.value = ''
        messages.value = []

        historyError.value =
          error instanceof Error
            ? error.message
            : String(error)
      } finally {
        if (
          generation
          === historyGeneration
        ) {
          historyBusy.value = false
        }
      }
    }


    async function newConversation() {
      if (
        chatBusy.value
        || historyBusy.value
      ) {
        return
      }

      if (
        !props.actorUserId
      ) {
        context.emit(
          'request-settings'
        )
        return
      }

      historyBusy.value = true
      historyError.value = ''

      try {
        const fresh =
          await api.createConversation(
            '\u65b0\u5bf9\u8bdd'
          )

        conversations.value = [
          fresh,
          ...conversations.value.filter(
            item =>
              item.id
              !== fresh.id
          ),
        ]

        activeConversationId.value =
          fresh.id

        messages.value = []

        resetConversationUi()
      } catch (error) {
        historyError.value =
          error instanceof Error
            ? error.message
            : String(error)
      } finally {
        historyBusy.value = false
      }
    }


    async function ensureConversation():
      Promise<string> {
      if (
        activeConversationId.value
      ) {
        return (
          activeConversationId.value
        )
      }

      const fresh =
        await api.createConversation(
          '\u65b0\u5bf9\u8bdd'
        )

      conversations.value = [
        fresh,
        ...conversations.value.filter(
          item =>
            item.id
            !== fresh.id
        ),
      ]

      activeConversationId.value =
        fresh.id

      return fresh.id
    }


    async function switchConversation(
      id: string,
    ) {
      if (
        !id
        || id
          === activeConversationId.value
        || chatBusy.value
        || historyBusy.value
      ) {
        return
      }

      historyBusy.value = true
      historyError.value = ''

      try {
        await loadConversationDetail(
          id
        )
      } catch (error) {
        historyError.value =
          error instanceof Error
            ? error.message
            : String(error)
      } finally {
        historyBusy.value = false
      }
    }


    function updateConversationSummary(
      conversationId: string,
      firstUserText: string,
    ) {
      const now =
        new Date().toISOString()

      conversations.value =
        conversations.value.map(
          item => {
            if (
              item.id
              !== conversationId
            ) {
              return item
            }

            const current =
              (
                item.title
                || ''
              ).trim()

            const shouldRetitle =
              !current
              || current
                === '\u65b0\u5bf9\u8bdd'
              || current
                === '\u65b0\u4f1a\u8bdd'

            return {
              ...item,
              title:
                shouldRetitle
                  ? (
                      firstUserText
                        .replace(
                          /\s+/g,
                          ' ',
                        )
                        .trim()
                        .slice(
                          0,
                          80,
                        )
                      || '\u65b0\u5bf9\u8bdd'
                    )
                  : item.title,
              updated_at: now,
            }
          }
        )

      conversations.value.sort(
        (
          left,
          right,
        ) =>
          Date.parse(
            right.updated_at
          )
          - Date.parse(
              left.updated_at
            )
      )
    }


    function detectApproval(
      result: ChatResult,
    ) {
      if (
        !result.pending_approval
      ) {
        return
      }

      const data =
        result.structured_data as
          Record<string, unknown>
          | null
          | undefined

      const id =
        typeof data?.approval_id
          === 'string'
          ? data.approval_id
          : ''

      if (id) {
        approvalId.value = id
        approvalResourceId.value = ''
        approvalOpen.value = true
      }
    }


    async function sendChat() {
      const text =
        prompt.value.trim()

      if (
        !text
        || chatBusy.value
      ) {
        return
      }

      if (
        !props.actorUserId
      ) {
        context.emit(
          'request-settings'
        )
        return
      }

      let conversationId = ''

      try {
        conversationId =
          await ensureConversation()
      } catch (error) {
        historyError.value =
          error instanceof Error
            ? error.message
            : String(error)

        return
      }

      prompt.value = ''
      routePreview.value = null
      historyError.value = ''

      messages.value.push({
        id: uid(),
        role: 'user',
        content: text,
        createdAt: Date.now(),
        mode: chatMode.value,
      })

      const assistant =
        typedReactive<ChatMessage>({
          id: uid(),
          role: 'assistant',
          content:
            '\u6b63\u5728\u5206\u6790\u4e0e\u68c0\u7d22\u2026',
          createdAt: Date.now(),
          mode: chatMode.value,
        })

      messages.value.push(
        assistant
      )

      chatBusy.value = true

      await scrollBottom()

      try {
        let result:
          ChatResult

        if (
          chatMode.value
          === 'smart'
        ) {
          result =
            await api.conversationChat(
              conversationId,
              text,
            )
        } else {
          result =
            await api.chat(
              chatMode.value,
              text,
              props.actorUserId,
            )
        }

        assistant.content =
          result.answer
          || '\u8bf7\u6c42\u5df2\u5b8c\u6210\u3002'

        assistant.result =
          result

        detectApproval(
          result
        )

        if (
          chatMode.value
          !== 'smart'
        ) {
          try {
            await api.appendConversationMessages(
              conversationId,
              [
                {
                  role: 'user',
                  content: text,
                  citations: [],
                  metadata_json: {
                    mode:
                      chatMode.value,
                  },
                },
                {
                  role: 'assistant',
                  content:
                    assistant.content,
                  citations:
                    Array.isArray(
                      result.citations
                    )
                      ? result.citations
                      : [],
                  metadata_json: {
                    mode:
                      chatMode.value,
                    result,
                  },
                },
              ],
            )
          } catch (persistError) {
            assistant.error =
              '\u56de\u7b54\u5df2\u751f\u6210\uff0c\u4f46\u670d\u52a1\u7aef\u5386\u53f2\u4fdd\u5b58\u5931\u8d25\uff1a'
              + (
                persistError
                instanceof Error
                  ? persistError.message
                  : String(
                      persistError
                    )
              )
          }
        }

        updateConversationSummary(
          conversationId,
          text,
        )
      } catch (error) {
        assistant.content =
          '\u8bf7\u6c42\u5931\u8d25'

        assistant.error =
          error instanceof Error
            ? error.message
            : String(error)
      } finally {
        chatBusy.value = false
        await scrollBottom()
      }
    }


    async function previewRoute() {
      const text =
        prompt.value.trim()

      if (!text) {
        return
      }

      routeBusy.value = true
      interactionError.value = ''

      try {
        routePreview.value =
          await api.routeQuery(
            text,
            props.actorUserId,
          )
      } catch (error) {
        interactionError.value =
          error instanceof Error
            ? error.message
            : String(error)
      } finally {
        routeBusy.value = false
      }
    }


    async function submitApproval(
      approved: boolean,
    ) {
      if (
        !props.actorUserId
      ) {
        context.emit(
          'request-settings'
        )
        return
      }

      approvalBusy.value = true
      interactionError.value = ''

      try {
        const result =
          await api.resumeAgent({
            approval_id:
              approvalId.value,
            actor_user_id:
              props.actorUserId,
            approved,
            resource_id:
              approvalResourceId.value,
          })

        const content =
          String(
            result.answer
            || '\u5ba1\u6279\u64cd\u4f5c\u5df2\u5b8c\u6210'
          )

        messages.value.push({
          id: uid(),
          role: 'assistant',
          content,
          createdAt: Date.now(),
          result:
            result as ChatResult,
        })

        if (
          activeConversationId.value
        ) {
          try {
            await api.appendConversationMessages(
              activeConversationId.value,
              [
                {
                  role: 'assistant',
                  content,
                  citations:
                    Array.isArray(
                      result.citations
                    )
                      ? result.citations
                      : [],
                  metadata_json: {
                    result,
                  },
                },
              ],
            )
          } catch {
            // The approval action itself already completed.
            // Do not turn a persistence-only problem into
            // a false business-action failure.
          }
        }

        approvalOpen.value = false
      } catch (error) {
        interactionError.value =
          error instanceof Error
            ? error.message
            : String(error)
      } finally {
        approvalBusy.value = false
      }
    }


    async function clearChat() {
      if (
        chatBusy.value
        || historyBusy.value
      ) {
        return
      }

      const id =
        activeConversationId.value

      if (!id) {
        messages.value = []
        resetConversationUi()
        return
      }

      const confirmed =
        window.confirm(
          '\u786e\u5b9a\u5220\u9664\u5f53\u524d\u4f1a\u8bdd\u5417\uff1f\u8be5\u64cd\u4f5c\u4f1a\u5220\u9664\u670d\u52a1\u7aef\u4e2d\u7684\u5f53\u524d\u5386\u53f2\u8bb0\u5f55\u3002'
        )

      if (!confirmed) {
        return
      }

      historyBusy.value = true
      historyError.value = ''

      try {
        await api.deleteConversation(
          id
        )

        activeConversationId.value = ''
        messages.value = []

        await reloadHistory()
      } catch (error) {
        historyError.value =
          error instanceof Error
            ? error.message
            : String(error)
      } finally {
        historyBusy.value = false
      }
    }


    watch(
      () =>
        props.actorUserId,
      (
        nextActorUserId: string,
      ) => {
        if (
          !nextActorUserId
        ) {
          ++historyGeneration
          conversations.value = []
          activeConversationId.value = ''
          messages.value = []
          historyError.value = ''
          resetConversationUi()
          return
        }

        void reloadHistory()
      },
    )


    onMounted(() => {
      if (
        props.actorUserId
      ) {
        void reloadHistory()
      }
    })


    return {
      modes,
      conversations,
      activeConversationId,
      messages,
      chatMode,
      prompt,
      chatBusy,
      historyBusy,
      historyError,
      interactionError,
      routeBusy,
      routePreview,
      messageList,
      approvalOpen,
      approvalBusy,
      approvalId,
      approvalResourceId,
      sendChat,
      previewRoute,
      submitApproval,
      clearChat,
      newConversation,
      switchConversation,
    }
  },

  template: `
  <section class="page chat-page">
    <header class="page-header chat-header">
      <div>
        <h1>
          \u667a\u80fd\u95ee\u7b54
        </h1>
      </div>

      <div class="chat-header-actions">
        <label class="conversation-history">
          <span>
            \u5386\u53f2\u4f1a\u8bdd
          </span>

          <select
            :value="activeConversationId"
            :disabled="chatBusy||historyBusy||!actorUserId"
            @change="switchConversation($event.target.value)"
          >
            <option
              v-if="!conversations.length"
              value=""
            >
              \u6682\u65e0\u5386\u53f2\u4f1a\u8bdd
            </option>

            <option
              v-for="conversation in conversations"
              :key="conversation.id"
              :value="conversation.id"
            >
              {{conversation.title||'\u65b0\u5bf9\u8bdd'}}
            </option>
          </select>
        </label>

        <div class="mode-select">
          <span>
            \u8fd0\u884c\u6a21\u5f0f
          </span>

          <select
            v-model="chatMode"
            :disabled="chatBusy"
            :title="modes.find(item=>item.value===chatMode)?.hint"
          >
            <option
              v-for="item in modes"
              :value="item.value"
            >
              {{item.label}}
            </option>
          </select>
        </div>

        <button
          class="btn secondary"
          :disabled="chatBusy||historyBusy||!actorUserId"
          @click="newConversation"
        >
          + \u65b0\u5efa\u5bf9\u8bdd
        </button>

        <button
          class="btn secondary"
          :disabled="chatBusy||historyBusy||!activeConversationId"
          @click="clearChat"
        >
          \u5220\u9664\u5f53\u524d
        </button>
      </div>
    </header>

    <div
      v-if="historyError"
      class="alert error"
    >
      {{historyError}}
    </div>

    <div
      v-if="interactionError"
      class="alert error page-feedback"
    >
      {{interactionError}}
    </div>

    <div
      ref="messageList"
      class="message-list"
    >
      <div
        v-if="!messages.length"
        class="welcome-card"
      >
        <div class="welcome-intro">
          <div class="welcome-mark">
            CM
          </div>

          <div class="welcome-copy">
            <h2>
              \u4f60\u597d\uff0c\u6211\u662f CampusMind
            </h2>

            <p>
              \u8bfe\u7a0b\u5b66\u4e60 \u00b7 \u77e5\u8bc6\u67e5\u8be2 \u00b7 \u6821\u56ed\u4e8b\u52a1
            </p>
          </div>
        </div>

        <div class="welcome-query-panel">
          <div class="welcome-query-heading">
            <strong>\u5e38\u7528\u95ee\u9898</strong>
          </div>

          <div class="suggestions">
            <button
              @click="prompt='\u673a\u5668\u5b66\u4e60\u8bfe\u7a0b\u6709\u54ea\u4e9b\u5148\u4fee\u8981\u6c42\uff1f'"
            >
              \u673a\u5668\u5b66\u4e60\u6709\u54ea\u4e9b\u5148\u4fee\u8981\u6c42\uff1f
            </button>

            <button
              @click="prompt='\u5f53\u524d\u77e5\u8bc6\u56fe\u8c31\u4e2d\uff0c\u4ece\u8bfe\u7a0b\u300c\u6570\u636e\u7ed3\u6784\u300d\u6cbf PREREQUISITE_OF \u6b63\u5411\u4e00\u8df3\u4f1a\u5230\u8fbe\u54ea\u95e8\u8bfe\u7a0b\uff1f'"
            >
              \u67e5\u8be2\u8bfe\u7a0b\u56fe\u8c31\u5173\u7cfb
            </button>

            <button
              @click="prompt='\u4ecb\u7ecd\u4e00\u4e0b\u5f53\u524d\u77e5\u8bc6\u5e93\u4e2d\u7684\u6559\u5ba4\u9884\u7ea6\u786e\u8ba4\u89c4\u5219\u3002'"
            >
              \u4e86\u89e3\u9884\u7ea6\u786e\u8ba4\u89c4\u5219
            </button>
          </div>
        </div>
      </div>

      <article
        v-for="message in messages"
        :key="message.id"
        class="message-row"
        :class="message.role"
      >
        <div class="avatar">
          {{message.role==='user'?'\u4f60':'CM'}}
        </div>

        <div class="message-body">
          <div class="message-meta">
            <strong>
              {{message.role==='user'?'\u4f60':'CampusMind'}}
            </strong>

            <span v-if="message.mode">
              {{modes.find(m=>m.value===message.mode)?.label}}
            </span>
          </div>

          <div class="message-content">
            {{message.content}}
          </div>

          <div
            v-if="message.error"
            class="alert error"
          >
            {{message.error}}
          </div>

          <template v-if="message.result">
            <div
              v-if="message.result.decision"
              class="route-strip"
            >
              <span class="tag">
                {{message.result.decision.route}}
              </span>

              <span>
                {{message.result.decision.intent}}
              </span>

              <span>
                \u7f6e\u4fe1\u5ea6
                {{
                  Math.round(
                    message.result.decision.confidence
                    * 100
                  )
                }}%
              </span>
            </div>

            <details
              v-if="message.result.citations?.length"
              class="detail"
            >
              <summary>
                \u5f15\u7528\u6765\u6e90 \u00b7
                {{message.result.citations.length}}
              </summary>

              <div class="citation-list">
                <article
                  v-for="(item,index) in message.result.citations"
                  class="citation-card"
                >
                  <div class="citation-title">
                    <span class="citation-index">
                      {{index+1}}
                    </span>

                    <strong>
                      {{item.title}}
                    </strong>
                  </div>

                  <p>
                    {{item.quote}}
                  </p>

                  <div class="citation-meta">
                    <span v-if="item.section">
                      {{item.section}}
                    </span>

                    <span v-if="item.page">
                      \u7b2c {{item.page}} \u9875
                    </span>

                    <span>
                      {{item.object_key}}
                    </span>
                  </div>
                </article>
              </div>
            </details>

            <details
              v-if="message.result.graph_paths?.length"
              class="detail"
            >
              <summary>
                \u56fe\u8c31\u8def\u5f84 \u00b7
                {{message.result.graph_paths.length}}
              </summary>

              <div class="path-list">
                <div
                  v-for="path in message.result.graph_paths"
                  class="path-row"
                >
                  <span class="tag ghost">
                    {{path.source_type}}
                  </span>

                  <b>
                    {{path.source_name}}
                  </b>

                  <span>
                    \u2014 {{path.relation_type}} \u2192
                  </span>

                  <span class="tag success">
                    {{path.target_type}}
                  </span>

                  <b>
                    {{path.target_name}}
                  </b>
                </div>
              </div>
            </details>

            <details class="detail">
              <summary>
                \u6267\u884c\u8be6\u60c5
              </summary>

              <div class="execution-grid">
                <div>
                  <span>
                    \u89c4\u5212\u8def\u7531
                  </span>
                  <strong>
                    {{
                      message.result.planned_route
                      || message.result.decision?.route
                      || '-'
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    \u5b9e\u9645\u8def\u7531
                  </span>
                  <strong>
                    {{
                      message.result.executed_route
                      || message.result.active_route
                      || '-'
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    \u610f\u56fe
                  </span>
                  <strong>
                    {{
                      message.result.decision?.intent
                      || '-'
                    }}
                  </strong>
                </div>

                <div>
                  <span>
                    \u8017\u65f6
                  </span>
                  <strong>
                    {{
                      message.result.elapsed_ms!=null
                        ? Math.round(
                            message.result.elapsed_ms
                          )+' ms'
                        : '-'
                    }}
                  </strong>
                </div>
              </div>

              <div
                v-if="message.result.fallback_reason"
                class="alert warn"
              >
                {{message.result.fallback_reason}}
              </div>

              <div
                v-if="message.result.diagnostics?.length"
                class="alert warn"
              >
                Graph diagnostics:
                {{message.result.diagnostics.join(' \u00b7 ')}}
              </div>

              <pre
                v-if="message.result.steps?.length||message.result.child_results?.length"
                class="json-preview"
              >{{JSON.stringify(message.result.steps||message.result.child_results,null,2)}}</pre>
            </details>
          </template>
        </div>
      </article>
    </div>

    <div class="composer-shell">
      <div
        v-if="routePreview"
        class="route-preview"
      >
        <span>
          \u8def\u7531\u9884\u89c8
        </span>

        <strong>
          {{routePreview.decision?.route||'-'}}
        </strong>

        <small>
          {{
            (
              routePreview.decision?.reasons
              || []
            ).join(' \u00b7 ')
          }}
        </small>
      </div>

      <div class="composer">
        <textarea
          v-model="prompt"
          rows="2"
          maxlength="4000"
          placeholder="\u8f93\u5165\u4f60\u7684\u95ee\u9898\u2026"
          @keydown.ctrl.enter.prevent="sendChat"
        ></textarea>

        <div class="composer-actions">
          <div class="composer-left">
            <button
              class="btn secondary"
              :disabled="routeBusy"
              @click="previewRoute"
            >
              {{routeBusy?'\u5206\u6790\u4e2d\u2026':'\u8def\u7531\u9884\u89c8'}}
            </button>

          </div>

          <button
            class="btn primary"
            :disabled="chatBusy||historyBusy||!prompt.trim()||!actorUserId"
            @click="sendChat"
          >
            {{chatBusy?'\u5904\u7406\u4e2d\u2026':'\u53d1\u9001'}}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="approvalOpen"
      class="modal-backdrop"
    >
      <div class="modal">
        <div class="modal-head">
          <h3>
            \u9700\u8981\u4eba\u5de5\u786e\u8ba4
          </h3>
        </div>

        <div class="alert warn">
          CampusMind \u5df2\u6682\u505c\u5199\u64cd\u4f5c\u3002
          \u53ea\u6709\u4f60\u660e\u786e\u786e\u8ba4\u540e\u624d\u4f1a\u7ee7\u7eed\u6267\u884c\u3002
        </div>

        <div class="approval-meta">
          <span>approval_id</span>
          <code>{{approvalId}}</code>

          <span>actor_user_id</span>
          <code>{{actorUserId||'\u672a\u767b\u5f55'}}</code>
        </div>

        <label>
          \u8d44\u6e90 ID\uff08room_id / book_id\uff0c\u53ef\u7559\u7a7a\uff09
          <input
            v-model="approvalResourceId"
          >
        </label>

        <div class="modal-actions">
          <button
            class="btn secondary"
            :disabled="approvalBusy"
            @click="submitApproval(false)"
          >
            \u62d2\u7edd
          </button>

          <button
            class="btn primary"
            :disabled="approvalBusy||!actorUserId"
            @click="submitApproval(true)"
          >
            \u786e\u8ba4\u6267\u884c
          </button>
        </div>
      </div>
    </div>
  </section>`
}
