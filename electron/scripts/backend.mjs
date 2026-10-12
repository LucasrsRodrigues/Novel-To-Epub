// Script Node puro (.mjs, sem TypeScript): a regra de tipo de retorno nao se aplica.
/* eslint-disable @typescript-eslint/explicit-function-return-type */
// Backend Python (PyInstaller) no empacotamento do app.
//
//   node scripts/backend.mjs build            → compila backend/dist/novel-backend
//   node scripts/backend.mjs check [win|mac|linux]
//       → confere se o binário em dist/ é DA plataforma alvo (default: a atual)
//
// PyInstaller não faz cross-compile: rodar `build:win` num Mac empacotaria o
// binário de Mac dentro do instalador do Windows (o app instalaria e o backend
// nunca subiria). O `check` lê os bytes mágicos do executável e falha com uma
// mensagem clara antes do electron-builder.
import { spawnSync } from 'node:child_process'
import { existsSync, openSync, readSync, closeSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const BACKEND = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'backend')
const HOST = { win32: 'win', darwin: 'mac', linux: 'linux' }[process.platform]
const LABEL = { win: 'Windows', mac: 'macOS', linux: 'Linux' }

function fail(msg) {
  console.error(`\n[backend] ${msg}\n`)
  process.exit(1)
}

function build() {
  const venvBin = join(BACKEND, '.venv', HOST === 'win' ? 'Scripts' : 'bin')
  const pyinstaller = join(venvBin, HOST === 'win' ? 'pyinstaller.exe' : 'pyinstaller')
  if (!existsSync(pyinstaller)) {
    fail(
      `PyInstaller não encontrado em ${pyinstaller} — rode \`make install\` e \`pip install pyinstaller\` no venv do backend.`
    )
  }
  const r = spawnSync(pyinstaller, ['--clean', '--noconfirm', 'novel-backend.spec'], {
    cwd: BACKEND,
    stdio: 'inherit'
  })
  process.exit(r.status ?? 1)
}

function formatOf(file) {
  const fd = openSync(file, 'r')
  const b = Buffer.alloc(4)
  readSync(fd, b, 0, 4, 0)
  closeSync(fd)
  const hex = b.toString('hex')
  if (b[0] === 0x4d && b[1] === 0x5a) return 'win' // "MZ" (PE)
  if (hex === '7f454c46') return 'linux' // ELF
  if (['cffaedfe', 'cefaedfe', 'feedfacf', 'feedface', 'cafebabe'].includes(hex)) return 'mac' // Mach-O
  return null
}

function check(target = HOST) {
  if (!LABEL[target]) fail(`plataforma inválida: ${target} (use win, mac ou linux)`)
  const exe = join(
    BACKEND,
    'dist',
    'novel-backend',
    target === 'win' ? 'novel-backend.exe' : 'novel-backend'
  )
  const crossHint =
    `PyInstaller não faz cross-compile: gere o build:${target} numa máquina ` +
    `${LABEL[target]} (ou num runner de CI dessa plataforma).`
  if (!existsSync(exe)) {
    fail(
      target === HOST
        ? `binário do backend não encontrado: ${exe} — rode \`npm run build:backend\`.`
        : `não há backend de ${LABEL[target]} em dist/ (esta máquina é ${LABEL[HOST]}). ${crossHint}`
    )
  }
  const got = formatOf(exe)
  if (got !== target) {
    fail(
      `o backend em dist/ foi compilado para ${LABEL[got] ?? 'formato desconhecido'}, ` +
        `mas o pacote é para ${LABEL[target]}. ${crossHint}`
    )
  }
  console.log(`[backend] ok: binário ${LABEL[target]} em ${exe}`)
}

const [cmd, arg] = process.argv.slice(2)
if (cmd === 'build') build()
else if (cmd === 'check') check(arg)
else fail('uso: node scripts/backend.mjs build | check [win|mac|linux]')
