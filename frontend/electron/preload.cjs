const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("xiaoAnDesktop", {
  platform: process.platform,
});
