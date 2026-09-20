// Rasterises public/icon.svg (the master) into resources/icon.png, using the Electron we already ship with.
// Run after editing the SVG: node scripts/make-icon.cjs && python scripts/make-icon-ico.py
const { app, BrowserWindow } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

const root = path.join(__dirname, '..')
const svg = fs.readFileSync(path.join(root, 'public/icon.svg'), 'utf8')
const out = path.join(root, 'resources/icon.png')

app.disableHardwareAcceleration()

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 512, height: 512, show: false, frame: false, transparent: true,
    useContentSize: true, backgroundColor: '#00000000',
  })
  const html = `<style>html,body{margin:0;padding:0;background:transparent}svg{display:block}</style>${svg}`
  await win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html))
  await new Promise((r) => setTimeout(r, 600))
  const img = await win.webContents.capturePage()
  fs.mkdirSync(path.dirname(out), { recursive: true })
  fs.writeFileSync(out, img.toPNG())
  console.log('wrote', out, img.getSize())
  app.quit()
})
