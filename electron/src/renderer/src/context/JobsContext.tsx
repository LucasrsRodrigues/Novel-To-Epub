import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, wsUrl, type JobStatus } from '@renderer/lib/api'

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
 * Semeia com GET /api/downloads e atualiza ao vivo pelos eventos do WS.
 */
export function JobsProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const [jobs, setJobs] = useState<Record<string, JobStatus>>({})
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    api
      .listDownloads()
      .then((list) =>
        setJobs((prev) => {
          const next = { ...prev }
          for (const job of list) next[job.id] = job
          return next
        })
      )
      .catch(() => {
        /* backend ainda subindo */
      })

    let closed = false
    let retry: ReturnType<typeof setTimeout>

    function connect(): void {
      const ws = new WebSocket(wsUrl())
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data as string) as { event: string; job: JobStatus }
        setJobs((prev) => ({ ...prev, [msg.job.id]: msg.job }))
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
