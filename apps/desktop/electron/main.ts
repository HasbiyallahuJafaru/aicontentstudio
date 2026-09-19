import { app, BrowserWindow, ipcMain, Menu, net, protocol, screen, shell } from 'electron'
import { existsSync } from 'node:fs'
import { join, resolve, sep } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createBackend, type BackendStatus } from './backend'
import { createSecrets, type SecretName } from './secrets'

const dev = !app.isPackaged
const dataDir = process.env.ACS_DATA_DIR || (dev ? resolve(app.getAppPath(), '../../data') : join(app.getPath('userData'), 'data'))
const mediaDir = join(dataDir, 'media')
const secrets = createSecrets(join(app.getPath('userData'), 'secrets.json'))
let status: BackendStatus = { state: 'starting' }
let backend: ReturnType<typeof createBackend>

// Library thumbnails reach the sandboxed renderer over this scheme (it cannot read files itself).
protocol.registerSchemesAsPrivileged([
  { scheme: 'media', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } },
])

const broadcast = (channel: string, ...args: unknown[]) =>
  BrowserWindow.getAllWindows().forEach((w) => { try { w.webContents.send(channel, ...args) } catch { /* window closing */ } })

function createWindow() {
  // Fit the display's work area (scaled laptops can be narrower than 1440 logical px), never larger.
  const area = screen.getPrimaryDisplay().workAreaSize
  const win = new BrowserWindow({
    width: Math.min(1440, area.width),
    height: Math.min(900, area.height),
    minWidth: Math.min(1024, area.width),
    minHeight: Math.min(680, area.height),
    center: true,
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
  protocol.handle('media', (req) => {
    // media:///thumbs/x.bmp and media://thumbs/x.bmp are the same URL once parsed; take host + path.
    const u = new URL(req.url)
    const rel = decodeURIComponent(`${u.host}${u.pathname}`).replace(/^\/+/, '')
    const file = resolve(mediaDir, rel)
    if (!file.startsWith(mediaDir + sep) || !existsSync(file)) return new Response('Not found', { status: 404 })
    return net.fetch(pathToFileURL(file).toString())
  })
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
  ipcMain.handle('app:openExternal', (_e, url: string) =>
    typeof url === 'string' && url.startsWith('https://') ? shell.openExternal(url) : Promise.resolve())

  createWindow()
})

app.on('before-quit', () => backend?.stop())
app.on('window-all-closed', () => app.quit())
