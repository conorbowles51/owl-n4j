You are currently inside the repository for an AI-powered investigations platform.

The product is currently branded as **OWL**, because it was originally built for/with OWL Consultancy. We are now splitting this product off into its own standalone company/product and need a complete rebrand.

Your task is to inspect the codebase and produce a polished set of brand strategy and visual identity materials that I can share with colleagues. These materials should help us decide on the new brand name, voice, visual direction, logo direction, website messaging, and overall positioning.

The final output should be visual and easy to review, preferably as one or more **HTML documents** rather than plain Markdown.

## Product context

This is an AI-powered investigations platform for:

* Investigators
* Legal professionals
* Fraud teams
* Compliance teams
* Intelligence/research teams
* Anyone who needs to process large volumes of documents, entities, timelines, relationships, and evidence

The platform helps users upload and analyse investigative material, extract entities and relationships, explore graphs/timelines/maps, ask questions over case data, and speed up complex investigative workflows.

Please inspect the repository to understand the product’s real capabilities, UI structure, existing design system, terminology, colour usage, and current branding. Do not rely only on the description above. Use the codebase as evidence.

## Rebrand goal

We want the brand to communicate:

* Professionalism
* Trust
* Stability
* Seriousness
* Accuracy
* Security
* Investigative clarity
* Practical AI, not hype
* AI as an enhancement to expert workflows, not a replacement for expertise

We specifically do **not** want to feel like:

* A flashy AI startup
* A young, hot-headed company
* A gimmicky “AI magic” product
* Overly futuristic or sci-fi
* Too playful
* Too vague or abstract
* Too corporate and lifeless

The message should be something like:

> “A stable, professional platform that brings AI into investigations in a controlled, useful, and trustworthy way — helping experienced professionals work faster, see connections more clearly, and manage complex evidence.”

We may keep many of the existing colours, including support for light and dark mode, but we are open to thoughtful changes. The new brand does not need to keep the owl concept unless there is a very strong reason to do so.

## What to produce

Create a new folder such as:

`/docs/brand-rebrand/`

Inside that folder, create a polished HTML-based brand presentation that can be opened locally in a browser and shared with colleagues.

At minimum, produce:

1. `index.html`
   A polished visual overview of the proposed rebrand directions.

2. `brand-strategy.html`
   A detailed brand strategy document.

3. `naming-and-identity.html`
   A document showing name options, rationale, taglines, and logo directions.

4. `visual-direction.html`
   A document showing colour, typography, logo, UI, and website direction.

5. An `/assets/` folder containing generated logo concepts and any supporting visual assets.

Use CSS either inline or in a dedicated stylesheet such as:

`/docs/brand-rebrand/styles.css`

The HTML should look polished, professional, and presentation-ready. It should not look like a raw developer document.

## Brand Strategy Document

Include:

* Summary of the product based on the codebase
* Target audience
* Core positioning
* Brand personality
* Brand values
* What the brand should feel like
* What the brand should avoid
* Key messaging pillars
* Recommended tone of voice
* Example phrases/taglines
* Website hero messaging options
* How to explain the product in:

  * One sentence
  * One paragraph
  * A longer website-style description

## Naming & Identity Options

Come up with at least **10 possible product/company names**.

For each name, include:

* Meaning/rationale
* Why it fits the product
* Possible risks or weaknesses
* Suggested tagline
* Logo direction
* Voice/feel
* Suggested colour treatment
* Suggested website hero line

Then include a ranked shortlist of the strongest **3–5 names**.

Avoid names that sound:

* Too generic
* Childish
* Crypto-like
* Overly sci-fi
* Too much like a flashy AI startup
* Too close to existing major legal, investigation, or AI brands
* Too abstract to understand
* Too tied to the old OWL Consultancy brand unless there is a strong strategic reason

## Logo generation requirement

For the strongest shortlisted names, use the available image generation model/tool to generate logo concepts.

Generate logo options for at least **3 different names**.

For each of the top 3 names, generate at least **2 distinct logo concepts**, giving a minimum of **6 generated logo images** total.

Each logo concept should be suitable for a serious AI-powered investigations/legal/compliance platform.

The logos should feel:

* Professional
* Trustworthy
* Stable
* Modern
* Clear
* Premium but not flashy
* Suitable for legal/investigative users
* Practical rather than gimmicky

The logos should avoid:

* Cartoon owls
* Generic magnifying glasses unless used in a very refined way
* Overly futuristic AI brain imagery
* Neon cyberpunk styling
* Cheap SaaS startup gradients
* Scales of justice clichés unless handled subtly
* Anything that feels like crypto, gaming, or sci-fi

For each generated logo, include:

* The name it belongs to
* A short explanation of the concept
* Where the image file is saved
* Suggested usage notes
* Strengths
* Weaknesses
* Whether it would work in light mode and dark mode
* Whether it would work as a favicon/app icon

Save the generated logo assets in:

`/docs/brand-rebrand/assets/logos/`

Use clear filenames, for example:

* `name-01-logo-concept-a.png`
* `name-01-logo-concept-b.png`
* `name-02-logo-concept-a.png`
* `name-02-logo-concept-b.png`

Also include the exact image-generation prompts used for each logo concept in the HTML document, so we can iterate later.

## Visual & Website Direction

Include:

* Recommended visual direction
* Colour palette recommendations based on the existing app
* Whether existing colours should be kept, refined, or replaced
* Light mode and dark mode guidance
* Typography direction
* Logo style ideas
* Iconography style
* UI/website feel
* Suggested homepage structure
* Suggested website sections and copy examples
* Examples of phrases to use
* Examples of phrases to avoid

Where possible, create visual swatches, example cards, mock hero sections, and small brand examples directly in HTML/CSS.

## Website messaging examples

Include concrete copy examples such as:

* Hero headlines
* Hero subheadings
* CTA text
* Feature section copy
* Navigation labels
* Short sales pitch
* Product description
* “About” section copy
* Tone of voice examples
* Before/after examples of weak vs stronger wording

The messaging should avoid sounding like generic AI hype.

Avoid phrases like:

* “Unlock the power of AI”
* “Revolutionise your workflow”
* “AI-powered magic”
* “Supercharge everything”
* “The future of investigations”
* “10x your team overnight”

Prefer grounded, professional language such as:

* “Bring structure to complex investigations.”
* “Find the relationships hidden across your case material.”
* “Analyse documents, entities, timelines, and evidence in one controlled workspace.”
* “AI assistance for investigative teams that need clarity, traceability, and speed.”
* “Designed to support expert judgment, not replace it.”

## Repository inspection guidance

When inspecting the repository, look for:

* Product features
* Existing pages/components
* Current wording and terminology
* Current colours/design tokens
* Existing logo or brand assets
* Any documentation, README files, config files, or screenshots
* Any UI copy that reveals the product’s intended use
* Any references to OWL, Owl Consultancy, investigations, cases, entities, graphs, timelines, maps, evidence, documents, users, roles, reports, or AI chat

Make the documents practical and usable. They should not read like generic branding theory. They should feel tailored to this specific product.

## HTML presentation guidance

The HTML output should be polished enough to show directly to colleagues.

Aim for a visual style that feels:

* Serious
* Premium
* Calm
* Investigative
* Trustworthy
* Modern
* Legible
* Boardroom-ready

Include:

* A clear landing page/index
* Navigation between sections
* Visual cards for each naming option
* Ranked recommendation cards
* Logo galleries
* Colour palette swatches
* Example website hero mockups
* Tone-of-voice comparison tables
* Short, readable sections rather than walls of text

The HTML should work locally without a build step. Do not require a running dev server unless absolutely necessary.

## Tone of your written output

The documents should be:

* Professional
* Clear
* Strategic
* Realistic
* Persuasive
* Not too buzzword-heavy
* Not overly academic
* Written so I can send them directly to colleagues for discussion

## Final response requirements

After creating the files, provide a short summary listing:

* The files created
* Where the HTML presentation can be opened
* The generated logo asset paths
* The strongest recommended brand direction
* The top 3 name candidates
* The strongest logo concept and why
* Any important assumptions
* Any areas where a human decision is still needed
