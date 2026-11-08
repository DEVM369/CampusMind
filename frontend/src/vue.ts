declare const Vue: any

export const createApp = Vue.createApp
export const computed = Vue.computed
export const nextTick = Vue.nextTick
export const onMounted = Vue.onMounted
export const reactive = Vue.reactive
export const ref = Vue.ref
export const watch = Vue.watch

export function typedRef<T>(value: T): { value: T } {
  return Vue.ref(value) as { value: T }
}

export function typedReactive<T extends object>(value: T): T {
  return Vue.reactive(value) as T
}
