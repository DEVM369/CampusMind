import { createApp, computed, onMounted, ref, typedRef } from './vue.js'
import type { ViewName } from './types.js'
import * as api from './api.js'
import { ChatView } from './views/chat.js'
import { KnowledgeView } from './views/knowledge.js'
import { ToolsView } from './views/tools.js'
import { SystemView } from './views/system.js'
import { StudentView } from './views/student.js'
import { GraphView } from './views/graph.js'
import { TraceView } from './views/trace.js'
import { AdminView } from './views/admin.js'


const App = {
  components: {
    ChatView,
    StudentView,
    KnowledgeView,
    GraphView,
    TraceView,
    AdminView,
    ToolsView,
    SystemView,
  },

  setup() {
    const view =
      typedRef<ViewName>('chat')

    const sidebarCollapsed =
      ref(false)

    const settingsOpen =
      ref(false)

    const authUser =
      typedRef<api.AuthUser | null>(
        null
      )

    const authChecking =
      ref(true)

    const authBusy =
      ref(false)

    const authError =
      ref('')

    const loginUsername =
      ref('')

    const loginPassword =
      ref('')

    const actorUserId =
      computed(
        () =>
          authUser.value?.user_id
          || ''
      )

    const pageTitles:
      Record<ViewName, string> = {
        chat: '\u667a\u80fd\u95ee\u7b54',
        student: '\u5b66\u751f\u4e2d\u5fc3',
        knowledge: '\u77e5\u8bc6\u5e93',
        graph: '\u77e5\u8bc6\u56fe\u8c31',
        trace: '\u6267\u884c\u8ffd\u8e2a',
        admin: '\u7ba1\u7406\u540e\u53f0',
        tools: '\u6821\u56ed\u5de5\u5177',
        system: '\u7cfb\u7edf\u72b6\u6001',
      }

    const pageTitle =
      computed(
        () =>
          pageTitles[
            view.value
          ]
      )

    function setView(
      name: ViewName,
    ) {
      view.value = name
      location.hash = name
    }

    function openSettings() {
      authError.value = ''
      settingsOpen.value = true
    }

    async function restoreAuth() {
      authChecking.value = true

      try {
        authUser.value =
          await api.authMe()
      } catch {
        authUser.value = null
      } finally {
        authChecking.value = false
      }
    }

    async function login() {
      const username =
        loginUsername.value.trim()

      const password =
        loginPassword.value

      if (
        !username
        || !password
      ) {
        authError.value =
          '\u8bf7\u8f93\u5165\u7528\u6237\u540d\u548c\u5bc6\u7801'
        return
      }

      authBusy.value = true
      authError.value = ''

      try {
        const result =
          await api.authLogin(
            username,
            password,
          )

        authUser.value =
          result.user

        loginPassword.value = ''
        settingsOpen.value = false
      } catch (error) {
        authError.value =
          error instanceof Error
            ? error.message
            : String(error)
      } finally {
        authBusy.value = false
      }
    }

    async function logout() {
      authBusy.value = true
      authError.value = ''

      try {
        await api.authLogout()

        authUser.value = null
        loginPassword.value = ''
      } catch (error) {
        authError.value =
          error instanceof Error
            ? error.message
            : String(error)
      } finally {
        authBusy.value = false
      }
    }

    onMounted(() => {
      // Old development actor selection is deliberately
      // retired. Legacy conversation keys remain untouched.
      localStorage.removeItem(
        'campusmind.actorUserId'
      )

      const applyHash = () => {
        const next =
          location.hash.replace(
            '#',
            '',
          ) as ViewName

        if (
          [
            'chat',
            'student',
            'knowledge',
            'graph',
            'trace',
            'admin',
            'tools',
            'system',
          ].includes(next)
        ) {
          view.value = next
        }
      }

      applyHash()

      window.addEventListener(
        'hashchange',
        applyHash,
      )

      void restoreAuth()
    })

    return {
      view,
      sidebarCollapsed,
      settingsOpen,
      pageTitle,
      actorUserId,
      authUser,
      authChecking,
      authBusy,
      authError,
      loginUsername,
      loginPassword,
      setView,
      openSettings,
      login,
      logout,
    }
  },

  template: `
  <div
    class="app-shell"
    :class="{ collapsed: sidebarCollapsed }"
  >
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">CM</div>
        <div class="brand-copy">
          <strong>CampusMind</strong>
          <span>Enterprise AI</span>
        </div>
      </div>

      <nav class="nav-list">
        <div class="nav-section-label">
          WORKSPACE
        </div>

        <button
          :class="{active:view==='chat'}"
          @click="setView('chat')"
        >
          <span class="nav-icon">&#10022;</span>
          <span>\u667a\u80fd\u95ee\u7b54</span>
        </button>

        <button
          :class="{active:view==='student'}"
          @click="setView('student')"
        >
          <span class="nav-icon">&#9678;</span>
          <span>\u5b66\u751f\u4e2d\u5fc3</span>
        </button>

        <button
          :class="{active:view==='knowledge'}"
          @click="setView('knowledge')"
        >
          <span class="nav-icon">&#9638;</span>
          <span>\u77e5\u8bc6\u5e93</span>
        </button>

        <button
          :class="{active:view==='graph'}"
          @click="setView('graph')"
        >
          <span class="nav-icon">&#9670;</span>
          <span>\u77e5\u8bc6\u56fe\u8c31</span>
        </button>

        <div class="nav-section-label nav-section-label-ops">
          OPERATIONS
        </div>

        <button
          :class="{active:view==='trace'}"
          @click="setView('trace')"
        >
          <span class="nav-icon">&#8644;</span>
          <span>\u6267\u884c\u8ffd\u8e2a</span>
        </button>

        <button
          :class="{active:view==='tools'}"
          @click="setView('tools')"
        >
          <span class="nav-icon">&#9874;</span>
          <span>\u6821\u56ed\u5de5\u5177</span>
        </button>

        <button
          :class="{active:view==='admin'}"
          @click="setView('admin')"
        >
          <span class="nav-icon">&#9881;</span>
          <span>\u7ba1\u7406\u540e\u53f0</span>
        </button>

        <button
          :class="{active:view==='system'}"
          @click="setView('system')"
        >
          <span class="nav-icon">&#9673;</span>
          <span>\u7cfb\u7edf\u72b6\u6001</span>
        </button>
      </nav>

    </aside>

    <main class="main-area">
      <header class="topbar">
        <div class="topbar-left">
          <button
            class="icon-button"
            aria-label="折叠或展开侧栏"
            title="折叠或展开侧栏"
            @click="sidebarCollapsed=!sidebarCollapsed"
          >
            &#9776;
          </button>

          <div class="topbar-heading">
            <span class="topbar-context">
              CAMPUSMIND / WORKSPACE
            </span>

            <span class="topbar-title">
              {{pageTitle}}
            </span>
          </div>
        </div>

        <div class="topbar-right">
          <span class="live-pill">
            <i></i>
            API \u5728\u7ebf
          </span>

          <button
            class="actor-chip"
            :aria-label="authUser?'打开账号信息':'打开登录窗口'"
            :title="authUser?'账号信息':'登录 CampusMind'"
            @click="openSettings"
          >
            <span class="actor-dot">
              {{authUser?'U':'?'}}
            </span>

            <span v-if="authChecking">
              \u8eab\u4efd\u68c0\u67e5\u4e2d\u2026
            </span>

            <span v-else-if="authUser">
              {{authUser.full_name || authUser.username}}
            </span>

            <span v-else>
              \u767b\u5f55
            </span>
          </button>
        </div>
      </header>

      <ChatView
        v-if="view==='chat'"
        :actor-user-id="actorUserId"
        @request-settings="openSettings"
      />

      <StudentView
        v-else-if="view==='student'"
        :actor-user-id="actorUserId"
        @request-settings="openSettings"
      />

      <KnowledgeView
        v-else-if="view==='knowledge'"
      />

      <GraphView
        v-else-if="view==='graph'"
      />

      <TraceView
        v-else-if="view==='trace'"
        :actor-user-id="actorUserId"
        @request-settings="openSettings"
      />

      <AdminView
        v-else-if="view==='admin'"
        :actor-user-id="actorUserId"
        @request-settings="openSettings"
      />

      <ToolsView
        v-else-if="view==='tools'"
      />

      <SystemView
        v-else
      />
    </main>

    <div
      v-if="settingsOpen"
      class="modal-backdrop"
      @click.self="settingsOpen=false"
    >
      <div class="modal">
        <div class="modal-head">
          <h3>
            {{authUser?'\u5f53\u524d\u8d26\u53f7':'\u767b\u5f55 CampusMind'}}
          </h3>

          <button
            class="icon-button"
            aria-label="关闭"
            title="关闭"
            @click="settingsOpen=false"
          >
            &times;
          </button>
        </div>

        <template v-if="authUser">
          <p>
            \u5df2\u901a\u8fc7\u670d\u52a1\u7aef Session \u8ba4\u8bc1\u3002
            actor_user_id \u7531\u767b\u5f55\u8eab\u4efd\u81ea\u52a8\u786e\u5b9a\uff0c
            \u4e0d\u518d\u5141\u8bb8\u624b\u5de5\u8f93\u5165\u3002
          </p>

          <div class="approval-meta">
            <span>username</span>
            <code>{{authUser.username}}</code>

            <span>user_id</span>
            <code>{{authUser.user_id}}</code>

            <span>roles</span>
            <code>{{authUser.roles.join(', ') || '-'}}</code>
          </div>

          <div
            v-if="authError"
            class="alert error"
          >
            {{authError}}
          </div>

          <div class="modal-actions">
            <a
              class="btn secondary"
              href="/docs"
              target="_blank"
            >
              Swagger
            </a>

            <button
              class="btn secondary"
              :disabled="authBusy"
              @click="logout"
            >
              {{authBusy?'\u5904\u7406\u4e2d\u2026':'\u9000\u51fa\u767b\u5f55'}}
            </button>
          </div>
        </template>

        <template v-else>
          <p>
            \u767b\u5f55\u540e\uff0c\u5bf9\u8bdd\u5386\u53f2\u5c06\u6309\u5f53\u524d\u8d26\u53f7
            \u5b58\u50a8\u5728 PostgreSQL\uff0c\u5e76\u7531\u670d\u52a1\u7aef\u6821\u9a8c\u5f52\u5c5e\u3002
          </p>

          <label>
            \u7528\u6237\u540d
            <input
              v-model="loginUsername"
              autocomplete="username"
              placeholder="student001"
              @keydown.enter.prevent="login"
            >
          </label>

          <label>
            \u5bc6\u7801
            <input
              v-model="loginPassword"
              type="password"
              autocomplete="current-password"
              @keydown.enter.prevent="login"
            >
          </label>

          <div
            v-if="authError"
            class="alert error"
          >
            {{authError}}
          </div>

          <div class="modal-actions">
            <a
              class="btn secondary"
              href="/docs"
              target="_blank"
            >
              Swagger
            </a>

            <button
              class="btn primary"
              :disabled="authBusy"
              @click="login"
            >
              {{authBusy?'\u767b\u5f55\u4e2d\u2026':'\u767b\u5f55'}}
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>`
}


createApp(
  App
).mount(
  '#app'
)
