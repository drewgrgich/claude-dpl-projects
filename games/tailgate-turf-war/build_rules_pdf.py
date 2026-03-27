#!/usr/bin/env python3
"""Generate the Tailgate Turf War v0.1.5 ruleset PDF with Print & Play guide."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.platypus.flowables import Flowable

# ── Colors ──
NAVY = HexColor("#1a2744")
DARK_BLUE = HexColor("#2b3e5e")
ACCENT_BLUE = HexColor("#4a7fb5")
ACCENT_GOLD = HexColor("#c9a227")
LIGHT_BG = HexColor("#f5f5f0")
ZONE_RED = HexColor("#cc3333")
ZONE_YELLOW = HexColor("#d4a017")
ZONE_GREEN = HexColor("#2d8c2d")
ZONE_BLUE = HexColor("#3366aa")
SUBTLE_GRAY = HexColor("#888888")
LIGHT_GRAY = HexColor("#dddddd")
TABLE_HEADER_BG = HexColor("#2b3e5e")
TABLE_ALT_BG = HexColor("#eef2f7")


class ColorBar(Flowable):
    """A thin colored bar for visual separation."""
    def __init__(self, width, height=3, color=ACCENT_GOLD):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.color = color

    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)


class ZoneSquare(Flowable):
    """Small colored square inline."""
    def __init__(self, color, size=10):
        Flowable.__init__(self)
        self.color = color
        self.size = size
        self.width = size
        self.height = size

    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.roundRect(0, 0, self.size, self.size, 2, fill=1, stroke=0)


def build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        'DocTitle', parent=styles['Title'],
        fontName='Helvetica-Bold', fontSize=28, leading=34,
        textColor=NAVY, alignment=TA_CENTER, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontName='Helvetica', fontSize=12, leading=16,
        textColor=SUBTLE_GRAY, alignment=TA_CENTER, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        'SectionHead', parent=styles['Heading1'],
        fontName='Helvetica-Bold', fontSize=16, leading=20,
        textColor=NAVY, spaceBefore=16, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        'SubHead', parent=styles['Heading2'],
        fontName='Helvetica-Bold', fontSize=12, leading=16,
        textColor=DARK_BLUE, spaceBefore=10, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, leading=14,
        textColor=black, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        'BodyBold', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=10, leading=14,
        textColor=black, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        'BulletItem', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, leading=14,
        textColor=black, leftIndent=18, spaceAfter=3,
        bulletIndent=6, bulletFontName='Helvetica',
    ))
    styles.add(ParagraphStyle(
        'Formula', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=11, leading=16,
        textColor=NAVY, alignment=TA_CENTER, spaceBefore=6, spaceAfter=6,
        backColor=LIGHT_BG, borderPadding=8,
    ))
    styles.add(ParagraphStyle(
        'Example', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9, leading=13,
        textColor=HexColor("#333333"), leftIndent=12, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        'ExampleBold', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9, leading=13,
        textColor=HexColor("#333333"), leftIndent=12, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, leading=10,
        textColor=SUBTLE_GRAY, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        'TableCell', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9, leading=12,
        textColor=black,
    ))
    styles.add(ParagraphStyle(
        'TableHeader', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9, leading=12,
        textColor=white,
    ))
    styles.add(ParagraphStyle(
        'TipBody', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9, leading=13,
        textColor=HexColor("#333333"), spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        'PnPHead', parent=styles['Heading2'],
        fontName='Helvetica-Bold', fontSize=13, leading=17,
        textColor=ACCENT_GOLD, spaceBefore=10, spaceAfter=4,
    ))

    return styles


def make_table(headers, rows, col_widths=None):
    """Create a styled table."""
    s = build_styles()
    header_row = [Paragraph(h, s['TableHeader']) for h in headers]
    data = [header_row]
    for row in rows:
        data.append([Paragraph(str(c), s['TableCell']) for c in row])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]
    # Alternating row colors
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), TABLE_ALT_BG))

    t.setStyle(TableStyle(style_cmds))
    return t


def add_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(SUBTLE_GRAY)
    canvas.drawCentredString(
        letter[0] / 2, 0.5 * inch,
        f"Tailgate Turf War v0.1.5  |  Page {doc.page}"
    )
    canvas.restoreState()


def build_pdf():
    output_path = "/sessions/youthful-inspiring-mccarthy/mnt/tailgate-turf-war/GAME-RULES-v0.1.5.pdf"
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        topMargin=0.7 * inch,
        bottomMargin=0.8 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    s = build_styles()
    story = []
    usable = letter[0] - 1.5 * inch

    # ═══════════════════════════════════════════
    # TITLE PAGE
    # ═══════════════════════════════════════════
    story.append(Spacer(1, 1.2 * inch))
    story.append(ColorBar(usable, 4, ACCENT_GOLD))
    story.append(Spacer(1, 16))
    story.append(Paragraph("TAILGATE TURF WAR", s['DocTitle']))
    story.append(Paragraph("Rules &amp; Print-and-Play Guide", s['Subtitle']))
    story.append(Spacer(1, 4))
    story.append(Paragraph("v0.1.5  |  2-5 Players  |  Ages 10+  |  15-20 Minutes", s['Subtitle']))
    story.append(Spacer(1, 16))
    story.append(ColorBar(usable, 4, ACCENT_GOLD))
    story.append(Spacer(1, 30))

    story.append(Paragraph(
        "A zone-control card game with simultaneous blind deployment. "
        "Draft your hand, read the conditions, and fight for four contested zones "
        "across four rounds. Every round is a new optimization puzzle.",
        s['Body']
    ))
    story.append(Spacer(1, 20))

    # Quick stats box
    stats_data = [
        [Paragraph("<b>Players</b>", s['TableCell']),
         Paragraph("<b>Cards Dealt</b>", s['TableCell']),
         Paragraph("<b>Pass/Round</b>", s['TableCell']),
         Paragraph("<b>Min Play/Round</b>", s['TableCell'])],
        ["2", "24", "4 (setup only)", "3"],
        ["3", "16", "2", "3"],
        ["4", "12", "2", "3"],
        ["5", "9", "1", "2"],
    ]
    stats_data_p = []
    for i, row in enumerate(stats_data):
        if i == 0:
            stats_data_p.append(row)
        else:
            stats_data_p.append([Paragraph(str(c), s['TableCell']) for c in row])

    t = Table(stats_data_p, colWidths=[usable*0.2]*4 + [usable*0.2])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 2), (-1, 2), TABLE_ALT_BG),
        ('BACKGROUND', (0, 4), (-1, 4), TABLE_ALT_BG),
    ]))
    story.append(t)

    story.append(PageBreak())

    # ═══════════════════════════════════════════
    # COMPONENTS
    # ═══════════════════════════════════════════
    story.append(Paragraph("COMPONENTS", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    story.append(Paragraph("<b>56-Card Main Deck</b>", s['BodyBold']))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>44 Number Cards</b> -- 4 colors (Red, Yellow, Green, Blue) "
        "x 11 cards each. Ranks per color: 0, 0, 1, 1, 3, 5, 7, 9, 9, 10, 10",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>4 Mascots</b> -- one per color. Doubles the rank of your best card at that zone.",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>4 Action Cards</b> -- one per color, each with a unique effect. "
        "Default set: Shield (Red), Heist (Yellow), Contaminate (Green), Bounty (Blue).",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>4 Duds</b> -- one per color. Share the same card back as Action Cards "
        "(opponents can't tell them apart). Play as rank 5 of their color.",
        s['BulletItem']
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Additional Components</b>", s['BodyBold']))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>12 Condition Cards</b> -- modify the rules for one round each",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>4 Zone Cards</b> -- placed in the center of the table (Red, Yellow, Green, Blue)",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>Player Boards</b> -- one per player, with 4 zone slots for face-down deployment",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>Score Pad</b> or VP tokens",
        s['BulletItem']
    ))

    # ═══════════════════════════════════════════
    # SETUP
    # ═══════════════════════════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("SETUP", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "<b>1.</b> Place the 4 Zone Cards face-up in a row in the center of the table: "
        "Red, Yellow, Green, Blue.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>2.</b> Shuffle the 56-card main deck and deal each player their starting hand "
        "(see table on page 1). Place remaining cards face-down as a draw pile -- these are not used.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>3.</b> Shuffle the 12 Condition Cards face-down in a pile near the zones.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>4.</b> Each player takes a Player Board and places it in front of them.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>5.</b> Choose a starting player (youngest, random, etc.). Play proceeds clockwise.",
        s['Body']
    ))

    # ═══════════════════════════════════════════
    # ROUND STRUCTURE
    # ═══════════════════════════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("ROUND STRUCTURE", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "The game is played over <b>4 rounds</b>. Each round has four phases:",
        s['Body']
    ))

    # Phase 1
    story.append(Paragraph("Phase 1 -- Pass", s['SubHead']))
    story.append(Paragraph(
        "Each player selects cards from their hand and passes them <b>face-down to the player "
        "on their left</b>. Pick up the cards passed to you. This happens <b>every round</b>, "
        "not just at setup.",
        s['Body']
    ))
    story.append(make_table(
        ["Players", "Cards Passed Per Round"],
        [["2", "4 (setup only -- no per-round passing at 2P)"],
         ["3-4", "2"],
         ["5", "1"]],
        col_widths=[usable*0.25, usable*0.75],
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<i>The pass happens before the condition is revealed. You're passing blind -- "
        "you can't game the pass based on the round's condition.</i>",
        s['Example']
    ))

    # Phase 2
    story.append(Paragraph("Phase 2 -- Condition", s['SubHead']))
    story.append(Paragraph(
        "Flip the top <b>Condition Card</b> and read it aloud. This condition applies to all players "
        "for the entire round. (For your first game, skip the Condition Card in Round 1 so new "
        "players learn the base rules first.)",
        s['Body']
    ))

    # Phase 3
    story.append(Paragraph("Phase 3 -- Deploy", s['SubHead']))
    story.append(Paragraph(
        "All players simultaneously choose cards from their hand and place them <b>face-down</b> in the "
        "zone slots on their Player Board. You may place any number of cards at any zone, subject to "
        "any restrictions from the active Condition Card.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>Minimum play:</b> You must play at least <b>3 cards per round</b> (2 at 5 players), "
        "or all remaining cards if you have fewer. You are not required to play all your cards -- "
        "any cards you keep will be available in future rounds.",
        s['Body']
    ))
    story.append(Paragraph(
        "Once all players are ready, say <b>\"Reveal!\"</b>",
        s['Body']
    ))

    # Phase 4
    story.append(Paragraph("Phase 4 -- Reveal, Resolve &amp; Score", s['SubHead']))
    story.append(Paragraph(
        "All players flip their cards face-up at the same time. Resolve action cards, "
        "calculate strength, and score each zone.",
        s['Body']
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════
    # STRENGTH & SCORING
    # ═══════════════════════════════════════════
    story.append(Paragraph("STRENGTH &amp; SCORING", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "Strength = Best Card Rank  +  2 per Extra Card  +  3 Home Field Bonus",
        s['Formula']
    ))

    story.append(Paragraph(
        "<b>Best Card Rank:</b> The highest rank among your number cards (and duds) at that zone.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>Extra Card Bonus:</b> +2 for each additional card beyond the first. "
        "The Mascot does not count as an extra card.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>Home Field Bonus:</b> +3 if at least one <b>natural card</b> (number card or dud) in your "
        "stack matches the zone's color. Mascots and Action Cards cannot anchor Home Field. "
        "A Dud of the matching color does anchor Home Field.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>Mascot:</b> Doubles the rank of your best card. Does not add +2 as an extra card "
        "and cannot anchor Home Field.",
        s['Body']
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Scoring", s['SubHead']))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>Zone Winner:</b> Highest strength wins <b>5 VP</b>. "
        "Ties split VP rounded down.",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>2nd Place:</b> At each zone with a clear winner (no tie for 1st), "
        "the runner-up scores <b>1 VP</b>. Multiple 2nd-place ties each get 1 VP. "
        "No 2nd-place award on tied zones.",
        s['BulletItem']
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Strength Examples", s['SubHead']))

    examples = [
        ("Simple play", "You play a 7 and a 3 at the Blue zone.",
         "Best: 7. Extra cards: 1 (+2). Home Field: neither is Blue (+0). <b>Strength = 9</b>"),
        ("Home Field", "You play a Red 10 and a Red 3 at the Red zone.",
         "Best: 10. Extra: 1 (+2). HF: Red matches Red (+3). <b>Strength = 15</b>"),
        ("Mascot combo", "You play a Green Mascot and a Green 9 at the Green zone.",
         "Best: 9, doubled = 18. Extra: 0 (Mascot doesn't count). HF: Green 9 matches (+3). <b>Strength = 21</b>"),
        ("Dud at matching zone", "You play a Yellow Dud at the Yellow zone.",
         "Best: 5 (dud = rank 5). HF: Yellow Dud matches Yellow (+3). <b>Strength = 8</b>"),
    ]
    for title, setup, calc in examples:
        story.append(Paragraph(f"<b>{title}:</b> {setup}", s['ExampleBold']))
        story.append(Paragraph(calc, s['Example']))

    # ═══════════════════════════════════════════
    # ACTION CARDS
    # ═══════════════════════════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("ACTION CARDS", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "Action Cards do not have a rank. They do not contribute to Strength and do not count as "
        "an extra card for the +2 bonus. They activate during the Resolve phase in a fixed order.",
        s['Body']
    ))

    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Default Set of 4</b> (resolve in this order):", s['BodyBold']))
    story.append(make_table(
        ["Order", "Card", "Color", "Effect"],
        [
            ["1st", "Shield", "Red",
             "Protects your stack from Heist. If you lose this zone, score 2 VP consolation."],
            ["2nd", "Heist", "Yellow",
             "Steal the highest-ranked card from the strongest unshielded opponent at this zone. Add it to your stack before scoring."],
            ["3rd", "Contaminate", "Green",
             "This zone scores inverted: lowest Strength wins instead of highest."],
            ["4th", "Bounty", "Blue",
             "Double VP if you win this zone. 0 VP if you lose (overrides Shield consolation)."],
        ],
        col_widths=[usable*0.08, usable*0.14, usable*0.10, usable*0.68],
    ))

    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>Variant Cards</b> (Spice Option -- see Variants section):", s['BodyBold']))
    story.append(make_table(
        ["Card", "Effect"],
        [
            ["Bomb", "Destroys the highest-ranked card at this zone (from any unshielded player). Resolves after Heist."],
            ["Swap", "Exchange your top card here with your top card at any other zone you occupy. Resolves after Bomb."],
            ["Ambush", "+5 Strength if you are the only player at this zone. Resolves last."],
        ],
        col_widths=[usable*0.15, usable*0.85],
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<b>Duds</b> share the same card back as Action Cards -- opponents can't tell them apart until "
        "revealed. Duds play as a rank 5 card of their color. They contribute to Strength normally "
        "and can anchor Home Field.",
        s['Body']
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════
    # CONDITION CARDS
    # ═══════════════════════════════════════════
    story.append(Paragraph("CONDITION CARDS", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "One Condition Card is flipped at the start of each round (after passing). "
        "It applies to all players equally for that round. The deck contains 12 cards; "
        "you will see 4 of the 12 each game.",
        s['Body']
    ))

    story.append(Spacer(1, 4))
    story.append(Paragraph("Home Field Disruptors", s['SubHead']))
    story.append(Paragraph(
        "These conditions change or remove the Home Field Bonus. "
        "Roughly 1 in 4 rounds will feature one of these.",
        s['Body']
    ))
    story.append(make_table(
        ["Condition", "Effect"],
        [
            ["Inversion", "Lowest Strength wins each zone this round. "
             "(Home Field's +3 now hurts you -- lower is better.)"],
            ["Neutral Ground", "The Home Field Bonus (+3) does not apply this round."],
            ["Color Tax", "Home Field is a <b>-2 penalty</b> instead of +3 this round. "
             "If any natural card in your stack matches the zone color, you get -2."],
        ],
        col_widths=[usable*0.22, usable*0.78],
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Rank Disruptors", s['SubHead']))
    story.append(make_table(
        ["Condition", "Effect"],
        [
            ["Ceiling", "All card ranks are capped at 5 this round. "
             "(A 10 counts as 5, a 9 counts as 5, etc. Cards ranked 5 or below are unaffected.)"],
            ["Mirror", "Every card's rank becomes 10 minus its printed rank. "
             "(A 10 becomes 0, a 0 becomes 10, a 7 becomes 3, etc.)"],
        ],
        col_widths=[usable*0.22, usable*0.78],
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Deployment Constraints", s['SubHead']))
    story.append(make_table(
        ["Condition", "Effect"],
        [
            ["Spread Out", "You must play cards at 2 or more different zones this round."],
            ["Lone Wolf", "Maximum 1 card per zone this round. "
             "(You can still play at multiple zones -- just 1 card each.)"],
        ],
        col_widths=[usable*0.22, usable*0.78],
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Scoring Twists", s['SubHead']))
    story.append(make_table(
        ["Condition", "Effect"],
        [
            ["Double Stakes", "Each zone is worth <b>10 VP</b> instead of 5 this round."],
            ["Sudden Death", "If two or more players tie at a zone, <b>nobody scores</b> that zone."],
            ["Diminishing Returns", "VP per zone won this round: 1st zone = 7, 2nd = 5, 3rd = 3, 4th = 1. "
             "(Rewards focusing on fewer zones.)"],
        ],
        col_widths=[usable*0.22, usable*0.78],
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Momentum &amp; Interaction", s['SubHead']))
    story.append(make_table(
        ["Condition", "Effect"],
        [
            ["Grudge Match", "The player(s) who won the fewest zones last round get "
             "<b>+3 Strength at every zone</b> this round. (Does not apply in Round 1.)"],
            ["Second Wave", "After all players reveal, each player may deploy <b>1 additional card</b> "
             "from their hand to any zone where they already have cards. "
             "(This is done simultaneously, face-up.)"],
        ],
        col_widths=[usable*0.22, usable*0.78],
    ))

    # ═══════════════════════════════════════════
    # GAME END
    # ═══════════════════════════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("GAME END", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "After <b>4 rounds</b>, the player with the most VP wins.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>Tiebreaker:</b> Most total zones won. If still tied, the players share the victory.",
        s['Body']
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════
    # VARIANTS
    # ═══════════════════════════════════════════
    story.append(Paragraph("VARIANTS", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Spice Option (Action Card Pool)", s['SubHead']))
    story.append(Paragraph(
        "Instead of using the default 4 action cards, randomly select 4 from the full pool of 7 "
        "(Shield, Heist, Contaminate, Bounty, Bomb, Swap, Ambush) at the start of each game. "
        "Replace the corresponding action cards in the deck. This adds game-to-game variety.",
        s['Body']
    ))
    story.append(Paragraph(
        "<b>Full resolution order:</b> Shield (1st), Heist (2nd), Bomb (3rd), Swap (4th), "
        "Contaminate (5th), Bounty (6th), Ambush (7th).",
        s['Body']
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("First Game Mode", s['SubHead']))
    story.append(Paragraph(
        "For new players: skip the Condition Card in Round 1, and use only the default 4 action cards. "
        "This lets everyone learn the core strength formula and deployment before adding variety.",
        s['Body']
    ))

    # ═══════════════════════════════════════════
    # STRATEGY TIPS
    # ═══════════════════════════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("STRATEGY TIPS", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    tips = [
        ("<b>Home Field is king -- until it isn't.</b> "
         "The +3 bonus makes matching colors almost always correct. "
         "A Red 7 at Red zone (Str 10) beats a wild 9 (Str 9). "
         "But watch for Inversion, Color Tax, and Neutral Ground -- "
         "about 1 in 4 rounds will punish autopiloting on color."),
        ("<b>The draft is everything.</b> "
         "Use the pass phase to build a hand of colors you want to fight with, "
         "and pass away colors you don't need. Since you pass every round, "
         "your hand reshapes constantly."),
        ("<b>Pace yourself.</b> "
         "You have 4 rounds but a fixed hand. Dumping everything early leaves you empty later. "
         "The minimum play rule (3 cards/round) prevents pure hoarding, "
         "but smart pacing still matters."),
        ("<b>0s have their uses.</b> "
         "Under Inversion or Mirror, low cards become powerhouses. "
         "As zone padding, a 0 adds +2 to your best card. Perfect to pass away in the draft."),
        ("<b>Fight for 2nd.</b> "
         "Even losing a zone earns 1 VP for the runner-up. "
         "A single card tossed at a zone you won't win can pay off over four rounds."),
        ("<b>Read the Condition.</b> "
         "Lone Wolf rewards going where others won't. Sudden Death punishes going where everyone does. "
         "Double Stakes makes one round worth twice as much. Adapt every round."),
        ("<b>Watch the card backs.</b> "
         "Action cards and Duds share the same back. When an opponent plays one, "
         "it might be a Heist -- or it might be a harmless rank 5. The uncertainty is part of the game."),
    ]
    for tip in tips:
        story.append(Paragraph(f"<bullet>&bull;</bullet>{tip}", s['BulletItem']))
        story.append(Spacer(1, 2))

    # ═══════════════════════════════════════════
    # QUICK REFERENCE
    # ═══════════════════════════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("QUICK REFERENCE", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "<b>Strength</b> = Best Rank (+doubled by Mascot) + 2 per extra card + 3 Home Field",
        s['Formula']
    ))

    ref_items = [
        "<b>Round order:</b> Pass, Condition, Deploy, Reveal/Score",
        "<b>Action resolution:</b> Shield, Heist, Contaminate, Bounty",
        "<b>VP per zone:</b> 5 (winner) / 1 (2nd place)",
        "<b>Ties:</b> Split VP rounded down. No 2nd-place award on tied zones.",
        "<b>Home Field:</b> Need a natural card matching the zone color",
        "<b>Mascot:</b> Doubles best rank. Not an extra card. Can't anchor HF.",
        "<b>Hand sizes:</b> 2P=24 | 3P=16 | 4P=12 | 5P=9",
        "<b>Pass/round:</b> 2P=setup only | 3-4P=2 | 5P=1",
        "<b>Min play/round:</b> 3 cards (2 at 5P)",
        "<b>Ranks per color:</b> 0, 0, 1, 1, 3, 5, 7, 9, 9, 10, 10",
    ]
    for item in ref_items:
        story.append(Paragraph(f"<bullet>&bull;</bullet>{item}", s['BulletItem']))

    story.append(PageBreak())

    # ═══════════════════════════════════════════
    # PRINT & PLAY GUIDE
    # ═══════════════════════════════════════════
    story.append(Paragraph("PRINT &amp; PLAY GUIDE", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_GOLD))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "Here's everything you need to build a playable prototype. "
        "Standard poker-size cards (2.5\" x 3.5\") work best. "
        "You can use blank cards, index cards cut to size, or print onto cardstock.",
        s['Body']
    ))

    # Number cards
    story.append(Paragraph("1. Number Cards (44 cards)", s['PnPHead']))
    story.append(Paragraph(
        "Make 11 cards in each of the 4 colors (Red, Yellow, Green, Blue). "
        "Write the rank prominently on the face along with a color indicator.",
        s['Body']
    ))
    story.append(make_table(
        ["Rank", "Per Color", "Total", "Notes"],
        [
            ["0", "2", "8", "Common low card"],
            ["1", "2", "8", "Common low card"],
            ["3", "1", "4", "Scarce mid"],
            ["5", "1", "4", "Scarce mid"],
            ["7", "1", "4", "Scarce mid"],
            ["9", "2", "8", "Common high card"],
            ["10", "2", "8", "Common high card"],
        ],
        col_widths=[usable*0.12, usable*0.15, usable*0.12, usable*0.61],
    ))
    story.append(Paragraph(
        "<i>Tip: Use colored markers, stickers, or print on colored paper. "
        "The color needs to be instantly readable at a glance.</i>",
        s['Example']
    ))

    # Mascots
    story.append(Spacer(1, 4))
    story.append(Paragraph("2. Mascots (4 cards)", s['PnPHead']))
    story.append(Paragraph(
        "One per color. Mark with a star or \"M\" symbol. "
        "These should have the same card back as number cards "
        "(not the action card back). Write the color clearly. "
        "No rank on the face -- just the mascot indicator and color.",
        s['Body']
    ))

    # Action cards
    story.append(Spacer(1, 4))
    story.append(Paragraph("3. Action Cards (4 cards, or 7 for Spice Option)", s['PnPHead']))
    story.append(Paragraph(
        "These need a <b>distinct card back</b> -- different from number cards. "
        "This is important because Duds share this same back, creating bluffing opportunities. "
        "Use a different color back, a bold border, or a stamp.",
        s['Body']
    ))
    story.append(make_table(
        ["Card", "Color", "Face Text"],
        [
            ["Shield", "Red", "SHIELD -- Protected. 2 VP consolation if you lose."],
            ["Heist", "Yellow", "HEIST -- Steal opponent's best card here."],
            ["Contaminate", "Green", "CONTAMINATE -- Lowest strength wins this zone."],
            ["Bounty", "Blue", "BOUNTY -- Double VP if you win. 0 VP if you lose."],
            ["Bomb*", "Any", "BOMB -- Destroy the highest card here."],
            ["Swap*", "Any", "SWAP -- Exchange your top card with another zone."],
            ["Ambush*", "Any", "AMBUSH -- +5 Strength if alone at this zone."],
        ],
        col_widths=[usable*0.16, usable*0.12, usable*0.72],
    ))
    story.append(Paragraph(
        "<i>*Variant cards -- only needed if using the Spice Option.</i>",
        s['Example']
    ))

    # Duds
    story.append(Spacer(1, 4))
    story.append(Paragraph("4. Duds (4 cards)", s['PnPHead']))
    story.append(Paragraph(
        "One per color. <b>Must share the same card back as Action Cards</b> -- "
        "this is the core bluff. On the face, write \"DUD\" and the color. "
        "They play as rank 5 of their color.",
        s['Body']
    ))

    # Condition cards
    story.append(Spacer(1, 4))
    story.append(Paragraph("5. Condition Cards (12 cards)", s['PnPHead']))
    story.append(Paragraph(
        "These should have their own distinct back (different from both main deck backs). "
        "Write the condition name and effect on the face. Use index cards or a different card color.",
        s['Body']
    ))
    story.append(make_table(
        ["#", "Name", "Short Text for Card Face"],
        [
            ["1", "Inversion", "Lowest Strength wins each zone."],
            ["2", "Neutral Ground", "No Home Field Bonus this round."],
            ["3", "Color Tax", "Home Field is -2 penalty (not +3)."],
            ["4", "Ceiling", "All card ranks capped at 5."],
            ["5", "Mirror", "Rank = 10 minus printed rank."],
            ["6", "Spread Out", "Must play at 2+ zones."],
            ["7", "Lone Wolf", "Max 1 card per zone."],
            ["8", "Double Stakes", "Zones worth 10 VP."],
            ["9", "Sudden Death", "Ties score 0."],
            ["10", "Dim. Returns", "VP per zone: 7 / 5 / 3 / 1."],
            ["11", "Grudge Match", "+3 Strength to last round's loser(s). (Not Round 1.)"],
            ["12", "Second Wave", "After reveal, deploy 1 more card (face-up)."],
        ],
        col_widths=[usable*0.06, usable*0.18, usable*0.76],
    ))

    # Zone cards
    story.append(Spacer(1, 4))
    story.append(Paragraph("6. Zone Cards (4 cards)", s['PnPHead']))
    story.append(Paragraph(
        "Four large, clearly colored cards: Red, Yellow, Green, Blue. "
        "These sit in the center of the table. Index cards work fine -- "
        "just color them solidly so the zone color is unmistakable.",
        s['Body']
    ))

    # Player boards
    story.append(Spacer(1, 4))
    story.append(Paragraph("7. Player Boards (1 per player)", s['PnPHead']))
    story.append(Paragraph(
        "Each player needs a board with 4 labeled zone slots (Red, Yellow, Green, Blue) "
        "to place cards face-down during deployment. Options:",
        s['Body']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>Simple:</b> A sheet of paper divided into 4 labeled columns.",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>Better:</b> A folded piece of cardstock with labeled slots and a lip "
        "to hide cards from opponents.",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>Quickest:</b> Skip boards entirely -- just have players place "
        "cards face-down in front of each Zone Card (works fine for casual play).",
        s['BulletItem']
    ))

    # Scoring
    story.append(Spacer(1, 4))
    story.append(Paragraph("8. Score Tracking", s['PnPHead']))
    story.append(Paragraph(
        "Use a notepad, a phone, or small tokens (coins, poker chips, etc.) to track VP. "
        "Typical final scores are 20-40 VP, so plan accordingly.",
        s['Body']
    ))

    # Summary
    story.append(Spacer(1, 10))
    story.append(Paragraph("Card Count Summary", s['SubHead']))
    story.append(make_table(
        ["Component", "Count", "Card Back"],
        [
            ["Number Cards", "44", "Standard (same for all)"],
            ["Mascots", "4", "Standard (same as number cards)"],
            ["Action Cards", "4 (or 7 for Spice)", "Action back (distinct from standard)"],
            ["Duds", "4", "Action back (same as action cards)"],
            ["Condition Cards", "12", "Condition back (third distinct back)"],
            ["Zone Cards", "4", "N/A (face-up on table)"],
        ],
        col_widths=[usable*0.28, usable*0.28, usable*0.44],
    ))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<b>Total cards to make:</b> 68 (56 main deck + 12 conditions), plus 4 zone cards "
        "and player boards. With the Spice Option variant cards, 71 main + 12 conditions = 83 total.",
        s['Body']
    ))

    # ═══════════════════════════════════════════
    # DESIGNER NOTES
    # ═══════════════════════════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("DESIGNER NOTES", s['SectionHead']))
    story.append(ColorBar(usable, 2, ACCENT_BLUE))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "This is <b>v0.1.5</b> -- a working draft for playtesting. "
        "The game is currently themed \"Tailgate Turf War\" (sports/tailgate zone control). "
        "Art and a finalized title will come after the mechanics are validated.",
        s['Body']
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph("What's New in v0.1.5", s['SubHead']))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>Per-round passing:</b> You now pass cards every round, not just at setup. "
        "This means your hand reshapes each round, creating a fresh puzzle every time.",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>New action cards:</b> Heist and Contaminate replace Bomb and Swap as the "
        "default set. They create more interesting two-way decisions. Bomb, Swap, and Ambush are "
        "available as variant cards via the Spice Option.",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet><b>Condition card overhaul:</b> 12 new conditions designed to shake up each round. "
        "Three HF disruptors ensure you can't autopilot on color matching. "
        "Rank disruptors, deployment constraints, and scoring twists create genuine variety.",
        s['BulletItem']
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Playtesting Feedback Requested", s['SubHead']))
    story.append(Paragraph(
        "<bullet>&bull;</bullet>Does each round feel like a different puzzle?",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet>Are any condition cards confusing or unfun?",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet>Does the per-round passing feel good, or is it too much shuffling?",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet>How do Heist and Contaminate feel compared to Bomb and Swap?",
        s['BulletItem']
    ))
    story.append(Paragraph(
        "<bullet>&bull;</bullet>At 3 players: does sniper strategy (dumping everything at one zone) dominate?",
        s['BulletItem']
    ))

    story.append(Spacer(1, 20))
    story.append(ColorBar(usable, 2, ACCENT_GOLD))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Designed by Drew  |  Simulation-validated across 120,000+ games  |  v0.1.5",
        s['Footer']
    ))

    # Build
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    return output_path


if __name__ == "__main__":
    path = build_pdf()
    print(f"Built: {path}")
