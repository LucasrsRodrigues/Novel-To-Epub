import { spawn, type ChildProcess } from 'child_process'
import { createServer, type AddressInfo } from 'net'
import { request } from 'http'
import { existsSync } from 'fs'

let proc: ChildProcess | null = null

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
}

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

async function waitForHealth(url: string, timeoutMs = 30000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await ping(url)) return
    await new Promise((r) => setTimeout(r, 300))
  }
  throw new Error('backend nao respondeu ao /api/health a tempo')
}

/** Sobe o backend Python e resolve com a URL base depois do health check. */
export async function startBackend(cfg: BackendConfig): Promise<string> {
  const host = cfg.host ?? '127.0.0.1'
  const port = cfg.port ?? (await freePort())
  const url = `http://${host}:${port}`

  let cmd: string
  let args: string[]
  if (cfg.binaryPath && existsSync(cfg.binaryPath)) {
    cmd = cfg.binaryPath
    args = ['serve', '--host', host, '--port', String(port)]
  } else {
    cmd = cfg.pythonPath
    args = ['main.py', 'serve', '--host', host, '--port', String(port)]
  }

  const env: NodeJS.ProcessEnv = { ...process.env }
  if (cfg.dataDir) env.NOVEL_DATA_DIR = cfg.dataDir

  proc = spawn(cmd, args, { cwd: cfg.backendDir, stdio: 'inherit', env })
  proc.on('exit', (code, signal) => {
    console.log(`[backend] saiu (code=${code} signal=${signal})`)
    proc = null
  })
  proc.on('error', (err) => console.error('[backend] falha ao iniciar:', err))

  await waitForHealth(url)
  return url
}

/** Encerra o backend (idempotente). */
export function stopBackend(): void {
  if (proc && !proc.killed) {
    proc.kill('SIGTERM')
    proc = null
  }
}
