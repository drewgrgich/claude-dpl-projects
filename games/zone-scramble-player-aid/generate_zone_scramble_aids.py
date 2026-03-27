#!/usr/bin/env python3
"""
Generate two print-ready player aid cards for Zone Scramble v2.5.

Front Card: Turn structure, core rules, scoring, win condition
Back Card: Faction powers grid (3 rows × 2 columns)

Specifications:
- Canvas: 1200 × 1500 px (4" × 5" at 300 DPI)
- Fonts: Liberation Sans Bold and Regular from /usr/share/fonts/
- Safe margin: 37px all sides
- DPI metadata: (300, 300)
"""

from PIL import Image, ImageDraw, ImageFont
import textwrap

# Constants
DPI = 300
WIDTH_PX = 1200
HEIGHT_PX = 1500
SAFE_MARGIN = 37
CONTENT_WIDTH = WIDTH_PX - (2 * SAFE_MARGIN)

# Colors
BG_COLOR = "#F5F5F0"
TEXT_COLOR = "#1A1A1A"
HEADER_BLUE = "#2B4C7E"
SECTION_BOX_BG = "#E8EDF4"
WARM_HIGHLIGHT = "#FFF3E0"

# Faction colors (at 10% opacity will be very light tints)
FACTION_COLORS = {
    "RED": "#8B2500",
    "ORANGE": "#CC6600",
    "YELLOW": "#B8860B",
    "GREEN": "#2E5339",
    "BLUE": "#2B4C7E",
    "PURPLE": "#663399",
}

# Load fonts
try:
    font_title = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 70
    )
    font_header = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 50
    )
    font_body = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 36
    )
    font_faction_header = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 42
    )
    font_faction_label = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 30
    )
    font_faction_body = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 30
    )
except Exception as e:
    print(f"Error loading fonts: {e}")
    exit(1)


def wrap_text(draw, text, font, max_width):
    """
    Wrap text to fit within max_width using pixel-based measurement.
    Returns list of lines.
    """
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        line_width = bbox[2] - bbox[0]

        if line_width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def lighten_color(hex_color, opacity=0.1):
    """
    Create a light tint of a hex color by blending with background.
    opacity: 0.0 (white) to 1.0 (full color)
    """
    # Parse hex
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)

    # Blend towards #F5F5F0 (background)
    bg_r, bg_g, bg_b = 0xF5, 0xF5, 0xF0

    r = int(bg_r + (r - bg_r) * opacity)
    g = int(bg_g + (g - bg_g) * opacity)
    b = int(bg_b + (b - bg_b) * opacity)

    return f"#{r:02X}{g:02X}{b:02X}"


def draw_section_box(draw, x, y, width, height, bg_color, border_color=None, corner_radius=12):
    """Draw a rounded rectangle section box."""
    draw.rounded_rectangle(
        [(x, y), (x + width, y + height)],
        fill=bg_color,
        outline=None,
        radius=corner_radius,
    )


def measure_section_height(draw, header_text, body_lines, font_h, font_b, max_width, padding, line_spacing):
    """Calculate the exact pixel height a section needs."""
    # Header height
    height = padding  # top padding
    bbox = draw.textbbox((0, 0), header_text, font=font_h)
    height += (bbox[3] - bbox[1]) + 12  # header text + gap below header

    # Body lines height
    for line in body_lines:
        wrapped = wrap_text(draw, line, font_b, max_width)
        height += len(wrapped) * line_spacing

    height += padding  # bottom padding
    return height


def generate_front_card():
    """Generate the front player aid card."""

    # Define all sections upfront so we can measure them
    sections = [
        {
            "title": "TURN STRUCTURE",
            "bg": SECTION_BOX_BG,
            "lines": [
                "1. Play 1 Monster to legal arena — OR Fumble the Bag — OR The Bench",
                "2. Draw 1 card (if draw pile has cards)",
                "3. May use 1 Signature Move (max 1/turn)",
            ],
        },
        {
            "title": "TURF COLOR",
            "bg": SECTION_BOX_BG,
            "lines": [
                "First Monster claims arena color. Only matching color or Chameleons (0/10) may enter.",
                "Clears when arena scores.",
                "Chameleons: Max 2/round per player. Choose color in empty arena.",
            ],
        },
        {
            "title": "THE CROWD ROARS",
            "bg": SECTION_BOX_BG,
            "lines": [
                "5th Monster → arena scores immediately.",
                "Highest total rank wins: Side arena = +1 VP / Center = +2 VP",
                "Win 2+ arenas in a round = +1 VP Momentum",
                "Tie in arena → nobody scores. Clear arena.",
            ],
        },
        {
            "title": "FUMBLE / BENCH",
            "bg": SECTION_BOX_BG,
            "lines": [
                "Fumble: Discard 1, Draw 1. Max 2/round.",
                "Bench: If locked out — reveal hand, discard 1, draw 1.",
            ],
        },
        {
            "title": "WIN CONDITION",
            "bg": WARM_HIGHLIGHT,
            "lines": [
                "Most VP after 3 rounds (6 turns each).",
                "Tiebreaker: 1) Most arenas won → 2) Highest single-arena total → 3) Most recent scorer",
            ],
        },
        {
            "title": "ROUND END",
            "bg": SECTION_BOX_BG,
            "lines": [
                "Score remaining arenas → Momentum → Discard hand → Draw 6",
            ],
        },
    ]

    img = Image.new("RGB", (WIDTH_PX, HEIGHT_PX), BG_COLOR)
    draw = ImageDraw.Draw(img)

    x_left = SAFE_MARGIN
    section_width = CONTENT_WIDTH
    section_padding = 15
    line_spacing = 42
    section_gap = 12
    inner_width = section_width - 2 * section_padding

    # Measure total content height to check fit
    # Title block: title + subtitle
    title_block_height = 85 + 50  # title line + subtitle line
    total_sections_height = sum(
        measure_section_height(draw, s["title"], s["lines"], font_header, font_body, inner_width, section_padding, line_spacing)
        for s in sections
    )
    total_gaps = section_gap * (len(sections) - 1)
    total_needed = SAFE_MARGIN + title_block_height + total_sections_height + total_gaps + SAFE_MARGIN

    # If content overflows, reduce line spacing proportionally
    if total_needed > HEIGHT_PX:
        overflow = total_needed - HEIGHT_PX
        # Count total body lines to distribute the squeeze
        total_body_lines = 0
        for s in sections:
            for line in s["lines"]:
                total_body_lines += len(wrap_text(draw, line, font_body, inner_width))
        if total_body_lines > 0:
            line_spacing = max(36, line_spacing - (overflow // total_body_lines) - 1)
            section_gap = max(6, section_gap - 2)

    # Now render
    y_cursor = SAFE_MARGIN

    # Title: "ZONE SCRAMBLE v2.5"
    title_text = "ZONE SCRAMBLE v2.5"
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_width = bbox[2] - bbox[0]
    title_x = (WIDTH_PX - title_width) // 2
    draw.text((title_x, y_cursor), title_text, fill=TEXT_COLOR, font=font_title)
    y_cursor += 85

    # Subtitle: "Player Aid"
    subtitle_text = "Player Aid"
    bbox = draw.textbbox((0, 0), subtitle_text, font=font_body)
    subtitle_width = bbox[2] - bbox[0]
    subtitle_x = (WIDTH_PX - subtitle_width) // 2
    draw.text((subtitle_x, y_cursor), subtitle_text, fill=HEADER_BLUE, font=font_body)
    y_cursor += 50

    # Render each section with dynamically measured height
    for idx, section in enumerate(sections):
        box_height = measure_section_height(
            draw, section["title"], section["lines"],
            font_header, font_body, inner_width, section_padding, line_spacing,
        )
        draw_section_box(draw, x_left, y_cursor, section_width, box_height, section["bg"])

        y_text = y_cursor + section_padding
        draw.text((x_left + section_padding, y_text), section["title"], fill=HEADER_BLUE, font=font_header)
        bbox = draw.textbbox((0, 0), section["title"], font=font_header)
        y_text += (bbox[3] - bbox[1]) + 12

        for line in section["lines"]:
            wrapped = wrap_text(draw, line, font_body, inner_width)
            for wline in wrapped:
                draw.text((x_left + section_padding, y_text), wline, fill=TEXT_COLOR, font=font_body)
                y_text += line_spacing

        y_cursor += box_height + section_gap

    # Save with DPI metadata
    output_path = "/sessions/peaceful-vigilant-fermi/mnt/zone-scramble-player-aid/zone-scramble-v2.5-player-aid-front.png"
    img.save(output_path, dpi=(300, 300))
    print("Front card saved: zone-scramble-v2.5-player-aid-front.png")


def generate_back_card():
    """Generate the back player aid card with 3×2 faction grid."""

    img = Image.new("RGB", (WIDTH_PX, HEIGHT_PX), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Title at top
    title_text = "FACTION POWERS"
    bbox = draw.textbbox((0, 0), title_text, font=font_header)
    title_width = bbox[2] - bbox[0]
    title_x = (WIDTH_PX - title_width) // 2
    draw.text((title_x, SAFE_MARGIN), title_text, fill=HEADER_BLUE, font=font_header)

    # Grid layout: 3 rows × 2 columns
    y_start = SAFE_MARGIN + 70  # Below title
    available_height = HEIGHT_PX - y_start - SAFE_MARGIN
    row_height = available_height // 3

    col_width = (CONTENT_WIDTH - 30) // 2  # 30px gutter between columns
    col_gutter = 30

    # Faction data: [name, color, personality_desc, signature_label, signature_desc]
    factions = [
        # Row 1
        (
            "RED",
            FACTION_COLORS["RED"],
            "Personality: 2+ of your Monsters in arena → highest gets +1 rank",
            "Signature: Heroic Intervention (1/rd)",
            "Move your Monster from adjacent arena here"
        ),
        (
            "ORANGE",
            FACTION_COLORS["ORANGE"],
            "Personality: First Orange in arena with no other Orange → +1 rank",
            "Signature: Big Borrow (ONCE/GAME)",
            "Lose by ≤3 → steal rank 1-5 Monster to Trophy (+1 VP)"
        ),
        # Row 2
        (
            "YELLOW",
            FACTION_COLORS["YELLOW"],
            "Personality: First 2 Monsters you play each round → each +1 rank",
            "Signature: Double-Install (1/rd)",
            "Play 2nd Monster to same arena, draw 1"
        ),
        (
            "GREEN",
            FACTION_COLORS["GREEN"],
            "Personality: Before playing, peek top card of deck — keep or discard",
            "Signature: Scheduled Outcome (1/rd)",
            "Draw 2, keep 1, discard 1"
        ),
        # Row 3
        (
            "BLUE",
            FACTION_COLORS["BLUE"],
            "Personality: When playing Blue, may return your other Monster from that arena to hand",
            "Signature: Is This Your Card? (1/rd)",
            "Swap your/opponent's Monster in same arena (ranks within 3)"
        ),
        (
            "PURPLE",
            FACTION_COLORS["PURPLE"],
            "Personality: Keep 2 cards between rounds instead of discarding all",
            "Signature: Rewind (1/rd)",
            "Take top discard if rank 1-6"
        ),
    ]

    # Render 3×2 grid
    cell_padding = 12
    line_spacing = 34

    for idx, (name, color, personality, sig_label, sig_desc) in enumerate(factions):
        row = idx // 2
        col = idx % 2

        x = SAFE_MARGIN + col * (col_width + col_gutter)
        y = y_start + row * row_height

        # Draw light tinted background for this cell
        light_color = lighten_color(color, opacity=0.08)
        draw.rounded_rectangle(
            [(x, y), (x + col_width, y + row_height)],
            fill=light_color,
            radius=8,
        )

        y_text = y + cell_padding
        x_text = x + cell_padding
        inner_width = col_width - 2 * cell_padding

        # Faction name as header
        draw.text((x_text, y_text), name, fill=color, font=font_faction_header)
        y_text += 48

        # Personality description (wrap the label + text together)
        wrapped_personality = wrap_text(draw, personality, font_faction_body, inner_width)
        # Draw "Personality:" as bold on first line
        draw.text((x_text, y_text), "Personality:", fill=color, font=font_faction_label)
        y_text += line_spacing

        for line in wrapped_personality:
            draw.text((x_text, y_text), line, fill=TEXT_COLOR, font=font_faction_body)
            y_text += line_spacing

        y_text += 6

        # Signature label — wrap it so long labels don't truncate
        wrapped_sig_label = wrap_text(draw, sig_label, font_faction_label, inner_width)
        for line in wrapped_sig_label:
            draw.text((x_text, y_text), line, fill=color, font=font_faction_label)
            y_text += line_spacing

        # Signature description
        wrapped_sig = wrap_text(draw, sig_desc, font_faction_body, inner_width)
        for line in wrapped_sig:
            draw.text((x_text, y_text), line, fill=TEXT_COLOR, font=font_faction_body)
            y_text += line_spacing

    # Save with DPI metadata
    output_path = "/sessions/peaceful-vigilant-fermi/mnt/zone-scramble-player-aid/zone-scramble-v2.5-player-aid-back.png"
    img.save(output_path, dpi=(300, 300))
    print("Back card saved: zone-scramble-v2.5-player-aid-back.png")


if __name__ == "__main__":
    print("Generating Zone Scramble v2.5 player aid cards...")
    generate_front_card()
    generate_back_card()
    print("\nBoth cards generated successfully!")
    print("Front: 1200×1500 px (4×5 inches at 300 DPI)")
    print("Back: 1200×1500 px (4×5 inches at 300 DPI)")
