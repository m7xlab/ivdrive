/**
 * Centralized CARTO Basemaps tile URL builder.
 *
 * CARTO Basemaps now require an API key for public tile access (CARTO gated
 * the public service). Without a key, every tile returns 401 and the "API
 * key required" watermark shows on every map in the app.
 *
 * Get a free key at https://carto.com/basemaps/apikey/ — no approval queue,
 * no CARTO account required.
 *
 * The `NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY` env var is inlined into the client
 * bundle at build time by Next.js, so it must also be passed via `build.args`
 * in docker-compose.yml + `ARG`/`ENV` in the frontend Dockerfile builder
 * stage. See PR #181 for the full build-args wiring.
 *
 * Returns a tile URL suitable for Leaflet `TileLayer.url`.
 *
 * @param isDark - whether to use the dark theme variant
 * @returns the tile URL with optional `?key=***` query param appended
 */
export function getCartoTileUrl(isDark: boolean): string {
  const key = process.env.NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY;
  const theme = isDark ? "dark_all" : "light_all";
  const keySuffix = key ? `?key=***}` : "";
  return `https://{s}.basemaps.cartocdn.com/${theme}/{z}/{x}/{y}{r}.png${keySuffix}`;
}
