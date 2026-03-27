---
name: card-layout
description: Generate print-ready card faces for tabletop games from structured data (CSV, XLSX, or markdown tables). Use this skill whenever someone wants to create card layouts, card templates, print sheets, card faces, or prototype cards for a card game or board game. Also trigger when someone says "lay out my cards", "generate cards from a spreadsheet", "make a print sheet", "card template", "print and play", "PnP cards", or has a CSV/spreadsheet of card data and wants to turn it into physical cards. Handles template definition, per-card rendering at 300 DPI, and imposition onto print-ready PDF sheets with bleed, crop marks, and gutters.
---

# Card Layout & Templating

Turn a spreadsheet of card data into print-ready card faces and PDF print sheets. This skill handles the full pipeline: read structured data, apply a visual template, render each card as a high-resolution PNG, and arrange them onto pages ready for cutting and sleeving.

## How This Skill Works

The pipeline has three phases:

1. **Data Ingestion** — Read card data from CSV, XLSX, or markdown tables. Auto-detect the format.
2. **Template & Render** — Define zones on the card (title, cost, art, body text, stats), then render every card to PNG at 300 DPI using Pillow.
3. **Imposition** — Arrange the card PNGs onto letter/A4 print sheets with bleed, crop marks, and gutters, output as a PDF.

Each phase builds on the previous one. Don't skip ahead — bad data parsing or a bad template will cascade into unusable output.

---

## Phase 1: Data Ingestion

### Supported Formats

Auto-detect input format by file extension and content:

| Format | Detection | Library |
|--------|-----------|---------|
| `.csv` / `.tsv` | File extension | `csv` (stdlib) or `pandas` |
| `.xlsx` | File extension | `openpyxl` |
| `.md` / `.txt` | Pipe-delimited table inside the file | Regex parser |

Install dependencies as needed:
```bash
pip install openpyxl Pillow reportlab --break-system-packages
```

### Reading the Data

Parse into a list of dictionaries — one dict per card. Every key is a column header, every value is the cell content as a string.

```python
import csv, re
from pathlib import Path

def read_card_data(filepath):
    path = Path(filepath)
    if path.suffix == '.csv':
        with open(path) as f:
            return list(csv.DictReader(f))
    elif path.suffix == '.tsv':
        with open(path) as f:
            return list(csv.DictReader(f, delimiter='\t'))
    elif path.suffix == '.xlsx':
        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        return [
            {h: (row[i].value or '') for i, h in enumerate(headers)}
            for row in ws.iter_rows(min_row=2)
            if any(cell.value for cell in row)
        ]
    else:
        # Try markdown table extraction
        text = path.read_text()
        return parse_markdown_table(text)

def parse_markdown_table(text):
    lines = [l.strip() for l in text.strip().split('\n')
             if l.strip() and not re.match(r'^[\s|:-]+$', l.strip())]
    # Find pipe-delimited lines
    table_lines = [l for l in lines if '|' in l]
    if len(table_lines) < 2:
        return []
    headers = [h.strip() for h in table_lines[0].split('|') if h.strip()]
    rows = []
    for line in table_lines[1:]:
        if re.match(r'^[\s|:-]+$', line):
            continue
        vals = [v.strip() for v in line.split('|') if v.strip() or line.count('|') > 1]
        # Handle empty cells from split
        raw = line.split('|')[1:-1] if line.startswith('|') else line.split('|')
        vals = [v.strip() for v in raw]
        if len(vals) == len(headers):
            rows.append(dict(zip(headers, vals)))
    return rows
```

### Column Mapping

After reading the data, identify which columns map to which template zones. Use these heuristics (case-insensitive):

| Zone | Common column names |
|------|-------------------|
| **name** / **title** | name, title, card_name, card |
| **type** / **category** | type, category, kind, class, faction |
| **cost** | cost, mana, energy, price, value |
| **body** / **ability** | text, ability, effect, body, description, power |
| **flavor** | flavor, flavor_text, quote, lore |
| **stats** | attack, defense, hp, health, rank, strength, speed |
| **art** | art, image, illustration, image_path, art_path |
| **count** | count, copies, qty, quantity |

If a column doesn't match any heuristic, ask the user what it maps to. The `count` column controls how many copies of that card appear on the print sheet (default: 1).

Present the mapping to the user before rendering: "Here's how I'm reading your card data — does this look right?" This avoids rendering 50 cards only to discover the ability text was mapped to the wrong column.

---

## Phase 2: Template & Render

### Card Sizes

See `references/card-sizes.md` for the full table of standard sizes with pixel dimensions at 300 DPI, including bleed. If the user doesn't specify a size, default to **Poker (2.5" × 3.5")**.

### Defining the Template

A template is a set of rectangular zones on the card, each assigned a data column and rendering rules. Think of it like a form layout — every card uses the same template, but the content in each zone changes per card.

The template should be defined as a Python data structure for clarity:

```python
# Example template zones for a simple card game
template = {
    "card_size": "poker",        # from references/card-sizes.md
    "background": "#FFFFFF",
    "border": {"width": 3, "color": "#333333", "radius": 24},
    "zones": [
        {
            "name": "title",
            "type": "text",
            "bounds": (60, 36, 690, 108),  # (x, y, width, height) in px
            "font": "bold",
            "font_size": 48,
            "color": "#1A1A1A",
            "align": "center",
            "column": "name",            # which data column feeds this zone
        },
        {
            "name": "type_line",
            "type": "text",
            "bounds": (60, 150, 690, 54),
            "font": "regular",
            "font_size": 30,
            "color": "#666666",
            "align": "center",
            "column": "type",
        },
        {
            "name": "art",
            "type": "image",
            "bounds": (60, 216, 690, 420),
            "placeholder_color": "#E0E0E0",
            "placeholder_label": "ART",
            "column": "art",             # optional — if no image, show placeholder
        },
        {
            "name": "body_text",
            "type": "text",
            "bounds": (60, 660, 690, 270),
            "font": "regular",
            "font_size": 33,
            "color": "#1A1A1A",
            "align": "left",
            "column": "ability",
            "wrap": True,
        },
        {
            "name": "flavor",
            "type": "text",
            "bounds": (60, 940, 690, 72),
            "font": "italic",
            "font_size": 28,
            "color": "#888888",
            "align": "center",
            "column": "flavor",
            "wrap": True,
        },
    ],
}
```

### Template Design Principles

When building the template for a specific game, follow these guidelines:

**Zone sizing is content-driven.** Look at the actual data before committing to zone dimensions. If the longest ability text is 120 characters, the body zone needs to be taller than if the longest is 40 characters. Scan the data first:

```python
max_body = max(len(str(card.get('ability', ''))) for card in cards)
# If max_body > 100 chars, allocate at least 300px height for body zone at 33px font
```

**Title and type always go at the top.** Players identify cards top-down. Name first, type/category second.

**Cost goes top-right or top-left corner.** It should be visible when cards are fanned in hand (only the top-left corner shows). If the game has a cost mechanic, put it there.

**Body text gets the most vertical space.** Ability text is the most variable-length content. Give it room and use text wrapping. If text overflows, shrink the font incrementally (down to the minimum in the card-sizes reference) rather than clipping.

**Stats go at the bottom.** Attack/defense, rank, HP — these belong in the footer zone where they're easy to compare when cards are side by side.

**Flavor text is optional and goes last.** It's the first thing to drop if space is tight.

**Color-code by type or faction.** If the data has a type/faction/color column, use it to tint the card background, title bar, or border. This makes cards instantly identifiable by category. Use light tints (10-15% opacity blend toward white) so text stays readable.

### Rendering Each Card

Use Pillow to render each card. The rendering loop:

```python
from PIL import Image, ImageDraw, ImageFont

def render_card(card_data, template, fonts, card_size_px):
    img = Image.new('RGB', card_size_px, template['background'])
    draw = ImageDraw.Draw(img)

    # Draw border if specified
    if 'border' in template:
        b = template['border']
        draw.rounded_rectangle(
            [(b['width']//2, b['width']//2),
             (card_size_px[0] - b['width']//2, card_size_px[1] - b['width']//2)],
            radius=b.get('radius', 0),
            outline=b['color'],
            width=b['width']
        )

    # Render each zone
    for zone in template['zones']:
        value = str(card_data.get(zone.get('column', ''), ''))
        if not value:
            if zone['type'] == 'image':
                draw_placeholder(draw, zone, fonts)
            continue

        x, y, w, h = zone['bounds']

        if zone['type'] == 'text':
            render_text_zone(draw, value, x, y, w, h, zone, fonts)
        elif zone['type'] == 'image':
            render_image_zone(img, value, x, y, w, h, zone)

    return img
```

**Font loading** — same priority as the player-aid skill:
1. Check for fonts bundled with the skill or in `./fonts/`
2. System fonts: Liberation Sans > DejaVu Sans > Noto Sans
3. Load Regular, Bold, and Italic weights

**Text wrapping** — use pixel-based wrapping, not character-count estimates. Measure each word with `draw.textbbox()`:

```python
def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
```

**Overflow handling** — if wrapped text exceeds the zone height:
1. Try reducing font size by 2px increments (down to the minimum from card-sizes.md)
2. If still overflowing, truncate with "..." and warn the user which cards overflowed

**Art zones** — if the card data has an image path and the file exists, scale and crop it to fill the zone (maintaining aspect ratio, center-crop). If no image is provided or the file doesn't exist, draw a labeled placeholder box:

```python
def draw_placeholder(draw, zone, fonts):
    x, y, w, h = zone['bounds']
    color = zone.get('placeholder_color', '#E8E8E8')
    draw.rounded_rectangle([(x, y), (x + w, y + h)], fill=color, radius=8)
    label = zone.get('placeholder_label', 'IMAGE')
    font = fonts.get('regular_small')
    bbox = draw.textbbox((0, 0), label, font=font)
    lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x + (w - lw)//2, y + (h - lh)//2), label, fill='#AAAAAA', font=font)
```

### Saving Individual Cards

Save each card as a PNG at 300 DPI:

```python
img.save(f'{card_name}.png', dpi=(300, 300))
```

**Naming convention:** Use the card's name column, slugified: `fire-dragon.png`, `healing-potion.png`. If names aren't unique, append an index: `fire-dragon-1.png`, `fire-dragon-2.png`.

---

## Phase 3: Imposition (Print Sheets)

See `references/print-sheets.md` for detailed imposition specs. This phase arranges individual card PNGs onto full pages for printing.

### What Imposition Does

Takes your rendered card PNGs and places them in a grid on letter-size (or A4) pages with:
- **Bleed** — cards are rendered slightly oversized so trimming doesn't leave white edges
- **Crop marks** — thin lines at each card corner showing where to cut
- **Gutters** — small gaps between cards for the cutting tool

### The Imposition Script

Build a PDF using reportlab that places cards in a grid:

```python
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def impose_cards(card_images, card_size_inches, output_pdf,
                 page_size=letter, gutter=0.125):
    """
    card_images: list of PIL Image objects (or file paths)
    card_size_inches: (width, height) in inches
    gutter: space between cards in inches
    """
    page_w, page_h = page_size
    card_w = card_size_inches[0] * inch
    card_h = card_size_inches[1] * inch
    gut = gutter * inch

    # Calculate grid
    cols = int((page_w - 0.5 * inch) // (card_w + gut))  # 0.25" margin each side
    rows = int((page_h - 0.5 * inch) // (card_h + gut))

    # Center the grid on the page
    grid_w = cols * card_w + (cols - 1) * gut
    grid_h = rows * card_h + (rows - 1) * gut
    x_offset = (page_w - grid_w) / 2
    y_offset = (page_h - grid_h) / 2

    c = canvas.Canvas(output_pdf, pagesize=page_size)
    card_idx = 0

    while card_idx < len(card_images):
        for row in range(rows):
            for col in range(cols):
                if card_idx >= len(card_images):
                    break
                x = x_offset + col * (card_w + gut)
                y = page_h - y_offset - (row + 1) * card_h - row * gut
                # Draw the card
                c.drawImage(card_images[card_idx], x, y,
                           width=card_w, height=card_h)
                # Draw crop marks
                draw_crop_marks(c, x, y, card_w, card_h)
                card_idx += 1
        c.showPage()

    c.save()
```

### Respecting Card Counts

If the data includes a `count` / `copies` / `qty` column, repeat that card image the specified number of times in the imposition. A card with `count: 3` should appear three times on the print sheet.

### Output

Always produce:
1. **Individual card PNGs** in a `cards/` subdirectory
2. **Print sheet PDF** with all cards imposed — named `{game-name}-print-sheet.pdf`

Tell the user:
- Total card count (including copies)
- How many print sheet pages were generated
- The grid layout (e.g., "3×3 poker cards per letter page")
- Print instructions: "Print at Actual Size on letter paper. Cut along the crop marks."

---

## Common Pitfalls

**Mapping the wrong column.** Always confirm the column mapping with the user before rendering all cards. One wrong mapping means re-rendering everything.

**Text overflow on a few cards.** Most cards might fit fine, but a few with long ability text overflow. Scan all cards for the longest text in each zone before finalizing zone sizes. Design the template for the longest content, not the average.

**Forgetting card counts.** If someone has 4 copies of a "Basic Land" card, the print sheet needs to show it 4 times. Don't just render unique cards.

**Art path issues.** Image paths in spreadsheets are often relative or wrong. Resolve paths relative to the data file's directory, and fall back to placeholders gracefully rather than crashing.

**DPI mismatch.** Always render at 300 DPI and set the metadata. If someone provides art at 72 DPI, warn them it will look pixelated at print size.

**Color-coding without contrast check.** When tinting cards by faction/type color, make sure the body text zone still has sufficient contrast. Dark text on a light tint is safe; dark text on a saturated background is not.
