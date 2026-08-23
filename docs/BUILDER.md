# PartsMatcher as a product — capture app, MCP scaffolding, and the builder

Decision doc for the commercial fork (Ben, 2026-08-23). Same shape as
`APP_ARCHITECTURE.md` and `MOBILE.md`: options, a recommendation, and open
questions — **nothing here is ratified and no code has moved.**

The ask, in Ben's words across three conversations: a simple, intuitive
commercial MVP for inventory capture ("Add Inventory" button → camera →
confirm name → enter quantity); the LLM-heavy *builder* half ("what can I
actually build?") running on **users' own native model subscriptions**, not
metered API calls, against a scaffolding we provide; and building the
**electronics component** of HEPH — a friend's working chat→3D-print
generator, installed and inspected locally on 2026-08-23 (see Decision 2) —
with PartsMatcher's inventory as its auto-check layer. The collaboration is
already live in spirit: HEPH's author has accepted Ben's help, and some of
Ben's ideas ship in the program today.

## The three facts that decide this

**1. The credential prohibition from MOBILE.md still stands — but MCP flips
the direction of integration, and the flipped direction is sanctioned.**
A branded app may not collect, store, or intermediate Claude.ai credentials;
there is no third-party "Sign in with Claude." What *is* first-class, on
both Anthropic's and OpenAI's surfaces, is the opposite plug: the user's own
Claude or ChatGPT connects **to our remote MCP server**, authenticating with
**our** OAuth (their PartsMatcher account — a credential we are fully
entitled to issue). The Claude app has a connectors directory; remote MCP
servers work on consumer plans; Claude Code speaks MCP natively; OpenAI
adopted MCP in 2025. One server makes the scaffolding model-agnostic:
"bring your native subscription" covers whichever assistant the user
already pays for.

**2. The cost structure cleaves cleanly, if we let it.** Everything
deterministic — the matcher, the inventory database, name reconciliation
against the alias dataset — costs ~nothing to serve and never needs a
model. Everything expensive — open-ended build conversations, project
adaptation, wiring walkthroughs, substitution reasoning — is exactly what
users' subscriptions already pay for. An all-API product would meter its
most engaging feature; the BYO-model split makes marginal cost per user
approximately storage plus a web server. The only product-side model spend
left is naming a part in a capture photo, and a Data Matrix barcode
(DigiKey/Mouser bags) decodes on-device for free before vision is even
consulted.

**3. The bench repo already ran this architecture end to end
(2026-08-22/23, Ben, live).** A user's own subscription (Remote Control
from a phone), driving an authored protocol (SKILL.md), calling a
deterministic tool (`python -m partsmatcher match`), against user-owned
data: 33+ photos across multiple sessions, 0 → 76+ part types / 856+
parts, 73+ alias records — with **zero product-side LLM spend**. The
protocol survives contact with a real workbench. Productizing it is a
transport swap: files in a git repo become tools on a server; the SKILL.md
prose becomes tool descriptions and server instructions. The standing rule
("never state a match result from memory — run the matcher") gets
*structurally* enforced under MCP: calling `match_projects` is the only way
the model can obtain a verdict at all.

## The architecture

```
+- OUR PRODUCT (near-zero LLM cost) ----------------------------+
|  Phone app (capture surface):                                 |
|    [Add Inventory] -> camera -> on-device barcode decode      |
|    -> (fallback: one vision API call to name the part)        |
|    -> user confirms name, enters quantity -> row lands in DB  |
|  Hosted DB: inventory - projects - photos - alias records     |
|  Remote MCP server (our OAuth):                               |
|    get_inventory - add_parts - match_projects - check_bom     |
|    reconcile_names - log_alias                                |
+---------------------------+-----------------------------------+
                            | user connects it once (connector)
+- USER'S SUBSCRIPTION (all the expensive reasoning) -----------+
|  Their Claude / ChatGPT / Claude Code:                        |
|  "what can I build tonight?" - project adaptation -           |
|  wiring walkthroughs - substitution reasoning                 |
+---------------------------------------------------------------+
             ^
   Friend's chat->3D-print generator: emits an electronics BOM
   -> check_bom -> grounded verdict + shopping list net of owned parts
```

Division of labor at capture: the model does the one job it's good at
(name the part); the human does the two jobs it's bad at (confirm
identity, count). Quantity is a number pad, not an inference.

## Decision 1 — where the LLM spend lives

- **Option A: all-API.** Our app hosts the whole conversation on our key.
  Full UX control, no connector setup — and we meter our stickiest
  feature, carry abuse/prompt-injection surface on our bill, and rebuild
  chat UX that Anthropic and OpenAI already ship better. Rejected.
- **Option B: BYO-model via MCP (recommended).** Users' native clients do
  the reasoning; we serve deterministic tools and data. Our spend is
  capture-vision fallback only.
- **Option C: all-BYO, including capture.** No API key at all; capture
  runs as protocol prose like the bench repo. Rejected for the commercial
  surface: the capture flow Ben specified is a widget, not a
  conversation, and one cheap vision call is what makes it two seconds.

**Recommendation: B**, with C's spirit retained — anything expressible as
a deterministic tool stays out of the model entirely.

## Decision 2 — the electronics component of HEPH

The generator answers *"what could exist?"*; PartsMatcher answers *"what
can happen tonight, with these drawers?"* The integration is one tool
call: HEPH emits an electronics BOM, `check_bom` returns the three-bucket
verdict, per-part shortfalls, and a shopping list **net of what the user
owns**.

### What HEPH turned out to be (inspected locally, 2026-08-23)

HEPH v0.1.6 — *"text to working mechanical object: plan, sculpt, validate,
ship printable STLs"* — is a Tauri desktop app (HEPH Studio: 3D viewer
beside a terminal) with a compiled Python 3.13 core, driving **the user's
own Claude Code** through a per-project `CLAUDE.md` and MCP tools
(`heph_rebuild`, `heph_state`, `heph_catalog`, `heph_ship`). That is the
**same BYO-model architecture this doc recommends** — protocol file + MCP
tools + deterministic core + the user's own subscription — independently
converged on. Both halves of the partnership already speak the paradigm;
fact 1 above is its legal basis and fact 3 its field evidence.

Its electronics layer is **more built-out than expected** — this is not
greenfield. The catalogue drives everything from one entry: auto-generated
standoffs on real hole patterns, connector keepout volumes ("a wall
fouling a USB plug is a validation error rather than a discovery made with
a soldering iron"), per-dimension confidence tiers (datasheet / common /
nominal), power budgeting with brownout arithmetic, wire-gauge-from-current
netlists, and harness routing that cuts cable troughs into the model.

The real gaps, from inspection plus Ben's hands-on testing:

- **Catalogue breadth.** ~23 curated, robot-shaped components
  (`arduino_nano`, `esp32devkit`, `pi4/pi5/pizero2w`, `picam3`,
  `sg90`, `mg996r`, `nema17`, `n20_gearmotor`, `tt_motor`, `l298n`,
  `tb6612`, `hcsr04`, `mpu6050`, `ssd1306`, `mp1584`, `xl4015`,
  18650 packs, wheels, casters). Ben's bench alone holds 76 part types.
  Growing entries — hole patterns, keepouts, power figures, honest
  confidence tiers — is exactly the electronics domain work on offer.
- **No concept of ownership.** The BOM prices everything as purchased and
  emits Amazon *search* URLs. This is the PartsMatcher-shaped hole.
- **Electronics UX is clunky** (Ben's word, from real use), and the
  shopping-list links never opened in a browser anywhere — the purchase
  affordance is broken in practice, which makes "net of what you own"
  land even harder: the best shopping list is a shorter one.

### The seams already exist, on both sides

- **HEPH's output:** `out/bom.json` is structured — lines of
  `{key, description, qty, category, note, url, unit_usd}`. The adapter to
  the matcher's `{name, quantity}` contract is a dozen lines. The neutral
  v0 interchange below survives as the format for any *other* generator;
  for HEPH the contract is "adapter over `bom.json`".
- **HEPH's input:** `parts.load_overrides("my-parts.json")` — a documented
  hook for user-supplied catalogue entries. So the integration runs both
  directions: BOM → PartsMatcher ("you own 3 of these 5; short an L298N —
  but you have an L293D, want the substitution?"), and inventory → a
  generated overrides file, so HEPH designs around the drawers from the
  start.
- **The vocabulary bridge has a live test fixture.** Ben's real inventory
  vs. HEPH's catalogue ids: "HC-SR04 ultrasonic sensor" ↔ `hcsr04`,
  "TT gear motor" ↔ `tt_motor`, "SG90 micro servo" ↔ `sg90` — while the
  Arduino **Uno** (Ben's main board) is absent from the catalogue
  (`arduino_nano` only), and Ben's L293D sits adjacent to `l298n`/`tb6612`.
  Layers 2–3 below are demonstrable today with files on this machine.

### Layered scope, ascending difficulty — each layer shippable alone

1. **Catalogue expansion:** new component entries with real hole patterns,
   keepouts, power figures and honest confidence tiers. High value,
   cleanly scoped, touches nothing in HEPH's core — and the author has
   already accepted Ben's help, so this can start immediately.
2. **Check API** (`check_bom`) + the `bom.json` adapter: a thin wrapper
   over `matcher.py`. Days. A local demo — hatrack `bom.json` vs. the real
   bench inventory — is an afternoon.
3. **Vocabulary bridging:** HEPH says `l298n`; an inventory says "L293D
   motor driver". Exact-match fails machine-to-machine constantly. This is
   reconcile industrialized, seeded by the alias dataset — the hard,
   valuable middle.
4. **Substitution modeling:** parked in ROADMAP "Later," **promoted to
   core by this integration**. The bench sessions hand-applied
   Uno-for-Nano across 9 projects; a generator needs it automatic and
   honest ("Uno works here: same 5V logic; check enclosure fit").
   Electrical-compatibility reasoning is the domain expertise Ben brings.
5. **Wiring validation** (proposed runs vs. actual pinouts): further out,
   same shape — though HEPH's netlist/harness layer means this is closer
   than it looked before inspection.

**Boundary to fix in writing before code:** friendly acceptance of help is
not a scope agreement. The clean line stands: HEPH emits a BOM in an
agreed format; PartsMatcher owns everything from BOM to bench. Catalogue
entries (layer 1) are contributions *into* HEPH and should be licensed/
credited explicitly; layers 2–5 are PartsMatcher's, reached through the
contract.

Neutral BOM interchange (v0, for generators that aren't HEPH — it *is* the
existing projects schema plus provenance):

```json
{
  "bom": [
    {"name": "0.1uF ceramic capacitor", "quantity": 4,
     "package": "0603", "role": "decoupling", "substitutable": true}
  ],
  "source": {"generator": "<name>", "design_id": "...", "date": "..."}
}
```

`name`/`quantity` are required and match the matcher's contract today;
the rest is optional context for layers 3–4.

## What happens to the existing code

- **`matcher.py` — unchanged, and now the core of a service.** Its
  docstring's promise ("no I/O... reusable by other frontends") pays out a
  second time. **Still do not port it to JavaScript** — it runs
  server-side behind MCP.
- **The inventory/projects schema — is the contract**, verbatim, for the
  app, the MCP tools, and the BOM check alike.
- **The alias dataset — becomes the moat.** Every reconcile and
  correction across the user base flows through `log_alias`, growing the
  photo→canonical-name corpus with consent baked into the product's
  purpose. No competitor shortcuts owner-labeled drawer photos.
- **`chat.py` protocol prose — source text** for MCP tool descriptions
  and server instructions, same composition move MOBILE.md planned for
  SKILL.md.
- **`app/` — stays frozen** as the personal desk surface. The sync/recover
  family stays demoted; git-and-DB replace its jobs on every commercial
  path.
- **The bench repo — continues as-is**: Ben's daily driver, the dataset
  collector, and the living reference implementation of the BYO pattern.

## Open questions for Ben

1. **Pricing and the free tier.** Capture + inventory free, connector
   paid? Storage caps? The builder half costs us ~nothing to serve — is
   it a paid feature anyway, because it's the value?
2. **Which clients to certify first?** Claude app + Claude Code first
   (known surfaces), ChatGPT second? Each needs its own onboarding doc.
3. **Does the personal edition stay public** once a commercial fork
   exists? (The Commercial ToS obligation from MOBILE.md attaches to
   distributing software that *runs* Claude Code — the personal `app/`
   surface — regardless.)
4. **The HEPH conversation.** The format questions answered themselves at
   inspection (`bom.json` out, `load_overrides` in, catalogue ids as the
   vocabulary). What remains is the human part: the ownership boundary
   above agreed in writing, whether HEPH's author wants `check_bom` called
   from inside HEPH or PartsMatcher consuming `out/` from outside, and
   whether catalogue contributions land upstream or via an overrides pack
   PartsMatcher ships. Also worth raising: the broken shopping-link
   affordance — if PartsMatcher supplies the net-of-owned shopping list,
   that UX problem may be ours to solve, not theirs.
5. **Consent and privacy for the alias/photo corpus.** Opt-in wording,
   what's retained, whether photos ever train anything beyond the user's
   own inventory.
6. **Name and entity.** "PartsMatcher" the OSS tool vs. the commercial
   product; whether the SaaS needs its own name.

## Hazards to carry forward

- **Platform dependency, eyes open.** The builder conversation lives in
  Claude's/ChatGPT's UI — their surface, their changes. Blast radius if a
  surface moves: "the connector needs re-onboarding," never "the product
  breaks" — capture, DB, and matcher stand alone. (Same consolation
  MOBILE.md recorded for Remote Control.)
- **Onboarding friction is real.** "Open Claude → add connector → sign in
  to PartsMatcher" costs top-of-funnel users. One-time, and both vendors
  keep sanding it, but design the app to be worth keeping before the
  connector is ever added.
- **A model subscription is a soft prerequisite** for the builder half.
  Capture and inventory must be fully useful without one.
- **Prompt injection through BOMs and fetched pages** now crosses a trust
  boundary: `check_bom` input arrives from third-party generators. The
  server treats BOMs as data — validate against schema, never echo into
  tool descriptions or instructions.
- **The append-only alias contract** graduates from prose to a server
  guarantee: `log_alias` appends; no tool mutates history.
- **Don't let the MCP server grow a second matcher.** Every verdict path
  goes through `matcher.py`; the moment a tool "helpfully" recomputes a
  match, the determinism story is gone.
