// API keys, encrypted with the OS (DPAPI on Windows) via safeStorage. Only main + Python ever see plaintext.
import { safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'

export const SECRET_NAMES = ['DEEPSEEK_API_KEY', 'PEXELS_API_KEY', 'UNSPLASH_ACCESS_KEY'] as const
export type SecretName = (typeof SECRET_NAMES)[number]

export function createSecrets(file: string) {
  const read = (): Record<string, string> => (existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : {})

  return {
    all(): Record<string, string> {
      const out: Record<string, string> = {}
      for (const [k, v] of Object.entries(read())) out[k] = safeStorage.decryptString(Buffer.from(v, 'base64'))
      return out
    },
    status(): Record<SecretName, boolean> {
      const stored = read()
      return Object.fromEntries(SECRET_NAMES.map((n) => [n, n in stored])) as Record<SecretName, boolean>
    },
    set(name: SecretName, value: string) {
      if (!SECRET_NAMES.includes(name)) throw new Error('Unknown key name')
      const stored = read()
      const v = value.trim()
      if (v) stored[name] = safeStorage.encryptString(v).toString('base64')
      else delete stored[name]
      writeFileSync(file, JSON.stringify(stored, null, 2))
    },
  }
}
