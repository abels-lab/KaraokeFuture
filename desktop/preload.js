const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("karaokeDesktop", {
  isDesktop: true,
  openProjector: () => ipcRenderer.invoke("open-projector"),
  toggleFullscreen: () => ipcRenderer.invoke("toggle-fullscreen")
});
