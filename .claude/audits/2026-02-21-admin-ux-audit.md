# Admin UX Audit — SeeSee Email

Date: 2026-02-21
Scope: admin-only
Audited by: Claude
Project type: Self-Hosted Developer Tool

---

## Stack Summary

SeeSee is a lightweight, self-hosted email log aggregator built with **Python 3.12+** and **FastAPI**. The admin UI is **server-side rendered** using **Jinja2** templates with **Tailwind CSS** (CDN) for styling and **Alpine.js** (CDN) for client-side interactivity. A small vanilla JS file (`app.js`) handles clipboard operations, keyboard shortcuts, and relative timestamp formatting. CSS custom properties power a theming system with accent/paper color tokens. Dark mode is supported via Tailwind's `class` strategy. Package management uses pip with `pyproject.toml` (setuptools).

---

## User Tiers

| Tier | Present? | Notes |
|------|----------|-------|
| Public/guest users | No | Everything behind login |
| Authenticated frontend users | No | Single-tier admin |
| Regular admin users | Yes | Single admin user via env vars |
| Super admin / system admin | Yes (same as admin) | No tier distinction |

All UI routes require session auth (`require_session`). API routes use HTTP Basic (`require_admin`) or Bearer token (`get_current_app`). This is an admin-only surface — no public-facing views exist.

---

## Admin Surface Map

| Route | Function | Data Density | Mobile Usability |
|-------|----------|-------------|-----------------|
| `GET /login` | Login form | Sparse | Good |
| `GET /` | Dashboard — stats cards, volume chart, status/app breakdown | Medium | Good |
| `GET /emails` | Email list — search, filters, pagination | Dense | Good (responsive column hiding) |
| `GET /emails/{id}` | Email detail — tabbed content (preview, HTML, text, metadata) | Dense | Good |
| `POST /emails/{id}/delete` | Delete single email | N/A (action) | Good |
| `POST /emails/bulk-delete` | Bulk delete by filter | N/A (action) | Good |
| `GET /apps` | App list — table with actions | Medium | Good |
| `POST /apps` | Create app (modal form) | Sparse | Good |
| `GET /apps/{id}` | App detail — stats, integration snippets, actions | Dense | Good |
| `POST /apps/{id}/rotate-key` | Rotate API key | N/A (action) | Good |
| `POST /apps/{id}/purge` | Purge app emails | N/A (action) | Good |
| `POST /apps/{id}/delete` | Delete app | N/A (action) | Good |
| `GET /settings` | Retention config (read-only), storage usage, manual cleanup | Medium | Good |
| `POST /settings/cleanup` | Run cleanup | N/A (action) | Good |
| `GET /docs` | Swagger API docs (FastAPI built-in) | Dense | Acceptable |

---

## Existing Design Infrastructure

- **Theme system**: CSS custom properties (`--color-accent`, `--color-paper`) in `style.css`, referenced via Tailwind config as `accent` and `paper` colors
- **Dark mode**: Fully supported via `class` strategy, toggled by Alpine.js, persisted to localStorage
- **Breakpoints**: Tailwind defaults — `sm:640px`, `md:768px`, `lg:1024px`, `xl:1280px`
- **Reusable patterns**: Copy button (icon swap + toast), code block copy, confirmation modals, toast notification system, relative timestamps with UTC tooltip — all consistently applied but not formal extracted components
- **Responsiveness**: Good overall — sidebar collapses to drawer, tables hide columns progressively, forms are full-width on mobile

---

## Phase 2 — Audit Checklist Results

### Navigation & Layout

| Item | Score | Notes |
|------|-------|-------|
| Nav accessible on mobile | ✅ Pass | Sidebar drawer with overlay, hamburger menu |
| No horizontal scroll at 375/768/1024px | ✅ Pass | `overflow-x-auto` on tables, responsive hiding |
| Page hierarchy legible | ✅ Pass | h1 on every page, consistent card structure |
| Sidebar shows active state | ✅ Pass | `current_page` variable drives accent highlight |
| Breadcrumbs / back navigation | ⚠️ Partial | Back links on detail pages but no breadcrumb trail |
| Footer doesn't obscure content | ✅ Pass | No fixed bottom elements |

### Tables & Data Lists

| Item | Score | Notes |
|------|-------|-------|
| Mobile strategy for tables | ✅ Pass | Progressive column hiding + horizontal scroll |
| Long text truncated with full value accessible | ⚠️ Partial | `truncate max-w-xs` applied but no tooltip for full value |
| Empty states | ✅ Pass | Well-designed on all list pages |
| Sortable columns visually indicated | ❌ Fail | Sort supported via URL params but headers not clickable, no indicators |
| Row actions usable on touch | ⚠️ Partial | Actions work but touch targets below 44px |
| Pagination implemented | ✅ Pass | Full pagination with page numbers |
| Filter/search controls accessible | ✅ Pass | Search bar + collapsible filter dropdowns |
| Active filters indicated and clearable | ✅ Pass | Badge count on filter button, "Clear all filters" link on empty state |

### Touch & Interaction

| Item | Score | Notes |
|------|-------|-------|
| 44px minimum touch targets | ⚠️ Partial | Most buttons ~36px tall (`py-2`); action icons ~32px; mobile hamburger ~32px |
| Tap targets have active feedback | ✅ Pass | `:active` states defined consistently |
| No hover-only functionality | ✅ Pass | Code copy buttons use `@media (hover: hover)` correctly |
| Hover states have touch alternatives | ✅ Pass | Pattern implemented properly |
| No swipe/gesture conflicts | ✅ Pass | No custom gestures |
| Pointer and touch coexist | ✅ Pass | `@media (hover: hover)` used correctly |

### Copy-to-Clipboard

| Item | Score | Notes |
|------|-------|-------|
| IDs, keys, tokens have click-to-copy | ⚠️ Partial | API keys, credentials, email addresses have copy. Missing: email ID, provider_message_id, SMTP settings |
| Long values copy full value | ✅ Pass | `break-all` on code blocks, copy reads full text |
| Visual confirmation on copy | ✅ Pass | Icon swap + toast |
| Web Share API on mobile | ➖ N/A | Developer tool — clipboard preferred |
| Code blocks have copy buttons | ✅ Pass | All integration snippets have copy |

### Forms & Inputs

| Item | Score | Notes |
|------|-------|-------|
| All inputs have `<label>` elements | ✅ Pass | Login and app creation forms have proper labels |
| Input types semantically correct | ⚠️ Partial | Login uses correct types; search input uses `type="text"` instead of `type="search"` |
| Font size 16px+ on inputs | ❌ Fail | All inputs use `text-sm` (14px) — causes iOS Safari auto-zoom on focus |
| Validation errors visible and field-adjacent | ⚠️ Partial | Login shows error banner; app creation relies only on browser `required` |
| Form submission has loading state | ⚠️ Partial | Cleanup button has spinner; login and app creation do not |
| Success confirmation shown | ✅ Pass | Toast notifications + flash messages |
| Destructive actions have confirmation | ✅ Pass | Modals for delete, rotate, purge — well-implemented |
| Required fields marked | ⚠️ Partial | `required` attribute present but no visual asterisk indicator |

### Visual Feedback & States

| Item | Score | Notes |
|------|-------|-------|
| Loading states for async | ⚠️ Partial | Cleanup has spinner; form submits don't show loading |
| Error states handled | ⚠️ Partial | Login shows error; other forms rely on browser validation |
| Success states acknowledged | ✅ Pass | Toast system works well |
| Empty states designed | ✅ Pass | Dashboard, emails, apps all have custom empty states |
| Disabled states distinct | ✅ Pass | `disabled:opacity-50 disabled:cursor-not-allowed` |
| Selected/active states distinct | ✅ Pass | Keyboard highlight ring, nav active styles |

### Typography & Readability

| Item | Score | Notes |
|------|-------|-------|
| Body text 14px+ | ⚠️ Partial | Most text is `text-sm` (14px) — acceptable but at minimum |
| Line length manageable | ✅ Pass | Cards and max-width constraints prevent runaway text |
| Monospace for codes/IDs | ✅ Pass | `<code>` elements styled appropriately |
| Text contrast WCAG AA | ✅ Pass | gray-900 on white, gray-100 on gray-900 |
| Readable in light and dark | ✅ Pass | Dark mode thoroughly implemented |

### Admin Convenience Features

| Item | Score | Notes |
|------|-------|-------|
| Keyboard shortcuts | ✅ Pass | `/` search, `j/k` navigate, `Enter` open, `?` help modal |
| Toast/notification system | ✅ Pass | Alpine.js toast manager with success/error types |
| Relative timestamps with tooltip | ✅ Pass | `data-timestamp` with local + UTC tooltip |
| Bulk actions | ⚠️ Partial | Bulk delete by filter criteria, but no checkbox select pattern |
| Filter state persists | ❌ Fail | URL params used for current page but not remembered across sessions |
| Clipboard for developer values | ✅ Pass | Extensive copy support on keys, credentials, addresses |
| Search with debounce | ➖ N/A | Form-submit model, no real-time search |

---

## Critical Issues (Fix First)

### 1. iOS Safari auto-zoom on form inputs

- **Where:** `/login`, `/emails` (search), `/apps` (create modal)
- **What:** All `<input>` and `<select>` elements use Tailwind's `text-sm` class (14px font-size). iOS Safari auto-zooms the viewport when an input with font-size less than 16px receives focus.
- **Why it matters:** On iPhone, tapping any input field zooms in and the page doesn't zoom back out, requiring the user to manually pinch-to-zoom. This makes the entire admin UI frustrating to use on iOS. Since iOS is the dominant mobile browser, this is a critical mobile usability issue.
- **Fix:** Add a custom Tailwind utility or override in `style.css` to ensure all form controls render at 16px:
  ```css
  input, select, textarea {
      font-size: 16px !important;
  }
  /* Or more targeted with Tailwind: replace text-sm with text-base on form controls */
  ```
  Alternatively, add `text-base` (16px) to all `<input>` and `<select>` elements in templates while keeping `text-sm` for surrounding label text.
- **Effort:** Low

### 2. Sortable columns not indicated or interactive

- **Where:** `/emails` table, `/apps` table
- **What:** The email list supports sorting by `logged_at`, `created_at`, and `subject` via URL parameters, but column headers are plain text with no visual indicator of sort capability, current sort column, or sort direction. Users cannot click headers to sort.
- **Why it matters:** In a data-heavy email log viewer, sorting is a core interaction. Users who don't know about the URL parameter hack have no access to this feature. This is the primary "scanning and finding information quickly" interaction for the product.
- **Fix:** Make table header cells clickable links that toggle sort direction. Add a directional arrow indicator (chevron up/down) on the active sort column. Example:
  ```html
  <th>
    <a href="/emails?sort=logged_at&order={{ 'asc' if sort == 'logged_at' and order == 'desc' else 'desc' }}&...">
      Date
      {% if sort == 'logged_at' %}
      <svg ...><!-- up or down chevron --></svg>
      {% endif %}
    </a>
  </th>
  ```
- **Effort:** Low

---

## Moderate Issues

### 3. Mobile touch targets below 44px minimum

- **Where:** All pages — buttons, nav links, action icons
- **What:** Most interactive elements use `py-2` (8px padding) + 14px text = ~36px height. Table action icon buttons (rotate, delete in apps table) are ~32px. The mobile hamburger menu button uses `p-1` (4px) + 24px icon = ~32px. The sidebar close button is ~28px.
- **Why it matters:** Apple's HIG specifies 44pt minimum tap targets. Undersized targets cause mis-taps, especially frustrating on a tool users might check from a phone notification. Given the project type (developer tool where mobile is "usable in a pinch"), this is moderate rather than critical.
- **Fix:** Add a global minimum height for interactive elements:
  ```css
  button, a, [role="button"], select {
      min-height: 44px;
  }
  ```
  Or use Tailwind: `min-h-[44px]` on buttons. For icon-only buttons, increase padding: `p-2.5` or `p-3` instead of `p-1`/`p-2`.
- **Effort:** Low-Medium

### 4. Email metadata values not copyable

- **Where:** `/emails/{id}` — Metadata tab
- **What:** The email ID, provider, provider_message_id, ingest_method, and body_size are displayed as plain text without copy buttons. For a developer debugging email delivery, these are the values most likely to be pasted into logs, tickets, or API calls.
- **Why it matters:** Copy-to-clipboard is a first-class feature for this project type. The metadata tab is specifically where developers go for technical details. Having to manually select and copy text is friction.
- **Fix:** Add copy buttons next to provider_message_id and email ID. Consider adding a "Copy all metadata" button that copies a JSON or key-value representation.
- **Effort:** Low

### 5. SMTP settings values not individually copyable

- **Where:** `/apps/{id}` — SMTP Settings tab
- **What:** The SMTP host, port, username, and encryption values are displayed in `<code>` elements but lack copy buttons. Users setting up SMTP integration need to copy each value individually into their mail client or app config.
- **Why it matters:** Same rationale as #4 — developer values need clipboard access. The REST API code snippets in adjacent tabs all have copy buttons, creating an inconsistency.
- **Fix:** Add copy buttons next to each SMTP setting value, using the same pattern as the address block on email detail.
- **Effort:** Low

### 6. Truncated table text has no tooltip

- **Where:** `/emails` table, `/apps` table
- **What:** Subject, from_address, and to_addresses columns use `truncate max-w-xs` to clip long text, but no `title` attribute or tooltip mechanism shows the full value on hover/long-press.
- **Why it matters:** An email with a truncated subject like "Your order #123456 has..." is useless without seeing the full text. The user must click through to the detail page just to read a subject line.
- **Fix:** Add `title="{{ email.subject }}"` attributes to truncated cells:
  ```html
  <div class="font-medium truncate max-w-xs" title="{{ email.subject }}">{{ email.subject }}</div>
  ```
- **Effort:** Low

### 7. No loading state on login and app creation forms

- **Where:** `/login`, `/apps` (create modal)
- **What:** The login form and app creation form submit without any loading indicator. The button remains clickable, allowing double-submission. Contrast with the cleanup button in Settings which correctly shows a spinner and disables while running.
- **Why it matters:** On slow connections, users may click submit multiple times. For app creation, this could create duplicate apps. The login form on slow connections gives no feedback that anything is happening.
- **Fix:** Apply the same `x-data="{ submitting: false }"` pattern used on the cleanup button:
  ```html
  <form @submit="submitting = true" x-data="{ submitting: false }">
    <button :disabled="submitting" type="submit">
      <span x-show="!submitting">Sign in</span>
      <span x-show="submitting">Signing in...</span>
    </button>
  </form>
  ```
- **Effort:** Low

---

## Minor / Polish

### 8. Search input should use type="search"

- **Where:** `/emails` search bar
- **What:** Uses `type="text"` instead of `type="search"`.
- **Why it matters:** `type="search"` gives mobile browsers a "Search" keyboard action button, and desktop browsers show a clear (x) button. Minor but free improvement.
- **Fix:** Change `type="text"` to `type="search"` on the search input.
- **Effort:** Trivial

### 9. Required fields not visually marked

- **Where:** `/apps` create modal
- **What:** The "App Name" field has the HTML `required` attribute but no visual indicator (asterisk, "(required)" label, etc.) telling users it's required before they try to submit.
- **Why it matters:** Minor — most users will figure it out from browser validation, but explicit visual marking is a UX convention.
- **Fix:** Add `<span class="text-red-500">*</span>` next to required labels, or add `(required)` in label text.
- **Effort:** Trivial

### 10. Email ID not displayed or copyable on email detail

- **Where:** `/emails/{id}` header section
- **What:** The email's UUID is in the URL but not shown anywhere on the detail page itself. Developers debugging delivery issues often need to reference email IDs in logs or API calls.
- **Fix:** Add the email ID as a small monospace value near the header, with a copy button:
  ```html
  <code class="text-xs text-gray-400 font-mono">{{ email.id }}</code>
  <button onclick="copyToClipboard('{{ email.id }}', this)" ...>Copy</button>
  ```
- **Effort:** Trivial

### 11. App detail page missing "View emails" link

- **Where:** `/apps/{id}`
- **What:** The app detail shows email counts but no direct link to view emails filtered by that app. Users must go to `/emails`, open filters, and select the app manually.
- **Fix:** Add a link to `/emails?app_id={{ app.id }}` near the email count stat card or as an action button.
- **Effort:** Trivial

### 12. HTML Source and Plain Text tabs lack copy buttons

- **Where:** `/emails/{id}` — HTML Source and Plain Text tabs
- **What:** The Preview, HTML Source, and Plain Text tabs display email body content, but only the integration snippet code blocks on `/apps/{id}` have copy buttons. The HTML source and plain text tabs show `<pre>` blocks without copy functionality.
- **Fix:** Wrap these in the same `group/code` pattern with a `code-copy-btn` button.
- **Effort:** Low

---

## Quick Wins (can fix in one session)

1. **Fix iOS input zoom**: Change `text-sm` to `text-base` on all `<input>` and `<select>` elements (5 minutes, all templates)
2. **Add `title` tooltips to truncated table cells**: 4 cells across emails.html and apps.html
3. **Add `type="search"` to search input**: One attribute change
4. **Add loading state to login form**: Copy the cleanup button pattern (Alpine.js `submitting` state)
5. **Add loading state to app creation form**: Same pattern
6. **Add copy buttons to SMTP settings**: Replicate existing copy button pattern
7. **Add email ID display + copy on email detail**: Small template addition
8. **Add "View emails" link on app detail**: One `<a>` tag
9. **Add `title` to truncated values in apps table**: Slug, storage mode columns
10. **Required field asterisk on app creation form**: One `<span>` element

## Larger Efforts (plan separately)

1. **Clickable sortable column headers**: Requires template changes to generate sort links, add chevron icons, and preserve current filter state in sort links. Medium effort — need to thread all current query params through sort links.
2. **Increase touch targets globally**: Requires systematic audit of padding values across all templates. Need to balance density (developer tool) with usability. Consider a `min-h-[44px]` utility class applied broadly.
3. **Copy buttons on email metadata tab**: Need to add individual copy buttons for email ID, provider_message_id, and possibly a "Copy all metadata as JSON" button. Low-medium effort.
4. **Filter state persistence via localStorage**: Would require JS that reads/writes filter selections to localStorage and auto-applies them on page load. Medium effort — need to handle interaction with URL params gracefully.

## Not Applicable

| Item | Reason |
|------|--------|
| Web Share API | Developer tool — clipboard is the right pattern |
| Search debounce | Form-submit model, not real-time search |
| Public-facing UX | No public views — admin-only surface |
| User theming/customization | Admin tool — no end-user customization needed |
| Breadcrumbs | Flat navigation structure, back links sufficient |
| Swipe gestures | No custom gestures needed |

---

## Summary Scores

| Category | Pass | Partial | Fail | N/A |
|----------|------|---------|------|-----|
| Navigation & Layout | 5 | 1 | 0 | 0 |
| Tables & Data Lists | 5 | 2 | 1 | 0 |
| Touch & Interaction | 5 | 1 | 0 | 0 |
| Copy-to-Clipboard | 3 | 1 | 0 | 1 |
| Forms & Inputs | 3 | 4 | 1 | 0 |
| Visual Feedback & States | 4 | 2 | 0 | 0 |
| Typography & Readability | 4 | 1 | 0 | 0 |
| Admin Convenience | 4 | 1 | 1 | 1 |
| **Total** | **33** | **13** | **3** | **2** |

Overall: The admin UI is well-built with consistent patterns, proper dark mode, keyboard shortcuts, and a functional toast system. The main gaps are around form input sizing for iOS, sort interactivity on tables, touch target sizing, and some missing copy buttons on developer-relevant values. All issues are low-to-medium effort fixes.
