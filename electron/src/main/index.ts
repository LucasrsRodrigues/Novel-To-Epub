import { app, shell, BrowserWindow, dialog, ipcMain } from 'electron'
import { writeFile } from 'fs/promises'
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

// Salva bytes vindos do renderer via save dialog (download "Baixar tudo"). Devolve
// o caminho salvo ou {canceled}. Mais confiável que o download do Chromium e dá
// feedback claro ("salvo em ...") em vez do <a download> silencioso.
ipcMain.handle(
  'save-file',
  async (_evt, payload: { defaultName: string; data: ArrayBuffer }) => {
    const win = BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0]
    const opts = { defaultPath: payload.defaultName }
    const { canceled, filePath } = win
      ? await dialog.showSaveDialog(win, opts)
      : await dialog.showSaveDialog(opts)
    if (canceled || !filePath) return { canceled: true }
    await writeFile(filePath, Buffer.from(payload.data))
    return { canceled: false, filePath }
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
