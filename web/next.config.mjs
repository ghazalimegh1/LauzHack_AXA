import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

// `npm run build` writes plain files to web/out, which the Python server (port 8000) serves.
// `npm run dev` (port 3000) is only for editing the design: it forwards /api to port 8000.
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
  return { output: "export", images: { unoptimized: true }, eslint: { ignoreDuringBuilds: true } };
}
