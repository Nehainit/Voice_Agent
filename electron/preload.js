const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("codeDuck", {
  getConfig: () => ipcRenderer.invoke("app:getConfig"),
  captureSelection: () => ipcRenderer.invoke("selection:capture"),
  chooseProjectRoot: () => ipcRenderer.invoke("project:chooseRoot"),
  applyReplacement: (proposedCode) => ipcRenderer.invoke("patch:applyReplacement", proposedCode),
  writeClipboardText: (text) => ipcRenderer.invoke("clipboard:writeText", text),
  pasteText: (text) => ipcRenderer.invoke("clipboard:pasteText", text),
  resizeWindow: (size) => ipcRenderer.invoke("window:resize", size),
  closePanel: () => ipcRenderer.invoke("window:closePanel"),
  quitApp: () => ipcRenderer.invoke("window:quitApp"),
  openMainWindow: () => ipcRenderer.invoke("window:openMain"),
  updatePresence: (presence) => ipcRenderer.invoke("presence:update", presence),
  onPresence: (callback) => {
    const listener = (_event, presence) => callback(presence);
    ipcRenderer.on("presence:updated", listener);
    return () => ipcRenderer.removeListener("presence:updated", listener);
  },
  onShortcut: (callback) => {
    const listener = (_event, context) => callback(context);
    ipcRenderer.on("shortcut:triggered", listener);
    return () => ipcRenderer.removeListener("shortcut:triggered", listener);
  },
});
