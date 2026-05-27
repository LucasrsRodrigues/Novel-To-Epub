import { resolve } from 'path'
import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import pkg from './package.json'

// Injeta a versão do package.json em tempo de build. Renderer le via
// `__APP_VERSION__` (declarado em src/renderer/src/env.d.ts). Sem custo
// runtime, sem IPC — fica imutável no bundle.
const define = {
  __APP_VERSION__: JSON.stringify(pkg.version)
}

export default defineConfig({
  main: { define },
  preload: { define },
  renderer: {
    resolve: {
      alias: {
        '@renderer': resolve('src/renderer/src')
      }
    },
    define,
    plugins: [react(), tailwindcss()]
  }
})
