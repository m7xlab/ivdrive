## 📋 Summary

Ship the public marketing surface for iVDrive without changing self-host UX. Adds an optional landing image (static Next.js + Caddy) and Docusaurus docs so newcomers understand the product before signing in, while mobile and signed-in users still reach the console directly.

- Marketing site: home, features, roadmap (2026–2028 VW Group EV plan), sponsors, about, open source, community
- Caddy dual-routing on `/`: desktop guest → landing; auth cookie / mobile UA → app; crawlers → landing
- `docker-compose.landing.yml` overlay; self-host `docker compose up` alone is unchanged (console at `/`)
- User documentation under `documentation/` served at `/docs/`
- Fresh product screenshots and GitHub issue-forms / funding / PR template refresh
- Deploy runbook uses placeholders only (no internal host/path data)

---

## 🧩 Type of Change

- [ ] Bug fix
- [x] Feature
- [x] Documentation / marketing
- [ ] Refactor / chore
- [ ] Breaking change

---

## Checklist

- [x] I have tested locally (`docker compose` or frontend/backend dev)
- [x] UI changes include screenshots (light + dark when relevant)
- [x] Docs updated if behaviour or setup changed
- [x] No secrets / tokens / full VINs in the diff

---

## Screenshots

Product UI shots live in `assets/screenshots/` and `landing/public/marketing/` (dashboard, charging curve, battery SoH, light + dark). Landing was visually QA'd at desktop and mobile widths.

---

## Related Issues

Public roadmap / marketing surface for the upcoming release. No issue number.
