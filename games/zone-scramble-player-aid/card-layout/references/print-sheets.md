# Print Sheet Imposition Reference

How to arrange card images onto full pages for printing, cutting, and sleeving.

## Page Sizes

| Name | Inches | Points (reportlab) |
|------|--------|--------------------|
| US Letter | 8.5 × 11 | 612 × 792 |
| A4 | 8.27 × 11.69 | 595.28 × 841.89 |

Default to US Letter unless the user specifies otherwise.

## Layout Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| Page margin | 0.25" | Space from page edge to first card |
| Gutter | 0.125" | Space between adjacent cards |
| Bleed | 0.125" per side | Only for professional print — extends card art past trim |
| Crop mark length | 0.15" | Short lines at card corners |
| Crop mark offset | 0.06" | Gap between mark and card edge |
| Crop mark color | #AAAAAA | Light gray, 0.5pt line weight |

## Imposition Modes

### Home Print (Default)

For printing on a home color printer, cutting with scissors or a paper trimmer.

- No bleed — cards are rendered at exact trim size
- Crop marks at all four corners of each card
- Gutters between cards (makes cutting easier)
- Center the grid on the page
- Print at "Actual Size" / 100% scale

### Professional Print

For submission to a print-on-demand service (The Game Crafter, DriveThruCards, MakePlayingCards).

- Cards rendered with 0.125" bleed on all sides (art extends past trim)
- Crop marks show trim lines
- Each service may have specific submission formats — check their specs
- Some services want individual card images, not imposed sheets

### Print-on-Demand Service Specs

| Service | Format | Bleed | Resolution | Notes |
|---------|--------|-------|------------|-------|
| The Game Crafter | Individual PNG | 0.125" | 300 DPI | Upload per-card, they handle imposition |
| DriveThruCards | Individual PNG/PDF | 0.125" | 300 DPI | Similar to TGC |
| MakePlayingCards | Individual PNG | 36px (0.12") | 300 DPI | Slightly less bleed |
| PrinterStudio | Individual PNG | 0.125" | 300 DPI | Various card sizes |

For POD services, skip imposition — just provide individual card PNGs with bleed. Mention this to the user if they say they're submitting to a POD service.

## Crop Mark Drawing

```python
def draw_crop_marks(c, x, y, card_w, card_h,
                    mark_len=0.15, mark_offset=0.06,
                    color='#AAAAAA', weight=0.5):
    """Draw L-shaped crop marks at each corner of a card.

    Args:
        c: reportlab canvas
        x, y: bottom-left corner of the card (in points)
        card_w, card_h: card dimensions (in points)
        mark_len: length of each mark line (inches)
        mark_offset: gap between mark and card edge (inches)
    """
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor

    c.setStrokeColor(HexColor(color))
    c.setLineWidth(weight)
    ml = mark_len * inch
    mo = mark_offset * inch

    corners = [
        (x, y, -1, -1),              # bottom-left
        (x + card_w, y, 1, -1),      # bottom-right
        (x, y + card_h, -1, 1),      # top-left
        (x + card_w, y + card_h, 1, 1),  # top-right
    ]
    for cx, cy, dx, dy in corners:
        c.line(cx + dx * mo, cy, cx + dx * (mo + ml), cy)  # horizontal
        c.line(cx, cy + dy * mo, cx, cy + dy * (mo + ml))  # vertical
```

## Double-Sided Printing

For cards with front and back faces:

- **Page N** = fronts, **Page N+1** = backs
- Back page cards must be in **mirrored column order** for short-edge duplex to align correctly
- Tell the user: "Print duplex with short-edge flip"
- If only one back design (shared card back), repeat it for every card position

### Back Page Mirroring

When printed duplex with short-edge flip, the back of column 1 aligns with the front of column 1 only if the back row is reversed left-to-right:

```
Front page:  [A] [B] [C]
Back page:   [C] [B] [A]   ← mirrored
```

This ensures that when you flip the sheet along the short edge, each front aligns with its back.

## Registration Marks (Optional)

For precise front-back alignment on professional prints, add small crosshair marks (+) at the four corners of the page, outside the card grid. These help the printer align front and back sheets.

```python
def draw_registration(c, page_w, page_h, margin=0.15):
    """Draw registration crosshairs at page corners."""
    from reportlab.lib.units import inch
    m = margin * inch
    size = 0.1 * inch
    positions = [(m, m), (page_w - m, m),
                 (m, page_h - m), (page_w - m, page_h - m)]
    c.setStrokeColor(HexColor('#000000'))
    c.setLineWidth(0.25)
    for px, py in positions:
        c.line(px - size, py, px + size, py)
        c.line(px, py - size, px, py + size)
```
