import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, wsUrl, type JobStatus } from '@renderer/lib/api'
import { mergeSnapshot, type JobsMap } from '@renderer/lib/jobsMerge'

interface JobsContextValue {
  jobs: Record<string, JobStatus>
  connected: boolean
}

const JobsContext = createContext<JobsContextValue>({ jobs: {}, connected: false })

export function useJobs(): JobsContextValue {
  return useContext(JobsContext)
}

/**
 * Mantem UMA conexao WebSocket para todo o app e o estado de todos os jobs.
 * A cada (re)conexao re-semeia com GET /api/downloads — eventos perdidos
 * enquanto o WS estava caido (ex.: backend reiniciou) sao recuperados — e
 * atualiza ao vivo pelos eventos do WS.
 */
export function JobsProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const [jobs, setJobs] = useState<JobsMap>({})
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let closed = false
    let retry: ReturnType<typeof setTimeout>

    function resync(): void {
      const requestedAt = Date.now()
      api
        .listDownloads()
        .then((list) => {
          if (!closed) setJobs((prev) => mergeSnapshot(prev, list, requestedAt))
        })
        .catch(() => {
          /* backend ainda subindo — a proxima conexao tenta de novo */
        })
    }

    function connect(): void {
      const ws = new WebSocket(wsUrl())
      wsRef.current = ws
      ws.onopen = () => {
        setConnected(true)
        resync()
      }
      ws.onmessage = (e) => {
        let msg: { event: string; job?: JobStatus; job_id?: string }
        try {
          msg = JSON.parse(e.data as string)
        } catch {
          return // mensagem malformada nao derruba o handler
        }
        // Evento 'removed' (descarte) não traz job — remove a linha pelo id.
        if (msg.event === 'removed' && msg.job_id) {
          setJobs((prev) => {
            const next = { ...prev }
            delete next[msg.job_id as string]
            return next
          })
          return
        }
        const job = msg.job
        if (job) setJobs((prev) => ({ ...prev, [job.id]: job }))
      }
      ws.onerror = () => ws.close()
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = setTimeout(connect, 1500)
      }
    }

    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      wsRef.current?.close()
    }
  }, [])

  return <JobsContext.Provider value={{ jobs, connected }}>{children}</JobsContext.Provider>
}
