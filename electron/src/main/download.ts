import { createWriteStream } from 'fs'
import { unlink } from 'fs/promises'
import { Readable, Transform } from 'stream'
import { pipeline } from 'stream/promises'
import type { ReadableStream as WebReadableStream } from 'stream/web'

export type DownloadResult = { filePath?: string; bytes?: number; error?: string }

/**
 * Baixa `url` pra `filePath` via stream (sem segurar o arquivo na memória).
 *
 * - pipeline(): propaga erro de qualquer ponta (disco cheio, permissão negada,
 *   conexão caída) como rejeição — antes, um erro do WriteStream sem listener
 *   virava exceção solta no processo main — e respeita backpressure.
 * - falha no meio → apaga o arquivo parcial.
 * - `onProgress` (0..1, ou -1 sem Content-Length) no máximo ~10x/s, + 1 no fim.
 *
 * Nunca rejeita: devolve {filePath, bytes} ou {error}.
 */
export async function downloadToFile(
  url: string,
  filePath: string,
  onProgress: (pct: number) => void = () => {}
): Promise<DownloadResult> {
  let received = 0
  let opened = false
  try {
    const res = await fetch(url)
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
    let lastSent = 0
    const counter = new Transform({
      transform(chunk: Buffer, _enc, cb) {
        received += chunk.length
        const now = Date.now()
        if (now - lastSent >= 100) {
          lastSent = now
          onProgress(total ? received / total : -1)
        }
        cb(null, chunk)
      }
    })
    opened = true
    await pipeline(
      Readable.fromWeb(res.body as WebReadableStream<Uint8Array>),
      counter,
      createWriteStream(filePath)
    )
    onProgress(1)
    return { filePath, bytes: received }
  } catch (err) {
    // não deixa arquivo pela metade no disco
    if (opened) await unlink(filePath).catch(() => {})
    return { error: err instanceof Error ? err.message : String(err) }
  }
}
