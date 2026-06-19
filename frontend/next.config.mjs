/** @type {import('next').NextConfig} */
const nextConfig = {
  // PersonalTutor's backend is DeepTutor's FastAPI server (default :8001).
  // Rewrites keep the frontend calling same-origin /api/* so CORS is a non-issue
  // in dev; point DEEPTUTOR_API at a different host in production.
  async rewrites() {
    const target = process.env.DEEPTUTOR_API || "http://localhost:8001";
    return [
      // DeepTutor native API (chat, memory, knowledge, sessions, ...)
      { source: "/api/v1/:path*", destination: `${target}/api/v1/:path*` },
      // DeepTutor auth + attachments (non-versioned prefixes)
      { source: "/api/auth/:path*", destination: `${target}/api/auth/:path*` },
      { source: "/api/attachments/:path*", destination: `${target}/api/attachments/:path*` },
    ];
  },
};

export default nextConfig;
