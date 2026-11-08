import { readFile, stat } from 'node:fs/promises'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const mustExist = [
  'src/main.ts',
  'src/api.ts',
  'src/types.ts',
  'src/vue.ts',
  'src/views/chat.ts',
  'src/views/knowledge.ts',
  'src/views/tools.ts',
  'src/views/system.ts',
  'dist/index.html',
  'dist/src/main.js',
  'dist/src/api.js',
  'dist/src/views/chat.js',
  'dist/src/views/knowledge.js',
  'dist/src/views/tools.js',
  'dist/src/views/system.js',
  'dist/vendor/vue.global.prod.js',
  'dist/styles.css',
]
for (const rel of mustExist) await stat(resolve(root, rel))

const html = await readFile(resolve(root, 'dist/index.html'), 'utf8')
const main = await readFile(resolve(root, 'dist/src/main.js'), 'utf8')
const api = await readFile(resolve(root, 'dist/src/api.js'), 'utf8')
const vue = await readFile(resolve(root, 'dist/vendor/vue.global.prod.js'), 'utf8')

for (const token of ['./vendor/vue.global.prod.js', './src/main.js']) {
  if (!html.includes(token)) throw new Error(`dist/index.html missing ${token}`)
}
for (const token of ['ChatView', 'KnowledgeView', 'ToolsView', 'SystemView']) {
  if (!main.includes(token)) throw new Error(`compiled frontend missing ${token}`)
}
for (const endpoint of ['/chat', '/agent/chat', '/documents/upload', '/system/health', '/tools/course/query']) {
  if (!api.includes(endpoint)) throw new Error(`compiled API client missing ${endpoint}`)
}
if (!vue.includes('vue v3.5.13')) throw new Error('vendored Vue runtime version mismatch')

console.log('PASS: CampusMind Vue frontend validation')
