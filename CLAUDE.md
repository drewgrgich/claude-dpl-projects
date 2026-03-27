# Design Play Labs

## Me
Drew (drew@grgich.org) — solo game designer and developer at Design Play Labs.

## Work Areas
Game design, development, simulation/playtesting, rules writing, playtest analysis, and project management.

## Workspace Structure
- `games/` — all game designs, each with rules and (eventually) their own simulator
  - `contests-of-chaos/` — flagship game, furthest along (has simulator, playtesting data, skill)
  - `get-stuffed/`, `hamster-high-council/`, `lockdown-protocol/`, `mystery-mascots/`, `summit-scramble/`, `tailgate-turf-war/`, `the-merch-stand-mob/`, `the-tunnel-brawl/`, `zone-scramble/`
- `hm-kickstarter/` — Hamsters & Monsters Kickstarter launch (campaign, Danny Beck deal, budget, manufacturing)
- `marketing/` — general DPL marketing (substack, website, research)
- `content-series/` — blog/newsletter content (drafts, published, voice guide)

## Active Projects
| Project | Folder | Status |
|---------|--------|--------|
| **Contests of Chaos** | `games/contests-of-chaos/` | Active — card-drafting game for 2-4 players |
| **H&M Kickstarter** | `hm-kickstarter/` | Active — Kickstarter launch for Hamsters & Monsters |
| **Game Simulators** | `games/` | Building simulators for all games, using CoC as the template |

## Contests of Chaos — Quick Reference
- 66 Recruit Cards (6 factions, ranks 0-10), 37 Event Cards (tiers 1-6), 24 Playbook Cards
- Factions: RED (Super-Dupes), ORG (Finders-Keepers), YLW (Tinkerers), GRN (Prognosticationers), BLU (Magicians), PUR (Time Travelers)
- Key files: `contests-of-chaos-rules.md` (current rules), `contests-of-chaos-rules-final copy.md` (reference), CSVs for events and playbooks
- Python simulator in `simulator/` — used for AI playtesting and balance analysis
- Game simulator skill in `game-simulator-skill/` and `game-simulator.skill`

## Preferences
- Keep files minimal and purposeful — no unnecessary boilerplate
- This workspace is shared between Claude Code and Cowork sessions
