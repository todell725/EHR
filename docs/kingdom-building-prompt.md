# Kingdom Building Expansion — Brief for kimi

You are expanding the kingdom management dashboard for **EmberHeart Reborn**
(`/Users/todd/Projects/EmberHeartReborn`). Read `project-EmberHeartReborn.md` in the
docs folder before starting — you've already done this once so you know the codebase.
The kingdom is **The Kingdom of EmberHeart**, a frost-frontier divine hearth-realm ruled
by the God-Ascendant Flamekeeper Kaelrath and Queen Talmarr.

---

## What you're doing

Replace the current `BUILDINGS` dict in `backend/sim/kingdom.py` with the full catalog
below. Each building needs:

- `label` — display name
- `desc` — one-sentence flavour description
- `cost` — dict of `lumber / ore / treasury` (and optionally `stone`)
- `turns` — construction time in ticks
- `effect` — permanent stat changes applied on completion
- `requires` — list of building keys that must already be built (empty list if none)
- `category` — one of: `defense`, `divine`, `leadership`, `sustenance`, `industry`, `civilian`, `infrastructure`
- `ongoing` — optional dict of recurring per-tick bonus keys (e.g. `food_cap_mult`, `craft_bonus`, `market_income`) — these must be **read by `economy.py`'s tick**, not stored as dead keys

Update the **Kingdom tab UI** to display buildings organised by category rather than a
flat list. Show locked buildings as greyed-out with the prerequisite listed.

---

## Hard constraints — read before touching anything

- `SCHEMA_VERSION` is currently **8** — any new migration must be **v9**
- `economy.py` was recently rewritten with a starvation fix — do **NOT** revert it; build on it
- `get_domain()` / `set_domain()` must remain the public API for the domain ledger
- Edit `KingdomPane` in `app.js` **surgically** — do not rewrite the whole file; other
  panes (Inventory, Journal, Ascension, Mount, Idle) live in the same file
- The `KINGDOM_CHANGE` mechanic in `mechanics.py` reads
  `morale / treasury / military / population / infrastructure / stockpiles` — keep those
  field names stable or ping the senior dev to re-sync
- All **105 existing tests** must still pass; add new ones for any new building logic
- The `economy.py` tick already reads `food_cap_mult`, `craft_bonus`, and
  `"market" in built` — extend that same pattern for new ongoing effects; do not
  introduce dead keys

---

## Pre-existing / already-built buildings

Seed these into `domain["buildings"]` on kingdom founding (or via migration) so they
appear as "already built" in the UI from day one:

- `blood_wall` — The Geomantic Ring
- `ember_vault` — The Ember-Vault (Heart Chamber)
- `god_forge` — The God-Forge

---

## The full building catalog

### INFRASTRUCTURE (build these first — they unlock everything else)

| Key | Label | Notes |
|-----|-------|-------|
| `hearth_channels` | Hearth-Channels | The geothermal distribution network. **Prerequisite** for Aquaculture Basins, Greenhouses, Bathhouse, Ring-Housing. Without it those buildings can't function. Low cost, massive unlock value. |
| `ember_cisterns` | Ember Cisterns | Heated underground water reserves. Requires `hearth_channels`. Enables Bathhouse; gives siege resilience (softens border skirmish morale/food penalties). |
| `quarry_works` | Quarry Works | Extraction face, hauling ramps, block-cutting. **Prerequisite** for Mason's Yard, Scout's Perches, Void-Ward Stones, Smelting Hall. Generates passive stone/ore income each tick. |

---

### THE PERIMETER AND DEFENSE

| Key | Label | Notes |
|-----|-------|-------|
| `blood_wall` | The Geomantic Ring (The Blood-Wall) | Already built. 15-ft black stone barrier mortared with Kaelrath's life. Foundational passive defense. |
| `ironwood_gatehouse` | The Ironwood Gatehouse | Reinforced timber and iron primary entry. Requires `blood_wall`. |
| `wardens_redoubt` | The Warden's Redoubt and Barracks | Command post and militia housing against the inner wall. Requires `ironwood_gatehouse`. Military boost. |
| `scouts_perches` | Scout's Perches | Insulated stone watchtowers with archer slits. Requires `quarry_works`. |
| `sally_port` | The Sally Port | Narrow secondary gate hidden in the wall's curve. For sorties and emergency supply runs. Requires `ironwood_gatehouse`. |
| `void_ward_stones` | The Void-Ward Stones | Rune-carved basalt markers beyond the wall, anchored to the EmberHeart's pulse. Early warning against ley-touched or void-scarred threats. Requires `scouts_perches`. |
| `signal_braziers` | Signal Braziers | Wall-linked warning fires completing the early-warning network. **Upgrade** — requires `scouts_perches` + `void_ward_stones`. Military bonus; reduces chance of being surprised by skirmish/void events. |

---

### THE DIVINE CORE

| Key | Label | Notes |
|-----|-------|-------|
| `ember_vault` | The Ember-Vault (The Heart Chamber) | Already built. Underground vault housing the EmberHeart and Sol-Thairn. |
| `god_forge` | The God-Forge | Already built. The sprawling open-air stone smithy that never goes cold. Passive morale bonus to all who live here. |
| `ash_pit` | The Ash-Pit | Sacred disposal for failed forgings and funeral pyres. Requires `god_forge`. Small morale bonus (grief has a home). |
| `offering_steps` | The Offering Steps | Broad stone stairway to the Ember-Vault where citizens leave offerings to Sol-Thairn. Morale and faith bonus. |
| `pilgrims_court` | The Pilgrim's Court | Sheltered forecourt for supplicants, mourners, and oath-taking. **Upgrade** — requires `offering_steps`. Larger morale and infrastructure bonus; deepens EmberHeart's faith culture. |
| `shardwork` | The Shardwork | Dedicated ember-glass workshop where Bheric and Sol-Thairn work harvested shards and the Elder's Heart into relics and armor. Requires `god_forge`. Unique to EmberHeart — boosts infrastructure and unlocks special crafting. |

---

### LEADERSHIP AND ADMINISTRATION

| Key | Label | Notes |
|-----|-------|-------|
| `hearth_hall` | The Hearth-Hall | Central gathering place, dining hall, and seat of the King and Queen. Morale and treasury bonus. |
| `loremaster_archive` | The Loremaster's Archive | Climate-controlled stone building for vellum, ciphers, and lore. Run by Sella. Requires `quarry_works`. Infrastructure bonus. |
| `hearthkeepers_lodge` | The Hearthkeeper's Lodge | Administrative centre for rationing food, wood, and medical supplies. Run by Orina. Food efficiency bonus. |
| `war_table` | The War Table | Stone annexe with a carved relief map of surrounding territories. Renn briefs the council here. Requires `wardens_redoubt`. Military bonus. |
| `royal_quarters` | The Royal Quarters | The king and queen's private rooms directly above the Ember-Vault. Modest in size — a hearth-god lives among his people. Morale bonus. |

---

### SUSTENANCE AND LIFE SUPPORT

| Key | Label | Notes |
|-----|-------|-------|
| `grand_granaries` | The Grand Granaries | Fortified raised dry-stone silos. Significant food cap increase (`food_cap_mult`). Requires `quarry_works`. |
| `aquaculture_basins` | Geothermal Aquaculture Basins | Stone-lined indoor tanks heated by the EmberHeart. Passive food income each tick. Requires `hearth_channels`. |
| `greenhouses` | Hearth-Warmed Greenhouses | Glass and timber lean-tos against the forge for herbs and vegetables. Herb/supply yield bonus. Requires `hearth_channels` + `god_forge`. |
| `smokehouse` | The Hunter's Smokehouse | Large curing shed for processing Frost Bucks and heavy game. Extends effective food value; raw_meat → cooked_meal efficiency bonus. |
| `root_cellar_network` | The Root Cellar Network | Frost-cut tunnels for cold storage of root vegetables and salted game. Softens crop failure seasonal events. |
| `brewery` | The Brewery | Communal ale and mead house. Run by Orina. Significant morale boost; recurring morale income each tick. Requires `hearth_hall`. |
| `sled_house` | The Sled House and Winter Stores | Frontier hauling and deep-cold logistics. Softens shortage and crop failure seasonal event penalties. Enables supply and refugee movement through heavy snow. |
| `ember_cisterns` | Ember Cisterns | *(see Infrastructure above)* |

---

### INDUSTRY AND CRAFT

| Key | Label | Notes |
|-----|-------|-------|
| `carpenters_mill` | The Carpenter's Mill and Lumber Yard | Wood processing, framing, furniture. Lumber output bonus. |
| `tannery` | The Tannery and Leatherworks | Boiling and tanning monster hides into cold-resistant armor. Supplies bonus. Requires `char_pit`. |
| `masons_yard` | The Mason's Yard | Hub for stonecraft, mining tools, basalt block staging. Requires `quarry_works`. Reduces stone cost on future buildings. |
| `weavers_guild` | The Weaver's Guild | Longhouse for spinning wool, canvas, and winter clothing. Morale and supplies bonus. |
| `smelting_hall` | The Smelting Hall | Bulk ore smelting at scale, separate from the God-Forge. Ore output and metal bar income. Requires `masons_yard`. |
| `stables_mews` | The Stables and Mews | Housing for Cindermane and mounts, with a falcon mews above. Cindermane's stall is built first. Military and logistics bonus. |
| `beast_pens` | Beast Pens and Kennels | Expands the stable complex with pack animals, hunting hounds, and slaughter pens. **Upgrade** — requires `stables_mews`. Food output boost; reduces logistics costs. |
| `alchemists_den` | The Alchemist's Den | Orina's secondary workspace for refining herbs, frost-glands, void-essence, and fire-glands into tinctures and wards. Requires `menders_clinic`. Infrastructure and supplies bonus. |
| `char_pit` | The Char Pit and Tallow House | Produces fuel, tallow, candles, and waterproofing. Reduces Tannery costs; part of the industrial chain (hunt → smokehouse → char pit → tannery). Requires `ash_pit`. |

---

### CIVILIAN LIFE

| Key | Label | Notes |
|-----|-------|-------|
| `ring_housing` | The Ring-Housing (The Commons) | Dense stone and timber homes heated by the EmberHeart's geothermal network. Population cap increase; morale bonus. Requires `hearth_channels`. |
| `menders_clinic` | The Mender's Clinic | Sterile herbal medical ward for the sick and injured. Run by Orina. Softens population loss from food shortage events. |
| `wayfarers_hearth` | The Wayfarer's Hearth | Secure communal bunkhouse near the gate for refugees and traders. Supports population growth; small treasury income from traders. |
| `memorial_wall` | The Memorial Wall | A smooth section of the Blood-Wall's inner face carved with the names of the dead. A blank space is left — everyone knows what it's for. **Cannot be demolished.** Auto-completes (free, instant) once the kingdom has 10+ chronicle beats. Permanent morale bonus. |
| `apprentice_hall` | The Apprentice Hall | School and workshop for children and young adults. Sella teaches EmberHeart's history here. Long-term infrastructure and population quality bonus. Requires `loremaster_archive`. |
| `bathhouse` | The Bathhouse | Geothermally heated stone baths. Disease prevention and morale. Requires `hearth_channels` + `ember_cisterns`. |

---

## Economy tick integration

The `economy.py` tick must read ALL ongoing building effects — not store them as dead
keys. The current tick already handles `food_cap_mult`, `craft_bonus`, and market income.
Extend the same `_bonus(stat)` helper pattern for every new ongoing effect key you
introduce. Before shipping, verify each new ongoing effect is actually reflected in tick
output by adding a test.

## UI guidance

- Group the building catalog by category (matching the sections above) in the Buildings sub-tab
- Show a **prerequisite chain** — locked buildings greyed out, showing what they need
- The `blood_wall`, `ember_vault`, and `god_forge` show as "built" (not purchasable) from the start
- The `memorial_wall` shows as "auto-complete" with its trigger condition
- Progress bars on active projects are already implemented — keep them

## Test requirements

- All 105 existing tests must pass
- Add tests for: prerequisite blocking, `memorial_wall` auto-completion trigger, at least
  two new ongoing effects verified through the economy tick, infrastructure unlock chain

---

*Senior dev contact: if you rename any domain ledger fields, break `get_domain()/set_domain()`,
or touch `mechanics.py` / `economy.py`'s starvation fix, flag it — those have downstream
dependents that will need re-syncing.*
