import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      backendUrl: string
      apiToken: string
      downloadFile: (
        url: string,
        defaultName: string
      ) => Promise<{ canceled?: boolean; filePath?: string; bytes?: number; error?: string }>
      onDownloadProgress: (cb: (pct: number) => void) => () => void
    }
  }
}
