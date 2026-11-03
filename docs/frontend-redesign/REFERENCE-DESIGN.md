# Warm technical minimalism

A reusable design guide based on this portfolio. The style combines editorial hierarchy, warm neutral colors, generous spacing, and precise technical illustrations.

Use this guide for portfolios, research tools, documentation, developer products, and focused dashboards. Preserve the visual language while adapting the layout to the work people need to do.

## Design principles

- **Lead with the content.** Titles and useful information carry the page. Illustrations support the reading order.
- **Separate through spacing and alignment.** Use thin rules to mark meaningful boundaries. Reserve containers for content that needs to be grouped or manipulated together.
- **Keep one clear hierarchy.** Give each section a primary heading, supporting metadata, and a readable body.
- **Use color sparingly.** Warm neutrals establish the surface. Accent color identifies interaction or a meaningful detail.
- **Keep technical detail precise.** Diagrams explain real relationships, processes, or structures. Labels remain readable at their displayed size.
- **Keep related text together.** A title, its metadata, and its description form a coherent block. A tall illustration must not insert gaps inside that block.

## Color

These are the current site's semantic tokens. Consume the tokens in components rather than repeating hex values.

| Token | Light | Dark | Purpose |
| --- | --- | --- | --- |
| `--bg` | `#f8f3e9` | `#1b1814` | Page background and open diagram surfaces |
| `--text` | `#1e1a15` | `#efebe2` | Headings, body copy, primary controls |
| `--muted` | `#5e574f` | `#a9a49b` | Metadata, secondary links, supporting diagrams |
| `--border` | `#dcd7cd` | `#393530` | Quiet dividers and decorative outlines |
| `--accent` | `#9d4616` | `#ec9c63` | Focus rings, link hover, selected illustration details |

```css
:root {
	color-scheme: light;
	--bg: #f8f3e9;
	--text: #1e1a15;
	--muted: #5e574f;
	--border: #dcd7cd;
	--accent: #9d4616;
	--f-body: 'Schibsted Grotesk', system-ui, -apple-system, sans-serif;
}

[data-theme="dark"] {
	color-scheme: dark;
	--bg: #1b1814;
	--text: #efebe2;
	--muted: #a9a49b;
	--border: #393530;
	--accent: #ec9c63;
}
```

The portfolio starts in dark mode unless a saved preference exists. Other projects can follow the system preference instead. Apply the chosen theme before first paint to avoid a flash of the wrong background.

Keep text at full opacity when using `--muted`. Lower opacity can make small labels fail contrast requirements. The border token is decorative; a control that depends on its outline for identification needs a stronger, verified outline.

For products with success, warning, and error states, add semantic tokens for those meanings. Pair color with text or an icon. The portfolio palette does not define a complete status system.

## Typography

Use **Schibsted Grotesk** for both headings and body text. Hierarchy comes from size, weight, spacing, and placement rather than several font families. The system font stack is the fallback.

Current reference sizes are listed below. Rem values assume the browser's usual 16px root size; preserve user font-size preferences.

| Role | Size | Weight | Line height |
| --- | --- | --- | --- |
| Hero title | `clamp(2.75rem, 6vw, 4rem)` | 600 | 1.05 |
| Main section heading | `2rem` | 600 | Inherited 1.6 |
| Experience role | `1.5rem`, `1.375rem` on small screens | 650, inherited from the base role style | 1.35 |
| Project heading within an entry | `1.125rem` | 600 | 1.45 |
| Experience body | `1.0625rem`, `1rem` on small screens | 400 | 1.65 |
| Organization | `0.9375rem` | 400 | Inherited 1.6 |
| Dates | `0.9rem` | 400 | Inherited 1.6 |
| Tooling and supporting labels | `0.875rem` | 400 | Inherited from the entry body |

For reuse, 600 is a suitable heading weight when the font files do not include intermediate weights. Use slightly negative letter spacing for large headings, around `-0.02em` to `-0.03em`. Leave body tracking normal.

Keep primary reading columns around **60–72ch**. The portfolio caps standard bullets at 68ch and Experience bullets at 72ch. Allow headings and dates to wrap or stack before reducing the body size.

Write sentence-case interface labels and concrete headings. Keep metadata visually secondary without making it faint or difficult to read.

## Spacing and alignment

Use a small, repeatable spacing vocabulary. Useful starting values are 4, 8, 12, 16, 24, 32, 48, 64, and 72px. These are reuse recommendations, not an existing set of CSS spacing tokens.

The current page container is:

```css
.container {
	max-width: 1440px;
	margin-inline: auto;
	padding-inline: clamp(1.5rem, 4vw, 4rem);
}
```

Align navigation, hero content, section headings, and footer to the same outer container. Constrain long text inside that container. Giving one section its own narrower centered container introduces an unintended second alignment.

Current large sections use 4.5rem vertical padding, reduced to 3rem on small screens. Within a text block, metadata gaps are smaller than the gaps between entries. Treat line length and whitespace together: large gaps do not compensate for an overly wide paragraph.

## Layout patterns

### Editorial entry

Use this pattern for experience, case studies, research summaries, or records with supporting illustrations.

```text
Wide view
┌────────────────────────────────────────────────────────────┐
│ Role or title                                  Date        │
│ Organization or other supporting context                    │
│                                                            │
│ Project heading                    Supporting diagram      │
│ Accomplishments or description      with readable labels    │
│ More evidence                                              │
│ Tooling or other metadata                                  │
└────────────────────────────────────────────────────────────┘

Narrow view
┌──────────────────────────────┐
│ Role or title                │
│ Organization                 │
│ Date                         │
│                              │
│ Project heading              │
│ Accomplishments              │
│ Tooling                      │
│                              │
│ Supporting diagram           │
└──────────────────────────────┘
```

The outline above describes layout boundaries, not a visible card border. Use a thin top rule between entries.

Keep the header across the full entry width. Put the narrative and diagram in a separate grid below it. Align the diagram with the start of that evidence row. Keep the date in the header's DOM order, immediately after the role and organization.

Current Experience dimensions are:

| Viewport | Evidence columns | Gap | Header behavior |
| --- | --- | --- | --- |
| Above 1100px | Flexible text + 330px diagram | 4rem | Title and date beside each other |
| 901–1100px | Flexible text + 280px diagram | 2rem | Title and date beside each other |
| 651–900px | One column; diagram below text | 1.75rem | Title and date beside each other when they fit |
| 650px and below | One column; diagram below text | 1.75rem | Role, organization, then date stacked |

Stacked diagrams are centered and capped at 360px, while remaining fluid within narrower containers. The header-to-evidence gap is 1.875rem, reduced to 1.5rem on small screens.

These are page-specific breakpoints. In another project, switch layouts when the available component width becomes cramped. Test long titles, long organization names, and dates near the breakpoint.

### Compact section rail

Use a narrow section label beside a larger content column for short, repeated content such as skills or grouped settings. The portfolio uses an 11rem label column and a 2rem gap, then stacks at 860px.

Keep the outer alignment consistent with the editorial entry pattern. Use a label rail only when the label helps visitors scan several related groups.

### Project grid

Use two equal columns for independent projects with similar amounts of content. Preserve a clear heading, description, tooling line, and illustration within each project. Stack the projects when either column becomes difficult to read.

Avoid forcing unrelated content into equal-height cards. Content can determine the height.

## Diagrams and illustration

Use monochrome SVG illustrations with thin lines, simple geometric forms, and restrained shading. Prefer `currentColor` so the illustration can follow the theme. Use the page background for open fills and cutouts.

The portfolio's technical diagrams use roughly 1–1.25px strokes, with selected emphasis at 2px. `vector-effect: non-scaling-stroke` preserves stroke thickness as the SVG scales.

Experience diagrams are unframed and use `--muted`. Project diagrams can use a quiet frame when the frame helps establish a separate figure. Reserve opacity reductions for decorative geometry; supporting text remains fully opaque.

SVG font sizes are viewBox units, not guaranteed screen pixels. Inspect the diagram at its rendered width. If labels become too small, enlarge or simplify the diagram, stack it below the text, or provide an accessible enlarged view.

Give meaningful diagrams an accessible description, such as `role="img"` with `aria-label`. Hide purely decorative art from assistive technology. Do not put essential information only in an illustration.

The hero's isometric illustration establishes character. Other projects can use an original illustration relevant to their subject; the specific puzzle terrain is not a required motif.

## Controls and product states

The portfolio uses 6px button corners, a 1px outline, and a minimum 2.75rem control height. The primary action uses `--text` as its background and `--bg` as its foreground. Secondary actions retain the page background.

For other products, extend these rules by purpose:

| Element or state | Treatment |
| --- | --- |
| Primary action | One clear action per local task; filled foreground color |
| Secondary action | Outlined or plain text treatment with a clear label |
| Inline link | Underlined in body copy; preserve a visible hover and focus state |
| Keyboard focus | 2px accent outline with 3px offset; keep it visible |
| Selected item | Persistent indicator plus a semantic state such as `aria-current` or `aria-selected` |
| Field | Visible label, clear input boundary, supporting text when needed |
| Invalid field | Specific error text associated with the field; do not rely on color alone |
| Loading | Preserve layout space and communicate what is loading |
| Empty result | State what is empty and offer the relevant next action |
| Disabled action | Explain the reason when it is not apparent from context |

The field and state rows are guidance for new projects, not components already implemented in this portfolio. Start with native controls and add only the variants the product needs.

## Motion

Use motion to communicate a change or explain a process. The portfolio's dashed flow lines illustrate movement through a system. Most of the page remains still.

Respect `prefers-reduced-motion`. Stop decorative animation and remove smooth scrolling when reduced motion is requested. Avoid continuous entrance effects, parallax, and animation that delays access to information.

## Applying the style elsewhere

Keep the neutral palette, font hierarchy, shared alignment, thin rules, bounded reading measure, and restrained illustrations. Choose the page structure for the new project's task.

| Project | Suitable adaptation |
| --- | --- |
| Portfolio or research site | Editorial entries with visible supporting diagrams |
| Documentation | Reading column with a navigation rail; diagrams near the explanation |
| Dashboard | Calm page header, aligned tables and charts, compact filters, explicit status labels |
| Developer tool | Clear task heading, labeled controls, readable output, diagrams only when they explain behavior |
| Marketing page | Strong introduction, evidence-led sections, one clear primary action |

For dense applications, reduce section spacing and increase useful information density before shrinking the text. Use containers for functional groups such as a filter panel or independent report. Keep complex workflows visible when hiding them would increase effort.

Avoid visual changes that weaken this style: decorative gradients, large soft shadows, oversized rounded containers, accent-colored paragraphs, tiny metadata, arbitrary alternating alignments, or illustrations that overpower the content.

### Brief for a new project

Copy this brief and replace the bracketed fields:

> Design [project] in warm technical minimalism for [audience and primary task]. Use Schibsted Grotesk, warm ivory and charcoal themes, restrained accent color, thin dividers, and generous but purposeful spacing. Establish hierarchy through typography and shared alignment. Keep reading columns around 60–72ch. Use precise monochrome diagrams where they explain the subject. Give related text a continuous reading flow, and keep dates or other metadata in logical reading order. Adapt the structure to [content and workflow] rather than reproducing the portfolio layout. Make controls accessible, support reduced motion, and verify realistic content in both themes on desktop and mobile.

## Acceptance checks

- Page sections share the intended outer alignment.
- Headings, metadata, and body copy have a clear reading order.
- Long titles and realistic content do not create collisions or arbitrary internal gaps.
- Body text has a comfortable measure and survives text resizing and browser zoom.
- Normal text reaches at least 4.5:1 contrast; large text reaches at least 3:1.
- Essential control boundaries, icons, and state indicators reach at least 3:1 against adjacent colors.
- Diagram labels remain legible at the actual display size in both themes.
- Keyboard focus, accessible names, and interaction states work without a mouse.
- At narrow widths, the page reflows without horizontal overflow, except intentional scrollable data regions.
- Loading, empty, error, and selected states preserve the hierarchy when the product needs those states.
- Reduced motion removes decorative animation.
- Rendered desktop and mobile views are inspected before completion.

For this portfolio, representative viewport checks include 320, 390, 650, 900, 1100, 1440, and 1920px, plus widths immediately around layout breakpoints. Adapt the set for the target platform.

## Implementation references

The current portfolio implementation supplies concrete examples:

- [Global styles](app/globals.css) define theme tokens, typography, layout, controls, and responsive rules.
- [Page and EntryBlock](app/page.tsx) show the editorial entry structure and shared content model.
- [Root layout](app/layout.tsx) loads the font and restores the theme before first paint.
- [Technical diagrams](app/components/Diagrams.tsx) show the SVG illustration language.
- [Hero illustration](app/components/HeroArt.tsx) and its [generator](app/components/heroArt.ts) show the decorative isometric treatment.
- [Social preview image](app/opengraph-image.tsx) adapts the palette and typography to a small shared-link image with larger text and stronger contrast.

The sources define the current site's behavior. The adaptation guidance in this document provides a starting point for other products.
