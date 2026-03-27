# My $200/Month Solo Founder Tech Stack (And the Weird One That Makes It Work)

*The tools, the face computer, and the part where I'm the integration layer*

*Week 2 — Feature*

---

I'm launching a tabletop card game on Kickstarter in September. Solo founder. No team. No publisher. Just me and a collection of software subscriptions that I keep insisting are "investments." Last week I wrote about using AI as my project manager. This week I want to zoom out and show you the whole bench — every tool I'm actually using, what each one costs, and the one that makes people tilt their heads sideways when I mention it in conversation.

But first: the honest framing. I'm not a tools-for-tools-sake person. I've tried the thing where you spend three days setting up Notion dashboards and then never open Notion again. Every tool on this list survived the same test — *did I reach for it this week without being reminded it existed?* If the answer was no for two weeks straight, it got cut.

Here's what survived.

## Claude Cowork — The PM I Can't Fire

This is the centerpiece. Claude on the Max plan, running in Cowork mode. A hundred bucks a month. That sounds like a lot until you price out what a part-time project manager or virtual assistant would cost for the same hours. (Spoiler: it's not close.)

What does it actually do? It holds the master plan. It models the budget. It manages task lists, helps me think through decisions, and occasionally talks me off a ledge when I'm spiraling about timelines. It also drafts content - yes, including this piece - but I then go through and try to be less "polite robot" and more "genuine Drew." Cowork is the coworker who's read every book on project management but has never once remembered to water a plant. Most recently, Anthropic, the company behind Claude, enhanced Cowork with a new contract-review skill that I used to examine, review, and enhance the term sheet that the artist and I are working on. 

What Cowork can't do: anything that involves the outside world. It can't send emails. It can't check if my manufacturer responded. It can't nudge me at 3pm on a Tuesday to follow up with someone. It's brilliant inside its own walls and completely helpless outside them.

That's where the next tool comes in.

## Open Claw ("Clyde") — The One Who Leaves the Building

Open Claw — I call it Clyde, because naming your AI tools is apparently just something folks do now — handles the things Claude can't. Automated research. Web lookups. Task orchestration. It reads a shared task file and can push things out to other systems.

In theory, Clyde is the bridge between "Claude decided this needs to happen" and "the thing actually happens in the real world." In practice... we'll get to that.

## Todoist — Where Tasks Go to Actually Get Done

Todoist is the daily driver. Labels, priorities, reminders that buzz my phone when I'm pretending I don't need to work tonight. The reason it's on this list instead of some fancier project management tool is simple: I open it. Every morning. Without thinking about it. That's the whole evaluation criteria.

It's also where tasks are *supposed* to land after Claude and Clyde process them. Supposed to. (That's what is known as foreshadowing. More later)

## Typora — Markdown, But Make It Pretty

Everything in this project lives in markdown files. The master plan. The budget model. The content series outline. This article draft. Typora is just a clean markdown editor that makes `.md` files look nice while you're writing them. Nothing fancy. That's the point. You can also export markdown in a variety of templates. This will be great for rulebook creation — assuming I ever stop redesigning the game long enough to write one. Good $14 one-time investment.

## Wispr Flow — Talk Instead of Type

Here's one that changed my workflow more than I expected. Wispr Flow is voice-to-text software. You hold a key, talk, and it transcribes. I paired it with a decent USB mic/speaker combo and started dictating instead of typing when I'm interacting with AI tools.

It turns out that talking to your AI project manager is genuinely faster than typing to it. But the real shift isn't speed. It's *how* you think. When I type prompts, they come out structured and careful. When I talk, they come out messy and honest. And messy-honest prompts? They actually produce better results. You give the AI more to work with. More context, more nuance, more of the actual problem instead of the sanitized version.

I now talk through most of my planning sessions out loud in my office like a person who should maybe close the door.

## Apple Vision Pro — The Weird One

Okay. Here it is. The one in the headline.

I use an Apple Vision Pro as my monitor. Before you close this tab — hear me out.

I picked one up used. The price, after the initial wave of early adopters moved on to the next thing, landed at roughly what you'd pay for a high-end ultrawide monitor. So the comparison isn't "I bought a $3,500 face computer for fun." It's "I bought a spatial computing display for the same price as a really nice LG/Samsung ultra wide screen"

And here's what it actually does for productivity: multiple windows, arranged in space, at whatever size I want. I can have Claude's workspace open in front of me, my markdown editor to the left, a browser to the right, and my task list floating below — all without a physical monitor, monitor arm, or desk space. It's a virtual ultrawide. And it works.

Is it weird? Absolutely. Is it a gimmick? That's what I thought for the first week. But I kept reaching for it. Every morning. Without thinking about it. Same test as everything else on this list.

The gotcha: you look ridiculous wearing it. There is no dignified way to sit in a home office with this thing on. I use a halo mounting headset that hangs it in front of my face, which is significantly more comfortable than ski goggles but no more dignified. My wife has photographic evidence.

## The Total Cost

Let me add it up. Claude Max is $100/month. Wispr Flow is free tier for my usage. Typora was a one-time purchase. Todoist free tier. Open Claw is open source. The Vision Pro was a one-time used purchase that I'm amortizing in my head as a monitor and in my marriage as "a business expense, I promise."

Monthly recurring cost: roughly $200, depending on how you count it. For that, I get a project manager, a research assistant, a writing partner, a voice interface, and a monitor setup that would otherwise require hardware I don't have room for.

## The Drew API (Or: When the Integration Layer Is Just... You)

Now for the part where I admit the system doesn't fully work.

The dream was beautiful. Claude generates tasks and writes them to a shared markdown file called `TASKS.md`. Clyde watches that file, picks up new tasks, and automatically pushes them to Todoist with the right labels, priorities, and due dates. A fully automated task pipeline. AI brain → AI orchestrator → human task list. Seamless.

It didn't work.

Not in a dramatic, everything-broke way. In a slow, frustrating, *almost*-working way. Clyde would pick up tasks but miss context. Priorities would get garbled. Due dates would land wrong or not at all. Every fix introduced a new edge case. I spent a weekend debugging the automation and realized I'd spent more time fixing the pipeline than I would have spent just... copying tasks over myself.

So that's what I do now. Claude writes to `TASKS.md`. I read it. I copy the tasks to Todoist manually. Sometimes I adjust the priority. Sometimes I rewrite the task because Claude was being too vague or too specific. Then I move on with my day.

I am the integration layer. The human middleware between two AI systems and a to-do app.

It's not elegant. It's not the future anyone's selling you on LinkedIn. But it works *every single time*, and it takes me about five minutes a day. The unglamorous reality of AI toolchains in 2026: sometimes the most reliable connector is just a person with a clipboard.

I still call it The Drew API, because at that point you might as well name the joke.

And The Drew API holds it all together with copy-paste and mild caffeine dependency.

---

**Your turn.** What's the weirdest tool in your workflow — the one you'd be slightly embarrassed to explain at a dinner party but can't imagine working without? I collect these like trading cards. Hit reply and tell me. Bonus points if it involves hardware that makes you look ridiculous.

Next week: the 47 things that need to happen before September, and the moment I realized "planning to plan" ate an entire weekend. Subscribe so you don't miss it.

---

*Drew Grgich is the founder of Design Play Labs, currently using an improbable collection of AI tools to launch a tabletop card game on Kickstarter. He is also the world's most overqualified middleware.*
