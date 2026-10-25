# Warehouse Catalog Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить адаптивные представления карточками, компактным списком и таблицей в существующий складской каталог.

**Architecture:** `Catalog` сохраняет единственный набор данных и бизнес-состояния. Отдельные компоненты отвечают за переключатель и отображение одного и того же массива позиций. Черновик выдачи остаётся единственной корзиной и управляется `useDraft('issue')`.

**Tech Stack:** React, TypeScript, Tailwind CSS, React Router, lucide-react, Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-23-warehouse-catalog-views-design.md`

## Global Constraints

- Без изменений БД, миграций, `.env`, volumes, рабочего стенда, backend и deploy-конфигурации.
- Не добавлять зависимости и не создавать отдельное состояние корзины.
- Сохранять permissions `inventory.read` и `inventory.issue`.
- Добавление в черновик не изменяет складской остаток.

## Review Focus

- Повреждённое или отсутствующее значение режима в `localStorage`: использовать безопасный режим карточек.
- Отсутствующее/небезопасное фото: показать нейтральную заглушку без внешней подстановки.
- Нет permission `inventory.issue`: не показывать действия добавления или ссылку на корзину.
- Повторное добавление той же позиции: применять существующее увеличение количества, не создавать новую корзину.
- Узкий экран и длинное название: не создавать переполнение, сохранить доступность полного названия.

---

### Task 1: Presentation components and mode persistence

**Files:**
- Create: `frontend/src/features/inventory/CatalogView.tsx`
- Modify: `frontend/src/features/inventory/Catalog.tsx`
- Test: `frontend/src/test/catalog.test.tsx`

**Interfaces:** `CatalogView` receives current `InventoryItem[]`, mode, `onAdd`, and disabled state. `Catalog` remains responsible for fetched data, query state and filters.

- [x] Add tests for three modes, default card mode, persistence, and unchanged search/filter values.
- [x] Run focused Vitest test; expected new assertions failed before implementation (sandbox initially blocked spawn; rerun outside sandbox reached assertions).
- [x] Implement keyboard-accessible Lucide mode selector and three layouts, with cards as default and neutral photo fallback.
- [x] Run focused tests and confirm all view assertions pass (8/8).

### Task 2: Basket path and permissions

**Files:**
- Modify: `frontend/src/pages/Inventory.tsx`
- Modify: `frontend/src/test/catalog.test.tsx`

**Interfaces:** use existing `useDraft('issue')`; basket count is line count and link target is `/issues`.

- [x] Add tests for add notification/link, basket persistence across mode changes, repeated add, and permissions.
- [x] Run focused tests; initial assertions exposed notification and duplicate basket link issues.
- [x] Implement sticky basket access and notification action without changing draft or stock semantics.
- [x] Run focused tests (8/8); adding an item updates the existing issue draft without issue-post API calls.

### Task 3: Full verification and progress

**Files:**
- Modify: `PROGRESS.md`

- [x] Run targeted catalog tests (8/8) and full Vitest (45/45, 6 files) outside sandbox.
- [x] Run frontend production build, TypeScript, Prettier and `git diff --check`.
- [x] Record results and remaining manual responsive/browser checks in `PROGRESS.md`.
- [x] Inspect `git diff`; no DB, migration, `.env`, Docker or deploy files changed.
