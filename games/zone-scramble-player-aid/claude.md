# Project: Refine the `player-aid` Skill

## Context

You have a draft skill in the `player-aid/` folder. This skill teaches Claude how to create print-ready player aid cards (reference cards, cheat sheets) for tabletop games. It was written collaboratively but has not been tested against real game rules yet.

Your job is to review the skill, test it against the game rules files in this folder, and improve it based on what you learn.

## What's in this folder

- `player-aid/SKILL.md` — The skill definition (the main deliverable)
- `player-aid/references/game-archetypes.md` — Content plan templates for common game types
- `claude.md` — This file (your instructions)
- Any `.md`, `.txt`, `.pdf`, or `.docx` files — These are game rules to test the skill against

## Your tasks

### 1. Review the skill for structural issues

Read `player-aid/SKILL.md` carefully. Check for:
- Are the instructions clear and unambiguous?
- Is the content triage system (Tier 1–4) practical?
- Are the print specifications correct (DPI math, font size conversions)?
- Are there gaps — things a Claude instance would need to know but aren't covered?
- Is the skill under 500 lines? (It should be.)
- Does the description in the YAML frontmatter trigger on the right phrases?

Fix anything you find. Note what you changed and why.

### 2. Test the skill against real game rules

For each set of game rules in this folder:
1. Read the rules thoroughly
2. Follow the skill's Phase 1 (Content Audit) — produce a content plan with tiers
3. Follow the skill's Phase 2 (Layout and Rendering) — generate a 4" × 5" (1200 × 1500 px) player aid PNG at 300 DPI
4. Follow the skill's Phase 3 (Output and Delivery) — save the PNG

After generating each card, evaluate your own output:
- Is all text legible at print size (≥ 8pt / 33px)?
- Is the most important information (turn structure, actions) prominent?
- Does the card feel full but not cramped?
- Would a player actually find this useful mid-game?
- Did the skill's instructions lead you in the right direction, or did you have to improvise?

### 3. Revise the skill based on what you learned

Update `player-aid/SKILL.md` with improvements. Common things to fix:
- Instructions that were confusing or led to bad output
- Missing guidance you had to figure out yourself
- Font size recommendations that didn't work in practice
- Layout patterns that didn't fit real game content
- Content triage rules that miscategorized important information

### 4. Verify the folder name and skill name are correct

The skill is designed to be installed as a Cowork user skill. Confirm:
- The folder is named `player-aid/`
- The file is named `SKILL.md` (not renamed)
- The YAML frontmatter `name:` field matches the folder name
- The `references/` subfolder and its contents are intact

### 5. Output

Save all final files in place:
- Updated `player-aid/SKILL.md`
- Updated `player-aid/references/game-archetypes.md` (if you improved it)
- All generated player aid PNGs (save alongside the rules files they came from)

## Important notes

- The PNGs must have DPI metadata set: `img.save('file.png', dpi=(300, 300))`
- Use `pip install Pillow --break-system-packages` if Pillow isn't available
- Look for system fonts (DejaVu Sans is usually available at `/usr/share/fonts/`) before falling back to Pillow defaults
- The player aid cards are meant to be printed on a color printer and placed in Apple Pages or similar software — physical print size matters
