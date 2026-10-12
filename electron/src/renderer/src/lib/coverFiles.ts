// As imagens da galeria vêm do backend (http://127.0.0.1:8000). No app empacotado
// o renderer roda em file:// → <img src> cross-origin é bloqueado pelo ORB do
// Chromium. fetch() passa (CORS liberado), então buscamos os bytes e os
// convertemos em data: URL (decodifica em qualquer contexto, sem precisar
// revogar object URL).
export async function fetchDataUrl(url: string): Promise<string> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`falha ao carregar (${res.status})`)
  const blob = await res.blob()
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error('falha ao ler imagem'))
    reader.readAsDataURL(blob)
  })
}

export async function downloadCover(url: string, filename: string): Promise<void> {
  const dataUrl = await fetchDataUrl(url)
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}
