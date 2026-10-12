import { spawn, type ChildProcess } from 'child_process'
import { createServer, type AddressInfo } from 'net'
import { request } from 'http'
import {
  createWriteStream,
  existsSync,
  mkdirSync,
  renameSync,
  statSync,
  type WriteStream
} from 'fs'
import { dirname } from 'path'
import { randomBytes } from 'crypto'

export interface BackendConfig {
  /** Diretorio que contem o main.py (dev) ou o binario (prod). */
  backendDir: string
  /** Executavel Python do venv (modo dev). */
  pythonPath: string
  /** Binario empacotado via PyInstaller (modo prod — Etapa 4). */
  binaryPath?: string
  /** Porta fixa (se ausente, escolhe uma livre). Util p/ testes. */
  port?: number
  host?: string
  /** Onde o backend grava cache/epubs (NOVEL_DATA_DIR). No app empacotado,
   *  apontar para `app.getPath('userData')` pra nao escrever dentro do bundle. */
  dataDir?: string
  /** Arquivo de log do backend (stdout+stderr). Sem ele, so vai pro console —
   *  no app empacotado isso e o mesmo que nao ter log nenhum. */
  logFile?: string
}

export interface BackendInfo {
  url: string
  /** Token exigido pelo backend em toda request (header X-Api-Token ou ?token=).
   *  Novo a cada abertura do app — impede que paginas abertas no navegador
   *  chamem a API local (ver backend/app/api/auth.py). */
  token: string
}

export interface BackendHooks {
  /** O backend caiu e foi re-iniciado (mesma porta/token — a UI segue valendo). */
  onRestarted?: () => void
  /** O backend caiu e nao voltou (limite de restarts). O app nao funciona mais. */
  onFatal?: (err: Error) => void
}

// Restart automatico: no maximo MAX_RESTARTS quedas dentro de RESTART_WINDOW_MS.
// Passou disso e crash em loop (binario quebrado, banco corrompido...) — insistir
// so esconde o problema.
const MAX_RESTARTS = 3
const RESTART_WINDOW_MS = 60_000
const STOP_TIMEOUT_MS = 5_000
const LOG_MAX_BYTES = 5 * 1024 * 1024
const TAIL_LINES = 15

let proc: ChildProcess | null = null
let stopping = false
let logStream: WriteStream | null = null
// Ultimas linhas de saida — entram na mensagem de erro quando o backend morre.
const tail: string[] = []

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer()
    srv.unref()
    srv.on('error', reject)
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address() as AddressInfo
      srv.close(() => resolve(port))
    })
  })
}

function ping(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const req = request(`${url}/api/health`, { method: 'GET', timeout: 2000 }, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => {
      req.destroy()
      resolve(false)
    })
    req.end()
  })
}

/** Espera o /api/health — ou falha NA HORA se o processo morrer antes. */
async function waitForHealth(url: string, child: ChildProcess, timeoutMs = 30000): Promise<void> {
  let exited: string | null = null
  const onExit = (code: number | null, signal: string | null): void => {
    exited = `code=${code} signal=${signal}`
  }
  const onError = (err: Error): void => {
    exited = err.message
  }
  child.once('exit', onExit)
  child.once('error', onError)
  try {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      if (exited) throw backendError(`o backend saiu durante a inicializacao (${exited})`)
      if (await ping(url)) return
      await new Promise((r) => setTimeout(r, 300))
    }
    throw backendError('o backend nao respondeu ao /api/health a tempo')
  } finally {
    child.off('exit', onExit)
    child.off('error', onError)
  }
}

function backendError(message: string): Error {
  const lines = tail.length ? `\n\nUltimas linhas do log:\n${tail.join('\n')}` : ''
  return new Error(`${message}${lines}`)
}

function openLog(file: string): WriteStream {
  mkdirSync(dirname(file), { recursive: true })
  try {
    if (statSync(file).size > LOG_MAX_BYTES) renameSync(file, `${file}.1`)
  } catch {
    /* ainda nao existe */
  }
  const stream = createWriteStream(file, { flags: 'a' })
  stream.on('error', (err) => console.error('[backend] log indisponivel:', err))
  return stream
}

function pipeOutput(child: ChildProcess, echo: NodeJS.WriteStream): void {
  const sink = (chunk: Buffer): void => {
    echo.write(chunk)
    logStream?.write(chunk)
    for (const line of chunk.toString().split('\n')) {
      if (!line.trim()) continue
      tail.push(line)
      if (tail.length > TAIL_LINES) tail.shift()
    }
  }
  child.stdout?.on('data', sink)
  child.stderr?.on('data', sink)
}

/**
 * Sobe o backend Python e resolve com URL + token depois do health check.
 *
 * Depois de pronto, se o processo cair sozinho (nao por stopBackend), ele e
 * re-iniciado na MESMA porta e com o MESMO token — a janela continua valendo e
 * o WebSocket reconecta sozinho. Ver BackendHooks.
 */
export async function startBackend(
  cfg: BackendConfig,
  hooks: BackendHooks = {}
): Promise<BackendInfo> {
  const host = cfg.host ?? '127.0.0.1'
  const port = cfg.port ?? (await freePort())
  const url = `http://${host}:${port}`
  const token = randomBytes(32).toString('hex')

  // Falha clara em vez de spawn de um caminho que nao existe (antes: binario
  // ausente caia pro python '' e esperava 30s por um health que nunca vinha).
  let cmd: string
  let args: string[]
  if (cfg.binaryPath) {
    if (!existsSync(cfg.binaryPath)) {
      throw new Error(`binario do backend nao encontrado: ${cfg.binaryPath}`)
    }
    cmd = cfg.binaryPath
    args = ['serve', '--host', host, '--port', String(port)]
  } else {
    if (!existsSync(cfg.pythonPath)) {
      throw new Error(`Python do venv nao encontrado: ${cfg.pythonPath} (rode \`make install\`)`)
    }
    cmd = cfg.pythonPath
    args = ['main.py', 'serve', '--host', host, '--port', String(port)]
  }

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    NOVEL_API_TOKEN: token,
    // O backend se encerra sozinho se este processo morrer sem avisar (SIGKILL,
    // crash) — ver backend/app/parent_watch.py.
    NOVEL_PARENT_PID: String(process.pid)
  }
  if (cfg.dataDir) env.NOVEL_DATA_DIR = cfg.dataDir
  if (cfg.logFile) logStream = openLog(cfg.logFile)
  stopping = false

  const restarts: number[] = []

  const spawnChild = (): ChildProcess => {
    tail.length = 0
    logStream?.write(`\n===== backend iniciando ${new Date().toISOString()} (${url}) =====\n`)
    const child = spawn(cmd, args, { cwd: cfg.backendDir, stdio: ['ignore', 'pipe', 'pipe'], env })
    pipeOutput(child, process.stdout)
    child.on('error', (err) => console.error('[backend] falha ao iniciar:', err))
    proc = child
    return child
  }

  const watch = (child: ChildProcess): void => {
    child.once('exit', (code, signal) => {
      console.log(`[backend] saiu (code=${code} signal=${signal})`)
      if (proc === child) proc = null
      if (stopping) return
      void restart(`code=${code} signal=${signal}`)
    })
  }

  const restart = async (why: string): Promise<void> => {
    const now = Date.now()
    while (restarts.length && now - restarts[0] > RESTART_WINDOW_MS) restarts.shift()
    if (restarts.length >= MAX_RESTARTS) {
      hooks.onFatal?.(backendError(`o backend caiu ${MAX_RESTARTS + 1}x em 1 minuto (${why})`))
      return
    }
    restarts.push(now)
    const delay = 500 * 2 ** (restarts.length - 1)
    console.warn(`[backend] caiu (${why}); reiniciando em ${delay}ms`)
    await new Promise((r) => setTimeout(r, delay))
    if (stopping) return
    const child = spawnChild()
    try {
      await waitForHealth(url, child)
    } catch (err) {
      // Nao subiu: mata o que sobrou e tenta de novo (conta no limite de restarts).
      if (child.exitCode === null) {
        child.kill('SIGKILL')
        await new Promise((r) => child.once('exit', r))
      }
      if (!stopping) void restart((err as Error).message.split('\n')[0])
      return
    }
    watch(child)
    hooks.onRestarted?.()
  }

  const child = spawnChild()
  try {
    await waitForHealth(url, child)
  } catch (err) {
    if (child.exitCode === null) child.kill('SIGKILL')
    proc = null
    throw err
  }
  watch(child)
  return { url, token }
}

/**
 * Encerra o backend: SIGTERM (o uvicorn fecha jobs e SQLite com calma) e, se nao
 * sair em STOP_TIMEOUT_MS, SIGKILL. Resolve quando o processo de fato saiu.
 * Idempotente; desliga o restart automatico.
 */
export function stopBackend(): Promise<void> {
  stopping = true
  const child = proc
  if (!child || child.exitCode !== null) {
    proc = null
    return Promise.resolve()
  }
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      console.warn('[backend] nao saiu com SIGTERM; enviando SIGKILL')
      child.kill('SIGKILL')
    }, STOP_TIMEOUT_MS)
    child.once('exit', () => {
      clearTimeout(timer)
      proc = null
      logStream?.end()
      logStream = null
      resolve()
    })
    child.kill('SIGTERM')
  })
}

/** Ultimo recurso sincrono (process 'exit'): manda SIGKILL sem esperar. */
export function killBackendNow(): void {
  stopping = true
  if (proc && proc.exitCode === null) proc.kill('SIGKILL')
}
