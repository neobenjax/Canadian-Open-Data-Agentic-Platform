# CAN-53: Hosted Demo and Documentation Portal Deployment (Polish & Alignment)

**Task Key:** `CAN-53` (Linear: `BEN-53` / Sprint 5 Milestone 5)  
**Owners:** Benjamin Sanchez Zebadua (Lead) / Yassir Tagelsir Khougali  
**Status:** In Progress (Fumadocs UI & Design System Alignment Revision)  
**Deliverable:** High-grade Fumadocs polish, Next.js 16.4.6 migration, Canadian Open Data design system tokens, floating sidebar docs layout, favicon resolution, and zero-error Vercel/Streamlit hosting.

---

## 📋 Activities & Implementation Checklist

### Phase 1: Core Framework & Asset Fixes
- [x] **Activity 1.1:** Upgrade Next.js to `16.4.6` in `apps/docs-portal/package.json` and lockfile.
- [ ] **Activity 1.2:** Generate and stage `favicon.ico` and `icon.svg` in `apps/docs-portal/app/` and `apps/docs-portal/public/` to resolve 404 console errors.
- [ ] **Activity 1.3:** Eliminate top white bar artifact by resetting `html, body` margins, borders, and ensuring navbar sits flush at `top: 0`.

### Phase 2: Design System & Styling Alignment
- [ ] **Activity 2.1:** Import Fumadocs UI stylesheet (`import 'fumadocs-ui/style.css'`) in root layout.
- [ ] **Activity 2.2:** Align theme tokens in `globals.css` with Canadian Open Data design system (`--color-primary: #D80621`, warm light paper `#FDFCFB` / `#F9F6F6` background, crisp dark mode `#0B0F19`, subtle neutral borders).
- [ ] **Activity 2.3:** Remove non-standard Deep Navy overrides across all pages in favor of design system tokens.

### Phase 3: High-Grade Fumadocs Docs Page (`apps/docs-portal/app/docs`)
- [ ] **Activity 3.1:** Refactor `apps/docs-portal/app/docs/layout.tsx` to use native `DocsLayout` from `fumadocs-ui/layouts/docs` with `tree={source.pageTree}`, floating sidebar, search bar, and collapsible navigation.
- [ ] **Activity 3.2:** Refactor `apps/docs-portal/app/docs/[[...slug]]/page.tsx` to use `DocsPage`, `DocsTitle`, `DocsDescription`, `DocsBody`, and right-hand Table of Contents (`On this page`).
- [ ] **Activity 3.3:** Polish MDX component styles (Cards, Callouts, Code blocks with syntax highlighting and copy buttons).

### Phase 4: Fumadocs.dev-Inspired Landing Page & Animations (`apps/docs-portal/app/(home)`)
- [ ] **Activity 4.1:** Re-architect homepage layout inspired by `fumadocs.dev` (Screenshot 5): clean typography, quickstart install command pill (`$ uv run candata-mcp` with copy button), and dual action buttons.
- [ ] **Activity 4.2:** Add subtle CSS animations (floating animated civic data illustration, animated gradient shimmer, and tab transitions).
- [ ] **Activity 4.3:** Rebuild Bento feature grid using design system card styles and interactive hover transitions.

### Phase 5: Verification & Walkthrough
- [ ] **Activity 5.1:** Execute `npm run build` in `apps/docs-portal` with Next.js 16.4.6 asserting 0 errors.
- [ ] **Activity 5.2:** Run full test suite (`uv run pytest tests/test_hosted_deployment.py`, `uv run ruff check .`, `uv run pyright`).
- [ ] **Activity 5.3:** Author comprehensive walkthrough guide with side-by-side screenshots and manual verification steps.
