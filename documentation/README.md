# iVDrive documentation site

User-facing documentation built with [Docusaurus](https://docusaurus.io).

## Develop

```bash
npm install
npm start          # http://localhost:3000 (dev)
npm run build      # static export to ./build
npm run serve      # preview production build
```

## Content map

| Section | Path |
|---------|------|
| Introduction | `docs/intro.mdx` |
| Getting started | `docs/getting-started/` |
| User guide | `docs/user-guide/` |
| Self-hosting | `docs/self-hosting/` |
| Reference | `docs/reference/` |
| Community | `docs/community/` |

## Deploy

Serve `build/` from any static host (GitHub Pages, nginx, Caddy, Netlify, …).

Suggested production URL: `https://docs.ivdrive.eu` (update `docusaurus.config.ts` `url` if needed).

Link it from the marketing site navbar (Docs → GitHub or this site).
