import * as api from '../api.js';
import { computed, onMounted, ref, typedRef, watch, } from '../vue.js';
function dataOf(value) {
    const data = value?.data;
    return (data
        && typeof data === 'object')
        ? data
        : {};
}
export const StudentView = {
    props: {
        actorUserId: {
            type: String,
            default: '',
        },
    },
    emits: ['request-settings'],
    setup(props, context) {
        const activeTab = typedRef('profile');
        const loading = ref(false);
        const error = ref('');
        const profile = typedRef({});
        const credits = typedRef({});
        const graduationAnswer = ref('');
        const courses = typedRef([]);
        const libraryReservations = typedRef([]);
        const classroomReservations = typedRef([]);
        const tabs = [
            {
                value: 'profile',
                label: '\u4e2a\u4eba\u4fe1\u606f',
            },
            {
                value: 'courses',
                label: '\u6211\u7684\u8bfe\u7a0b',
            },
            {
                value: 'reservations',
                label: '\u6211\u7684\u9884\u7ea6',
            },
        ];
        const completionRate = computed(() => {
            const value = Number(credits.value.completion_rate
                || 0);
            return Math.max(0, Math.min(100, value));
        });
        function resetData() {
            profile.value = {};
            credits.value = {};
            graduationAnswer.value = '';
            courses.value = [];
            libraryReservations.value = [];
            classroomReservations.value = [];
            error.value = '';
        }
        function requestSettings() {
            context.emit('request-settings');
        }
        async function loadAll() {
            const actor = String(props.actorUserId || '').trim();
            resetData();
            if (!actor) {
                return;
            }
            loading.value = true;
            try {
                const [profileResult, creditsResult, coursesResult, graduationResult, libraryResult, classroomResult,] = await Promise.all([
                    api.getStudentProfile(actor),
                    api.getStudentCredits(actor),
                    api.getStudentCourses(actor),
                    api.getStudentGraduation(actor),
                    api.getLibraryReservations(actor),
                    api.getClassroomReservations(actor),
                ]);
                profile.value =
                    dataOf(profileResult);
                credits.value =
                    dataOf(creditsResult);
                courses.value =
                    Array.isArray(dataOf(coursesResult).courses)
                        ? dataOf(coursesResult).courses
                        : [];
                graduationAnswer.value =
                    String(graduationResult.answer
                        || '');
                libraryReservations.value =
                    Array.isArray(libraryResult.reservations)
                        ? libraryResult.reservations
                        : [];
                classroomReservations.value =
                    Array.isArray(classroomResult.reservations)
                        ? classroomResult.reservations
                        : [];
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
        function formatNumber(value) {
            const number = Number(value);
            if (!Number.isFinite(number)) {
                return '-';
            }
            return Number.isInteger(number)
                ? String(number)
                : number.toFixed(1);
        }
        function formatDate(value) {
            const text = String(value || '');
            if (!text)
                return '-';
            return text.slice(0, 10);
        }
        function formatDateTime(value) {
            const text = String(value || '');
            if (!text)
                return '-';
            const parsed = new Date(text);
            if (!Number.isNaN(parsed.getTime())) {
                return parsed.toLocaleString('zh-CN', {
                    hour12: false,
                });
            }
            return text
                .replace('T', ' ')
                .replace('Z', '');
        }
        function formatTime(value) {
            const text = String(value || '');
            return text
                ? text.slice(0, 5)
                : '-';
        }
        function courseStatus(value) {
            const key = String(value || '').toLowerCase();
            const map = {
                completed: '\u5df2\u5b8c\u6210',
                enrolled: '\u5728\u4fee',
                active: '\u5728\u4fee',
                passed: '\u5df2\u901a\u8fc7',
                failed: '\u672a\u901a\u8fc7',
            };
            return map[key]
                || String(value || '-');
        }
        function reservationStatus(value) {
            const key = String(value || '').toLowerCase();
            const map = {
                ready_for_pickup: '\u5f85\u53d6\u4e66',
                confirmed: '\u5df2\u786e\u8ba4',
                pending: '\u5f85\u5904\u7406',
                cancelled: '\u5df2\u53d6\u6d88',
                canceled: '\u5df2\u53d6\u6d88',
                completed: '\u5df2\u5b8c\u6210',
                expired: '\u5df2\u8fc7\u671f',
                rejected: '\u5df2\u62d2\u7edd',
            };
            return map[key]
                || String(value || '-');
        }
        function statusTone(value) {
            const key = String(value || '').toLowerCase();
            if ([
                'confirmed',
                'completed',
                'passed',
                'ready_for_pickup',
            ].includes(key)) {
                return 'success';
            }
            if ([
                'cancelled',
                'canceled',
                'expired',
                'rejected',
                'failed',
            ].includes(key)) {
                return 'muted-status';
            }
            return 'pending';
        }
        watch(() => props.actorUserId, () => {
            loadAll();
        });
        onMounted(() => {
            loadAll();
        });
        return {
            activeTab,
            tabs,
            loading,
            error,
            profile,
            credits,
            completionRate,
            graduationAnswer,
            courses,
            libraryReservations,
            classroomReservations,
            loadAll,
            requestSettings,
            formatNumber,
            formatDate,
            formatDateTime,
            formatTime,
            courseStatus,
            reservationStatus,
            statusTone,
        };
    },
    template: `
  <section class="page student-page">
    <header class="page-header student-header">
      <div>
        <span class="eyebrow">
          STUDENT PORTAL
        </span>

        <h1>
          &#23398;&#29983;&#20013;&#24515;
        </h1>

        <p>
          &#38598;&#20013;&#26597;&#30475;&#20010;&#20154;&#23398;&#31821;&#12289;&#35838;&#31243;&#19982;&#39044;&#32422;&#20449;&#24687;
        </p>
      </div>

      <button
        class="btn secondary"
        :disabled="loading || !actorUserId"
        @click="loadAll"
      >
        {{
          loading
            ? '\u5237\u65b0\u4e2d...'
            : '\u5237\u65b0\u6570\u636e'
        }}
      </button>
    </header>

    <div
      v-if="!actorUserId"
      class="student-auth-card"
    >
      <div class="student-auth-icon">
        U
      </div>

      <h2>
        &#35831;&#20808;&#30331;&#24405;&#26597;&#30475;&#20320;&#30340;&#26657;&#22253;&#25968;&#25454;
      </h2>

      <p>
        &#30331;&#24405;&#21518;&#21487;&#26597;&#30475;&#20010;&#20154;&#23398;&#31821;&#12289;&#35838;&#31243;&#36827;&#24230;&#21644;&#39044;&#32422;&#35760;&#24405;&#12290;
      </p>

      <button
        class="btn primary"
        @click="requestSettings"
      >
        &#30331;&#24405;&#21518;&#26597;&#30475;
      </button>
    </div>

    <template v-else>
      <div
        v-if="error"
        class="alert error student-error"
      >
        {{ error }}
      </div>

      <div class="student-overview">
        <div class="student-identity-card">
          <div class="student-avatar-large">
            {{
              profile.full_name
                ? String(
                    profile.full_name
                  ).slice(0,1)
                : 'U'
            }}
          </div>

          <div class="student-identity-copy">
            <span>
              &#24403;&#21069;&#23398;&#29983;
            </span>

            <strong>
              {{
                profile.full_name
                || '\u52a0\u8f7d\u4e2d...'
              }}
            </strong>

            <small>
              {{
                profile.student_no
                || actorUserId
              }}
            </small>
          </div>
        </div>

        <div class="student-stat-card">
          <span>
            &#24050;&#33719;&#23398;&#20998;
          </span>
          <strong>
            {{
              formatNumber(
                credits.earned_credits
              )
            }}
          </strong>
          <small>
            /
            {{
              formatNumber(
                credits.graduation_credits
              )
            }}
            &#23398;&#20998;
          </small>
        </div>

        <div class="student-stat-card">
          <span>
            &#21097;&#20313;&#23398;&#20998;
          </span>
          <strong>
            {{
              formatNumber(
                credits.remaining_credits
              )
            }}
          </strong>
          <small>
            &#27605;&#19994;&#23398;&#20998;&#24046;&#39069;
          </small>
        </div>

        <div class="student-stat-card">
          <span>
            &#35838;&#31243;&#35760;&#24405;
          </span>
          <strong>
            {{ courses.length }}
          </strong>
          <small>
            &#26465;&#32467;&#26500;&#21270;&#35760;&#24405;
          </small>
        </div>
      </div>

      <div class="student-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          :class="{
            active:
              activeTab === tab.value
          }"
          @click="activeTab=tab.value"
        >
          {{ tab.label }}
        </button>
      </div>

      <div
        v-if="activeTab==='profile'"
        class="student-tab-content"
      >
        <div class="student-profile-grid">
          <article class="panel-card student-profile-card">
            <div class="student-section-title">
              <div>
                <span class="eyebrow">
                  PROFILE
                </span>
                <h3>
                  &#23398;&#31821;&#20449;&#24687;
                </h3>
              </div>
            </div>

            <div class="student-kv-grid">
              <div>
                <span>
                  &#22995;&#21517;
                </span>
                <strong>
                  {{profile.full_name||'-'}}
                </strong>
              </div>

              <div>
                <span>
                  &#23398;&#21495;
                </span>
                <strong>
                  {{profile.student_no||'-'}}
                </strong>
              </div>

              <div>
                <span>
                  &#23398;&#38498;
                </span>
                <strong>
                  {{profile.college_name||'-'}}
                </strong>
              </div>

              <div>
                <span>
                  &#31995;&#25152;
                </span>
                <strong>
                  {{profile.department_name||'-'}}
                </strong>
              </div>

              <div>
                <span>
                  &#19987;&#19994;
                </span>
                <strong>
                  {{profile.major_name||'-'}}
                </strong>
              </div>

              <div>
                <span>
                  &#19987;&#19994;&#20195;&#30721;
                </span>
                <strong>
                  {{profile.major_code||'-'}}
                </strong>
              </div>

              <div>
                <span>
                  &#20837;&#23398;&#24180;&#20221;
                </span>
                <strong>
                  {{profile.enrollment_year||'-'}}
                </strong>
              </div>

              <div>
                <span>
                  &#24180;&#32423;
                </span>
                <strong>
                  {{
                    profile.grade_level
                    ? profile.grade_level
                      + '\u5e74\u7ea7'
                    : '-'
                  }}
                </strong>
              </div>

              <div class="student-kv-wide">
                <span>
                  &#39044;&#35745;&#27605;&#19994;&#26085;&#26399;
                </span>
                <strong>
                  {{
                    formatDate(
                      profile.expected_graduation_date
                    )
                  }}
                </strong>
              </div>
            </div>
          </article>

          <article class="panel-card student-progress-card">
            <div class="student-section-title">
              <div>
                <span class="eyebrow">
                  PROGRESS
                </span>
                <h3>
                  &#27605;&#19994;&#23398;&#20998;&#36827;&#24230;
                </h3>
              </div>

              <strong class="student-progress-number">
                {{
                  formatNumber(
                    completionRate
                  )
                }}%
              </strong>
            </div>

            <div class="student-progress-track">
              <div
                class="student-progress-value"
                :style="{
                  width:
                    completionRate + '%'
                }"
              ></div>
            </div>

            <div class="student-progress-meta">
              <div>
                <span>
                  &#24050;&#33719;&#24471;
                </span>
                <strong>
                  {{
                    formatNumber(
                      credits.earned_credits
                    )
                  }}
                </strong>
              </div>

              <div>
                <span>
                  &#27605;&#19994;&#35201;&#27714;
                </span>
                <strong>
                  {{
                    formatNumber(
                      credits.graduation_credits
                    )
                  }}
                </strong>
              </div>

              <div>
                <span>
                  &#23578;&#24046;
                </span>
                <strong>
                  {{
                    formatNumber(
                      credits.remaining_credits
                    )
                  }}
                </strong>
              </div>
            </div>

            <div
              v-if="graduationAnswer"
              class="student-progress-note"
            >
              {{graduationAnswer}}
            </div>
          </article>
        </div>
      </div>

      <div
        v-else-if="activeTab==='courses'"
        class="student-tab-content"
      >
        <article class="panel-card student-table-card">
          <div class="student-section-title">
            <div>
              <span class="eyebrow">
                ACADEMIC RECORD
              </span>
              <h3>
                &#25105;&#30340;&#35838;&#31243;
              </h3>
            </div>

            <span class="student-count-chip">
              {{courses.length}}
              &#38376;
            </span>
          </div>

          <div
            v-if="courses.length"
            class="student-table-wrap"
          >
            <table class="student-table">
              <thead>
                <tr>
                  <th>
                    &#35838;&#31243;&#20195;&#30721;
                  </th>
                  <th>
                    &#35838;&#31243;&#21517;&#31216;
                  </th>
                  <th>
                    &#23398;&#26399;
                  </th>
                  <th>
                    &#31867;&#22411;
                  </th>
                  <th>
                    &#23398;&#20998;
                  </th>
                  <th>
                    &#25104;&#32489;
                  </th>
                  <th>
                    &#29366;&#24577;
                  </th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="course in courses"
                  :key="
                    course.course_code
                    + '-'
                    + course.semester
                  "
                >
                  <td>
                    <code>
                      {{course.course_code}}
                    </code>
                  </td>

                  <td>
                    <strong>
                      {{course.course_name}}
                    </strong>
                  </td>

                  <td>
                    {{course.semester||'-'}}
                  </td>

                  <td>
                    {{course.course_type||'-'}}
                  </td>

                  <td>
                    {{
                      formatNumber(
                        course.credits_earned
                      )
                    }}
                  </td>

                  <td>
                    {{
                      course.score != null
                      ? formatNumber(
                          course.score
                        )
                      : '-'
                    }}
                  </td>

                  <td>
                    <span
                      class="student-status"
                      :class="
                        statusTone(
                          course.status
                        )
                      "
                    >
                      {{
                        courseStatus(
                          course.status
                        )
                      }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-else-if="!loading"
            class="student-empty"
          >
            &#24403;&#21069;&#27809;&#26377;&#35838;&#31243;&#35760;&#24405;
          </div>
        </article>
      </div>

      <div
        v-else
        class="student-tab-content"
      >
        <div class="student-reservation-grid">
          <article class="panel-card">
            <div class="student-section-title">
              <div>
                <span class="eyebrow">
                  LIBRARY
                </span>
                <h3>
                  &#22270;&#20070;&#39044;&#32422;
                </h3>
              </div>

              <span class="student-count-chip">
                {{libraryReservations.length}}
              </span>
            </div>

            <div
              v-if="libraryReservations.length"
              class="student-reservation-list"
            >
              <div
                v-for="item in libraryReservations"
                :key="item.reservation_id"
                class="student-reservation-item"
              >
                <div class="student-reservation-head">
                  <strong>
                    {{item.title||'-'}}
                  </strong>

                  <span
                    class="student-status"
                    :class="
                      statusTone(
                        item.status
                      )
                    "
                  >
                    {{
                      reservationStatus(
                        item.status
                      )
                    }}
                  </span>
                </div>

                <div class="student-reservation-meta">
                  <span>
                    &#22270;&#20070;&#32534;&#21495;
                    {{item.book_code||'-'}}
                  </span>

                  <span>
                    &#21462;&#20070;&#26399;&#38480;
                    {{
                      formatDateTime(
                        item.pickup_expires_at
                      )
                    }}
                  </span>
                </div>
              </div>
            </div>

            <div
              v-else-if="!loading"
              class="student-empty"
            >
              &#24403;&#21069;&#27809;&#26377;&#22270;&#20070;&#39044;&#32422;
            </div>
          </article>

          <article class="panel-card">
            <div class="student-section-title">
              <div>
                <span class="eyebrow">
                  CLASSROOM
                </span>
                <h3>
                  &#25945;&#23460;&#39044;&#32422;
                </h3>
              </div>

              <span class="student-count-chip">
                {{classroomReservations.length}}
              </span>
            </div>

            <div
              v-if="classroomReservations.length"
              class="student-reservation-list"
            >
              <div
                v-for="item in classroomReservations"
                :key="item.reservation_id"
                class="student-reservation-item"
              >
                <div class="student-reservation-head">
                  <strong>
                    {{
                      item.room_name
                      || item.room_id
                      || '-'
                    }}
                  </strong>

                  <span
                    class="student-status"
                    :class="
                      statusTone(
                        item.status
                      )
                    "
                  >
                    {{
                      reservationStatus(
                        item.status
                      )
                    }}
                  </span>
                </div>

                <div class="student-reservation-meta">
                  <span>
                    {{
                      item.building
                      || '-'
                    }}
                  </span>

                  <span>
                    {{
                      formatDate(
                        item.reservation_date
                      )
                    }}
                    {{
                      formatTime(
                        item.start_time
                      )
                    }}
                    -
                    {{
                      formatTime(
                        item.end_time
                      )
                    }}
                  </span>

                  <span>
                    {{
                      item.party_size
                      || '-'
                    }}
                    &#20154;
                  </span>
                </div>
              </div>
            </div>

            <div
              v-else-if="!loading"
              class="student-empty"
            >
              &#24403;&#21069;&#27809;&#26377;&#25945;&#23460;&#39044;&#32422;
            </div>
          </article>
        </div>
      </div>
    </template>
  </section>`
};
