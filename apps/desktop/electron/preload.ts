import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

function listen(channel: string, cb: (...args: any[]) => void) {
  const handler = (_e: IpcRendererEvent, ...args: any[]) => cb(...args)
  ipcRenderer.on(channel, handler)
  return () => { ipcRenderer.removeListener(channel, handler) }
}

const api = {
  call: (method: string, params?: object) => ipcRenderer.invoke('backend:call', method, params),
  status: () => ipcRenderer.invoke('backend:status'),
  restart: () => ipcRenderer.invoke('backend:restart'),
  onStatus: (cb: (s: unknown) => void) => listen('backend:status', cb),
  onEvent: (cb: (event: string, data: unknown) => void) => listen('backend:event', cb),
  secretsStatus: () => ipcRenderer.invoke('secrets:status'),
  setSecret: (name: string, value: string) => ipcRenderer.invoke('secrets:set', name, value),
  isFullScreen: (): Promise<boolean> => ipcRenderer.invoke('app:isFullScreen'),
  exitFullScreen: () => ipcRenderer.invoke('app:exitFullScreen'),
  onFullScreen: (cb: (on: boolean) => void) => listen('app:fullscreen', cb),
  openDataDir: () => ipcRenderer.invoke('app:openDataDir'),
  openExportPath: (p: string) => ipcRenderer.invoke('app:openExportPath', p),
  openExternal: (url: string) => ipcRenderer.invoke('app:openExternal', url),
}

contextBridge.exposeInMainWorld('studio', api)
export type StudioApi = typeof api
