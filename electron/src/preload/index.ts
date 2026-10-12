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
  // Baixa uma URL direto pro disco no processo main (download "Baixar tudo").
  // Evita trafegar o binário pelo IPC (corrompia o .zip).
  downloadFile: (
    url: string,
    defaultName: string
  ): Promise<{ canceled?: boolean; filePath?: string; bytes?: number; error?: string }> =>
    ipcRenderer.invoke('download-file', { url, defaultName }),
  // Assina o progresso do download (0..1, ou -1 = sem total). Devolve unsubscribe.
  onDownloadProgress: (cb: (pct: number) => void): (() => void) => {
    const listener = (_e: unknown, pct: number): void => cb(pct)
    ipcRenderer.on('download-progress', listener)
    return () => ipcRenderer.removeListener('download-progress', listener)
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
