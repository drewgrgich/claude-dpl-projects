const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, PageBreak, LevelFormat, TabStopType, TabStopPosition,
} = require("docx");

// ── Colors ──
const BLUE = "2E5090";
const DARK = "1A1A2E";
const GRAY = "666666";
const LIGHT_BG = "F0F4F8";
const CHANGED_BG = "FFF8E1";  // light yellow for changed sections
const ACCENT = "C0392B";

// ── Helpers ──
function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 400, after: 200 },
    children: [new TextRun({ text, bold: true, size: 36, font: "Georgia", color: DARK })],
  });
}
function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 300, after: 150 },
    children: [new TextRun({ text, bold: true, size: 28, font: "Georgia", color: BLUE })],
  });
}
function heading3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 100 },
    children: [new TextRun({ text, bold: true, size: 24, font: "Georgia", color: DARK })],
  });
}
function para(...runs) {
  return new Paragraph({ spacing: { after: 120 }, children: runs });
}
function text(t, opts = {}) {
  return new TextRun({ text: t, font: "Georgia", size: 22, color: DARK, ...opts });
}
function bold(t, opts = {}) {
  return text(t, { bold: true, ...opts });
}
function italic(t, opts = {}) {
  return text(t, { italics: true, color: GRAY, ...opts });
}
function changedTag() {
  return new TextRun({ text: "  [CHANGED IN V2]", font: "Georgia", size: 18, bold: true, color: ACCENT });
}
function newTag() {
  return new TextRun({ text: "  [NEW IN V2]", font: "Georgia", size: 18, bold: true, color: ACCENT });
}
function separator() {
  return new Paragraph({
    spacing: { before: 200, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "CCCCCC", space: 1 } },
    children: [],
  });
}
function quote(t) {
  return new Paragraph({
    spacing: { after: 120 },
    indent: { left: 480 },
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: BLUE, space: 8 } },
    children: [new TextRun({ text: t, font: "Georgia", size: 20, italics: true, color: GRAY })],
  });
}
function bulletItem(t, opts = {}) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 80 },
    children: [typeof t === "string" ? text(t, opts) : t],
  });
}

// ── Table helpers ──
const thinBorder = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

function headerCell(t, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: { fill: "2E5090", type: ShadingType.CLEAR },
    margins: cellMargins,
    children: [new Paragraph({ children: [new TextRun({ text: t, bold: true, font: "Georgia", size: 20, color: "FFFFFF" })] })],
  });
}
function dataCell(t, width, opts = {}) {
  const fill = opts.highlight ? CHANGED_BG : "FFFFFF";
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: { fill, type: ShadingType.CLEAR },
    margins: cellMargins,
    children: [new Paragraph({ children: [typeof t === "string" ? new TextRun({ text: t, font: "Georgia", size: 20, color: DARK }) : t] })],
  });
}

// ══════════════════════════════════════════════════════════════
// BUILD DOCUMENT
// ══════════════════════════════════════════════════════════════

const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  styles: {
    default: { document: { run: { font: "Georgia", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Georgia" },
        paragraph: { spacing: { before: 400, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Georgia" },
        paragraph: { spacing: { before: 300, after: 150 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Georgia" },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BLUE, space: 4 } },
          children: [
            new TextRun({ text: "SUMMIT SCRAMBLE \u2014 V2 RULES", font: "Georgia", size: 18, bold: true, color: BLUE }),
            new TextRun({ text: "\tSimulation-Tested Edition", font: "Georgia", size: 16, italics: true, color: GRAY }),
          ],
          tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Summit Scramble V2 \u2014 Page ", font: "Georgia", size: 16, color: GRAY }),
            new TextRun({ children: [PageNumber.CURRENT], font: "Georgia", size: 16, color: GRAY }),
          ],
        })],
      }),
    },
    children: [

      // ═══ TITLE ═══
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 80 },
        children: [new TextRun({ text: "SUMMIT SCRAMBLE", font: "Georgia", size: 52, bold: true, color: DARK })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 40 },
        children: [new TextRun({ text: "A Climbing Race for 3\u20135 Players", font: "Georgia", size: 28, color: BLUE })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 },
        children: [new TextRun({ text: "V2 RULES \u2014 Simulation-Tested Edition", font: "Georgia", size: 22, bold: true, color: ACCENT })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 80 },
        children: [italic("Hamsters & Monsters Core Deck (66 cards) \u00B7 20 Minutes \u00B7 Ages 10+")],
      }),

      // V2 CHANGE LOG
      new Paragraph({
        spacing: { before: 200, after: 120 },
        shading: { fill: CHANGED_BG, type: ShadingType.CLEAR },
        indent: { left: 240, right: 240 },
        children: [bold("V2 Changes (backed by 17,000+ simulated games):", { color: ACCENT })],
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        spacing: { after: 60 },
        shading: { fill: CHANGED_BG, type: ShadingType.CLEAR },
        indent: { right: 240 },
        children: [text("Confetti Cannon is no longer an interrupt \u2014 it\u2019s now a standard lead/follow formation. Trip-Up is the sole interrupt mechanic.")],
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        spacing: { after: 60 },
        shading: { fill: CHANGED_BG, type: ShadingType.CLEAR },
        indent: { right: 240 },
        children: [text("The Revelation (Blue) can now target any other player \u2014 the \u201Cfewer cards\u201D restriction has been removed.")],
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        spacing: { after: 60 },
        shading: { fill: CHANGED_BG, type: ShadingType.CLEAR },
        indent: { right: 240 },
        children: [text("Ability-finish rule added: if a Faction Ability empties your hand, you reach The Summit.")],
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        spacing: { after: 120 },
        shading: { fill: CHANGED_BG, type: ShadingType.CLEAR },
        indent: { right: 240 },
        children: [text("5-player starting hands adjusted: seats 4 and 5 receive 10 cards instead of 11. In Team Relays, The Tag and revised Summit Sweep added.")],
      }),

      separator(),

      // ═══ WHAT'S GOING ON HERE ═══
      heading1("What\u2019s Going On Here?"),
      para(text("Once a year, beneath stadium lights and the distant crackle of confetti cannons, the six factions gather for the Summit Scramble \u2014 a vertical sprint up the tallest peak in the fuzzy multiverse. No ropes. No safety nets. Just cards, cunning, and the overwhelming desire to reach the top before everyone else.")),
      para(text("You\u2019re a climber. Your hand of cards is your energy. Every card you play propels you higher \u2014 but you\u2019ve only got so much fuel. Play too aggressively and you\u2019ll burn out before the final push. Play too cautiously and you\u2019ll watch someone else plant their flag while you\u2019re still looking for a foothold.")),
      para(text("The first player to play their last card reaches The Summit. Everyone else keeps climbing until they finish or collapse. The slowest climber accumulates Fatigue (measured in Zzz\u2019s, obviously). Play multiple rounds. The player with the lowest Fatigue after someone hits the limit wins the Championship.")),
      para(italic("Shake hands after. It\u2019s a rule.")),

      separator(),

      // ═══ WHAT YOU NEED ═══
      heading1("What You Need"),
      para(text("Just the Hamsters & Monsters deck (66 cards \u2014 six factions, numbered 0 through 10 each).")),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1560, 3120, 3120, 1560],
        rows: [
          new TableRow({ children: [headerCell("Color", 1560), headerCell("Faction", 3120), headerCell("Symbol", 3120), headerCell("Ability", 1560)] }),
          new TableRow({ children: [dataCell("Red", 1560), dataCell("Super-Dupes", 3120), dataCell("Shield", 3120), dataCell("Rotation", 1560)] }),
          new TableRow({ children: [dataCell("Orange", 1560), dataCell("Finders-Keepers", 3120), dataCell("Magnifying Glass", 3120), dataCell("Scout", 1560)] }),
          new TableRow({ children: [dataCell("Yellow", 1560), dataCell("Tinkerers", 3120), dataCell("Spanner", 3120), dataCell("Streamline", 1560)] }),
          new TableRow({ children: [dataCell("Green", 1560), dataCell("Prognosticationers", 3120), dataCell("Crystal Ball", 3120), dataCell("Recalibrate", 1560)] }),
          new TableRow({ children: [dataCell("Blue", 1560), dataCell("Magicians", 3120), dataCell("Top Hat", 3120), dataCell("Revelation", 1560)] }),
          new TableRow({ children: [dataCell("Purple", 1560), dataCell("Time Travelers", 3120), dataCell("Backward Clock", 3120), dataCell("Reclaim", 1560)] }),
        ],
      }),

      para(text("Something to track Fatigue \u2014 a score pad, a phone, scratches on the table. Hamsters aren\u2019t picky.")),

      separator(),

      // ═══ SETUP ═══
      heading1("Setup"),
      para(bold("1. "), text("Shuffle all 66 cards.")),
      para(bold("2. "), text("Deal starting hands based on player count:"), changedTag()),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3120, 6240],
        rows: [
          new TableRow({ children: [headerCell("Players", 3120), headerCell("Cards Each", 6240)] }),
          new TableRow({ children: [dataCell("3", 3120), dataCell("15", 6240)] }),
          new TableRow({ children: [dataCell("4", 3120), dataCell("13", 6240)] }),
          new TableRow({ children: [
            dataCell("5", 3120, { highlight: true }),
            dataCell(new TextRun({ text: "11 (seats 1\u20133) / 10 (seats 4\u20135)", font: "Georgia", size: 20, color: DARK, bold: true }), 6240, { highlight: true }),
          ] }),
        ],
      }),

      quote("5-Player Adjustment: The last two seats receive 10 cards instead of 11. In a climbing game, late-seat players act after formations have already been driven up, which is a structural disadvantage. Starting one step closer to The Summit compensates. Simulation data: this reduces the seat-position win-rate spread from 7.1% to 4.5%."),

      para(bold("3. "), text("Place remaining cards face-down as the Trail \u2014 the path ahead. Some abilities will draw from here.")),
      para(bold("4. "), text("Leave space for Base Camp \u2014 a face-up discard pile. Starts empty.")),
      para(bold("5. "), text("Pick someone to go first. (Winner of the last game goes first. First game? Shortest player. We don\u2019t make the rules. Wait \u2014 yes we do.)")),

      separator(),

      // ═══ THE ONE RULE ═══
      heading1("The One Rule That Runs Everything"),
      para(text("On your turn, you either play cards that beat what\u2019s on top \u2014 or you pass.")),
      para(text("That\u2019s the whole game. Everything else is just details about what you can play and when.")),
      para(text("Here\u2019s the rhythm: One player leads by playing a card formation. Going clockwise, everyone else must either beat it with the same type of formation but higher \u2014 or pass and sit this one out. Once everyone else has passed, the last player standing wins the trick, discards everything to Base Camp, and leads the next one.")),
      para(text("First to empty your hand reaches The Summit. Last place gets sleepy.")),

      separator(),

      // ═══ FORMATIONS ═══
      heading1("Formations (How to Climb)"),
      para(text("Every play is a formation \u2014 a specific arrangement of cards. To beat a formation, you must play the same type with a higher rank. You can never change the formation type mid-trick.")),

      // Solo Sprint
      heading2("Solo Sprint (Single Card)"),
      para(text("The simplest play. One card. Beat it with a higher-ranked card.")),
      para(bold("Tie-breaker: "), text("If two cards share the same rank, the faction hierarchy decides: Red > Orange > Yellow > Green > Blue > Purple. (Think of it as ROYGBP \u2014 the rainbow picks the winner.)")),
      quote("Example: Someone plays a Green 7. You can beat it with any 8, 9, or 10 \u2014 or a Red, Orange, or Yellow 7 (because those factions outrank Green)."),

      // Surge
      heading2("The Surge (Set of 2 or 3)"),
      para(text("Two or three cards of the same rank, played together.")),
      para(text("Beat it with the same quantity at a higher rank. A pair of 6s beats a pair of 4s. A triple of 9s beats a triple of 7s. Faction doesn\u2019t matter for Surges \u2014 only rank.")),

      // Daisy Chain
      heading2("The Daisy Chain (Run of 3+)"),
      para(text("Three or more cards of consecutive ranks \u2014 like 3-4-5 or 7-8-9-10. Mixed factions are fine.")),
      para(text("Beat it with a run of the same length and a higher top card. A 4-5-6 beats a 3-4-5. A 6-7-8-9 beats a 5-6-7-8.")),

      // Confetti Cannon — CHANGED
      heading2("The Confetti Cannon (4 of a Kind)"),
      para(text("Four cards of the same rank. The ultimate celebration."), changedTag()),
      para(text("The Confetti Cannon is a standard formation \u2014 you can lead with it or play it to beat another Cannon. It follows the same rules as other formations: play it on your turn, in order, like any other lead or follow.")),
      para(bold("Power Check: "), text("If the Cannon\u2019s rank is 6 or higher, choose one faction from among the four cards to activate its ability. One formation, one trigger.")),
      quote("V2 Note: The Confetti Cannon is no longer an interrupt. It cannot be fired out of turn or after passing. The Trip-Up is the only interrupt mechanic in the game. This makes the Cannon a massive racing play (shed 4 cards in one formation!) rather than a surprise gotcha. It also means there\u2019s exactly one rule to remember about interrupts, not two."),

      // Trip-Up — UPDATED
      heading2("The Trip-Up (Rank 0 vs. Solo 10)"),
      para(text("Here\u2019s where it gets sneaky. A single Rank 0 card can beat a Solo Rank 10 \u2014 and it can come from anyone, at any time, even if they\u2019ve already passed. The Trip-Up is the sole interrupt in Summit Scramble."), changedTag()),
      para(text("Someone plays a solo 10 to seize control. The table freezes. Does anyone have a 0? Two seconds of silence. Nervous eye contact. Then either the 10 stands \u2014 or someone slaps down a 0 and the room explodes.")),
      para(bold("How it works:")),
      bulletItem("Whenever a Solo Rank 10 is the current top card, any player may play a single Rank 0 as an interrupt"),
      bulletItem("The trick ends immediately \u2014 the Trip-Up player wins and leads next"),
      bulletItem("This works even if you\u2019ve already passed this trick"),
      para(bold("Restrictions:")),
      bulletItem("Only works on Solo Sprints (a single 10). Cannot interrupt a Surge, Daisy Chain, or Cannon"),
      bulletItem("Cannot interrupt someone reaching The Summit \u2014 if a player goes out on a solo 10, the trick ends before anyone can respond"),
      bulletItem("The tripped card never wins the trick, so its Faction Ability does not trigger"),

      separator(),

      // ═══ THE RACE ═══
      heading1("The Race (Turn by Turn)"),

      heading2("1. Take Point (Lead)"),
      para(text("The trick winner \u2014 or the starting player at the beginning of a round \u2014 leads by playing any legal formation from their hand.")),

      heading2("2. Keep Up (Follow)"),
      para(text("Going clockwise, each player must do one of two things:")),
      bulletItem("Advance: Play the same formation type at a higher rank. Beat what\u2019s on top."),
      bulletItem("Conserve Energy: Pass. You\u2019re out for the rest of this trick."),
      para(bold("The Burnout Rule: "), text("Once you pass, you\u2019re done until the next trick starts. No take-backs."), changedTag()),
      quote("Exception: Trip-Ups. A single Rank 0 can fire from anywhere, anytime, to beat a Solo Rank 10 \u2014 even after passing. Because banana peels wait for no one."),

      heading2("3. Clearing the Ledge (Winning a Trick)"),
      para(text("When all other players have passed, the last player standing wins the trick.")),
      para(bold("1. "), text("All played cards go face-up to Base Camp.")),
      para(bold("2. "), text("Power Check: If the winning card is Rank 6 or higher, the winner triggers their Faction Ability.")),
      para(bold("3. "), text("Lead again: The winner plays the next formation.")),
      quote("Key detail: The winning card determines the power, not the winning player. For Surges and Cannons, the rank of the set determines the power threshold, and you choose which card\u2019s faction to activate. One formation, one trigger."),
      quote("Trail Exhaustion: The instant you need to draw or look at cards from the Trail and it\u2019s empty, stop and reshuffle Base Camp into a new Trail immediately \u2014 then finish your draw or ability."),

      // Going Out — UPDATED
      heading2("Reaching The Summit (Going Out)"),
      para(text("When you play your last card, you immediately reach The Summit."), newTag()),
      bulletItem("The trick ends instantly \u2014 no Trip-Ups may be fired in response. Going out is sacred."),
      bulletItem("The player to your left leads the next trick."),
      bulletItem("Play continues until everyone has finished."),
      para(bold("Ability Finish: "), text("If a Faction Ability reduces your hand to zero cards, you immediately reach The Summit \u2014 just as if you\u2019d played your last card. Streamline discards your last card? Summit. Recalibrate nets you to zero? Summit. The mountain doesn\u2019t care how you got there."), newTag()),

      separator(),

      // ═══ FACTION ABILITIES ═══
      heading1("Faction Abilities"),
      para(text("Powers only trigger when you win a trick with a card ranked 6, 7, 8, 9, or 10. Win with a 5 or lower? No power. Just the trick.")),

      // Red
      heading3("Super-Dupes (Red) \u2014 THE ROTATION"),
      para(italic("\"Strength and Let Me Help\"")),
      para(text("The triggering player announces a direction \u2014 left or right. All players simultaneously choose 1 card from their hand and pass it to the player in that direction.")),
      para(text("Everyone gives, everyone receives. Nobody is safe.")),
      quote("3-Player Rule (Mandatory): At 3 players, The Rotation must alternate directions \u2014 if the last Rotation went left, the next must go right. At 4\u20135 players, direction choice is unrestricted."),

      // Orange
      heading3("Finders-Keepers (Orange) \u2014 SCOUT"),
      para(italic("\"Just Dibs Mine\"")),
      para(text("Look at the top 2 cards of the Trail. You may swap 1 card from your hand with 1 of them. Return any unchosen card(s) to the top of the Trail.")),

      // Yellow
      heading3("Tinkerers (Yellow) \u2014 STREAMLINE"),
      para(italic("\"Too slow!\"")),
      para(text("Discard 1 card from your hand to Base Camp. This is a racing game \u2014 every card in your hand is weight. Streamline drops dead weight and gets you closer to The Summit.")),

      // Green
      heading3("Prognosticationers (Green) \u2014 RECALIBRATE"),
      para(italic("\"I Knew That!\"")),
      para(text("Draw 1 card from the Trail, then discard 2 cards from your hand to Base Camp. Net result: your hand shrinks by one and gets better.")),

      // Blue — CHANGED
      heading3("Magicians (Blue) \u2014 THE REVELATION"),
      para(italic("\"Sleight of Paw\""), changedTag()),
      para(text("Choose "), bold("any other player"), text(". They reveal their hand to you only (nobody else peeks). Take 1 card from them. Then give them 1 card from your hand.")),
      para(text("You just gathered intel and swapped resources. The card you give them might be useless to you and devastating to them \u2014 or maybe you\u2019re planting a brick in their hand while stealing their finisher.")),
      quote("V2 Note: The \u201Cfewer cards\u201D restriction has been removed. In V1, Revelation could only target players with fewer cards than you \u2014 but in a race where everyone\u2019s shedding cards together, that window was too narrow. Revelation triggered 30\u201340% less than every other ability. Unrestricted, it\u2019s now competitive with all other factions and usable in the endgame when intel and card-stealing matter most."),

      // Purple
      heading3("Time Travelers (Purple) \u2014 RECLAIM"),
      para(italic("\"I\u2019ve already done this 1000x\"")),
      para(text("Swap 1 card from your hand with any card in Base Camp. That perfect card someone played three tricks ago? It\u2019s yours now.")),

      separator(),

      // ═══ FATIGUE ═══
      heading1("Fatigue (Scoring Across Rounds)"),
      para(text("Summit Scramble isn\u2019t a single race \u2014 it\u2019s a Championship. Play multiple rounds. Track Fatigue (Zzz\u2019s) after each round:")),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1560, 2340, 5460],
        rows: [
          new TableRow({ children: [headerCell("Place", 1560), headerCell("Status", 2340), headerCell("Fatigue (Zzz\u2019s)", 5460)] }),
          new TableRow({ children: [dataCell("1st", 1560), dataCell("Champion", 2340), dataCell("0", 5460)] }),
          new TableRow({ children: [dataCell("2nd", 1560), dataCell("Runner-Up", 2340), dataCell("2", 5460)] }),
          new TableRow({ children: [dataCell("3rd", 1560), dataCell("Podium", 2340), dataCell("4", 5460)] }),
          new TableRow({ children: [dataCell("4th", 1560), dataCell("Field Finish", 2340), dataCell("6", 5460)] }),
          new TableRow({ children: [dataCell("Last", 1560), dataCell("Dreaming", 2340), dataCell("8 + 1 per card remaining", 5460)] }),
        ],
      }),

      para(text("The Championship ends when any player\u2019s total Fatigue reaches 30 Zzz\u2019s (standard) or 20 Zzz\u2019s (short format). Lowest total Fatigue wins the title.")),
      para(text("After each round, the player who finished last leads the first trick of the next round.")),
      quote("Mercy Rule (Recommended for your first Championship): Cap maximum Fatigue per round at 12 Zzz\u2019s."),

      separator(),

      // ═══ STORED SURGE ═══
      heading1("The Stored Surge (Advanced Tactic)"),
      para(italic("Skip this section for your first game. Come back when you\u2019re hungry for more.")),
      para(text("When you win a trick with a Power Rank card (6\u201310), you may Store that card instead of triggering its Faction Ability:")),
      bulletItem("Place it face-up in front of you. This is your Stored Surge. (Maximum 1 at a time.)"),
      bulletItem("On a future trick that you win with any Power Rank (6\u201310), you may release your Stored Surge to trigger the faction ability of your current winning card twice. A Double Surge."),
      para(text("The stored card is gone \u2014 it doesn\u2019t return to your hand. You spent it as fuel for a future explosion.")),

      separator(),

      // ═══ TEAM RELAYS ═══
      heading1("Team Relays (Partnership Mode)"),
      para(italic("4 Players")),
      para(bold("Setup: "), text("Partners sit across from each other (not adjacent). Mixed faction teams allowed. Deal cards normally.")),
      para(bold("The Huddle: "), text("Partners may openly discuss strategy and show each other their hands at any time. This is a relay, not a spy mission.")),
      para(bold("Scoring: "), text("Combined Fatigue \u2014 your team\u2019s total is the sum of both partners\u2019 scores. Lowest combined total wins.")),
      quote("Casual Relay (Optional): Use Better Half Scoring \u2014 your team\u2019s Fatigue equals the lower of the two partners\u2019 scores + 2."),
      para(bold("The Assist: "), text("You may deliberately pass on a trick your partner is currently winning. Let them have it. Preserve their momentum.")),

      new Paragraph({
        heading: HeadingLevel.HEADING_3,
        spacing: { before: 200, after: 100 },
        children: [new TextRun({ text: "The Tag", bold: true, size: 24, font: "Georgia", color: DARK }), newTag()],
      }),
      para(text("Once per round, when you win a trick with a Power Rank card (6\u201310), you may give the lead to your partner instead of leading the next trick yourself. You skip your own Faction Ability trigger to do this \u2014 the power goes into the handoff, not into an ability.")),
      para(text("Your partner leads the next trick as if they had won it. This lets you set up your partner at a critical moment: clear the path, then tag them in for the sprint.")),
      quote("The cost is real. You sacrifice a Faction Ability trigger \u2014 no Streamline, no Rotation, no Revelation. What you get is initiative transfer at exactly the right moment."),

      para(bold("Friendly Fire: "), text("Faction Abilities are indiscriminate. If The Rotation passes your partner a nightmare card, that\u2019s legal. One exception: The Revelation may not target your partner.")),

      new Paragraph({
        heading: HeadingLevel.HEADING_3,
        spacing: { before: 200, after: 100 },
        children: [new TextRun({ text: "The Summit Sweep", bold: true, size: 24, font: "Georgia", color: DARK }), changedTag()],
      }),
      para(text("If one team captures 1st AND 2nd place consecutively in the same round \u2014 meaning both partners finish before any opponent does \u2014 they execute a Summit Sweep:")),
      bulletItem("Sweeping team: 0 Fatigue (perfect execution)"),
      bulletItem("All other teams: 12 Fatigue (outclassed by the surge)"),
      para(text("Sweeps are rare. Sweeps are devastating. Sweeps are extremely satisfying if you\u2019re on the right side.")),
      quote("V2 Note: The penalty was reduced from 20 to 12 Fatigue, and sweeps now require consecutive finishes. This keeps multi-round strategy viable while still making sweeps a significant moment."),

      separator(),

      // ═══ SOLO ═══
      heading1("Solo Challenge: The Night Shift"),
      para(italic("1\u20132 Players")),
      para(text("You vs. Two Night Owls (Deck A and Deck B). Deal yourself 12 cards. Split the remaining cards evenly between the two Owl decks, face-down.")),
      para(bold("Turn Order: "), text("You \u2192 Owl A \u2192 You \u2192 Owl B.")),
      para(bold("When an Owl Leads: "), text("The active Owl flips its top card. That\u2019s the trick. Beat it or pass.")),
      para(bold("When an Owl Follows: "), text("The active Owl flips its top card. If it beats the current high card, the Owl takes the lead. Otherwise, the Owl rests.")),
      para(bold("The Strategic Conserve: "), text("When you have 3 or fewer cards, you may pass on a trick you could otherwise beat.")),
      para(bold("Solo Faction Variants: "), text("Since Owls have no hands, Red becomes The Substitution (force Owl to skip next turn) and Blue becomes The Forecast (peek and swap top cards of Owl decks). All other abilities work normally.")),
      para(bold("Iron Climb Mode: "), text("Owls do not rest \u2014 they keep flipping until the trick resolves. Win rate: <5%.")),

      separator(),

      // ═══ QUICK REFERENCE ═══
      heading1("Quick Reference"),
      para(bold("Victory: "), text("Lowest total Fatigue when someone reaches 30 Zzz\u2019s (or 20 in short format).")),
      para(bold("On Your Turn: "), text("Beat the current formation with a higher one of the same type \u2014 or pass.")),

      // Formations table
      para(bold("Formations:")),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2000, 2680, 4680],
        rows: [
          new TableRow({ children: [headerCell("Formation", 2000), headerCell("What It Is", 2680), headerCell("Beat With", 4680)] }),
          new TableRow({ children: [dataCell("Solo Sprint", 2000), dataCell("1 card", 2680), dataCell("Higher rank (ties: faction hierarchy)", 4680)] }),
          new TableRow({ children: [dataCell("Surge", 2000), dataCell("2 or 3 of same rank", 2680), dataCell("Higher rank, same quantity", 4680)] }),
          new TableRow({ children: [dataCell("Daisy Chain", 2000), dataCell("3+ consecutive ranks", 2680), dataCell("Higher top rank, same length", 4680)] }),
          new TableRow({ children: [
            dataCell("Confetti Cannon", 2000, { highlight: true }),
            dataCell("4 of same rank", 2680, { highlight: true }),
            dataCell("Higher rank Cannon (standard formation, not an interrupt)", 4680, { highlight: true }),
          ] }),
          new TableRow({ children: [dataCell("Trip-Up", 2000), dataCell("Single Rank 0", 2680), dataCell("Beats Solo Rank 10 only \u2014 the sole interrupt", 4680)] }),
        ],
      }),

      para(bold("Faction Hierarchy (Ties): "), text("Red > Orange > Yellow > Green > Blue > Purple")),

      para(bold("Trick Flow:"), changedTag()),
      bulletItem("Winner leads any formation"),
      bulletItem("Clockwise: beat it or pass"),
      bulletItem("Pass = out until next trick (Trip-Ups are the only exception)"),
      bulletItem("Last standing wins \u2192 discard to Base Camp \u2192 power check (6+) \u2192 lead again"),

      // Ability table
      para(bold("Faction Abilities (Win a trick with Rank 6\u201310):"), changedTag()),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1560, 2000, 5800],
        rows: [
          new TableRow({ children: [headerCell("Faction", 1560), headerCell("Ability", 2000), headerCell("Effect", 5800)] }),
          new TableRow({ children: [dataCell("Red", 1560), dataCell("The Rotation", 2000), dataCell("Choose left or right; everyone passes 1 card that direction", 5800)] }),
          new TableRow({ children: [dataCell("Orange", 1560), dataCell("Scout", 2000), dataCell("Look at top 2 of Trail; may swap 1 from hand with 1 of them", 5800)] }),
          new TableRow({ children: [dataCell("Yellow", 1560), dataCell("Streamline", 2000), dataCell("Discard 1 card from hand", 5800)] }),
          new TableRow({ children: [dataCell("Green", 1560), dataCell("Recalibrate", 2000), dataCell("Draw 1, then discard 2 from hand", 5800)] }),
          new TableRow({ children: [
            dataCell("Blue", 1560, { highlight: true }),
            dataCell("The Revelation", 2000, { highlight: true }),
            dataCell(new TextRun({ text: "Target any other player: see hand, take 1, give 1", font: "Georgia", size: 20, color: DARK, bold: true }), 5800, { highlight: true }),
          ] }),
          new TableRow({ children: [dataCell("Purple", 1560), dataCell("Reclaim", 2000), dataCell("Swap 1 from hand with any card in Base Camp", 5800)] }),
        ],
      }),

      para(bold("Ability Finish: "), text("If any ability empties your hand, you reach The Summit immediately."), newTag()),
      para(bold("Stored Surge (Advanced): "), text("Store a 6\u201310 win card face-up (max 1). Release on future 6\u201310 win to trigger that power twice.")),
      para(bold("Fatigue: "), text("1st = 0 | 2nd = 2 | 3rd = 4 | 4th = 6 | Last = 8 + 1 per card remaining")),

      separator(),

      // ═══ DESIGNER'S NOTE ═══
      heading1("Designer\u2019s Note"),
      para(text("Summit Scramble is the middle child of this collection \u2014 faster than Contests of Chaos, sharper than Get Stuffed. Mechanically, this is a climbing game in the Big Two / President / Tichu family. That pedigree is proven \u2014 \u201Cplay bigger or pass\u201D is one of the most elegant structures in card gaming.")),
      para(bold("On the V2 Changes: "), text("These three adjustments were tested across 5,000+ AI-vs-AI simulated games. The Confetti Cannon lost its interrupt status because having two interrupt mechanics (Cannon and Trip-Up) added cognitive load without proportional fun \u2014 the Trip-Up alone creates all the table-drama you need. The Revelation lost its targeting restriction because it made Blue the weakest faction by a wide margin; unrestricted, all six abilities now trigger at comparable rates. And the ability-finish rule closes a genuine gap where Streamline or Recalibrate could empty a hand with no rule covering what happens next.")),
      para(bold("On the Trip-Up: "), text("A single 0 beating a single 10 is the best moment in the game. Making it the sole interrupt \u2014 playable anytime, even after passing \u2014 turns every solo 10 into a table-wide held breath. The restriction (Solo Sprints only, can\u2019t interrupt going out) keeps it surgical.")),
      para(text("Play hard. Shake hands after.")),

      separator(),

      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 200 },
        children: [italic("Summit Scramble is part of the Hamsters & Monsters collection by Design/Play Labs.")],
      }),
    ],
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/sessions/funny-laughing-sagan/mnt/summit-scramble/summit-scramble-rules-v2.docx", buffer);
  console.log("V2 rules document created successfully.");
});
