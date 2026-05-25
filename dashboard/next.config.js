/** @type {import('next').NextConfig} */
// Backend URL is configurable so the dashboard can be deployed (e.g. Vercel)
// pointing at a hosted backend. Defaults to localhost for local dev.
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};
module.exports = nextConfig;
