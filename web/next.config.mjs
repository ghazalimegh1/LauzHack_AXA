import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";   // ".js" is required in an .mjs file

// Two ways to run the website:
// - Normal / demo: `npm run build` writes plain HTML, CSS and JS to web/out/, and the
//   FastAPI server (server.py) hands those files out. One program, one port (8000).
// - Editing the design: `npm run dev` (port 3000) reloads on every save; it forwards
//   /api/... to the FastAPI server on port 8000, which must be running too.
export default function config(phase) {
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      async rewrites() {
        return [
          { source: "/api/:path*", destination: "http://localhost:8000/api/:path*" },
          { source: "/demo.html", destination: "/demo" },
        ];
      },
    };
  }
  return {
    output: "export",                    // plain files, no Node server needed at demo time
    eslint: { ignoreDuringBuilds: true }, // no linter installed: keep the build quiet and fast
  };
}
