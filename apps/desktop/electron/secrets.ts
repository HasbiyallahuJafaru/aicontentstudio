// API keys, encrypted with the OS (DPAPI on Windows) via safeStorage. Only main + Python ever see plaintext.
import { safeStorage } from 'electron'
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'

// OPENROUTER covers every AI call (writing, clip selection, transcription); the rest are not AI services.
export const SECRET_NAMES = ['OPENROUTER_API_KEY', 'PEXELS_API_KEY', 'UNSPLASH_ACCESS_KEY'] as const
export type SecretName = (typeof SECRET_NAMES)[number]

export function createSecrets(file: string) {
  const read = (): Record<string, string> => {
    try { return existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : {} } catch { return {} }  // corrupt: start over
  }

  return {
    all(): Record<string, string> {
      const out: Record<string, string> = {}
      for (const [k, v] of Object.entries(read())) {
        try { out[k] = safeStorage.decryptString(Buffer.from(v, 'base64')) } catch { /* another user's or a broken entry: skip it */ }
      }
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
      writeFileSync(file + '.tmp', JSON.stringify(stored, null, 2))  // then rename: a crash never leaves half a file
      renameSync(file + '.tmp', file)
    },
  }
}
