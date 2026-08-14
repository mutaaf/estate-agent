#!/usr/bin/env python3
"""Build the Estate Agent website.

Generated from the same files in `docs/` that people read on GitHub, so the
site and the documentation cannot drift apart. That is the project's own
one-source-many-outputs principle applied to itself.

Two audiences, and the second one is unusual enough to be worth stating:

  Humans   get the rendered pages.
  Machines get `/llms.txt`, `/llms-full.txt`, JSON-LD, and every page also
           served as raw Markdown at a stable URL. An AI asked "how should we
           roll out coding agents across our org?" should be able to read this
           site properly rather than scraping HTML.

    python3 site/build.py [--out _site] [--base https://mutaaf.github.io/estate-agent]
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import markdown  # noqa: E402
from levels import LEVELS, NEXT_STEP, QUESTIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DEFAULT_BASE = "https://mutaaf.github.io/estate-agent"
REPO = "https://github.com/mutaaf/estate-agent"

TITLE = "Estate Agent"
TAGLINE = "The standard for AI agents working across your repo estate"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

# Order matters: it drives the navigation, the sitemap, and llms.txt.
PAGES = [
    ("levels", "The five levels",
     "How far you have adopted, from nothing to self-maintaining — in plain language, with what each level costs and what is still wrong at it."),
    ("start-here", "Start here",
     "Install Estate Agent and set one repository up in about fifteen "
     "minutes: detect the stack, write the deed, install the guardrails, "
     "generate the context files."),
    ("plain-english", "In plain English",
     "What Estate Agent does, with no jargon and no prior knowledge assumed."),
    ("estate", "The estate map",
     "How Estate Agent works out which service calls which, across ten "
     "languages that share no package manager."),
    ("tiers", "Tiers",
     "Deciding per repo how much autonomy an AI agent gets."),
    ("self-healing", "Self-healing",
     "Why these notes do not rot, and the four rules that stop self-repair "
     "becoming self-damage."),
    ("data-flow", "What data goes where",
     "Exactly what Estate Agent reads, writes, and sends. Written to be "
     "forwarded to a security reviewer unedited."),
    ("monorepo", "Monorepos",
     "Setting up a repository that contains many packages, plus the "
     "satellite repos around it, without the context files duplicating "
     "each other."),
    ("adoption", "Should your team do this?",
     "The costs, the benefits, and what failure looks like."),
    ("adding-a-stack", "Adding a language",
     "Teaching Estate Agent a new stack. One YAML file, no code."),
    ("interop", "Inside an existing initiative",
     "What Estate Agent covers, what it deliberately leaves to humans, and "
     "how to use it as a component of a documentation or knowledge-graph "
     "project you already have."),
    ("glossary", "Glossary", "Every term defined, including the ones the "
     "industry uses carelessly."),
]

WORKFLOWS = [
    ("workflows/cross-repo-change", "Worked example: a cross-repo change",
     "One realistic API change followed end to end across five consumers in "
     "five languages."),
]

# Question-shaped, because these are the phrasings people and answer engines
# actually use.
FAQ = [
    ("How do you let AI coding agents work safely across many repositories?",
     "Give each repo a single context file describing how to work there, map "
     "which services call which so an agent can see beyond its own folder, and "
     "block irreversible actions at the point of execution rather than by "
     "policy. Estate Agent does all three, runs locally, and needs no "
     "dependencies."),
    ("How do you stop an AI agent leaking secrets?",
     "A pre-execution hook that inspects every tool call before it runs and "
     "blocks anything touching credentials, paired with a permission profile "
     "that denies force-pushes, deploys and secret-manager reads. Estate "
     "Agent's guard is measured at 32 of 32 real credentials blocked with 0 "
     "false positives across 44 pieces of ordinary code."),
    ("How do you know what breaks if you change an API?",
     "Build a map of the estate from API contracts, generated client "
     "dependencies, configured service URLs and call sites, then query it. "
     "`estate impact payments-api /v2/charge` lists every affected repo "
     "including mobile and TV clients, and gives the order to ship in."),
    ("Why not use a code-graph tool to map the repos?",
     "Because none of them cover a real estate. The leading option parses "
     "Java, Rust, .NET, Node and Kotlin but not Swift, BrightScript or RPG, "
     "and it does not link separate repositories or read API specs at all. "
     "Estate Agent reads the contracts between languages instead, which works "
     "identically for Rust and for RPG."),
    ("How do you keep AI context files from going stale?",
     "Generate them from one source file, check them in CI, verify the "
     "documented commands still exist, and instruct the agent to correct the "
     "source whenever reality contradicts it — as part of the same pull "
     "request. The documentation then improves as a side effect of normal "
     "work instead of depending on someone remembering."),
    ("Does Estate Agent send our code anywhere?",
     "No. There is no network code in the project. No telemetry, no account, "
     "no licence check. It is standard-library Python with zero dependencies, "
     "and the claim is enforced by a test in the project's own CI rather than "
     "asserted in a README."),
    ("Does it work with Cursor and Copilot, or only Claude Code?",
     "All of them. One file — `.agent/estate.yaml` — generates CLAUDE.md, "
     "AGENTS.md, .cursor/rules, .github/copilot-instructions.md and GEMINI.md, "
     "so a team using different assistants gets the same guidance."),
    ("How do you handle a mainframe or AS400 in an AI workflow?",
     "Describe it rather than parse it. No tool reads RPG reliably, and it is "
     "usually the highest-risk, least-tested system in the building. Estate "
     "Agent treats it as an opaque node with a declared interface — programs, "
     "tables, queues — and defaults to letting agents explain it and write "
     "callers against it, never modify it."),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def layout(
    *, title: str, description: str, body: str, base: str, url_path: str,
    structured: list[dict] | None = None, raw_markdown: str | None = None,
    extra_head: str = "", scripts: str = "",
) -> str:
    canonical = f"{base}/{url_path}".rstrip("/") + ("/" if url_path else "")
    full_title = title if title == TITLE else f"{title} · {TITLE}"
    depth = url_path.strip("/").count("/") + 1 if url_path else 0
    prefix = "../" * depth if depth else ""

    nav = "".join(
        f'<a href="{prefix}{slug}/">{html.escape(label)}</a>'
        for slug, label in [
            ("start-here", "Start"), ("estate", "The map"),
            ("self-healing", "Self-healing"), ("data-flow", "Security"),
            ("spec", "Spec"),
        ]
    )

    jsonld = ""
    if structured:
        jsonld = "\n".join(
            f'<script type="application/ld+json">{json.dumps(item)}</script>'
            for item in structured
        )

    raw_link = ""
    if raw_markdown:
        raw_link = (
            f'<link rel="alternate" type="text/markdown" '
            f'href="{base}/{raw_markdown}">'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{canonical}">
{raw_link}
<meta property="og:type" content="website">
<meta property="og:site_name" content="{TITLE}">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(full_title)}">
<meta name="twitter:description" content="{html.escape(description)}">
<meta name="author" content="Mutaaf Aziz">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='26'>&#127968;</text></svg>">
<link rel="stylesheet" href="{prefix}assets/theme.css">
{extra_head}
{jsonld}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="masthead"><div class="inner">
  <a class="wordmark" href="{prefix or './'}">Estate&nbsp;<span>Agent</span></a>
  <nav>{nav}<a href="{REPO}">GitHub</a></nav>
</div></header>
<main id="main">
{body}
</main>
<footer><div class="wrap">
  <div class="row">
    <span>Estate Agent v{VERSION} · MIT licensed</span>
    <a href="{REPO}">Source</a>
    <a href="{base}/llms.txt">llms.txt</a>
    {'<a href="' + base + '/' + raw_markdown + '">This page as Markdown</a>' if raw_markdown else ''}
  </div>
  <p style="margin-top:1rem">Your repos are the estate. The AI is the agent.</p>
</div></footer>
{scripts}
</body>
</html>
"""


def article(source: str, title: str, slug: str = "") -> str:
    toc_items = markdown.headings(source, levels=(2,))
    toc = ""
    if len(toc_items) > 2:
        links = "".join(
            f'<li><a href="#{anchor}">{html.escape(text)}</a></li>'
            for _level, text, anchor in toc_items
        )
        toc = f'<nav class="toc" aria-label="On this page"><ul>{links}</ul></nav>'
    return (
        '<div class="wrap"><div class="doc">'
        + toc
        + '<div class="prose">' + markdown.render(source, slug) + "</div>"
        + "</div></div>"
    )


def build_index(base: str) -> str:
    faq_html = "".join(
        f"<h3>{html.escape(q)}</h3>{markdown.render(a)}" for q, a in FAQ
    )

    cards = "".join(
        f'<div class="card"><h3>{html.escape(t)}</h3><p>{html.escape(d)}</p></div>'
        for t, d in [
            ("One file, five assistants",
             "Maintain .agent/estate.yaml. Claude Code, Cursor, Copilot, "
             "Gemini and AGENTS.md are generated from it, and CI fails on drift."),
            ("A map with evidence",
             "Every connection cites the file and line proving it. Anything "
             "ambiguous becomes a question rather than a guess."),
            ("Guardrails that block",
             "Credentials and irreversible commands stopped at execution, not "
             "by policy. 32/32 caught, 0 false positives."),
            ("Notes that repair themselves",
             "Stale commands, deleted repos and vanished evidence are found "
             "and fixed — without ever overwriting something you wrote."),
        ]
    )

    body = f"""
<div class="wrap">
  <section class="hero">
    <p class="eyebrow">An open standard · v{VERSION}</p>
    <h1>Your repos are the estate.<br>The AI is the agent.</h1>
    <p class="lede">Estate Agent tells an AI coding assistant where everything
      is, what it is allowed to touch, and what breaks if it changes something
      — across Java, Rust, .NET, Node, Swift, Kotlin, React, Roku and AS400.</p>
    <p class="lede"><strong>No installation. No dependencies. Nothing leaves
      your machine.</strong></p>
    <div class="cta">
      <a class="button" href="start-here/">Start here</a>
      <a class="button ghost" href="{REPO}">Source on GitHub</a>
      <a class="button ghost" href="data-flow/">For your security team</a>
    </div>
  </section>

  <section class="demo" id="demo" aria-label="Interactive blast radius demo"></section>

  <div class="prose">
    <h2 id="the-problem">The problem</h2>
    <p>AI coding agents are good inside one well-described repo and bad across
      an estate. An agent working in the Java payments API has no idea the Rust
      ledger and three phone apps depend on the endpoint it is about to change.
      It sees one folder. The person supervising it often cannot see further.</p>
    <p>Estate Agent is four small tools against that: one context file per repo
      that every assistant reads, a map of which service calls which, guardrails
      that block irreversible actions, and a repair loop so none of it goes
      stale.</p>
  </div>

  <div class="grid">{cards}</div>

  <div class="prose">
    <h2 id="levels">The five levels</h2>
    <p>Adoption is a ladder, not a switch. Each level is worth having on its
      own, and you can stop at any of them. Click one to see what it gets you,
      what it costs, and — the part most descriptions leave out — what is still
      wrong once you are there.</p>
    <p class="quiz-intro">Not sure where you are? Answer the four questions
      underneath and you will be told, along with the single next thing to
      do.</p>
  </div>

  <section id="levels-explorer" aria-label="The five adoption levels"></section>

  <div class="prose">
    <p><em>Levels are not tiers.</em> A <strong>level</strong> is how far you
      have adopted. A <strong>tier</strong> is how much a single repo lets an
      agent do — read-only, pull requests, or merge on green.
      <a href="tiers/">Tiers are explained here →</a></p>

    <h2 id="how-it-works">How the map works</h2>
    <p>No code-graph tool covers a real estate. The best available option parses
      Java, Rust, .NET, Node and Kotlin — but not Swift, not BrightScript, not
      RPG — and it does not link separate repositories or read API specs at all.
      That is half your repos and none of your cross-service connections.</p>
    <blockquote><p>So instead of trying to read ten languages, Estate Agent
      reads the contracts between them.</p></blockquote>
    <p>API specifications, generated client libraries, configured service URLs,
      and a handful of per-language call patterns. This works identically for
      Rust and for RPG, because it never has to understand either one. Every
      connection is ranked by how it was resolved and cites the line proving it.
      <a href="estate/">How the map works →</a></p>

    <h2 id="measured">Measured, not asserted</h2>
    <p>Run <code>python3 tests/run_all.py --report</code> yourself:</p>
    <div class="scroll"><pre><code>Secret guard
  Real credentials blocked   32/32   (recall 100%)
  Ordinary code allowed      44/44   (false positive rate 0%)

Estate map, against a known answer
  Real connections found      8/8    (recall 100%)
  Phantom connections         0      (precision 100%)
  Sent for confirmation       1</code></pre></div>
    <p>Precision matters more than recall here. A missed connection gets added
      by hand and stays added. A phantom one destroys trust in the whole map,
      including the parts that were right.</p>

    <h2 id="get-started">Get started</h2>
    <div class="scroll"><pre><code>git clone {REPO} ~/.estate-agent
export PATH="$HOME/.estate-agent/bin:$PATH"

cd ~/work/payments-api
estate doctor        # what is here and what is missing. Changes nothing.
estate init          # set it up. Folds in your existing CLAUDE.md.
estate scan ~/work   # map the whole estate</code></pre></div>
    <p>Or, using Claude Code, just say: <em>read
      github.com/mutaaf/estate-agent and set this repo up</em>. That works
      because <a href="{REPO}/blob/main/AGENT.md">AGENT.md</a> is written for an
      agent to follow rather than for a human to skim.</p>

    <h2 id="faq">Questions</h2>
    {faq_html}
  </div>
</div>
"""

    structured = [
        {
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": TITLE,
            "description": TAGLINE,
            "applicationCategory": "DeveloperApplication",
            "operatingSystem": "macOS, Linux, Windows",
            "softwareVersion": VERSION,
            "url": base,
            "codeRepository": REPO,
            "license": "https://opensource.org/licenses/MIT",
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {"@type": "Answer", "text": answer},
                }
                for question, answer in FAQ
            ],
        },
    ]

    return layout(
        title=TITLE,
        description=(
            "An open standard for using AI coding agents across many "
            "repositories: one context file per repo for every assistant, a "
            "cross-repo service map with evidence, guardrails that block "
            "credential access, and self-healing docs. Local, zero "
            "dependencies, MIT."
        ),
        body=body, base=base, url_path="",
        structured=structured,
        extra_head=(
            '<script>window.ESTATE_LEVELS='
            + json.dumps({
                'levels': LEVELS, 'questions': QUESTIONS,
                'next': {str(k): v for k, v in NEXT_STEP.items()},
            })
            + ';</script>'
        ),
        scripts=(
            '<script src="assets/hero.js" defer></script>'
            '<script src="assets/levels.js" defer></script>'
        ),
    )


def build_spec(base: str) -> str:
    """A stable, versioned page with permanent anchors, so citations survive."""
    source = f"""# The Estate Agent specification

**Version {VERSION}.** Anchors on this page are permanent. Later versions add
sections; they do not renumber or rename existing ones, so a link or a citation
to any heading here keeps working.

## 1. The deed

Each repository has exactly one source of truth at `.agent/estate.yaml`. All
assistant-specific context files are generated from it and are never edited
directly. A conforming implementation MUST fail a check when a generated file
differs from what the deed would produce.

## 2. Generated context files

From one deed, an implementation generates `CLAUDE.md`, `AGENTS.md`,
`GEMINI.md`, `.github/copilot-instructions.md`, and `.cursor/rules/00-estate.mdc`.
Each carries a stamp recording the hash of the content generated, which allows a
hand edit to be distinguished from a stale file.

## 3. Tiers

A repository declares one of three tiers.

| Tier | Name | The agent may | The agent may not |
|---|---|---|---|
| 1 | Restricted | read, explain, propose | write, open pull requests, mutate state |
| 2 | Reviewed | edit, open pull requests | merge |
| 3 | Autonomous | edit, open pull requests, merge on green CI | bypass CI, edit another repo's deed |

Legacy systems default to tier 1. An implementation MUST NOT raise a tier
automatically.

## 4. The resolution ladder

A connection between two repositories is established by exactly one method, and
the method is recorded on the connection.

| Rank | Method | Basis | Confidence |
|---|---|---|---|
| 1 | `declared` | the source names the service outright | 0.95 |
| 2 | `dependency` | a generated client for the service is a dependency | 0.90 |
| 3 | `env` | a configured variable names the service | 0.75 |
| 4 | `host` | a URL hostname matches the service | 0.70 |
| 5 | `path` | the called path matches exactly one service's endpoint | 0.60 |

## 5. Evidence

Every connection MUST cite a file path and line number. A connection without
evidence MUST NOT appear on the map.

## 6. Ambiguity

Where a signal matches more than one service equally well, an implementation
MUST NOT choose. The signal is recorded for human confirmation, with its
candidates listed.

## 7. External dependencies

A signal that matches no service in the estate is external, not ambiguous. It
MUST be recorded separately from items awaiting confirmation.

## 8. Ship cost and landing order

Repositories are classified by how reversibly they deploy. Client applications
(mobile, TV, installed desktop) cannot be rolled forward, so where the affected
set contains one, an implementation MUST produce an expand-and-contract landing
order: add the new shape, migrate services, ship clients, and only then remove
the old shape.

## 9. Self-healing

An implementation repairs staleness automatically, subject to four constraints:

1. It MUST NOT overwrite a file that has been edited by hand.
2. It MUST NOT relax a safety rule without human action.
3. It MUST NOT modify source code.
4. It MUST migrate deeds written by earlier versions.

## 10. The correction protocol

Generated context files instruct the agent that when reality contradicts them,
the agent corrects the deed — not the generated file — within the same unit of
work, and notes the correction in the pull request.

## 11. Data flow

Levels 1 and 2 of a conforming implementation MUST NOT make network calls of
any kind, including telemetry.
"""
    return layout(
        title=f"Specification v{VERSION}",
        description=(
            f"The Estate Agent specification, version {VERSION}: deeds, tiers, "
            f"the resolution ladder, evidence requirements, landing order, and "
            f"the self-healing constraints. Permanent anchors."
        ),
        body=article(source, "Specification", "spec"), base=base, url_path="spec",
        raw_markdown="spec.md",
        structured=[{
            "@context": "https://schema.org", "@type": "TechArticle",
            "headline": f"The Estate Agent specification v{VERSION}",
            "version": VERSION, "url": f"{base}/spec/",
            "datePublished": date.today().isoformat(),
        }],
    ), source


def build(out: Path, base: str) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    shutil.copytree(SITE / "assets", out / "assets")

    urls: list[str] = [""]

    # -- home ---------------------------------------------------------------
    (out / "index.html").write_text(build_index(base), encoding="utf-8")

    # -- documentation pages ------------------------------------------------
    for slug, title, description in PAGES + WORKFLOWS:
        source_file = ROOT / "docs" / f"{slug}.md"
        if not source_file.is_file():
            print(f"  ! missing {source_file}", file=sys.stderr)
            continue
        source = read(source_file)
        page_dir = out / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        raw_name = f"{slug}.md"

        (page_dir / "index.html").write_text(
            layout(
                title=title, description=description,
                body=article(source, title, slug), base=base, url_path=slug,
                raw_markdown=raw_name,
                structured=[{
                    "@context": "https://schema.org", "@type": "TechArticle",
                    "headline": title, "description": description,
                    "url": f"{base}/{slug}/",
                    "isPartOf": {"@type": "WebSite", "name": TITLE, "url": base},
                }],
            ),
            encoding="utf-8",
        )
        # The same page as raw Markdown, at a stable URL. Agents fetch this
        # far more reliably than they parse rendered HTML.
        raw_path = out / raw_name
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(source, encoding="utf-8")
        urls.append(slug + "/")

    # -- specification -------------------------------------------------------
    spec_html, spec_source = build_spec(base)
    (out / "spec").mkdir(exist_ok=True)
    (out / "spec" / "index.html").write_text(spec_html, encoding="utf-8")
    (out / "spec.md").write_text(spec_source, encoding="utf-8")
    urls.append("spec/")

    # -- machine-readable ----------------------------------------------------
    _write_llms(out, base, spec_source)
    _write_sitemap(out, base, urls)
    (out / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n"
        "# Estate Agent is written to be read by machines as well as people.\n"
        f"Sitemap: {base}/sitemap.xml\n",
        encoding="utf-8",
    )
    (out / ".nojekyll").write_text("", encoding="utf-8")

    print(f"built {len(urls)} pages -> {out}")


def _write_llms(out: Path, base: str, spec_source: str) -> None:
    """`llms.txt` is an index for AI readers; `llms-full.txt` is everything."""
    lines = [
        f"# {TITLE}",
        "",
        f"> {TAGLINE}. An open standard for using AI coding agents across many "
        f"repositories: one context file per repo that every assistant reads, a "
        f"cross-repo service map built from API contracts rather than parsers, "
        f"guardrails that block credential access at execution, and a repair "
        f"loop that keeps it all true. Runs locally, zero dependencies, MIT "
        f"licensed. Version {VERSION}.",
        "",
        "## Documentation",
        "",
    ]
    for slug, title, description in PAGES + WORKFLOWS:
        lines.append(f"- [{title}]({base}/{slug}.md): {description}")
    lines += [
        f"- [Specification v{VERSION}]({base}/spec.md): the normative "
        f"definition — deeds, tiers, the resolution ladder, evidence "
        f"requirements, landing order, self-healing constraints.",
        "",
        "## Source",
        "",
        f"- [Repository]({REPO}): MIT licensed, standard-library Python.",
        f"- [AGENT.md]({REPO}/blob/main/AGENT.md): installation instructions "
        f"written for an AI agent to follow.",
        "",
        "## Key concepts",
        "",
        "- **Deed**: `.agent/estate.yaml`, the single source of truth per repo.",
        "- **Estate**: all your repositories taken together.",
        "- **Resolution ladder**: declared > dependency > env > host > path.",
        "- **Blast radius**: everything that breaks if you change one thing.",
        "- **Ship cost**: how many release cycles you must support an old API "
        "shape for; zero for a service, roughly two for a mobile or TV app.",
        "- **Tiers**: 1 restricted, 2 reviewed, 3 autonomous.",
        "",
    ]
    (out / "llms.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    full = [f"# {TITLE} — complete documentation", "", f"Version {VERSION}.", ""]
    for slug, title, _description in PAGES + WORKFLOWS:
        source_file = ROOT / "docs" / f"{slug}.md"
        if source_file.is_file():
            full += [f"\n\n---\n\n# {title}\n", read(source_file)]
    full += ["\n\n---\n\n", spec_source]
    (out / "llms-full.txt").write_text("\n".join(full), encoding="utf-8")


def _write_sitemap(out: Path, base: str, urls: list[str]) -> None:
    today = date.today().isoformat()
    entries = "".join(
        f"<url><loc>{base}/{path}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>weekly</changefreq>"
        f"<priority>{'1.0' if not path else '0.8'}</priority></url>"
        for path in urls
    )
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>\n",
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    out = ROOT / "_site"
    base = DEFAULT_BASE
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1]).resolve()
    if "--base" in argv:
        base = argv[argv.index("--base") + 1].rstrip("/")
    build(out, base)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
