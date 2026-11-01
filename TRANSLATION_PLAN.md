# Missing English translations - audit and plan

Branch: `feature/english-translations` (from `main`).

## How translation works today

- `LANGUAGE` (`dashboard.py`, ~line 145) comes from the app config and defaults to `"en"`.
- `_T_EN` (~line 218-774) maps **Italian source text -> English text**.
- `T(s)` returns `s` unchanged for `it`, else `_T_EN.get(s, s)`. A missing key silently falls back to Italian.
- `respond()` -> `_apply_translations()` also does a plain `str.replace` of every `_T_EN` key over the whole rendered HTML (longest keys first). The log page applies the same replace to log messages.
- Some labels use ad-hoc `"x" if LANGUAGE != "it" else "y"` branches (e.g. `Date`/`Data`, `of`/`di`).

## Risks / constraints

- Whole-page `str.replace` is fragile: short or common keys corrupt HTML, JS, CSS and attributes (already noted in a code comment about `di` / `Data`). New keys must be long/specific enough, or use `T()` at the call site.
- A key that is a substring of another key is handled by the longest-first sort, but new keys must be checked for collisions.
- Strings containing f-string values (e.g. `Abilitare 2FA per {user}?`) cannot match as one key; they need to be split or wrapped in `T()`.
- JS-side strings (`alert(...)`, `confirm(...)`, toast text inside `<script>`) are also rewritten by the page-wide replace, so quoting and escaping must be preserved.
- Italian log messages are stored in `app_log.json` as written; they are translated at display time only.
- Existing dictionary entries are not in scope except for obvious duplicates (e.g. `"eventi in memoria"` appears twice).

## Audit result (heuristic, `ast`-based)

Scanned all string literals after the dictionary for Italian vocabulary or accents and not covered by an existing `_T_EN` key:

- ~680 candidate strings, ~250 not covered by any `_T_EN` key after removing obvious noise (identifiers such as `password`, URLs, docstrings).
- Clusters seen: Guide / onboarding tour (~7500-8100), update dialog steps (~8890), "no router selected / no file selected" toasts (~6090-6400), 2FA setup and prompts (~6680-6800), site manager hints (~4155), About / credits page (~15079-15123), scheduler and backup log messages (~2440), `Enable`/`Disable` and `Copy`/`Hide` buttons.
- Needs a manual pass: the heuristic over-reports (identifiers, internal strings) and under-reports (single Italian words with no accent, e.g. `Tutto`, `giorni`).

## Plan

1. **Build a reliable inventory.** Extend the audit into a reviewable list (line, string, UI-visible yes/no, how it is rendered: HTML text, attribute, JS string, log message, API JSON message). Output stays out of the repo.
2. **Classify.** Mark each item as: translate via `_T_EN`; convert to `T()`; ignore (identifier, internal, developer-only); intentionally Italian (e.g. credits).
3. **Add dictionary entries**, grouped under the existing section comments (Navigation, Log, Users, ...), keeping keys specific. Fix duplicate keys.
4. **Convert unsafe or dynamic cases** to `T()` / split strings rather than relying on page-wide replace.
5. **Server-side messages**: API JSON `error`/`message` strings, toasts and log messages shown in the UI.
6. **Tests**: a unit test that (a) parses `_T_EN` and fails on duplicate keys, (b) checks no key is a risky short token, (c) checks every key in a curated "must translate" list resolves to English.
7. **Manual validation** in the UI with `language: en` and `it`: Guide, tour, Users, Site Manager, Settings, update dialog, About, log page.

## Decisions

- **About page credits stay Italian** for now (intentionally Italian, out of scope).
- **No retroactive log migration.** Previously stored log entries are left unchanged. The existing display-time translation of log messages stays as is; new dictionary entries for log messages apply to it automatically.
- **Natural English style**, not literal. Follow existing mappings for established terms such as `Sito`, `Pianificazione` and `Credenziali`.

## Progress

- Inventory rebuilt to ignore text that already has an English alternative (`lang_en` / `LANGUAGE` ternaries); this cut the ~250 heuristic candidates down to the real gaps (~110 strings, 75 of them genuine after review).
- Added ~85 entries to `_T_EN` (API messages, page-wide JS strings, dashboard/backup/discovery UI text).
- `_json()` now translates `msg` / `error` values through `T()` for non-Italian, so existing and future static API messages only need a dictionary entry. Dynamic messages (update flow, password error) were converted to `T()` / language-aware f-strings.
- Removed 6 conflicting duplicate dictionary keys, keeping the values that were already effective (last one won).
- Added `tests/test_translations.py` (conflicting duplicates, short-key guard, required entries, every static `T("...")` key has an entry).
- Still to do: manual UI walkthrough with `language: en` for Guide, tour, Users, Site Manager, Settings, update dialog and log page. Dynamically built strings that the heuristic cannot see may remain.

## Acceptance criteria

- With `language: en`, no Italian text remains in any UI-visible page, dialog, toast or API message, except items explicitly marked intentionally Italian.
- With `language: it`, output is unchanged.
- No HTML/JS corruption from new keys (page-wide replace).
- Tests above pass.
