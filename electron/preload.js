'use strict';

const { contextBridge, ipcRenderer } = require('electron');

// Expose a minimal surface to the renderer (the React app).
// The app communicates almost entirely through the local HTTP/WS server,
// but this bridge lets the frontend open external URLs natively (e.g. the
// GitHub OAuth browser window) rather than inside the Electron frame.
// shell.openExternal must be called from the main process via IPC.
contextBridge.exposeInMainWorld('talon', {
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  platform: process.platform,
});
