export const createApp = Vue.createApp;
export const computed = Vue.computed;
export const nextTick = Vue.nextTick;
export const onMounted = Vue.onMounted;
export const reactive = Vue.reactive;
export const ref = Vue.ref;
export const watch = Vue.watch;
export function typedRef(value) {
    return Vue.ref(value);
}
export function typedReactive(value) {
    return Vue.reactive(value);
}
