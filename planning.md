# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for thrifted items that match the user's keywords, optional size, and optional price ceiling. Returns the matching listings ranked by keyword relevance so the agent can pick the best result.

**Input parameters:**
- `description` (str): Keywords describing what the user wants (e.g., `"vintage graphic tee"`). Used to score each listing by overlap against its title, description, and style tags.
- `size` (str | None): Size string to filter by (e.g., `"M"`, `"S/M"`). Matching is case-insensitive. Pass `None` to skip size filtering.
- `max_price` (float | None): Maximum price in dollars, inclusive (e.g., `30.0`). Pass `None` to skip price filtering.

**What it returns:**
A `list[dict]` of matching listing dictionaries, sorted by relevance score (highest first). Returns an empty list if nothing matches — never raises an exception. Each dict contains:
- `id` (str): unique listing identifier
- `title` (str): item name
- `description` (str): full item description
- `category` (str): one of `tops`, `bottoms`, `outerwear`, `shoes`, `accessories`
- `style_tags` (list[str]): tags like `["vintage", "streetwear"]`
- `size` (str): e.g., `"M"` or `"S/M"`
- `condition` (str): one of `excellent`, `good`, `fair`
- `price` (float): listing price in dollars
- `colors` (list[str]): e.g., `["black", "white"]`
- `brand` (str | None): brand name, or `None` if unbranded
- `platform` (str): one of `depop`, `thredUp`, `poshmark`

**What happens if it fails or returns nothing:**
If the returned list is empty, the agent sets `session["error"]` to a friendly message explaining no listings matched (e.g., "No listings found for that search — try broader keywords, a different size, or a higher budget.") and returns the session early without calling `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted item the user is considering and the user's existing wardrobe, asks an LLM to suggest 1–2 complete outfits. If the wardrobe is empty, the LLM gives general styling advice for the item instead.

**Input parameters:**
- `new_item` (dict): A listing dict (same structure as returned by `search_listings`) representing the item the user is considering buying.
- `wardrobe` (dict): A wardrobe dictionary with an `"items"` key containing a list of wardrobe item dicts. Each wardrobe item has at minimum a `"name"` field. The list may be empty.

**What it returns:**
A non-empty `str` containing outfit suggestions from the LLM. When the wardrobe has items, the response names specific pieces from the wardrobe paired with the new item. When the wardrobe is empty, the response gives general styling advice (e.g., what types of bottoms, shoes, or layers pair well with the item and what vibe it suits).

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the tool does not fail — it pivots to a general-styling prompt rather than a wardrobe-pairing prompt. The tool always returns a non-empty string. The agent stores the result in `session["outfit_suggestion"]` and proceeds to `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, shareable Instagram/TikTok-style outfit caption for the thrifted find. Uses the LLM at higher temperature to produce casual, authentic-sounding copy that naturally mentions the item's name, price, and platform.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. Must be non-empty; if it is empty or whitespace-only the tool returns an error string immediately without calling the LLM.
- `new_item` (dict): The listing dict for the thrifted item (same structure as returned by `search_listings`), used to pull `title`, `price`, and `platform` for the caption.

**What it returns:**
A `str` of 2–4 sentences suitable as a social media caption. The caption mentions the item name, price, and platform once each, captures the outfit's vibe in specific terms, and reads like a real OOTD post rather than a product description. If `outfit` is empty or missing, returns a descriptive error string (e.g., `"Could not generate fit card: outfit suggestion was empty."`) — never raises an exception.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the tool returns an error string and the agent stores it in `session["fit_card"]` — no exception is raised and the session is still returned to the caller. The caller can detect the failure by checking whether `session["fit_card"]` starts with `"Could not generate"`.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The agent runs a fixed linear sequence of steps. There are no branches where it loops back or retries — each step either advances to the next or terminates early with an error stored in `session["error"]`.

**Step 1 — Initialize session**
Call `_new_session(query, wardrobe)`. This sets up the session dict with `query`, an empty `parsed` dict, empty `search_results`, `selected_item = None`, the passed-in `wardrobe`, `outfit_suggestion = None`, `fit_card = None`, and `error = None`.

**Step 2 — Parse the query**
Extract `description`, `size`, and `max_price` from the raw query string. Store the result as a dict in `session["parsed"]`. (Implementation uses the LLM to extract these fields from natural language, falling back to `None` for `size` and `max_price` if the user did not specify them.)

**Step 3 — Call `search_listings`**
Call `search_listings(description, size, max_price)` using the values from `session["parsed"]`.
Store the returned list in `session["search_results"]`.

- **If `session["search_results"]` is empty:** set `session["error"]` to a user-facing message (e.g., `"No listings found — try broader keywords, a different size, or a higher budget."`) and **return the session immediately**. Steps 4–6 are skipped.
- **If `session["search_results"]` is non-empty:** proceed to Step 4.

**Step 4 — Select the top result**
Set `session["selected_item"] = session["search_results"][0]`.
This is the highest-relevance listing and is what gets passed into the outfit and caption tools.

**Step 5 — Call `suggest_outfit`**
Call `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])`.
Store the returned string in `session["outfit_suggestion"]`.
This step always produces a non-empty string (the tool handles an empty wardrobe gracefully), so there is no early-exit condition here.

**Step 6 — Call `create_fit_card`**
Call `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])`.
Store the returned string in `session["fit_card"]`.

**Step 7 — Return session**
Return the completed session dict. `session["error"]` is `None` on the happy path. The caller reads `session["fit_card"]` for the final output.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | |
| suggest_outfit | Wardrobe is empty | |
| create_fit_card | Outfit input is missing or incomplete | |

---

## Architecture

```
User query  (natural language string)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Planning Loop  (run_agent)                                     │
│                                                                 │
│  Step 1 ── _new_session(query, wardrobe)                        │
│               └─► session["query"], session["wardrobe"] set     │
│                                                                 │
│  Step 2 ── Parse query (LLM)                                    │
│               └─► session["parsed"] = {description, size,      │
│                                         max_price}              │
│                                                                 │
│  Step 3 ── search_listings(description, size, max_price)        │
│               │                                                 │
│               ├── session["search_results"] = results           │
│               │                                                 │
│               │  results == []                                  │
│               ├──────────────────────────────────────────────►  │
│               │          session["error"] = "No listings found" │
│               │          return session  ◄── EARLY EXIT         │
│               │                                                 │
│               │  results != []                                  │
│               ▼                                                 │
│  Step 4 ── session["selected_item"] = results[0]               │
│               │                                                 │
│  Step 5 ── suggest_outfit(selected_item, wardrobe)              │
│               │   (empty wardrobe → general styling advice;     │
│               │    non-empty wardrobe → specific pairings)      │
│               └─► session["outfit_suggestion"] = "..."          │
│                       │                                         │
│  Step 6 ── create_fit_card(outfit_suggestion, selected_item)    │
│               └─► session["fit_card"] = "..."                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
Return session
    ├── session["error"] is None  → happy path
    │       session["fit_card"]         ← final output to user
    │       session["outfit_suggestion"]
    │       session["selected_item"]
    │
    └── session["error"] is set   → early-exit path
            session["fit_card"] = None
            session["outfit_suggestion"] = None
```

**State / Session dict** (single source of truth across all steps):

| Key                  | Set at step | Value                                      |
|----------------------|-------------|---------------------------------------------|
| `query`              | 1           | raw user input string                       |
| `wardrobe`           | 1           | wardrobe dict passed by caller              |
| `parsed`             | 2           | `{description, size, max_price}`            |
| `search_results`     | 3           | list of matching listing dicts              |
| `selected_item`      | 4           | `search_results[0]`, the top-ranked listing |
| `outfit_suggestion`  | 5           | string from `suggest_outfit`                |
| `fit_card`           | 6           | caption string from `create_fit_card`       |
| `error`              | 3 or never  | set on early exit; `None` on happy path     |

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**Tool: `search_listings`**
- **AI tool:** Claude Code
- **Input I'll give it:** The Tool 1 spec from this file (what it does, all input parameters with types, the full return-value field list, the failure mode), plus the `load_listings()` docstring from `utils/data_loader.py` showing the exact field names available.
- **Expected output:** A complete implementation of `search_listings()` in `tools.py` that calls `load_listings()`, filters by `max_price` and `size` (case-insensitive), scores each listing by keyword overlap with `description` across `title`, `description`, and `style_tags`, drops zero-score listings, and returns the list sorted highest score first.
- **Verification:** Run the function directly against 3 test queries — (1) `"vintage graphic tee"`, no filters → expect multiple results; (2) same query with `max_price=10.0` → expect a shorter or empty list; (3) `"designer ballgown"` with `max_price=5.0` → expect an empty list. Confirm return type is `list[dict]` and each dict contains all 11 expected fields.

**Tool: `suggest_outfit`**
- **AI tool:** Claude Code
- **Input I'll give it:** The Tool 2 spec (inputs, return contract, both wardrobe-empty and wardrobe-full branches), plus the `_get_groq_client()` helper already in `tools.py`.
- **Expected output:** An implementation of `suggest_outfit()` that checks `wardrobe["items"]`, builds the appropriate LLM prompt for each branch, calls the Groq client, and returns the response string — never returning an empty string.
- **Verification:** Call it twice — once with `get_empty_wardrobe()` and once with `get_example_wardrobe()`, both using the same `new_item` dict. Confirm both return a non-empty string. Confirm the non-empty-wardrobe response mentions specific item names from the wardrobe.

**Tool: `create_fit_card`**
- **AI tool:** Claude Code
- **Input I'll give it:** The Tool 3 spec (inputs, caption style rules, the guard-against-empty-outfit requirement, the instruction to use higher LLM temperature).
- **Expected output:** An implementation of `create_fit_card()` that guards against empty `outfit`, builds a prompt with item name/price/platform and the outfit suggestion, calls the Groq client at temperature ≥ 0.9, and returns a 2–4 sentence caption string.
- **Verification:** Call it with a real outfit string and a listing dict. Confirm the output is 2–4 sentences, mentions the item name, price, and platform exactly once each. Then call it with `outfit=""` and confirm it returns an error string without raising.

---

**Milestone 4 — Planning loop and state management:**

- **AI tool:** Claude Code
- **Input I'll give it:** The Planning Loop section (all 7 steps with exact session keys), the State Management section, the Architecture diagram (showing the early-exit branch at Step 3), and the `_new_session()` skeleton already in `agent.py`.
- **Expected output:** A complete implementation of `run_agent()` in `agent.py` that: initializes the session, uses the LLM to parse `description`/`size`/`max_price` from the query, calls the three tools in order, stores results in the correct session keys at each step, short-circuits with `session["error"]` if `search_results` is empty, and returns the session dict.
- **Verification:** Run the two CLI test cases already in `agent.py`'s `__main__` block — (1) `"looking for a vintage graphic tee under $30"` with `get_example_wardrobe()` should reach `fit_card` with `error=None`; (2) `"designer ballgown size XXS under $5"` should return with `error` set and `fit_card=None`. Confirm `session["selected_item"]` is `search_results[0]` on the happy path.

---

## A Complete Interaction (Step by Step)

**Example user query:** "vintage graphic tee, size M, under $30 — I have baggy jeans and chunky sneakers"

---

**Step 1 — Initialize session**

`_new_session()` is called. Session starts as:

```python
{
  "query":             "vintage graphic tee, size M, under $30 — I have baggy jeans and chunky sneakers",
  "parsed":            {},
  "search_results":    [],
  "selected_item":     None,
  "wardrobe":          {"items": [{"name": "baggy jeans"}, {"name": "chunky sneakers"}]},
  "outfit_suggestion": None,
  "fit_card":          None,
  "error":             None,
}
```

---

**Step 2 — Parse query**

The LLM reads the raw query and extracts structured parameters. Result stored in `session["parsed"]`:

```python
session["parsed"] = {
  "description": "vintage graphic tee",
  "size":        "M",
  "max_price":   30.0,
}
```

---

**Step 3 — Call `search_listings`**

```python
search_listings(description="vintage graphic tee", size="M", max_price=30.0)
```

Internally: loads all listings, drops any with `price > 30.0` or `size` not matching `"M"`, scores the rest by keyword overlap with `"vintage graphic tee"` (matching against title, description, style_tags), drops zero-score listings, sorts by score descending.

Returned value (example — two matches, highest score first):

```python
[
  {
    "id": "lst_042",
    "title": "Faded Nirvana Graphic Tee",
    "description": "Worn-in vintage band tee with distressed hem.",
    "category": "tops",
    "style_tags": ["vintage", "grunge", "graphic"],
    "size": "M",
    "condition": "good",
    "price": 24.0,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
  },
  {
    "id": "lst_017",
    "title": "90s Sun-Faded Graphic Tee",
    "description": "Soft, washed-out vintage tee.",
    "category": "tops",
    "style_tags": ["vintage", "streetwear"],
    "size": "M",
    "condition": "fair",
    "price": 18.0,
    "colors": ["white"],
    "brand": None,
    "platform": "thredUp",
  },
]
```

`session["search_results"]` is set to this list. List is non-empty → no early exit.

---

**Step 4 — Select top result**

```python
session["selected_item"] = session["search_results"][0]
# → the "Faded Nirvana Graphic Tee" dict
```

---

**Step 5 — Call `suggest_outfit`**

```python
suggest_outfit(
  new_item = session["selected_item"],   # Faded Nirvana Graphic Tee
  wardrobe = session["wardrobe"],        # {"items": [{"name": "baggy jeans"}, {"name": "chunky sneakers"}]}
)
```

Wardrobe is non-empty → the LLM prompt asks for specific pairings using the named wardrobe pieces.

Returned string stored in `session["outfit_suggestion"]`:

```
"Outfit 1: Tuck the Faded Nirvana Graphic Tee loosely into your baggy jeans and finish
with the chunky sneakers — classic 90s grunge energy without trying too hard. Outfit 2:
Let the tee hang untucked over the jeans, cuff the hem once, and layer an open flannel
on top for a more relaxed streetwear look."
```

---

**Step 6 — Call `create_fit_card`**

```python
create_fit_card(
  outfit   = session["outfit_suggestion"],   # the string above
  new_item = session["selected_item"],       # Faded Nirvana Graphic Tee, $24, depop
)
```

LLM is called at high temperature (~0.95) with a prompt asking for a 2–4 sentence Instagram caption that mentions item name, price, and platform once each.

Returned string stored in `session["fit_card"]`:

```
"thrifted this Faded Nirvana Graphic Tee on depop for $24 and it's doing
everything. baggy jeans tucked, chunky sneakers on, flannel halfway off —
90s without even trying. grunge is not dead it just moved to secondhand."
```

---

**Step 7 — Return session**

```python
{
  "query":             "vintage graphic tee, size M, under $30 ...",
  "parsed":            {"description": "vintage graphic tee", "size": "M", "max_price": 30.0},
  "search_results":    [ <2 listing dicts> ],
  "selected_item":     { "title": "Faded Nirvana Graphic Tee", "price": 24.0, ... },
  "wardrobe":          {"items": [{"name": "baggy jeans"}, {"name": "chunky sneakers"}]},
  "outfit_suggestion": "Outfit 1: Tuck the Faded Nirvana ...",
  "fit_card":          "thrifted this Faded Nirvana Graphic Tee on depop ...",
  "error":             None,
}
```

---

**Final output to user:**

The Gradio UI displays three sections:

1. **Top listing found:** "Faded Nirvana Graphic Tee — $24 — good condition — depop"
2. **How to style it:**
   > Outfit 1: Tuck the Faded Nirvana Graphic Tee loosely into your baggy jeans and finish with the chunky sneakers — classic 90s grunge energy without trying too hard. Outfit 2: Let the tee hang untucked over the jeans, cuff the hem once, and layer an open flannel on top for a more relaxed streetwear look.
3. **Your fit card:**
   > thrifted this Faded Nirvana Graphic Tee on depop for $24 and it's doing everything. baggy jeans tucked, chunky sneakers on, flannel halfway off — 90s without even trying. grunge is not dead it just moved to secondhand.
