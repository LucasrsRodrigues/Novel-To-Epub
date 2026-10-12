import { app, shell, BrowserWindow, dialog, ipcMain } from 'electron'
import { createWriteStream } from 'fs'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import { startBackend, stopBackend, type BackendConfig, type BackendInfo } from './backend'

// Modo headless (sem janela) — usado para validar o spawn do backend nos testes.
const HEADLESS = !!process.env.NOVEL_HEADLESS

// Ancora userData num path estável baseado no productName, NÃO no package.json:name.
// Sem isso, renomear `name` no package.json move o userData (Electron usa `name`
// por default) e a Library/Glossário "somem" — os dados antigos ficam orfanados
// na pasta com o nome antigo. Fixar aqui torna o caminho independente disso.
// Deve rodar ANTES de qualquer `app.getPath('userData')` (incluindo o backendConfig).
if (!is.dev) {
  app.setPath('userData', join(app.getPath('appData'), 'Novel to EPUB'))
}

function backendConfig(): BackendConfig {
  const isWin = process.platform === 'win32'
  const port = process.env.NOVEL_BACKEND_PORT ? Number(process.env.NOVEL_BACKEND_PORT) : undefined

  if (is.dev) {
    // out/main -> ../../../backend  (raiz do projeto/backend)
    const backendDir = join(__dirname, '../../../backend')
    const pythonPath = join(backendDir, '.venv', isWin ? 'Scripts/python.exe' : 'bin/python')
    return { backendDir, pythonPath, port } // em dev usa backend/data
  }

  // Produção: binário empacotado (PyInstaller) em resources/.
  // Dados vão pra userData (gravável, persiste entre updates do app).
  const backendDir = join(process.resourcesPath, 'backend')
  return {
    backendDir,
    pythonPath: '',
    binaryPath: join(backendDir, isWin ? 'novel-backend.exe' : 'novel-backend'),
    port,
    dataDir: app.getPath('userData')
  }
}

function createWindow(backend: BackendInfo): void {
  const mainWindow = new BrowserWindow({
    width: 1000,
    height: 720,
    show: false,
    autoHideMenuBar: true,
    // Esconde a title bar no macOS (traffic lights ficam, content vai ate o topo).
    // Linux/Windows: nao tem hiddenInset; usa um frame escondido.
    titleBarStyle: 'hiddenInset',
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      // injeta URL + token do backend no renderer (lidos pelo preload)
      additionalArguments: [`--backend-url=${backend.url}`, `--api-token=${backend.token}`]
    }
  })

  mainWindow.on('ready-to-show', () => mainWindow.show())

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// Baixa uma URL (backend localhost) direto pro disco, no processo main. O main
// faz o fetch e grava via stream — assim NENHUM binário grande cruza a fronteira
// do contextBridge/IPC (passar ArrayBuffer por lá corrompia o .zip). Emite
// progresso por evento 'download-progress' e devolve {filePath} | {canceled} | {error}.
ipcMain.handle(
  'download-file',
  async (evt, payload: { url: string; defaultName: string }) => {
    const win = BrowserWindow.fromWebContents(evt.sender) ?? BrowserWindow.getFocusedWindow()
    const opts = { defaultPath: payload.defaultName }
    const { canceled, filePath } = win
      ? await dialog.showSaveDialog(win, opts)
      : await dialog.showSaveDialog(opts)
    if (canceled || !filePath) return { canceled: true }

    try {
      const res = await fetch(payload.url)
      if (!res.ok || !res.body) {
        let detail = `HTTP ${res.status}`
        try {
          const j = (await res.json()) as { detail?: string }
          if (j?.detail) detail = j.detail
        } catch {
          /* corpo não-JSON */
        }
        return { error: detail }
      }

      const total = Number(res.headers.get('content-length')) || 0
      const out = createWriteStream(filePath)
      const reader = res.body.getReader()
      let received = 0
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        out.write(Buffer.from(value))
        received += value.length
        evt.sender.send('download-progress', total ? received / total : -1)
      }
      await new Promise<void>((resolve, reject) =>
        out.end((err?: Error | null) => (err ? reject(err) : resolve()))
      )
      return { filePath, bytes: received }
    } catch (err) {
      return { error: err instanceof Error ? err.message : String(err) }
    }
  }
)

app.whenReady().then(async () => {
  electronApp.setAppUserModelId('com.novel-to-epub')
  app.on('browser-window-created', (_, window) => optimizer.watchWindowShortcuts(window))

  let backend: BackendInfo
  try {
    backend = await startBackend(backendConfig())
    console.log('[main] backend pronto em', backend.url)
  } catch (err) {
    console.error('[main] backend falhou:', err)
    if (!HEADLESS) dialog.showErrorBox('Erro ao iniciar o backend', String(err))
    app.quit()
    return
  }

  if (!HEADLESS) {
    createWindow(backend)
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow(backend)
    })
  }
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

// Garante que o backend morre junto com o app.
app.on('before-quit', stopBackend)
process.on('exit', stopBackend)
for (const sig of ['SIGTERM', 'SIGINT'] as const) {
  process.on(sig, () => {
    stopBackend()
    app.quit()
  })
}
