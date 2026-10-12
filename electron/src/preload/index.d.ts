import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      backendUrl: string
      apiToken: string
      saveFile: (
        defaultName: string,
        data: ArrayBuffer
      ) => Promise<{ canceled: boolean; filePath?: string }>
    }
  }
}
