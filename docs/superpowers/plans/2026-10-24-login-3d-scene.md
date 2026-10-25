# Login 3D Scene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a clean asset-first login hero to `/login` while preserving auth behavior,
accessibility and responsive fallback rules.

## Direction change (25.10.2026)

The procedural R3F scene is removed from the login hero. The approved direction is
an asset-first decorative backdrop: one clean PNG/WebP without text, logos, fields,
buttons or authorization UI, plus a restrained CSS light sweep. No new cubes,
procedural geometry, WebGL, canvas or generated crop of the supplied screenshot is
allowed. The current repository does not contain the required clean asset:
`frontend/public/brand/login-hero.png` contains cropped text and is therefore not
used as a background. The implementation consumes
`/brand/login-hero-background.png`; until that asset is supplied, it deliberately
shows a neutral fallback and keeps the form fully functional.

## User-approved corrections (25.10.2026)

- The first deliverable is a **static 3D composition** matching the approved login
  screenshot as closely as practical. Geometry, camera, materials, lighting and
  composition must be reviewed before any animation code is enabled.
- Object count is secondary. The composition prioritizes broad light metallic
  surfaces, the characteristic perspective and orange emissive seams; it does not
  require a literal grid of identical low-poly blocks.
- `Suspense` only covers loading. A separate React Error Boundary catches lazy
  import and render failures and permanently disables the scene for the current
  login mount.
- WebGL initialization failure and `webglcontextlost` are terminal for that mount:
  no retry loop or automatic remount may occur.
- The later animation slice must use a React Three Fiber-compatible frame gate at
  approximately 30 FPS and pause while `document.visibilityState` is hidden.
  Cursor response must be inertial, capped to a 1–2 degree perspective change, and
  sampled without capturing form pointer events.
- The fallback PNG must contain no fields, buttons or text. If the supplied asset
  is not a clean decorative background, the implementation uses a neutral
  background and records that limitation rather than presenting a fake form.
- PNG remains visible until the first successful 3D frame is confirmed, then fades
  without a layout or interface flash. Any scene, WebGL or JavaScript failure keeps
  the HTML authorization form fully usable.
- Existing security, performance, accessibility, backend isolation, cookie/CSRF,
  and no-runtime-font/CDN constraints remain unchanged.

**Architecture:** `Login.tsx` owns the decorative shell and keeps the auth form
independent HTML. `LoginHeroBackdrop.tsx` loads one clean PNG/WebP and applies a
CSS-only light sweep. A missing or invalid asset leaves a neutral background; no
procedural scene, WebGL canvas or screenshot crop is used.

**Tech Stack:** React 19, TypeScript, Vite, CSS animation, Vitest/jsdom, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-24-login-3d-scene-design.md`

## Global Constraints

- The decorative asset is shown only on the desktop layout; narrow/touch layouts keep the form fully usable.
- No WebGL, canvas, HDRI, postprocessing, physics or procedural geometry is used.
- The image and sweep are decorative (`aria-hidden="true"`, no focus, no pointer interception); the form and auth contracts do not change.
- Original logos remain; no CDN, runtime font loading, backend, database, migration, `.env`, volume, or secret changes.
- On asset load or render failure, keep the neutral background without exposing sensitive data.

## Review Focus

- Narrow/touch viewport must never mount WebGL — test the `1280px` boundary and `pointer: coarse` fallback in `frontend/src/test/login-hero.test.tsx`.
- Reduced-motion users must keep the PNG and form usable — test media-query fallback in `frontend/src/test/login-hero.test.tsx`.
- WebGL context loss must restore the PNG and permanently disable retries for that mount — test the scene callback/Error Boundary in `frontend/src/test/login-hero.test.tsx`.
- Lazy chunk failure must not block login — test the Suspense fallback and submit path in `frontend/src/test/app.test.tsx`.
- Canvas must not capture input — test keyboard focus and form submission in the existing login tests and Playwright flow.

### Task 1: Asset boundary

**Files:**
- Modify: `frontend/src/components/LoginHeroBackdrop.tsx`
- Add: `docs/LOGIN-HERO-ASSET.md`
- Test: `frontend/src/test/login-hero.test.tsx`

**Interfaces:**
- Produces an asset-only decorative backdrop with neutral fallback and no form content.

- [ ] **Step 1: Write failing capability tests** for `1280` desktop/no-preference/WebGL true, `1279`, coarse pointer, reduced motion, and missing WebGL false.
- [ ] **Step 2: Run `node_modules\\.bin\\vitest.cmd run src/test/login-hero.test.tsx` and verify the expected failures.**
- [ ] **Step 3: Add pinned compatible `three` and `@react-three/fiber` dependencies and implement the pure capability predicate.** Keep browser feature detection outside the predicate so jsdom tests remain deterministic.
- [ ] **Step 4: Re-run the focused test and confirm all capability cases pass.**

### Task 2: Static visual prototype (current slice)

**Files:**
- Create: `frontend/src/components/LoginHeroScene.tsx`
- Create: `frontend/src/components/LoginHeroErrorBoundary.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/test/login-hero.test.tsx`

**Interfaces:**
- Consumes `onFallback: () => void` and `enabled: boolean`.
- Produces a static decorative `LoginHeroScene` component with no auth/data props and a `LoginHeroErrorBoundary` that permanently disables the scene after an error.

- [ ] **Step 1: Add failing component tests** asserting the static composition has an aria-hidden canvas, no pointer interception, no animation loop, and `onFallback` on a simulated context-loss event. Add Error Boundary tests showing a thrown render error falls back to PNG and does not retry.
- [ ] **Step 2: Run the focused test and verify it fails because the component does not exist.**
- [ ] **Step 3: Implement the static composition first: large light metallic planes/blocks, the reference perspective, orange emissive seams, and soft lighting. Do not add animation, pointer handlers, or a render loop. Handle `webglcontextlost` by calling `onFallback`, preventing default, and marking the scene failed so it cannot remount in the same login view.**
- [ ] **Step 4: Implement `LoginHeroErrorBoundary` with a one-way failed state and a PNG fallback. It must catch lazy import and render errors separately from Suspense.**
- [ ] **Step 5: Add CSS positioning for the canvas and preserve the PNG beneath it. Confirm the PNG contains no form fields, buttons, or text; if it is not a clean background, retain it only as a neutral decorative fallback and report that limitation.**
- [ ] **Step 6: Re-run focused tests and TypeScript.**
- [ ] **Step 7: Stop at the visual review gate. Run the static prototype in a
  browser at 2560x1440, 1366x768, 768x1024 and 390x844; show the result and launch
  instructions. Do not implement animation until the user approves geometry,
  camera, materials and lighting.**

### Task 3: Static prototype integration and visual review gate

**Files:**
- Modify: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/test/app.test.tsx`
- Test: `frontend/src/test/login-hero.test.tsx`

**Interfaces:**
- Consumes `shouldUseLoginHero`, `LoginHeroScene`, and `LoginHeroErrorBoundary` from Tasks 1–2.
- Produces a PNG-first login view that fades to the first confirmed successful static 3D frame without changing auth behavior.

- [ ] **Step 1: Add failing integration tests** for PNG-first rendering, desktop eligibility, Error Boundary fallback, first-frame readiness, and unchanged `login()` submission.
- [ ] **Step 2: Run focused tests and verify the failures are about missing static integration.**
- [ ] **Step 3: Add media/capability state in the left panel, lazy-load the static scene, keep PNG visible until `onReady` confirms the first frame, and transition opacity without a flash. On callback or import/render error, disable the scene for that mount and leave PNG active.**
- [ ] **Step 4: Re-run frontend tests and format changed files.**

### Task 4: Delicate image-light animation

**Files:**
- Modify: `frontend/src/components/LoginHeroBackdrop.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/test/login-hero.test.tsx`

**Interfaces:**
- Consumes the approved static composition from Task 2 and the integration gate from Task 3.
- Produces optional animation enabled only after the user approves the static prototype.

- [ ] **Step 1: Add failing tests** for an actual ~30 FPS scheduler, visibility pause/resume, bounded inertial cursor perspective change of 1–2 degrees, and no pointer interception by the canvas.
- [ ] **Step 2: Run the focused tests and verify they fail because animation is not yet implemented.**
- [x] **Step 3: Implement a very slow CSS light sweep over the image, disabled by
  `prefers-reduced-motion`, without pointer interception or geometry movement.**
- [ ] **Step 4: Re-run focused tests and verify performance guards.**

### Task 3: Login integration and static fallback

**Files:**
- Modify: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/test/app.test.tsx`
- Test: `frontend/src/test/login-hero.test.tsx`

**Interfaces:**
- Consumes `shouldUseLoginHero` and `LoginHeroScene` from Tasks 1–2.
- Produces the existing login form behavior with a lazy scene that can fall back to PNG.

- [ ] **Step 1: Add failing integration tests** for PNG-first rendering, desktop lazy scene eligibility, fallback after scene failure, and unchanged `login()` submission.
- [ ] **Step 2: Run focused tests and verify the failures are about the missing lazy integration.**
- [ ] **Step 3: Add media/capability state in the left panel, lazy-load the scene, and keep the PNG visible until the scene is ready. On callback or import error, disable the scene and leave PNG active. Do not alter form fields, labels, error handling, or auth calls.**
- [ ] **Step 4: Re-run frontend tests and format changed files.**

### Task 5: Browser and build verification

**Files:**
- Modify: `frontend/e2e/stage3.spec.ts` only if a focused login visual/behavior assertion is needed.

- [ ] **Step 1: Run `node_modules\\.bin\\tsc.cmd -b` and `node_modules\\.bin\\prettier.cmd --check src/components/LoginHeroScene.tsx src/features/login/loginHeroCapability.ts src/pages/Login.tsx src/styles.css`.**
- [ ] **Step 2: Run `node_modules\\.bin\\vitest.cmd run` and record any environment-level `spawn EPERM` limitation without changing dependencies to work around it.**
- [ ] **Step 3: Run the Vite build if local dependencies are available; otherwise report the exact blocked command.**
- [ ] **Step 4: Before Task 4 animation, run the static prototype in a browser at `2560x1440`, `1366x768`, `768x1024`, and `390x844`; verify geometry/camera/materials/lighting, form usability, and PNG fallback. Stop and show the prototype plus launch instructions for user review.**
- [ ] **Step 5: Only after explicit visual approval, run animation tests and then the full browser/build checks.**
- [ ] **Step 6: Run `git diff --check`, inspect the diff, and update `PROGRESS.md` only with a concise design-slice note that preserves existing changes.**
