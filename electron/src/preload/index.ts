import { contextBridge } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// URL do backend injetada pelo main via webPreferences.additionalArguments
const backendUrl =
  process.argv.find((arg) => arg.startsWith('--backend-url='))?.slice('--backend-url='.length) ?? ''

// Custom APIs for renderer
const api = { backendUrl }

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
