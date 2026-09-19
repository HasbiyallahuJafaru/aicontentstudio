import { app, BrowserWindow, ipcMain, Menu, shell } from 'electron'
import { join, resolve } from 'node:path'
import { createBackend, type BackendStatus } from './backend'
import { createSecrets, type SecretName } from './secrets'

const dev = !app.isPackaged
const dataDir = process.env.ACS_DATA_DIR || (dev ? resolve(app.getAppPath(), '../../data') : join(app.getPath('userData'), 'data'))
const secrets = createSecrets(join(app.getPath('userData'), 'secrets.json'))
let status: BackendStatus = { state: 'starting' }
let backend: ReturnType<typeof createBackend>

const broadcast = (channel: string, ...args: unknown[]) =>
  BrowserWindow.getAllWindows().forEach((w) => { try { w.webContents.send(channel, ...args) } catch { /* window closing */ } })

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    backgroundColor: '#111112',
    title: 'AI Social Content Studio',
    titleBarStyle: 'hidden',
    titleBarOverlay: { color: '#111112', symbolColor: '#a1a1a6', height: 44 },
    webPreferences: { preload: join(__dirname, '../preload/preload.js'), contextIsolation: true, sandbox: true },
  })
  win.once('ready-to-show', () => win.show())
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (e) => e.preventDefault())
  if (dev && process.env.ELECTRON_RENDERER_URL) win.loadURL(process.env.ELECTRON_RENDERER_URL)
  else win.loadFile(join(__dirname, '../renderer/index.html'))
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null)
  backend = createBackend({
    backendDir: dev ? resolve(app.getAppPath(), '../backend') : join(process.resourcesPath, 'backend'),
    dataDir,
    dev,
    onStatus: (s) => broadcast('backend:status', (status = s)),
    onEvent: (event, data) => broadcast('backend:event', event, data),
    onReady: () => backend.call('secrets.load', { keys: secrets.all() }),
  })

  // The renderer may call any backend method except secrets.*, which only main sends.
  ipcMain.handle('backend:call', (_e, method: string, params?: object) =>
    typeof method === 'string' && !method.startsWith('secrets.')
      ? backend.call(method, params)
      : { error: { message: 'Not allowed.' } })
  ipcMain.handle('backend:status', () => status)
  ipcMain.handle('backend:restart', () => backend.restart())
  ipcMain.handle('secrets:status', () => secrets.status())
  ipcMain.handle('secrets:set', async (_e, name: SecretName, value: string) => {
    secrets.set(name, value)
    await backend.call('secrets.load', { keys: secrets.all() })
    return secrets.status()
  })
  ipcMain.handle('app:openDataDir', () => shell.openPath(dataDir))

  createWindow()
})

app.on('before-quit', () => backend?.stop())
app.on('window-all-closed', () => app.quit())
