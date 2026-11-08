export const BASE = '/agarwood'
export const API = `${BASE}/api/v1`

export async function get(path) {
  const response = await fetch(API + path)
  if (!response.ok) throw new Error(`加载失败：${response.status}`)
  return response.json()
}
