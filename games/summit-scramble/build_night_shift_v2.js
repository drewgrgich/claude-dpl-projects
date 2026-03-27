const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageBreak, LevelFormat, PageNumber, TabStopType, TabStopPosition,
} = require("docx");

// Colors
const C = {
  dark: "1A1A2E",
  accent: "4A90D9",
  accentLight: "E8F1FB",
  highlight: "FFB347",
  gray: "666666",
  lightGray: "F5F5F5",
  white: "FFFFFF",
  border: "CCCCCC",
  red: "CC3333",
};

const border = { style: BorderStyle.SINGLE, size: 1, color: C.border };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function heading(text, level = HeadingLevel.HEADING_1) {
  return new Paragraph({ heading: level, spacing: { before: 300, after: 150 }, children: [new TextRun({ text, bold: true })] });
}

function para(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120 },
    ...opts,
    children: [new TextRun({ text, size: 22, font: "Arial", ...opts.run })],
  });
}

function boldPara(label, text) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [
      new TextRun({ text: label, size: 22, font: "Arial", bold: true }),
      new TextRun({ text, size: 22, font: "Arial" }),
    ],
  });
}

function italicPara(text) {
  return para(text, { run: { italics: true, color: C.gray } });
}

function tableRow(cells, header = false) {
  return new TableRow({
    children: cells.map((text, i) =>
      new TableCell({
        borders,
        margins: cellMargins,
        width: { size: cells.length === 2 ? (i === 0 ? 3120 : 6240) :
                        cells.length === 3 ? (i === 0 ? 2340 : i === 1 ? 2340 : 4680) :
                        cells.length === 4 ? [2340, 1560, 1560, 3900][i] : 9360 / cells.length,
                 type: WidthType.DXA },
        shading: header ? { fill: C.accentLight, type: ShadingType.CLEAR } : undefined,
        children: [new Paragraph({
          children: [new TextRun({ text, size: 22, font: "Arial", bold: header })]
        })],
      })
    ),
  });
}

function makeTable(headers, rows, widths = null) {
  const cols = headers.length;
  const defaultWidths = cols === 2 ? [3120, 6240] :
                        cols === 3 ? [2340, 2340, 4680] :
                        cols === 4 ? [2340, 1560, 1560, 3900] :
                        Array(cols).fill(Math.floor(9360 / cols));
  const w = widths || defaultWidths;

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: w,
    rows: [
      new TableRow({
        children: headers.map((h, i) =>
          new TableCell({
            borders,
            margins: cellMargins,
            width: { size: w[i], type: WidthType.DXA },
            shading: { fill: C.accentLight, type: ShadingType.CLEAR },
            children: [new Paragraph({ children: [new TextRun({ text: h, size: 22, font: "Arial", bold: true })] })],
          })
        ),
      }),
      ...rows.map(row =>
        new TableRow({
          children: row.map((text, i) =>
            new TableCell({
              borders,
              margins: cellMargins,
              width: { size: w[i], type: WidthType.DXA },
              children: [new Paragraph({ children: [new TextRun({ text, size: 22, font: "Arial" })] })],
            })
          ),
        })
      ),
    ],
  });
}

function spacer() {
  return new Paragraph({ spacing: { after: 60 }, children: [] });
}

// ========================================================================
// Document
// ========================================================================

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: C.dark },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: C.accent },
        paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: C.dark },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "numbers",
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            children: [
              new TextRun({ text: "SUMMIT SCRAMBLE", font: "Arial", size: 18, color: C.gray, bold: true }),
              new TextRun({ text: "\tThe Night Shift v2", font: "Arial", size: 18, color: C.gray, italics: true }),
            ],
            tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C.accent, space: 4 } },
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: "Page ", font: "Arial", size: 18, color: C.gray }),
              new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 18, color: C.gray }),
            ],
          })],
        }),
      },
      children: [
        // Title
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 80 },
          children: [new TextRun({ text: "THE NIGHT SHIFT", size: 52, bold: true, font: "Arial", color: C.dark })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 40 },
          children: [new TextRun({ text: "Solo & Co-op Challenge Mode", size: 28, font: "Arial", color: C.accent })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [new TextRun({ text: "1\u20132 Players  \u00B7  Simulation-Tested Edition  \u00B7  v2", size: 22, font: "Arial", color: C.gray })],
        }),

        // Flavor
        italicPara("The Stadium is dark. The crowd is gone. One Night Owl remains \u2014 and it never tires. Your job: summit before the clock runs out."),
        spacer(),

        // ---- OVERVIEW ----
        heading("How It Works", HeadingLevel.HEADING_1),
        para("You play against a single Night Owl \u2014 an automated opponent with a hand of cards and a bottomless reserve deck. You have a limited number of tricks to empty your hand. The Owl draws back up after every trick. You can\u2019t wait it out. Every trick counts."),
        spacer(),

        // ---- SOLO SETUP ----
        heading("Solo Setup (1 Player)", HeadingLevel.HEADING_2),
        boldPara("Deal yourself: ", "12 cards."),
        boldPara("Deal the Night Owl: ", "8 cards face-down (the Owl\u2019s hand \u2014 don\u2019t look)."),
        boldPara("Remaining cards: ", "Place face-down as the Owl Deck."),
        boldPara("Trick limit: ", "10 tricks to empty your hand."),
        spacer(),

        // ---- CO-OP SETUP ----
        heading("Co-op Setup (2 Players)", HeadingLevel.HEADING_2),
        para("Two climbers. One Owl. Both players must empty their hands to win."),
        spacer(),
        boldPara("Deal each player: ", "8 cards (16 total between both players)."),
        boldPara("Deal the Night Owl: ", "10 cards face-down."),
        boldPara("Remaining cards: ", "Place face-down as the Owl Deck."),
        boldPara("Trick limit: ", "8 tricks for both players to empty their hands."),
        spacer(),

        // ---- TURN STRUCTURE ----
        heading("Turn Structure", HeadingLevel.HEADING_1),

        heading("Solo", HeadingLevel.HEADING_3),
        para("You and the Owl alternate leading tricks. You lead first."),
        spacer(),
        boldPara("Your lead: ", "Play any legal formation from your hand. The Owl reveals its hand, plays the cheapest card(s) that beat your formation (same type), then hides its hand. If the Owl can\u2019t beat you, you win the trick."),
        spacer(),
        boldPara("Owl\u2019s lead: ", "The Owl plays its strongest formation (highest rank, preferring multi-card). Beat it from your hand if you can. If you can\u2019t, the Owl wins the trick."),
        spacer(),
        boldPara("After each trick: ", "All played cards go to Base Camp. The Owl draws back up to its hand limit from the Owl Deck. If the Owl Deck is empty, shuffle Base Camp into a new Owl Deck. The trick winner leads next."),
        spacer(),

        heading("Co-op: The Rope Team", HeadingLevel.HEADING_3),
        para("Both players are involved in every trick. Lead order rotates: Player 1 \u2192 Owl \u2192 Player 2 \u2192 Owl."),
        spacer(),
        boldPara("When a player leads: ", "Play any formation. The Owl tries to beat it. If the Owl beats you, your partner gets one chance to beat the Owl. If your partner succeeds, your team wins the trick."),
        spacer(),
        boldPara("When the Owl leads: ", "One player tries to beat it. If they can\u2019t, the other player tries. If neither can beat it, the Owl wins."),
        spacer(),
        boldPara("Communication: ", "Players can see each other\u2019s hands and discuss strategy openly. You\u2019re climbing together \u2014 coordinate your plays."),
        spacer(),
        italicPara("The Rope Team mechanic means your partner can rescue a trick the Owl would have won. Use it \u2014 \u201CI\u2019ll lead low to bait the Owl. You come over the top.\u201D"),
        spacer(),

        // ---- OWL BEHAVIOR ----
        heading("Owl Behavior", HeadingLevel.HEADING_1),
        para("The Night Owl plays automatically using simple rules. No hidden decisions. No ambiguity."),
        spacer(),

        boldPara("When the Owl leads: ", "Reveal its hand. It plays its strongest available formation: highest rank, preferring multi-card formations (surges, chains) that are harder for you to counter. In case of a tie, it picks the formation with the most cards."),
        spacer(),
        boldPara("When the Owl follows: ", "Reveal its hand. It plays the cheapest formation that beats the current trick (lowest rank that still wins, same formation type). If it can\u2019t beat the trick, it passes."),
        spacer(),
        boldPara("Trip-Up: ", "If the Owl holds a rank 0 and the current trick is a solo rank 10, the Owl plays the Trip-Up."),
        spacer(),
        boldPara("Refill: ", "After every trick, the Owl draws from the Owl Deck until its hand is full. If the Owl Deck is empty, shuffle Base Camp to form a new Owl Deck. The Owl never runs out."),
        spacer(),

        // ---- WIN / LOSS ----
        heading("Win & Loss", HeadingLevel.HEADING_1),

        heading("Solo", HeadingLevel.HEADING_3),
        boldPara("Win: ", "Empty your hand within the trick limit."),
        boldPara("Lose: ", "You still have cards when the trick limit is reached."),
        boldPara("Score: ", "Cards remaining = your Fatigue. Zero = perfect summit."),
        spacer(),

        heading("Co-op", HeadingLevel.HEADING_3),
        boldPara("Win: ", "BOTH players empty their hands within the trick limit."),
        boldPara("Lose: ", "Either player still has cards when tricks run out."),
        boldPara("Score: ", "Total cards remaining between both players."),
        spacer(),
        italicPara("If one player empties their hand early, they can\u2019t play cards anymore \u2014 but they\u2019re still part of the team. They can\u2019t lead, but they can still advise their partner."),
        spacer(),

        new Paragraph({ children: [new PageBreak()] }),

        // ---- FACTION ABILITIES ----
        heading("Faction Abilities", HeadingLevel.HEADING_1),
        para("Win a trick with a rank 6\u201310 card? Trigger that faction\u2019s ability. Same rules as multiplayer, with two modifications for solo play:"),
        spacer(),

        makeTable(
          ["Faction", "Ability", "Solo/Co-op Effect"],
          [
            ["Red", "The Substitution", "Skip the Owl\u2019s next lead. You (or your partner) lead twice in a row."],
            ["Orange", "Scout", "Look at top 2 cards of the Trail. May swap 1 from your hand."],
            ["Yellow", "Streamline", "Discard 1 card from your hand (does not count as a trick)."],
            ["Green", "Recalibrate", "Draw 1 from the Trail, then discard 2 from your hand."],
            ["Blue", "The Forecast", "Peek at the Owl\u2019s hand. You may swap one of your cards for one of theirs."],
            ["Purple", "Reclaim", "Swap 1 card from your hand with any card in Base Camp."],
          ],
          [1560, 2340, 5460]
        ),
        spacer(),
        para("Streamline and Recalibrate are your most valuable abilities in solo \u2014 they shed cards without costing a trick. The Forecast (Blue) is devastating in co-op: steal the Owl\u2019s best card and give it your worst."),
        spacer(),
        para("If a Faction Ability empties your hand, you summit immediately. This can win the game mid-trick."),
        spacer(),

        // ---- STRATEGY ----
        heading("Strategy Notes", HeadingLevel.HEADING_1),

        heading("Solo", HeadingLevel.HEADING_3),
        para("Lead with multi-card formations. Surges and Daisy Chains shed 2\u20134 cards per trick, and the Owl often can\u2019t match the type. A 3-card chain is worth three times as much as a solo \u2014 use them aggressively."),
        spacer(),
        para("Save your 0s for Trip-Ups. When the Owl leads a solo 10, your 0 seizes initiative AND sheds a card. Don\u2019t lead with rank 0 unless it\u2019s your last card."),
        spacer(),
        para("Trigger abilities on rank 6\u201310 wins. Streamline and Recalibrate effectively give you free card shedding outside the trick limit. One well-timed Recalibrate can be the difference between summit and failure."),
        spacer(),

        heading("Co-op", HeadingLevel.HEADING_3),
        para("Coordinate your leads. If your partner has a high chain, lead low to bait the Owl into spending its beaters. Then your partner drops the chain on a clean trick."),
        spacer(),
        para("Use The Forecast (Blue) to sabotage. Steal the Owl\u2019s highest card. In co-op, the stolen card goes to whichever player needs it more \u2014 discuss before you swap."),
        spacer(),
        para("One player should race to empty first. Once one player is out, the remaining player gets all the team\u2019s leads. Focus your stronger hand on finishing first to free up initiative."),
        spacer(),

        // ---- DIFFICULTY ----
        heading("Difficulty Tiers", HeadingLevel.HEADING_1),
        para("Adjust the Owl\u2019s hand size and the trick limit to change difficulty. All numbers are simulation-tested across 1,000+ games per configuration."),
        spacer(),

        heading("Solo Tiers", HeadingLevel.HEADING_3),
        makeTable(
          ["Tier", "Your Hand", "Owl Hand", "Trick Limit", "Win Rate"],
          [
            ["Basecamp", "12", "8", "12 tricks", "~39%"],
            ["The Ascent", "12", "8", "10 tricks", "~30%"],
            ["Summit Push", "12", "10", "10 tricks", "~22%"],
            ["Iron Climb", "12", "10", "7 tricks", "~11%"],
          ],
          [1872, 1404, 1404, 1872, 2808]
        ),
        spacer(),

        heading("Co-op Tiers", HeadingLevel.HEADING_3),
        makeTable(
          ["Tier", "Each Player", "Owl Hand", "Trick Limit", "Win Rate"],
          [
            ["Basecamp", "7 each", "8", "8 tricks", "~42%"],
            ["The Ascent", "8 each", "10", "8 tricks", "~29%"],
            ["Iron Climb", "8 each", "10", "6 tricks", "~3%"],
          ],
          [1872, 1404, 1404, 1872, 2808]
        ),
        spacer(),
        italicPara("Basecamp is for learning the mode. The Ascent is the intended challenge. Iron Climb is for people who think Dark Souls is too forgiving."),
        spacer(),

        // ---- QUICK REFERENCE ----
        heading("Quick Reference", HeadingLevel.HEADING_1),
        boldPara("Win: ", "Empty your hand within the trick limit."),
        boldPara("Formations: ", "Same as multiplayer \u2014 Solo Sprint, Surge, Daisy Chain, Confetti Cannon, Trip-Up."),
        boldPara("Owl behavior: ", "Leads strongest. Follows cheapest beater. Refills after every trick."),
        boldPara("Abilities: ", "Trigger on rank 6+ trick wins. Red = skip Owl turn. Blue = peek + swap with Owl."),
        boldPara("Co-op: ", "Partner can rescue tricks. Both must empty hands to win."),
        spacer(),

        // ---- DESIGNER'S NOTE ----
        heading("Designer\u2019s Note", HeadingLevel.HEADING_1),
        italicPara("The original Night Shift used flip-based owls \u2014 automated drones that revealed one card at a time from their decks. After extensive simulation testing (12,000+ games across 12 variants), we found the flip mechanic created a paradox: the owls were too easy in standard mode (74% win rate) and accidentally easier in Iron Climb mode (49% \u2014 against a claimed <5%) because aggressive flipping burned through owl decks faster."),
        spacer(),
        italicPara("The redesign replaces blind flips with a smart Owl that holds a hand of cards and plays optimally, paired with a trick-limit loss condition instead of deck exhaustion. This creates genuine time pressure, makes every formation type matter, and scales cleanly across difficulty tiers."),
        spacer(),
        italicPara("The co-op Rope Team mechanic emerged from testing. The \u201Cpartner rescue\u201D \u2014 where your teammate can beat a trick the Owl won \u2014 is the most satisfying moment in co-op play. It rewards coordination without requiring complex rules. \u201CI\u2019ll bait. You finish.\u201D That\u2019s the whole strategy, and it\u2019s enough."),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buffer) => {
  const outPath = process.argv[2] || "night-shift-v2.docx";
  fs.writeFileSync(outPath, buffer);
  console.log(`Written to ${outPath}`);
});
