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
    // v1.1.3 security/csp-header: Content-Security-Policy. Build-time computed so the
    // analytics host is included only when SITE_ANALYTICS_URL is configured.
    // Directives:
    //   default-src 'self'                         — baseline
    //   script-src 'self' 'unsafe-inline' + analytics — Next.js RSC streaming emits inline
    //                                              __next_f.push() scripts in production.
    //                                              'unsafe-inline' is unfortunately required by Next.js 16
    //                                              unless we move to nonce-based CSP (separate pass).
    //                                              Map tile domains (unpkg, cartocdn) belong ONLY in
    //                                              img-src — they serve image assets, never JS.
    //                                              Allowing arbitrary scripts from those CDNs would
    //                                              escalate any XSS into a full CDN-level hijack.
    //                                              (PR Agent #163 finding.)
    //   style-src 'self' 'unsafe-inline' + gfont CSS — Inter from Google Fonts
    //   img-src 'self' data: blob: + maps tiles      — CARTO basemap tiles + Leaflet marker icons (unpkg)
    //   font-src 'self' data: + gstatic             — Inter font files
    //   connect-src 'self' + analytics host         — API calls via Next.js rewrites;
    //                                              analytics provider needs fetch/XHR for telemetry
    //                                              (PR Agent #163 finding — was previously blocked).
    //   frame-ancestors 'self'                       — matches X-Frame-Options: SAMEORIGIN
    //   form-action 'self' base-uri 'self'           — defense in depth
    //   object-src 'none'                            — block Flash/PDF plugins
    const analyticsHost = (() => {
      try {
        return process.env.SITE_ANALYTICS_URL ? new URL(process.env.SITE_ANALYTICS_URL).origin : "";
      } catch {
        return "";
      }
    })();
    const scriptSrc = [
      "'self'",
      "'unsafe-inline'",
      ...(analyticsHost ? [analyticsHost] : []),
    ].join(" ");
    const connectSrc = [
      "'self'",
      ...(analyticsHost ? [analyticsHost] : []),
    ].join(" ");
    const csp = [
      `default-src 'self'`,
      `script-src ${scriptSrc}`,
      `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`,
      `img-src 'self' data: blob: https://*.basemaps.cartocdn.com https://unpkg.com`,
      `font-src 'self' data: https://fonts.gstatic.com`,
      `connect-src ${connectSrc}`,
      `frame-ancestors 'self'`,
      `form-action 'self'`,
      `base-uri 'self'`,
      `object-src 'none'`,
    ].join("; ");
    const cacheNoStore = { key: "Cache-Control", value: "no-store, must-revalidate" };
    return [
      { source: "/:path*", headers: [...securityHeaders, { key: "Content-Security-Policy", value: csp }, cacheNoStore] },
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
