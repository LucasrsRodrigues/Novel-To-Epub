import { app, shell, BrowserWindow, dialog } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import { startBackend, stopBackend, type BackendConfig } from './backend'

// Modo headless (sem janela) — usado para validar o spawn do backend nos testes.
const HEADLESS = !!process.env.NOVEL_HEADLESS

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

function createWindow(backendUrl: string): void {
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
      // injeta a URL do backend no renderer (lida pelo preload)
      additionalArguments: [`--backend-url=${backendUrl}`]
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

app.whenReady().then(async () => {
  electronApp.setAppUserModelId('com.novel-to-epub')
  app.on('browser-window-created', (_, window) => optimizer.watchWindowShortcuts(window))

  let backendUrl: string
  try {
    backendUrl = await startBackend(backendConfig())
    console.log('[main] backend pronto em', backendUrl)
  } catch (err) {
    console.error('[main] backend falhou:', err)
    if (!HEADLESS) dialog.showErrorBox('Erro ao iniciar o backend', String(err))
    app.quit()
    return
  }

  if (!HEADLESS) {
    createWindow(backendUrl)
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow(backendUrl)
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
