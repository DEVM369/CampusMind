import { copyFile, mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const dist = resolve(root, 'dist')
await mkdir(resolve(dist, 'vendor'), { recursive: true })
await copyFile(resolve(root, 'vendor', 'vue.global.prod.js'), resolve(dist, 'vendor', 'vue.global.prod.js'))
await copyFile(resolve(root, 'vendor', 'VUE-LICENSE.txt'), resolve(dist, 'vendor', 'VUE-LICENSE.txt'))
await copyFile(resolve(root, 'src', 'styles.css'), resolve(dist, 'styles.css'))
const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="theme-color" content="#2563eb" />
  <title>CampusMind 智慧校园智能平台</title>
  <link rel="stylesheet" href="./styles.css?v=20261112-ui6" />
</head>
<body>
  <div id="app"></div>
  <script src="./vendor/vue.global.prod.js"></script>
  <script type="module" src="./src/main.js?v=20261112-ui6"></script>
</body>
</html>`
await writeFile(resolve(dist, 'index.html'), html, 'utf8')
await writeFile(resolve(dist, '404.html'), html, 'utf8')
console.log('CampusMind Vue 3 + TypeScript frontend built to frontend/dist')
