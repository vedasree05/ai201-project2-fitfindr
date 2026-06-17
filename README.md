# FitFindr

A thrift-shopping agent that takes a natural language query, finds matching secondhand listings, and returns an outfit suggestion and shareable fit card caption.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Searches the mock listings dataset for secondhand items matching the user's keywords, optional size, and optional price ceiling. Returns results ranked by keyword relevance so the agent always receives the best match first.

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Keywords describing the item (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | Size to filter by; `None` skips size filtering. Case-insensitive substring match — `"M"` matches `M`, `S/M`, `M/L` |
| `max_price` | `float \| None` | Price ceiling in dollars, inclusive; `None` skips price filtering |

**Returns:** `list[dict]` — matching listing dicts sorted by relevance score (highest first). Each dict has 11 fields: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns an empty list if nothing matches — never raises.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Given a thrifted item the user is considering and their existing wardrobe, asks an LLM to suggest 1–2 complete outfits. If the wardrobe is empty, pivots to general styling advice rather than failing.

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict (same shape as returned by `search_listings`) |
| `wardrobe` | `dict` | Dict with an `"items"` key containing a list of wardrobe item dicts. The list may be empty |

**Returns:** `str` — a non-empty outfit suggestion. When the wardrobe has items, names specific pieces in the suggested outfits. When the wardrobe is empty, gives general advice on what types of bottoms, shoes, and layers pair well with the item.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Generates a 2–4 sentence Instagram/TikTok-style caption for the thrifted find. Uses high LLM temperature so outputs vary across different inputs.

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit`. Must be non-empty |
| `new_item` | `dict` | The listing dict for the item, used to pull title, price, and platform |

**Returns:** `str` — a casual, shareable caption that mentions the item name, price, and platform once each, and captures the outfit vibe in specific terms. If `outfit` is empty or whitespace-only, returns a descriptive error string (`"Could not generate fit card: outfit suggestion was empty."`) without calling the LLM.

---

## Planning Loop

`run_agent()` in `agent.py` runs a fixed 7-step linear sequence. The only branch point is after `search_listings`:

```
1. Initialize session dict
2. Parse query via LLM → extract description, size, max_price
3. Call search_listings(description, size, max_price)
       │
       ├── results == []  →  set session["error"], return session early
       │                     (suggest_outfit and create_fit_card are never called)
       │
       └── results != []  →  session["selected_item"] = results[0]
4. Call suggest_outfit(selected_item, wardrobe)
5. Call create_fit_card(outfit_suggestion, selected_item)
6. Return session
```

The agent does not retry on failure, loop back, or branch again after step 3. Once a non-empty result list exists, the remaining two tools are always called in order.

---

## State Management

All data is stored in a single `session` dict initialized by `_new_session()` and passed implicitly between steps as local state within `run_agent()`. No globals, no side channels.

| Key | Set at step | Value |
|-----|-------------|-------|
| `query` | 1 | Raw user input string |
| `wardrobe` | 1 | Wardrobe dict passed in by the caller |
| `parsed` | 2 | `{"description": str, "size": str\|None, "max_price": float\|None}` |
| `search_results` | 3 | Full list of matching listing dicts |
| `selected_item` | 3 (happy path) | `search_results[0]` — the top-ranked listing |
| `outfit_suggestion` | 4 | String returned by `suggest_outfit` |
| `fit_card` | 5 | Caption string returned by `create_fit_card` |
| `error` | 3 (no results) | User-facing error message; `None` on the happy path |

Each tool reads only what it needs from the session and writes only its own output key. `app.py` reads `session["error"]` first — if set, it displays the message in panel 1 and leaves the other panels empty.

---

## Error Handling

| Tool | Failure mode | What the agent does | Concrete example from testing |
|------|-------------|---------------------|-------------------------------|
| `search_listings` | No listings match the query | Sets `session["error"]` to `"No listings found — try broader keywords, a different size, or a higher budget."` and returns the session immediately. `suggest_outfit` and `create_fit_card` are never called. | Query `"designer ballgown size XXS under $5"` returned `search_results = []`, `error` was set, `fit_card` remained `None`, and mocking confirmed `suggest_outfit.called == False`. |
| `suggest_outfit` | Wardrobe is empty | Switches to a general-styling prompt instead of a wardrobe-pairing prompt. Always returns a non-empty string — no exception, no early exit. | Called with `get_empty_wardrobe()` (items list is `[]`); returned a full paragraph of general styling advice without raising. |
| `create_fit_card` | `outfit` string is empty or whitespace-only | Returns `"Could not generate fit card: outfit suggestion was empty."` immediately, before the Groq client is ever constructed. | Called with `outfit=""` — returned the error string; a mock confirmed the Groq client was never instantiated. |

---

## Spec Reflection

**One way the spec helped:** Writing the planning loop section of `planning.md` before touching `agent.py` made the early-exit branch completely unambiguous. When it came time to implement, there was no decision to make — the condition (`if not session["search_results"]`), the exact key to set (`session["error"]`), and the return behavior were all already written down. The implementation matched the spec line for line.

**One way the implementation diverged:** The spec described `search_listings` size matching as "case-insensitive," but during implementation it became clear that substring matching was also necessary — `"M"` had to match listings sized `"S/M"` and `"M/L"`, not just exact `"M"`. The spec's own example (`"M" matches "S/M"`) implied this, but the wording didn't say "substring." The implementation used `size_lower in listing["size"].lower()` rather than a strict equality check, and the spec was updated to reflect it.

---

## AI Usage

**Instance 1 — Implementing `search_listings`**

Given to Claude Code: the Tool 1 spec from `planning.md` (input parameters with types, the full 11-field return value list, the failure mode) plus the `load_listings()` docstring from `utils/data_loader.py` showing available field names.

What it produced: a complete implementation that filters by price and size, scores each listing by keyword overlap across `title`, `description`, and `style_tags`, drops zero-score listings, and returns sorted descending.

What I changed: nothing in the logic, but I verified the substring size matching behavior manually (`"m"` against `"S/M"` and `"M/L"`) before accepting it, since the spec was ambiguous on that point.

**Instance 2 — Implementing `run_agent`**

Given to Claude Code: the Planning Loop section of `planning.md` (all 7 steps with exact session keys at each step), the Architecture diagram (showing the early-exit branch at step 3), and the `_new_session()` skeleton already in `agent.py`.

What it produced: a complete `run_agent()` with the LLM-based query parser (`_parse_query`) and the full session flow.

What I changed: added a verification step using `unittest.mock.patch` on `suggest_outfit` to confirm it was genuinely never called on the no-results path — the implementation looked correct but I wanted proof, not just a passing visual check.
