'use strict';

const { contextBridge, shell } = require('electron');

// Expose a minimal surface to the renderer (the React app).
// The app communicates almost entirely through the local HTTP/WS server,
// but this bridge lets the frontend open external URLs natively (e.g. the
// GitHub OAuth browser window) rather than inside the Electron frame.
contextBridge.exposeInMainWorld('talon', {
  openExternal: (url) => shell.openExternal(url),
  platform: process.platform,
});
