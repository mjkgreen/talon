'use strict';

const { app, BrowserWindow, shell, dialog, Menu } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

// ---------------------------------------------------------------------------
// Single-instance lock — required for deep-link OAuth on Windows/Linux
// ---------------------------------------------------------------------------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

let mainWindow = null;
let pythonProcess = null;
let serverPort = null;

// ---------------------------------------------------------------------------
// Locate the bundled Python binary
// ---------------------------------------------------------------------------
function getPythonBinaryPath() {
  if (app.isPackaged) {
    const ext = process.platform === 'win32' ? '.exe' : '';
    if (process.platform === 'darwin' || process.platform === 'linux') {
      // One-dir bundle: resourcesPath/talon-server/talon-server
      return path.join(process.resourcesPath, 'talon-server', `talon-server${ext}`);
    }
    return path.join(process.resourcesPath, `talon-server${ext}`);
  }
  // Dev mode: run server_entry directly via Python
  return null;
}

// ---------------------------------------------------------------------------
// Start the Python FastAPI server subprocess
// ---------------------------------------------------------------------------
function startPythonServer() {
  return new Promise((resolve, reject) => {
    const binaryPath = getPythonBinaryPath();
    let proc;

    if (binaryPath) {
      proc = spawn(binaryPath, [], {
        windowsHide: true,
        env: { ...process.env },
      });
    } else {
      // Development: use the system Python in the venv
      const pythonExe = process.platform === 'win32' ? 'python' : 'python3';
      const repoRoot = path.join(__dirname, '..');
      proc = spawn(pythonExe, ['-m', 'talon.server_entry'], {
        cwd: repoRoot,
        windowsHide: true,
        env: { ...process.env, PYTHONPATH: repoRoot },
      });
    }

    pythonProcess = proc;

    // The server prints "PORT:<number>" as its first stdout line.
    proc.stdout.on('data', (data) => {
      const text = data.toString();
      const match = text.match(/PORT:(\d+)/);
      if (match && !serverPort) {
        serverPort = parseInt(match[1], 10);
        resolve(serverPort);
      }
    });

    proc.stderr.on('data', (data) => {
      // Suppress in production; log in dev for debugging.
      if (!app.isPackaged) {
        process.stderr.write(`[server] ${data}`);
      }
    });

    proc.on('error', (err) => {
      reject(new Error(`Failed to start Python server: ${err.message}`));
    });

    proc.on('exit', (code) => {
      if (serverPort === null) {
        reject(new Error(`Python server exited before announcing port (code ${code})`));
      }
    });

    // Timeout if the server never announces a port (e.g. import error)
    setTimeout(() => {
      if (serverPort === null) {
        reject(new Error('Timed out waiting for Python server to start (30 s)'));
      }
    }, 30_000);
  });
}

// ---------------------------------------------------------------------------
// Wait until the HTTP server is actually accepting connections
// ---------------------------------------------------------------------------
function waitForServer(port, retries = 30) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        if (res.statusCode === 200) return resolve();
        retry();
      });
      req.on('error', retry);
    };
    const retry = () => {
      attempts++;
      if (attempts >= retries) return reject(new Error('Server did not become healthy in time'));
      setTimeout(check, 500);
    };
    check();
  });
}

// ---------------------------------------------------------------------------
// Create the main browser window
// ---------------------------------------------------------------------------
function createWindow(port) {
  const iconExt = process.platform === 'win32' ? 'ico' : process.platform === 'darwin' ? 'icns' : 'png';
  const iconPath = path.join(__dirname, 'icons', `icon.${iconExt}`);

  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 800,
    minHeight: 600,
    title: 'Talon',
    icon: iconPath,
    show: false, // shown after ready-to-show to avoid visual flash
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    ...(process.platform === 'darwin'
      ? { titleBarStyle: 'hiddenInset' }
      : {}),
  });

  mainWindow.loadURL(`http://127.0.0.1:${port}`);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Open external links in the system browser, not in the app.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ---------------------------------------------------------------------------
// Deep-link OAuth: forward talon://oauth-callback?code=…&state=… to server
// ---------------------------------------------------------------------------
async function handleOAuthCallback(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (url.hostname !== 'oauth-callback') return;

    const code = url.searchParams.get('code');
    const state = url.searchParams.get('state');
    if (!code || !serverPort) return;

    // POST the code to the local server, which exchanges it for a token.
    const body = JSON.stringify({ code, state: state || '' });
    const req = http.request({
      hostname: '127.0.0.1',
      port: serverPort,
      path: '/api/auth/github/exchange',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    });
    req.write(body);
    req.end();

    // Bring the window to the front after auth
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  } catch (err) {
    if (!app.isPackaged) console.error('OAuth callback error:', err);
  }
}

// ---------------------------------------------------------------------------
// macOS: deep link arrives via open-url in the running instance
// ---------------------------------------------------------------------------
app.on('open-url', (event, url) => {
  event.preventDefault();
  handleOAuthCallback(url);
});

// ---------------------------------------------------------------------------
// Windows/Linux: deep link arrives as a second instance's argv
// ---------------------------------------------------------------------------
app.on('second-instance', (_event, argv) => {
  const deepLink = argv.find((arg) => arg.startsWith('talon://'));
  if (deepLink) handleOAuthCallback(deepLink);

  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

// Register talon:// as a custom protocol (needed on all platforms)
app.setAsDefaultProtocolClient('talon');

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------
app.on('ready', async () => {
  Menu.setApplicationMenu(null);

  app.setAboutPanelOptions({
    applicationName: 'Talon',
    applicationVersion: app.getVersion(),
    copyright: '© 2025 Chasqui AI',
  });

  try {
    const port = await startPythonServer();
    await waitForServer(port);
    createWindow(port);

    if (app.isPackaged) {
      autoUpdater.checkForUpdatesAndNotify();
    }
  } catch (err) {
    dialog.showErrorBox(
      'Talon failed to start',
      `The background server could not be launched.\n\n${err.message}`
    );
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && serverPort) {
    createWindow(serverPort);
  }
});

app.on('before-quit', () => {
  if (pythonProcess && !pythonProcess.killed) {
    pythonProcess.kill('SIGTERM');
  }
});

// Clean up on unexpected exit
process.on('exit', () => {
  if (pythonProcess && !pythonProcess.killed) {
    pythonProcess.kill();
  }
});
