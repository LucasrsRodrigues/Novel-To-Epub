import { app, shell, BrowserWindow, dialog, ipcMain } from 'electron'
import { join } from 'path'
import { fileURLToPath } from 'url'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import {
  killBackendNow,
  startBackend,
  stopBackend,
  type BackendConfig,
  type BackendInfo
} from './backend'
import { downloadToFile } from './download'

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

// Uma instancia so: duas abririam dois backends gravando no MESMO SQLite e nas
// mesmas capture_intents do userData. A segunda abertura so traz a janela da
// primeira pra frente.
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    const win = BrowserWindow.getAllWindows()[0]
    if (!win) return
    if (win.isMinimized()) win.restore()
    win.focus()
  })
}

function backendConfig(): BackendConfig {
  const isWin = process.platform === 'win32'
  const port = process.env.NOVEL_BACKEND_PORT ? Number(process.env.NOVEL_BACKEND_PORT) : undefined

  if (is.dev) {
    // out/main -> ../../../backend  (raiz do projeto/backend)
    const backendDir = join(__dirname, '../../../backend')
    const pythonPath = join(backendDir, '.venv', isWin ? 'Scripts/python.exe' : 'bin/python')
    return { backendDir, pythonPath, port } // em dev usa backend/data; log so no console
  }

  // Produção: binário empacotado (PyInstaller) em resources/.
  // Dados vão pra userData (gravável, persiste entre updates do app).
  const backendDir = join(process.resourcesPath, 'backend')
  return {
    backendDir,
    pythonPath: '',
    binaryPath: join(backendDir, isWin ? 'novel-backend.exe' : 'novel-backend'),
    port,
    dataDir: app.getPath('userData'),
    logFile: join(app.getPath('userData'), 'logs', 'backend.log')
  }
}

function isWebUrl(url: string): boolean {
  try {
    const { protocol } = new URL(url)
    return protocol === 'https:' || protocol === 'http:'
  } catch {
    return false
  }
}

const RENDERER_INDEX = join(__dirname, '../renderer/index.html')

// URL da própria UI: o dev server do Vite (dev) ou o index.html empacotado —
// só ele, não qualquer file:// (um link pra arquivo local também é navegação).
function isAppUrl(url: string): boolean {
  const devUrl = is.dev ? process.env['ELECTRON_RENDERER_URL'] : undefined
  try {
    if (devUrl) return new URL(url).origin === new URL(devUrl).origin
    const u = new URL(url)
    return u.protocol === 'file:' && fileURLToPath(u) === RENDERER_INDEX
  } catch {
    return false
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
      // Preload so usa contextBridge + ipcRenderer + process.argv, tudo
      // disponivel no preload sandboxed. Renderer sem Node, isolado do preload.
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      // injeta URL + token do backend no renderer (lidos pelo preload)
      additionalArguments: [`--backend-url=${backend.url}`, `--api-token=${backend.token}`]
    }
  })

  mainWindow.on('ready-to-show', () => mainWindow.show())

  // Links <a target="_blank"> (site da novel, wiki, repositório) abrem no
  // navegador do sistema — mas só http(s). Essas URLs vêm em parte de dados
  // raspados (source_url/wiki_url); um file:// ou esquema customizado
  // (ex.: app de terceiro registrado no SO) seria executado pelo openExternal.
  mainWindow.webContents.setWindowOpenHandler((details) => {
    if (isWebUrl(details.url)) void shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // A janela nunca sai do app: um <a href> sem target (ou um redirect) trocaria a
  // UI por uma página externa — que herdaria o preload e o window.api. Links
  // http(s) vão pro navegador do sistema; o resto é ignorado.
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (isAppUrl(url)) return
    event.preventDefault()
    if (isWebUrl(url)) void shell.openExternal(url)
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(RENDERER_INDEX)
  }
}

// Origem do backend (http://127.0.0.1:<porta>) — o download-file so aceita URLs
// dela. Definida quando o backend sobe.
let backendOrigin: string | null = null

// Baixa uma URL do backend direto pro disco, no processo main (ver
// downloadToFile). Nenhum binário grande cruza a fronteira do contextBridge/IPC
// (passar ArrayBuffer por lá corrompia o .zip). O progresso vai em
// 'download-progress' com o `id` do pedido, pra downloads simultâneos não se
// misturarem. Devolve {filePath, bytes} | {canceled} | {error}.
ipcMain.handle(
  'download-file',
  async (evt, payload: { id: string; url: string; defaultName: string }) => {
    if (!backendOrigin || new URL(payload.url).origin !== backendOrigin) {
      return { error: 'URL de download fora do backend do app' }
    }
    const win = BrowserWindow.fromWebContents(evt.sender) ?? BrowserWindow.getFocusedWindow()
    const opts = { defaultPath: payload.defaultName }
    const { canceled, filePath } = win
      ? await dialog.showSaveDialog(win, opts)
      : await dialog.showSaveDialog(opts)
    if (canceled || !filePath) return { canceled: true }

    return downloadToFile(payload.url, filePath, (pct) => {
      // a janela pode ter fechado no meio do download
      if (!evt.sender.isDestroyed()) evt.sender.send('download-progress', payload.id, pct)
    })
  }
)

// O backend caiu e nao voltou: sem ele o app nao faz nada. Oferece reabrir.
function backendFatal(err: Error): void {
  console.error('[main] backend parou de vez:', err)
  if (HEADLESS) return app.quit()
  const logHint = is.dev ? '' : `\n\nLog: ${join(app.getPath('userData'), 'logs', 'backend.log')}`
  const choice = dialog.showMessageBoxSync({
    type: 'error',
    title: 'O backend parou',
    message: 'O backend do app parou de responder e não conseguiu reiniciar.',
    detail: `${err.message}${logHint}`,
    buttons: ['Reabrir o app', 'Fechar'],
    defaultId: 0
  })
  if (choice === 0) app.relaunch()
  app.quit()
}

app.whenReady().then(async () => {
  if (!gotLock) return
  electronApp.setAppUserModelId('com.novel-to-epub')
  app.on('browser-window-created', (_, window) => optimizer.watchWindowShortcuts(window))

  let backend: BackendInfo
  try {
    backend = await startBackend(backendConfig(), {
      onRestarted: () => console.warn('[main] backend reiniciado apos queda'),
      onFatal: backendFatal
    })
    backendOrigin = new URL(backend.url).origin
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

// Garante que o backend morre junto com o app — e que o app SO sai depois dele:
// segura o quit, espera o SIGTERM terminar (jobs viram 'interrupted', SQLite
// fecha limpo; SIGKILL apos 5s) e ai sai de verdade.
let backendStopped = false
app.on('before-quit', (event) => {
  if (backendStopped) return
  event.preventDefault()
  void stopBackend().finally(() => {
    backendStopped = true
    app.quit()
  })
})
// Ultimo recurso se o processo sair sem passar pelo before-quit.
process.on('exit', killBackendNow)
for (const sig of ['SIGTERM', 'SIGINT'] as const) {
  process.on(sig, () => app.quit())
}
