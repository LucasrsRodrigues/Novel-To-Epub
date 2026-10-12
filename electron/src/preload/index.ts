import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// URL do backend injetada pelo main via webPreferences.additionalArguments
const argValue = (name: string): string =>
  process.argv.find((arg) => arg.startsWith(`--${name}=`))?.slice(name.length + 3) ?? ''
const backendUrl = argValue('backend-url')
// Token da API local (novo a cada abertura do app) — ver backend/app/api/auth.py
const apiToken = argValue('api-token')

// Custom APIs for renderer
const api = {
  backendUrl,
  apiToken,
  // Baixa uma URL do backend direto pro disco no processo main ("Baixar tudo").
  // Evita trafegar o binário pelo IPC (corrompia o .zip). O progresso (0..1, ou
  // -1 = sem total) chega em `onProgress`, filtrado pelo id deste download.
  downloadFile: async (
    url: string,
    defaultName: string,
    onProgress?: (pct: number) => void
  ): Promise<{ canceled?: boolean; filePath?: string; bytes?: number; error?: string }> => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
    const listener = (_e: unknown, evId: string, pct: number): void => {
      if (evId === id) onProgress?.(pct)
    }
    ipcRenderer.on('download-progress', listener)
    try {
      return await ipcRenderer.invoke('download-file', { id, url, defaultName })
    } finally {
      ipcRenderer.removeListener('download-progress', listener)
    }
  }
}

// Use `contextBridge` APIs to expose Electron APIs to
// renderer only if context isolation is enabled, otherwise
// just add to the DOM global.
if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (define in dts)
  window.electron = electronAPI
  // @ts-ignore (define in dts)
  window.api = api
}
