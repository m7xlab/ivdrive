import type { NextConfig } from "next";

const nextConfig = {
  output: "standalone",
  eslint: { ignore: true },
  typescript: { ignoreBuildErrors: true },
  images: {
    unoptimized: true,
  },
  // Reduce "Failed to find Server Action" after redeploy: don't cache HTML so clients get fresh action IDs.
  // Security headers (address Nuclei "http-missing-security-headers" findings).
  async headers() {
    const securityHeaders = [
      { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains; preload" },
      { key: "X-Frame-Options", value: "SAMEORIGIN" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(self)" },
      { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
      { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
      { key: "Cross-Origin-Embedder-Policy", value: "unsafe-none" },
    ];
    const cacheNoStore = { key: "Cache-Control", value: "no-store, must-revalidate" };
    return [
      { source: "/:path*", headers: [...securityHeaders, cacheNoStore] },
    ];
  },
  // Proxy /api/* to the backend (ivdrive-api in Docker; use localhost when running frontend on host)
  async rewrites() {
    const apiTarget =
      process.env.NEXT_PUBLIC_API_INTERNAL ?? "http://ivdrive-api:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
