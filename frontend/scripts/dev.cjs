const { spawn } = require("child_process");
const electron = require("electron");

async function run() {
  const { createServer } = await import("vite");
  const vite = await createServer({
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
    },
  });
  await vite.listen();
  vite.printUrls();

  const address = vite.httpServer.address();
  const port = typeof address === "object" ? address.port : 5173;
  const devServerUrl = `http://127.0.0.1:${port}`;

  const electronProcess = spawn(electron, ["."], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      VITE_DEV_SERVER_URL: devServerUrl,
    },
    stdio: "inherit",
  });

  electronProcess.on("exit", async (code) => {
    await vite.close();
    process.exit(code ?? 0);
  });
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
