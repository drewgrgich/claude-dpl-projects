const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, PageBreak, LevelFormat
} = require("docx");

// Color palette
const COLORS = {
  primary: "2E4057",    // Dark blue
  accent: "048A81",     // Teal
  warning: "D4A017",    // Gold
  danger: "C62828",     // Red
  success: "2E7D32",    // Green
  lightBg: "F5F7FA",    // Light gray bg
  headerBg: "2E4057",   // Dark blue bg
  white: "FFFFFF",
  black: "000000",
  gray: "666666",
  lightGray: "CCCCCC",
  bugBg: "FFF3E0",      // Light orange
  insightBg: "E8F5E9",  // Light green
  criticalBg: "FFEBEE",  // Light red
};

const border = { style: BorderStyle.SINGLE, size: 1, color: COLORS.lightGray };
const borders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0 };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function heading(text, level = HeadingLevel.HEADING_1) {
  return new Paragraph({ heading: level, children: [new TextRun(text)] });
}

function para(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120 },
    ...opts,
    children: [new TextRun({ font: "Arial", size: 22, color: COLORS.black, ...opts.run, text })]
  });
}

function boldPara(label, text) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [
      new TextRun({ font: "Arial", size: 22, bold: true, text: label }),
      new TextRun({ font: "Arial", size: 22, text })
    ]
  });
}

function bulletItem(text, ref = "bullets", level = 0) {
  return new Paragraph({
    numbering: { reference: ref, level },
    children: [new TextRun({ font: "Arial", size: 22, text })]
  });
}

function numberedItem(text, ref = "numbers", level = 0) {
  return new Paragraph({
    numbering: { reference: ref, level },
    children: [new TextRun({ font: "Arial", size: 22, text })]
  });
}

function spacer() {
  return new Paragraph({ spacing: { after: 60 }, children: [] });
}

function colorBox(title, body, bgColor, titleColor = COLORS.black) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders: {
              top: { style: BorderStyle.SINGLE, size: 2, color: titleColor },
              bottom: { style: BorderStyle.SINGLE, size: 1, color: COLORS.lightGray },
              left: { style: BorderStyle.SINGLE, size: 2, color: titleColor },
              right: { style: BorderStyle.SINGLE, size: 1, color: COLORS.lightGray }
            },
            shading: { fill: bgColor, type: ShadingType.CLEAR },
            margins: { top: 120, bottom: 120, left: 200, right: 200 },
            width: { size: 9360, type: WidthType.DXA },
            children: [
              new Paragraph({ spacing: { after: 80 }, children: [
                new TextRun({ font: "Arial", size: 24, bold: true, color: titleColor, text: title })
              ]}),
              ...body.map(line => new Paragraph({ spacing: { after: 60 }, children: [
                new TextRun({ font: "Arial", size: 21, text: line })
              ]}))
            ]
          })
        ]
      })
    ]
  });
}

function makeScoreTable() {
  const headerRow = (cells) => new TableRow({
    children: cells.map((text, i) => new TableCell({
      borders,
      shading: { fill: COLORS.headerBg, type: ShadingType.CLEAR },
      margins: cellMargins,
      width: { size: [2340, 1560, 1560, 1560, 1170, 1170][i], type: WidthType.DXA },
      children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
        new TextRun({ font: "Arial", size: 20, bold: true, color: COLORS.white, text })
      ]})]
    }))
  });

  const dataRow = (cells, highlight = false) => new TableRow({
    children: cells.map((text, i) => new TableCell({
      borders,
      shading: highlight ? { fill: "E8F5E9", type: ShadingType.CLEAR } : undefined,
      margins: cellMargins,
      width: { size: [2340, 1560, 1560, 1560, 1170, 1170][i], type: WidthType.DXA },
      children: [new Paragraph({ alignment: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER, children: [
        new TextRun({ font: "Arial", size: 20, bold: i === 0 || highlight, text: String(text) })
      ]})]
    }))
  });

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2340, 1560, 1560, 1560, 1170, 1170],
    rows: [
      headerRow(["Player", "Event VP", "Playbook VP", "Shiny Bonus", "Total VP", "Place"]),
      dataRow(["Player1", "35", "0", "0", "35", "1st"], true),
      dataRow(["Player3", "15", "0", "3", "18", "2nd"]),
      dataRow(["Player2", "6", "4", "2", "12", "3rd"]),
    ]
  });
}

function makeEventsTable() {
  const headerRow = new TableRow({
    children: ["Player", "Event", "Turn", "VP", "Cards Used"].map((text, i) => new TableCell({
      borders,
      shading: { fill: COLORS.headerBg, type: ShadingType.CLEAR },
      margins: cellMargins,
      width: { size: [1400, 2200, 900, 800, 4060][i], type: WidthType.DXA },
      children: [new Paragraph({ children: [
        new TextRun({ font: "Arial", size: 20, bold: true, color: COLORS.white, text })
      ]})]
    }))
  });

  const events = [
    ["Player2", "Tug of War", "5", "3", "3x Super-Dupes"],
    ["Player1", "Limbo Contest", "7", "8", "4 cards, Sum = 5"],
    ["Player2", "Drag Race", "14", "3", "YLW-5, YLW-6, RED-10 (FA as Tinkerer)"],
    ["Player1", "Convoy", "19", "6", "GRN-0, ORG-1, PUR-2 (run 0-1-2)"],
    ["Player3", "New Rules!", "25", "15", "PUR-5, RED-5, GRN-5, ORG-5 (quad 5s)"],
    ["Player1", "Capture the Flag", "29", "5", "BLU-7, YLW-10 (FA), ORG-4"],
    ["Player1", "Group Photo", "43", "16", "YLW-2, RED-3, ORG-7, GRN-2, BLU-6, PUR-1"],
  ];

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [1400, 2200, 900, 800, 4060],
    rows: [headerRow, ...events.map(cells => new TableRow({
      children: cells.map((text, i) => new TableCell({
        borders,
        margins: cellMargins,
        width: { size: [1400, 2200, 900, 800, 4060][i], type: WidthType.DXA },
        children: [new Paragraph({ children: [
          new TextRun({ font: "Arial", size: 19, text })
        ]})]
      }))
    }))]
  });
}

async function main() {
  const doc = new Document({
    styles: {
      default: { document: { run: { font: "Arial", size: 22 } } },
      paragraphStyles: [
        {
          id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 36, bold: true, font: "Arial", color: COLORS.primary },
          paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 }
        },
        {
          id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 30, bold: true, font: "Arial", color: COLORS.accent },
          paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 }
        },
        {
          id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 26, bold: true, font: "Arial", color: COLORS.primary },
          paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 }
        },
      ]
    },
    numbering: {
      config: [
        {
          reference: "bullets",
          levels: [{
            level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } }
          }]
        },
        {
          reference: "bullets2",
          levels: [{
            level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } }
          }]
        },
        {
          reference: "numbers",
          levels: [{
            level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } }
          }]
        },
        {
          reference: "numbers2",
          levels: [{
            level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } }
          }]
        },
      ]
    },
    sections: [
      // TITLE PAGE
      {
        properties: {
          page: {
            size: { width: 12240, height: 15840 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
          }
        },
        children: [
          spacer(), spacer(), spacer(), spacer(), spacer(), spacer(),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [
            new TextRun({ font: "Arial", size: 52, bold: true, color: COLORS.primary, text: "Contests of Chaos" })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [
            new TextRun({ font: "Arial", size: 32, color: COLORS.accent, text: "Playtest Analysis Report" })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [
            new TextRun({ font: "Arial", size: 24, color: COLORS.gray, text: "Seed 29 \u2014 3-Player Game with Playbooks" })
          ]}),
          spacer(), spacer(),
          new Paragraph({ alignment: AlignmentType.CENTER, border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: COLORS.accent } }, spacing: { after: 200 }, children: [] }),
          spacer(),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [
            new TextRun({ font: "Arial", size: 22, color: COLORS.gray, text: "Prepared for Drew Grgich" })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [
            new TextRun({ font: "Arial", size: 22, color: COLORS.gray, text: "Design/Play Labs" })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [
            new TextRun({ font: "Arial", size: 22, color: COLORS.gray, text: "March 2026" })
          ]}),
          spacer(), spacer(), spacer(), spacer(),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ font: "Arial", size: 20, italics: true, color: COLORS.gray, text: "Analysis based on agentic AI playtest: turn-by-turn transcript and designer report" })
          ]}),
        ]
      },
      // MAIN CONTENT
      {
        properties: {
          page: {
            size: { width: 12240, height: 15840 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
          }
        },
        headers: {
          default: new Header({ children: [
            new Paragraph({
              border: { bottom: { style: BorderStyle.SINGLE, size: 1, color: COLORS.accent } },
              spacing: { after: 200 },
              children: [
                new TextRun({ font: "Arial", size: 18, color: COLORS.gray, text: "Contests of Chaos \u2014 Playtest Analysis \u2014 Seed 29" })
              ]
            })
          ]})
        },
        footers: {
          default: new Footer({ children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({ font: "Arial", size: 18, color: COLORS.gray, text: "Page " }),
                new TextRun({ font: "Arial", size: 18, color: COLORS.gray, children: [PageNumber.CURRENT] })
              ]
            })
          ]})
        },
        children: [
          // EXECUTIVE SUMMARY
          heading("Executive Summary"),
          para("This report analyzes a 3-player AI playtest of Contests of Chaos (Seed 29) with the Playbook module enabled. The game ran 45 turns across 15 rounds, ending when Player1 triggered the Standing Ovation with 35 Event VP after completing Group Photo (16 VP) on Turn 43. The playtest revealed several actionable findings for the designer, including one significant rules ambiguity around Free Agent overlap in faction requirements, a Jumbotron stagnation problem in the late game, and balance concerns with the highest-VP events."),
          spacer(),

          // FINAL SCORES
          heading("Final Scores", HeadingLevel.HEADING_2),
          makeScoreTable(),
          spacer(),
          para("Player1 won decisively with 35 total VP, all from events. Player3 finished second at 18 VP (15 event + 3 Shiny bonus) despite completing only one event. Player2 placed third at 12 VP (6 event + 4 playbook + 2 Shiny bonus) despite being the first to score. The wide spread (35 vs 18 vs 12) suggests potential snowball dynamics worth monitoring across additional playtests."),
          spacer(),

          // ALL EVENTS COMPLETED
          heading("Events Completed During Game", HeadingLevel.HEADING_2),
          makeEventsTable(),
          spacer(),
          para("Only 7 events were completed across 45 turns (roughly 1 event per 6.4 turns). Player1 completed 4 events, Player2 completed 2, and Player3 completed 1. Despite completing the fewest events, Player3's single New Rules! play (15 VP) was worth more than both of Player2's events combined (6 VP)."),

          new Paragraph({ children: [new PageBreak()] }),

          // SECTION 1: BUGS AND RULE ISSUES
          heading("Section 1: Rules Bugs and Ambiguities"),
          para("Cross-referencing every action in the playtest transcript against the official rules document revealed one significant rules ambiguity and several minor observations. The game engine generally enforced the rules correctly, but the ambiguity caused real strategic harm to one player."),
          spacer(),

          // BUG 1 - Critical
          colorBox(
            "\u26A0 CRITICAL: Free Agent + Faction Overlap Ambiguity (Time Capsule)",
            [
              "Event: Time Capsule (9 VP) \u2014 Requires 3x Time Travelers + 2 Free Agents, Sum \u2265 22.",
              "",
              "Player2 attempted to complete this with: PUR-8 (signed TT), PUR-9 (signed TT), PUR-10 (TT Free Agent), ORG-0 (FK Free Agent). The engine rejected this combination.",
              "",
              "The ambiguity: PUR-10 is both a Time Traveler (its printed faction) AND a Free Agent (rank 10). Can it count toward the \"3x Time Travelers\" requirement AND also satisfy one of the \"2 Free Agents\" slots? The engine required 3 separate signed TTs plus 2 additional Free Agents (5 total cards), treating the requirements as non-overlapping.",
              "",
              "Player2 spent approximately 20 turns (Turns 17-38) building toward this event and was never able to complete it. This single ambiguity effectively locked Player2 out of competitive play for the entire mid-to-late game.",
              "",
              "RECOMMENDATION: Explicitly state in the rules whether Free Agents of a named faction can count toward both the faction requirement and the Free Agent requirement simultaneously. Consider adding a clarifying example to the Time Capsule or Soapbox Derby event entries."
            ],
            COLORS.criticalBg,
            COLORS.danger
          ),
          spacer(),

          // BUG 2 - Moderate
          colorBox(
            "\u26A0 MODERATE: Buddy System Edge Case with Free-Agent-Heavy Events",
            [
              "Events like Secret Playbook (4x Free Agents) and Sprinkler Ambush (3 cards of number 0) create confusion about whether the Buddy System applies. Since these events specifically request Free Agents or rank-0 cards rather than faction members, the Buddy requirement may not apply. However, the rules state Free Agents \"can count as any faction\" but need a Buddy for \"each faction you're claiming.\" If you're not claiming a faction (just playing Free Agents as Free Agents), no Buddy is needed.",
              "",
              "The engine handled this correctly in all observed cases, but Player2's feedback specifically flagged confusion about how faction identity overlaps with Free Agent identity in multi-requirement events.",
              "",
              "RECOMMENDATION: Add a sidebar or FAQ entry clarifying: \"When an event asks for Free Agents specifically, the Buddy System does not apply \u2014 these cards are being recruited as versatile athletes, not as faction representatives.\""
            ],
            COLORS.bugBg,
            COLORS.warning
          ),
          spacer(),

          // BUG 3 - Minor
          colorBox(
            "\u2139 MINOR: Playbook Timing Language (\"Combo\" vs \"Finish\")",
            [
              "Player1's feedback noted that the distinction between \"Combo\" timing (scored when completing an event) and \"Finish\" timing (scored at end of turn based on game state) could be confusing. The rules document doesn't explicitly define these timing keywords \u2014 they appear only on the Playbook cards themselves.",
              "",
              "RECOMMENDATION: Add a brief timing definition in the Playbook Setup section of the rules: \"Combo playbooks trigger when you complete an event that matches their condition. Finish playbooks trigger at the end of your turn if their condition is met.\""
            ],
            COLORS.lightBg,
            COLORS.primary
          ),
          spacer(),

          // Verified correct
          heading("Verified Rule Implementations", HeadingLevel.HEADING_3),
          para("The following mechanics were verified as correctly implemented throughout the playtest:"),
          bulletItem("Slot pricing: All Lineup drafts correctly charged 0/1/2/3 Shinies for Slots 1-4 and distributed Shinies to cards to the left"),
          bulletItem("Shiny collection: Players correctly collected all Shinies sitting on drafted cards"),
          bulletItem("Scramble mechanics: Slot 1 discarded, lineup slid, new card dealt to Slot 4, Shinies transferred correctly"),
          bulletItem("Free Agent Buddy System: All event completions using Free Agents included at least one signed player (ranks 1-9) of the claimed faction"),
          bulletItem("Run validation: Convoy accepted 0-1-2 as valid (rules explicitly state \"0-1-2 and 8-9-10 valid\")"),
          bulletItem("Hand limit enforcement: Players correctly discarded to 8 cards at end of turn"),
          bulletItem("Jumbotron sliding and refill after event completion and Timeout flushes"),
          bulletItem("Standing Ovation trigger at 30+ Event VP with remaining players getting final turns"),
          bulletItem("Playbook scoring limited to 1 per turn (Player2 scored The Perfect 10 on Turn 14)"),
          bulletItem("Timeout: 1 Shiny gained, optional discard of up to 2 cards, optional Jumbotron Slot 1 flush"),

          new Paragraph({ children: [new PageBreak()] }),

          // SECTION 2: DESIGN ANALYSIS
          heading("Section 2: Design Analysis"),

          heading("Game Pacing", HeadingLevel.HEADING_2),
          para("The game exhibited three distinct pacing phases with markedly different feel:"),
          spacer(),
          boldPara("Early Game (Turns 1-14): Excellent. ", "Fast drafting, early event completions (Tug of War Turn 5, Limbo Contest Turn 7, Drag Race Turn 14), and meaningful resource decisions. All three players felt engaged. The Tier 1-2 events provided accessible scoring opportunities that rewarded tempo play. Player2 achieved a satisfying 7 VP combo turn (Drag Race + The Perfect 10 playbook) on Turn 14."),
          spacer(),
          boldPara("Mid Game (Turns 15-29): Strong but uneven. ", "Player1 steadily built toward Convoy and completed it on Turn 19. Player3 executed a brilliant 8-turn plan to assemble four rank-5 cards for New Rules! (15 VP on Turn 25). Player2 began building toward Time Capsule but couldn't complete it due to the Free Agent ambiguity. The mid-game showcased the game's best strategic depth \u2014 multi-turn planning, reading opponents, and weighing draft vs. score decisions."),
          spacer(),
          boldPara("Late Game (Turns 30-45): Problematic. ", "The Jumbotron became clogged with events requiring Time Travelers, Free Agents, and rank-0 cards that no player could complete. Player3 spent roughly 5 consecutive turns calling Timeout just to flush events, gaining almost nothing. Player2 was similarly stuck for 15+ turns. Only Player1 maintained momentum by pursuing Group Photo. All three AI players flagged this phase as frustrating, with fun ratings dropping (Player2: 6/10, Player3: 6/10)."),
          spacer(),

          heading("Balance Observations", HeadingLevel.HEADING_2),

          heading("VP Curve and Event Dominance", HeadingLevel.HEADING_3),
          para("The VP distribution across tiers creates a steep power curve. Group Photo (16 VP) and New Rules! (15 VP) are worth roughly 5x a Tier 1 event. In this playtest, these two events accounted for 31 of the 62 total Event VP scored (50%). Player1 won almost entirely on the back of a single 16 VP play, jumping from 19 to 35 VP in one action."),
          spacer(),
          para("This isn't inherently problematic \u2014 big swing events create exciting moments \u2014 but the difficulty curve may not match the VP curve. Group Photo requires 6 cards (one per faction) with no sum requirement, no Free Agent restriction, and no minimum rank. A patient player who drafts one card per faction over 12+ turns can reliably complete it. Contrast this with Instant Replay (10 VP), which needs 4 Time Travelers with Sum \u2265 22 and max 1 Free Agent \u2014 a significantly harder requirement for less reward."),
          spacer(),
          boldPara("Recommendation: ", "Consider adding a constraint to Group Photo (Sum \u2265 20, or \"no Free Agents\") and/or reducing its VP to 12-14. Similarly, evaluate whether New Rules! at 15 VP is proportional to its difficulty of assembling 4 same-rank cards across different factions."),
          spacer(),

          heading("Jumbotron Stagnation", HeadingLevel.HEADING_3),
          para("The most consistently flagged issue across all three players was Jumbotron stagnation. From approximately Turn 30 to Turn 42, the Jumbotron displayed events that required resources none of the players had (Time Travelers, multiple Free Agents, rank-0 cards). Players could only flush one event per Timeout (Slot 1), meaning it took 4 Timeouts to fully cycle the Jumbotron. During this period, the game effectively paused for Player2 and Player3."),
          spacer(),
          para("The Event Deck's composition naturally skews toward harder events in the late game because Tier 1-2 events are completed or flushed early. By Turn 30, the remaining events were disproportionately Tier 4-6, requiring specific faction combinations that players couldn't assemble from the depleted Recruit Deck."),
          spacer(),
          boldPara("Recommendation: ", "Consider one or more of the following mitigations:"),
          numberedItem("Auto-flush: If no event is completed for X consecutive rounds (e.g., one full rotation of players), automatically flush the Slot 1 event at the start of the next round."),
          numberedItem("Wildcard flush: Introduce a new action or Timeout upgrade that flushes all 4 Jumbotron events at once (at a higher cost than a single flush)."),
          numberedItem("Event deck composition: Ensure the Event Deck has a more even tier distribution, or seed Tier 1-2 events throughout the deck rather than letting them cluster at the top."),
          numberedItem("Partial completion: Allow players to \"attempt\" an event with an incomplete hand, paying a Shiny penalty for each missing requirement, to prevent total lockout."),
          spacer(),

          heading("The Rookie Playbook Is Too Restrictive", HeadingLevel.HEADING_3),
          para("Player1 held The Rookie (3 VP: Complete an event using only ranks 1-5) for the entire game and never scored it. This happened despite Player1 completing 4 events, because most events require either high-rank cards for sum thresholds or rank 0/10 Free Agents for faction flexibility. The intersection of \"ranks 1-5 only\" and \"event requirements\" is extremely narrow \u2014 essentially limited to a few Tier 1 events."),
          spacer(),
          boldPara("Recommendation: ", "Broaden the condition to ranks 1-6, or increase the VP reward to 4-5 VP to justify the strategic cost of avoiding Free Agents and high-rank cards."),
          spacer(),

          heading("The Agent Action Economy", HeadingLevel.HEADING_3),
          para("No player used The Agent action during this playtest. At 5 Shinies, it represents a major investment (equivalent to drafting from Slot 4 plus 2 additional Shinies). Player2's feedback noted that the tension between spending on The Agent vs. saving for Lineup drafts made The Agent impractical. Player3 considered it but chose drafting every time."),
          spacer(),
          boldPara("Recommendation: ", "Consider reducing the cost to 3-4 Shinies, or adding a small bonus (e.g., draw 3 keep 1, or also gain 1 Shiny) to make the action more competitive with drafting."),
          spacer(),

          heading("Shiny Economy", HeadingLevel.HEADING_3),
          para("The Shiny economy worked well overall. The sliding Lineup pricing was consistently praised by all players \u2014 the tension between \"draft what I need\" vs. \"grab the pile of Shinies on that neglected card\" created interesting decisions every turn. Player3 accumulated 12 Shinies by Turn 39, reaching the effective cap (9 Shinies = 3 VP maximum Shiny bonus). Additional Shinies beyond 9 had zero marginal value."),
          spacer(),
          boldPara("Recommendation: ", "Consider communicating the 3 VP / 9 Shiny cap more prominently, or providing an alternative use for excess Shinies (e.g., \"pay 3 Shinies to draw a card from the Recruit Deck\" as a bonus action)."),

          new Paragraph({ children: [new PageBreak()] }),

          // SECTION 3: STRATEGY
          heading("Section 3: Strategy Diversity"),
          para("The three AI players pursued meaningfully different strategies, suggesting the game supports multiple paths. However, only the broadest strategy (diverse faction collection) proved viable in this particular game."),
          spacer(),

          heading("Player1: Faction Diversity \u2192 Group Photo", HeadingLevel.HEADING_2),
          para("Player1 started with two Free Agents and focused on low-rank efficiency early (Limbo Contest for 8 VP on Turn 7). After completing three mid-tier events, Player1 pivoted to deliberately collecting one card from each faction to pursue Group Photo (16 VP). This 12-turn commitment from Turn 31-43 paid off with a game-winning play. This strategy rewarded patience, broad drafting, and reading the Jumbotron correctly."),
          spacer(),

          heading("Player2: Faction Specialization \u2192 Stalled", HeadingLevel.HEADING_2),
          para("Player2 scored early with Tug of War (3x Super-Dupes) and Drag Race (3x Tinkerers with a Free Agent), then pivoted to assembling Time Travelers for Instant Replay (10 VP) or Time Capsule (9 VP). This specialization strategy failed due to two compounding factors: the Free Agent/faction overlap ambiguity prevented Time Capsule completion, and no signed Time Travelers appeared in the Lineup for 20+ turns. Player2 was effectively locked out of scoring from Turn 14 to game end."),
          spacer(),

          heading("Player3: Set Collection \u2192 New Rules!", HeadingLevel.HEADING_2),
          para("Player3 recognized an opportunity to collect four rank-5 cards from different factions and executed a brilliant 8-turn plan to complete New Rules! for 15 VP. After this explosive play, however, Player3 faced the same Jumbotron stagnation as Player2 and spent the remaining 20 turns flushing events and accumulating Shinies without scoring again."),
          spacer(),

          heading("Strategy Takeaways", HeadingLevel.HEADING_3),
          bulletItem("Diverse faction drafting was the most resilient strategy, working across multiple event types"),
          bulletItem("Deep faction specialization carried high risk due to dependence on specific cards appearing in the Lineup"),
          bulletItem("Early scoring (Tier 1-2 events) provided critical tempo advantage \u2014 Player1 and Player2 scored in the first 7 turns while Player3 waited until Turn 25"),
          bulletItem("The game rewarded reading the Jumbotron and adapting to available events rather than pre-planning a fixed strategy"),
          bulletItem("Playbooks influenced early drafting decisions (Player2 drafted RED-10 partly for The Perfect 10) but became less relevant in the mid-to-late game"),

          new Paragraph({ children: [new PageBreak()] }),

          // SECTION 4: WHAT WORKED WELL
          heading("Section 4: What Worked Well"),

          heading("Core Drafting Mechanic", HeadingLevel.HEADING_2),
          para("The sliding Lineup market with Shiny accumulation was the standout mechanic. All three players praised the tension it creates: cards become cheaper as they slide left, but they also accumulate Shinies from other players' purchases. This creates a genuine dilemma between \"draft the card I need now\" and \"wait for it to get cheaper and sweeter.\" The mechanic also provides natural catch-up, as neglected cards become treasure chests."),
          spacer(),

          heading("Event Variety", HeadingLevel.HEADING_2),
          para("The range of event requirements (faction-based, sum-based, runs, sets, mixed) rewarded flexible drafting and created diverse hand-building strategies. The flavor text on events was consistently entertaining and reinforced the game's light-hearted tone."),
          spacer(),

          heading("Playbook Integration", HeadingLevel.HEADING_2),
          para("When Playbooks triggered, they created satisfying combo moments. Player2's Drag Race + The Perfect 10 combo on Turn 14 was a highlight \u2014 a 7 VP turn that felt earned and strategic. The hidden information added meaningful tension to opponents' drafting decisions."),
          spacer(),

          heading("Free Agent Flexibility", HeadingLevel.HEADING_2),
          para("The Free Agent / Buddy System is a clever design that rewards holding versatile cards while preventing degenerate all-Free-Agent strategies. It was correctly applied in all event completions observed. The strategic depth of deciding which faction a Free Agent \"plays for\" was a recurring decision point that players engaged with thoughtfully."),

          new Paragraph({ children: [new PageBreak()] }),

          // SECTION 5: RECOMMENDATIONS SUMMARY
          heading("Section 5: Prioritized Recommendations"),
          spacer(),

          colorBox(
            "Priority 1: Clarify Free Agent + Faction Overlap Rules",
            [
              "Impact: High \u2014 directly caused a player to be locked out of scoring for 20+ turns",
              "Effort: Low \u2014 requires adding 2-3 sentences and an example to the rules",
              "Add explicit language for events with \"X Faction + Y Free Agents\" requirements stating whether a Free Agent of the named faction counts toward both requirements or only one"
            ],
            COLORS.criticalBg,
            COLORS.danger
          ),
          spacer(),

          colorBox(
            "Priority 2: Address Jumbotron Stagnation",
            [
              "Impact: High \u2014 all three players flagged late-game stagnation as the primary negative experience",
              "Effort: Medium \u2014 requires playtesting new mechanic (auto-flush, wildcard flush, or deck composition change)",
              "The current single-event-per-Timeout flush rate is too slow when all 4 events are uncompletable"
            ],
            COLORS.bugBg,
            COLORS.warning
          ),
          spacer(),

          colorBox(
            "Priority 3: Evaluate Group Photo and New Rules! VP Values",
            [
              "Impact: Medium \u2014 these events dominated the VP economy (31 of 62 total Event VP scored)",
              "Effort: Low \u2014 number adjustment and/or adding a constraint (e.g., sum requirement, no Free Agents)",
              "Consider whether a single event should be able to provide 50%+ of the victory threshold"
            ],
            COLORS.bugBg,
            COLORS.warning
          ),
          spacer(),

          colorBox(
            "Priority 4: Tune Playbook Balance",
            [
              "Impact: Low-Medium \u2014 The Rookie was unscoreable; The Agent was never used",
              "Effort: Low \u2014 adjust Rookie condition (ranks 1-6) and Agent cost (3-4 Shinies)",
              "Playbooks should feel achievable as secondary objectives, not impossible side quests"
            ],
            COLORS.lightBg,
            COLORS.primary
          ),
          spacer(),

          colorBox(
            "Priority 5: Improve Late-Game Agency",
            [
              "Impact: Medium \u2014 two of three players had nothing productive to do for 10+ turns",
              "Effort: Medium \u2014 requires structural additions like card trading, alternate scoring, or event deck rebalancing",
              "Consider ways to convert a mismatched hand into progress: \"trade 3 cards for 1 from deck,\" events that reward hand diversity rather than faction specialization, or a way to spend Shinies beyond the 9-Shiny cap"
            ],
            COLORS.insightBg,
            COLORS.success
          ),

          new Paragraph({ children: [new PageBreak()] }),

          // APPENDIX
          heading("Appendix: Methodology"),
          para("This analysis was conducted by cross-referencing three primary sources:"),
          spacer(),
          numberedItem("The official Contests of Chaos rules document (480 lines, covering all mechanics, setup, actions, endgame, and 2-player variant)"),
          numberedItem("The turn-by-turn game transcript (45 pages, showing every action, game state change, and card interaction across 45 turns)"),
          numberedItem("The AI designer analysis report (102 pages, containing player decision reasoning, strategic evaluations, and post-game feedback from all three AI players)"),
          spacer(),
          para("Every event completion was verified against the official event requirements CSV (37 events). Every playbook scoring was checked against the playbook requirements CSV (25 playbooks). Lineup pricing, Shiny transfers, hand limits, Jumbotron sliding, and Standing Ovation triggers were spot-checked across multiple turns throughout the game."),
          spacer(),
          para("Note: This was a single playtest with AI agents. Patterns observed here (e.g., Jumbotron stagnation, Group Photo dominance) should be validated across additional playtests with different seeds and player counts before making final design decisions. AI players may also exhibit different strategic biases than human players."),
        ]
      }
    ]
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync("/sessions/nifty-practical-lamport/mnt/game-ai-test/ContestsOfChaos_Playtest_Analysis.docx", buffer);
  console.log("Report generated successfully!");
}

main().catch(console.error);
