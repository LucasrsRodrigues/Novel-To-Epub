import { resolve } from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Config standalone SO do renderer — usada para rodar/validar a UI no browser
// fora do Electron (`npx vite`). O build real do app usa electron.vite.config.ts.
export default defineConfig({
  root: 'src/renderer',
  resolve: {
    alias: {
      '@renderer': resolve(__dirname, 'src/renderer/src')
    }
  },
  plugins: [react(), tailwindcss()],
  server: { port: 5273 }
})
