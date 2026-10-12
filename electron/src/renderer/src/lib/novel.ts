export function slugifyName(s: string): string {
  return (
    s
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'capa'
  )
}

// Matcha duas URLs ignorando fragment/trailing slash, e tambem comparando
// hosts diferentes do mesmo mirror (novelbin.me vs novelbin.com etc).
export function urlsMatch(a: string, b: string): boolean {
  if (!a || !b) return false
  const norm = (u: string): string => {
    try {
      const parsed = new URL(u)
      const path = parsed.pathname.replace(/\/$/, '')
      return path.toLowerCase()
    } catch {
      return u.toLowerCase()
    }
  }
  return norm(a) === norm(b)
}
