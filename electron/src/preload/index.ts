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
  // Salva bytes num arquivo via save dialog do main (download "Baixar tudo").
  saveFile: (
    defaultName: string,
    data: ArrayBuffer
  ): Promise<{ canceled: boolean; filePath?: string }> =>
    ipcRenderer.invoke('save-file', { defaultName, data })
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
