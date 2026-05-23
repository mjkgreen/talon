'use strict';

const { app, BrowserWindow, shell, dialog, Menu, ipcMain } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

// ---------------------------------------------------------------------------
// OAuth credentials — placeholders replaced at build time by CI.
// In dev mode these are empty and the server reads from .env instead.
// ---------------------------------------------------------------------------
const BUNDLED_CLIENT_ID = '__GITHUB_CLIENT_ID__';
const BUNDLED_CLIENT_SECRET = '__GITHUB_CLIENT_SECRET__';

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
    // One-dir bundle: resourcesPath/talon-server/talon-server(.exe)
    return path.join(process.resourcesPath, 'talon-server', `talon-server${ext}`);
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
    let stderrBuffer = '';

    // Only inject OAuth creds when they've been replaced by CI (i.e. not the
    // placeholder strings). In dev mode the server reads them from .env instead.
    const isRealId = BUNDLED_CLIENT_ID && !BUNDLED_CLIENT_ID.startsWith('__');
    const isRealSecret = BUNDLED_CLIENT_SECRET && !BUNDLED_CLIENT_SECRET.startsWith('__');
    const oauthEnv = isRealId && isRealSecret ? {
      GITHUB_CLIENT_ID: BUNDLED_CLIENT_ID,
      GITHUB_CLIENT_SECRET: BUNDLED_CLIENT_SECRET,
    } : {};

    if (binaryPath) {
      proc = spawn(binaryPath, [], {
        windowsHide: true,
        env: { ...process.env, ...oauthEnv, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
      });
    } else {
      // Development: use the system Python in the venv
      const pythonExe = process.platform === 'win32' ? 'python' : 'python3';
      const repoRoot = path.join(__dirname, '..');
      proc = spawn(pythonExe, ['-m', 'talon.server_entry'], {
        cwd: repoRoot,
        windowsHide: true,
        env: { ...process.env, ...oauthEnv, PYTHONPATH: repoRoot, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
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
      // Mirror server output to the Electron console in dev mode so progress
      // is visible without needing to run the server in a separate terminal.
      if (!app.isPackaged) {
        process.stdout.write(`[server] ${text}`);
      }
    });

    proc.stderr.on('data', (data) => {
      const text = data.toString();
      // Accumulate stderr so it can be shown in the error dialog on failure.
      stderrBuffer += text;
      if (stderrBuffer.length > 4000) stderrBuffer = stderrBuffer.slice(-4000);
      if (!app.isPackaged) {
        process.stderr.write(`[server] ${text}`);
      }
    });

    proc.on('error', (err) => {
      reject(new Error(`Failed to start Python server: ${err.message}`));
    });

    proc.on('exit', (code) => {
      if (serverPort === null) {
        const detail = stderrBuffer.trim() ? `\n\nServer output:\n${stderrBuffer.trim()}` : '';
        reject(new Error(`Python server exited before announcing port (code ${code})${detail}`));
      }
    });

    // Timeout if the server never announces a port (e.g. import error)
    setTimeout(() => {
      if (serverPort === null) {
        const detail = stderrBuffer.trim() ? `\n\nServer output:\n${stderrBuffer.trim()}` : '';
        reject(new Error(`Timed out waiting for Python server to start (30 s)${detail}`));
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

// Register talon:// as a custom protocol (needed on all platforms).
// In dev mode (process.defaultApp === true) Electron is invoked as
// `electron <app-path>`, so we must pass the app path explicitly;
// otherwise the OS launches a second instance with the deep-link URL as
// argv[1], which Electron tries to require() as an entry point.
if (process.defaultApp && process.argv.length >= 2) {
  app.setAsDefaultProtocolClient('talon', process.execPath, [path.resolve(process.argv[1])]);
} else {
  app.setAsDefaultProtocolClient('talon');
}

// ---------------------------------------------------------------------------
// IPC — open a URL in the system browser (shell must run in main process)
// ---------------------------------------------------------------------------
ipcMain.handle('open-external', (_event, url) => shell.openExternal(url));

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
