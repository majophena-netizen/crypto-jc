// pm2 ecosystem for the BTC/USDT trader.
// Usage:
//   pm2 start ecosystem.config.cjs
//   pm2 save
//   pm2 startup   (one-time, to auto-start on reboot)
module.exports = {
  apps: [
    {
      name: "trader-backend",
      cwd: "/root/opus/backend",
      // Use the venv's Python as the interpreter so pm2 doesn't try to
      // load uvicorn as a Node module. pm2 requires an absolute path here.
      interpreter: "/root/opus/backend/.venv/bin/python",
      script: "/root/opus/backend/.venv/bin/uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8000",
      env: {
        PYTHONUNBUFFERED: "1",
      },
      out_file: "/root/.pm2/logs/trader-backend.out.log",
      error_file: "/root/.pm2/logs/trader-backend.err.log",
      max_restarts: 10,
      restart_delay: 5000,
    },
    {
      name: "trader-frontend",
      cwd: "./frontend",
      script: "node_modules/next/dist/bin/next",
      args: "start -H 0.0.0.0 -p 3001",
      env: {
        NODE_ENV: "production",
      },
      out_file: "/root/.pm2/logs/trader-frontend.out.log",
      error_file: "/root/.pm2/logs/trader-frontend.err.log",
      max_restarts: 10,
      restart_delay: 5000,
    },
  ],
};
