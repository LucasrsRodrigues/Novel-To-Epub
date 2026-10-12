import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      backendUrl: string
      apiToken: string
      downloadFile: (
        url: string,
        defaultName: string,
        onProgress?: (pct: number) => void
      ) => Promise<{ canceled?: boolean; filePath?: string; bytes?: number; error?: string }>
    }
  }
}
