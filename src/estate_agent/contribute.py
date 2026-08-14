"""`estate contribute` - extend Estate Agent from wherever you are.

The most valuable contribution is a stack profile for a language Estate Agent
does not cover. The people who can write one are, by definition, looking at a
codebase in that language - and that codebase is usually at work, behind a
policy that makes contributing awkward and a confidentiality obligation that
makes it risky.

Two commands, both designed to be run on a machine you do not control:

    estate contribute stack <repo>     scaffold a profile from a real repo
    estate contribute check <profile>  validate it and try it against a repo

The scaffold is redacted the same way `estate report` is: no repo names, no
paths beyond a basename, and anything in a local `.publish-denylist` removed.
What survives is the shape - which marker files exist, which extensions
dominate, and a sample of the lines that look like outbound calls, which is
the raw material for writing the patterns.

Nothing here uploads anything. It writes a file; sending it is your decision.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from . import ui, yamlite
from .stacks import IGNORED_DIRS, all_stacks

# Build and marker files worth noticing, across ecosystems we do and do not
# already cover. A file here is a candidate `detect.files` entry.
MARKER_FILES = [
    "Makefile", "Justfile", "justfile", "Rakefile", "Gemfile", "Podfile",
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts",
    "settings.gradle", "Cargo.toml", "go.mod", "go.sum", "pyproject.toml",
    "setup.py", "requirements.txt", "Pipfile", "composer.json", "mix.exs",
    "rebar.config", "project.clj", "deps.edn", "build.sbt", "stack.yaml",
    "cabal.project", "pubspec.yaml", "Package.swift", "manifest",
    "CMakeLists.txt", "meson.build", "BUILD", "BUILD.bazel", "WORKSPACE",
    "Dockerfile", "docker-compose.yml", "serverless.yml", "nginx.conf",
    "angular.json", "nx.json", "turbo.json", "vite.config.ts",
    "next.config.js", "svelte.config.js", "nuxt.config.ts", "AndroidManifest.xml",
    "*.csproj", "*.sln", "*.fsproj", "*.vbproj", "*.xcodeproj", "*.gemspec",
    "*.cabal", "*.nimble", "*.opam",
]

# Generic shapes of an outbound call, used only to show the contributor what
# their code looks like. Deliberately loose - these are examples to write
# patterns from, not patterns themselves.
CALL_SHAPES = [
    (r"https?://[^\s\"'`<>)]{6,}", "a URL"),
    (r"\b\w*[Hh]ttp\w*\s*\.\s*\w+\s*\(", "an HTTP client call"),
    (r"\b(?:get|post|put|delete|patch)\s*\(\s*[\"'`/]", "a verb call"),
    (r"@\s*(?:Get|Post|Put|Delete|Patch|Request)\w*Mapping", "a route annotation"),
    (r"@(?:GET|POST|PUT|DELETE|PATCH)\s*\(", "a route annotation"),
    (r"\[Http(?:Get|Post|Put|Delete|Patch)", "a route attribute"),
    (r"\b(?:route|routes|router)\s*[.(\[]", "a router registration"),
    (r"\bfetch\s*\(", "a fetch call"),
    (r"\bproxy_pass\b", "a proxy directive"),
    (r"\b(?:consume|subscribe|publish|produce)\w*\s*\(", "a queue operation"),
]

SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".pdf", ".zip",
    ".gz", ".tar", ".jar", ".war", ".class", ".so", ".dylib", ".dll", ".exe",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".lock", ".min.js",
}

# Never sample from prose or data. Documentation names sibling projects,
# teams and people in ordinary sentences that no pattern-based redactor can
# reliably clean - and it is not where call patterns live anyway, so excluding
# it costs nothing and removes the largest leak surface.
NON_CODE_SUFFIXES = {
    ".md", ".markdown", ".rst", ".txt", ".adoc", ".org", ".csv", ".tsv",
    ".jsonl", ".ndjson", ".log", ".html", ".htm", ".xml", ".svg", ".po",
    ".ipynb", ".sql",
}

MAX_FILES = 3000
MAX_SAMPLES = 4


def _denylist() -> list[str]:
    """Terms the contributor has marked private. Never leaves the machine."""
    terms: list[str] = []
    for candidate in (Path.cwd() / ".publish-denylist", Path.home() / ".publish-denylist"):
        if not candidate.is_file():
            continue
        try:
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.split("#")[0].strip()
                if len(line) >= 3:
                    terms.append(line)
        except OSError:
            continue
    return terms


def redact(text: str, repo_name: str, terms: list[str]) -> str:
    """Strip the things that identify an employer from a sample line.

    A contributor writing a regex needs the *shape* of a call, never its
    destination. So the whole URL goes, not just the host: the path is where
    sibling service names live, and on a work machine those are exactly the
    names that must not leave.
    """
    # One line only. Several of the sample patterns contain `\\s*`, which
    # happily matches a newline, so an unbounded match can drag two or three
    # lines of surrounding prose along with it.
    text = text.strip().split("\n")[0].strip()

    if repo_name:
        text = re.sub(rf"(?i)\b{re.escape(repo_name)}\b", "<repo>", text)
    for term in terms:
        text = re.sub(rf"(?i)\b{re.escape(term)}\b", "<redacted>", text)

    # The entire URL, path included.
    text = re.sub(r"https?://[^\s\"'`<>)\]]+", "https://<host>/<path>", text)
    text = re.sub(
        r"\b[\w-]+\.(?:corp|internal|intranet|local|lan|prod|priv)"
        r"(?:\.[\w-]+)*\b", "<host>", text,
    )
    text = re.sub(r"/Users/[\w.-]+", "/Users/<user>", text)
    text = re.sub(r"/home/[\w.-]+", "/home/<user>", text)
    return text[:160]


def _walk(root: Path) -> list[Path]:
    files: list[Path] = []
    stack = [root]
    while stack and len(files) < MAX_FILES:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if len(files) >= MAX_FILES:
                break
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in IGNORED_DIRS and entry.name != ".git":
                    stack.append(entry)
                continue
            if entry.suffix.lower() in SKIP_SUFFIXES:
                continue
            files.append(entry)
    return files


def survey_repo(root: Path) -> dict[str, Any]:
    """What this repo looks like, in the terms a stack profile is written in."""
    files = _walk(root)
    extensions = Counter(
        p.suffix.lower() for p in files if p.suffix and len(p.suffix) <= 12
    )

    markers: list[str] = []
    for marker in MARKER_FILES:
        if any(ch in marker for ch in "*?["):
            if any(root.glob(marker)):
                markers.append(marker)
        elif (root / marker).exists():
            markers.append(marker)

    try:
        directories = sorted(
            d.name for d in root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
            and d.name not in IGNORED_DIRS
        )[:12]
    except OSError:
        directories = []

    # Sample lines that look like calls or routes, so the contributor has
    # concrete material to write regexes against.
    terms = _denylist()
    samples: dict[str, list[str]] = {}
    top_suffixes = {
        s for s, _ in extensions.most_common(8) if s not in NON_CODE_SUFFIXES
    }
    for path in files:
        if path.suffix.lower() not in top_suffixes:
            continue
        try:
            if path.stat().st_size > 400_000:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern, label in CALL_SHAPES:
            found = samples.setdefault(label, [])
            if len(found) >= MAX_SAMPLES:
                continue
            for match in re.finditer(pattern, text):
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                line = text[line_start: line_end if line_end > 0 else len(text)]
                cleaned = redact(line, root.name, terms)
                if cleaned and cleaned not in found:
                    found.append(cleaned)
                if len(found) >= MAX_SAMPLES:
                    break

    return {
        "files": len(files),
        "extensions": extensions.most_common(8),
        "markers": markers,
        "directories": directories,
        "samples": {k: v for k, v in samples.items() if v},
        "known": [d.stack for d in _known(root)],
    }


def _known(root: Path):
    from . import stacks as stacks_mod

    return stacks_mod.detect(root)


def scaffold(name: str, survey: dict[str, Any]) -> str:
    """A profile skeleton, filled in as far as inspection allows."""
    extensions = [ext for ext, count in survey["extensions"] if count >= 2][:5]
    markers = survey["markers"][:6]

    lines: list[str] = []
    lines.append(f"# Estate Agent stack profile: {name}")
    lines.append("#")
    lines.append("# Scaffolded by `estate contribute stack`. The detection")
    lines.append("# section is filled in from a real repo; the patterns are")
    lines.append("# yours to write - see docs/adding-a-stack.md.")
    lines.append("#")
    lines.append("# Precision over recall, always. A pattern that occasionally")
    lines.append("# invents a connection is worse than one that misses some:")
    lines.append("# missed connections get added by hand and stay added, while")
    lines.append("# one phantom edge stops the whole map being trusted.")
    lines.append("")
    lines.append(f"stack: {name}")
    lines.append(f"display: {name.replace('-', ' ').title()}")
    lines.append("kind: backend          # backend | client | legacy")
    lines.append("")
    lines.append("detect:")
    if markers:
        lines.append("  files:")
        lines += [f"    - {m}" for m in markers]
    else:
        lines.append("  files: []          # TODO: a marker file, if there is one")
    if extensions:
        lines.append("  extensions:")
        lines += [f"    - {e}" for e in extensions]
    if survey["directories"]:
        lines.append("  # any_dirs:       # uncomment if a directory is distinctive")
        lines += [f"  #   - {d}" for d in survey["directories"][:4]]
    lines.append("  min_source_files: 2")
    if survey["known"]:
        lines.append(
            f"  # NOTE: this repo already matches {', '.join(survey['known'])}."
        )
        lines.append(
            "  # Set `requires_marker: true` with a distinctive content_marker,"
        )
        lines.append("  # or your profile will compete with an existing one.")
    lines.append("")
    lines.append("commands:")
    lines.append("  build: ''            # TODO - leave empty rather than guess")
    lines.append("  test: ''             # TODO - the one that matters most")
    lines.append("  lint: ''")
    lines.append("")
    lines.append("conventions:")
    lines.append("  - TODO: what would you tell a competent new joiner?")
    lines.append("")
    lines.append("tier_default: 2        # 1 restricted, 2 reviewed, 3 autonomous")
    lines.append("")
    lines.append("provides:")
    lines.append("  contracts:")
    lines.append("    - openapi.yaml")
    lines.append("  routes:")
    lines.append("    # - name: my-route-declaration")
    lines.append("    #   regex: '...'")
    lines.append("    #   method_group: 1")
    lines.append("    #   path_group: 2")
    lines.append("")
    lines.append("consumes:")
    lines.append("  patterns:")
    lines.append("    # - name: my-http-client")
    lines.append("    #   regex: '...'")
    lines.append("    #   url_group: 1")
    lines.append("    #   via: rest")
    lines.append("")

    if survey["samples"]:
        lines.append("# ---------------------------------------------------------")
        lines.append("# What this repo actually looks like, redacted. Write your")
        lines.append("# patterns against these, then delete this block.")
        lines.append("#")
        for label, examples in survey["samples"].items():
            lines.append(f"#   {label}:")
            for example in examples:
                lines.append(f"#     {example}")
            lines.append("#")

    lines.append("notes: |")
    lines.append("  TODO: anything a reader should know - what this stack's")
    lines.append("  detection cannot see, where coverage is weak, and why.")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def _cmd_stack(args: list[str]) -> int:
    positional = [a for a in args if not a.startswith("-")]
    if not positional:
        ui.error("which repo? usage: estate contribute stack <repo> [--name X]")
        return 64

    root = Path(positional[0]).expanduser().resolve()
    if not root.is_dir():
        ui.error(f"{root} is not a directory")
        return 1

    name = root.name.lower()
    if "--name" in args:
        name = args[args.index("--name") + 1].lower()
    name = re.sub(r"[^a-z0-9-]+", "-", name).strip("-") or "my-stack"

    ui.title(f"Scaffolding a stack profile from {root.name}")

    survey = survey_repo(root)
    ui.item(ui.INFO, f"{survey['files']} files read")
    if survey["markers"]:
        ui.item(ui.PASS, "Marker files", ", ".join(survey["markers"][:6]))
    else:
        ui.item(
            ui.WARN, "No marker file found",
            "detection will rest on file extensions alone, which is weaker",
        )
    if survey["extensions"]:
        ui.item(
            ui.PASS, "Extensions",
            ", ".join(f"{e} ({n})" for e, n in survey["extensions"][:5]),
        )
    if survey["known"]:
        ui.item(
            ui.WARN, f"Already matches: {', '.join(survey['known'])}",
            "your profile will compete with it unless you add a required "
            "marker - see the note in the scaffold",
        )
    sample_count = sum(len(v) for v in survey["samples"].values())
    ui.item(
        ui.PASS, f"{sample_count} example line(s) collected",
        "redacted, and included in the scaffold as material for your patterns",
    )

    text = scaffold(name, survey)
    out = Path(f"{name}.yaml")
    if "--out" in args:
        out = Path(args[args.index("--out") + 1]).expanduser()
    out.write_text(text, encoding="utf-8")

    ui.summary(3, 0, 1 if survey["known"] else 0)
    ui.item(ui.PASS, str(out.resolve()), "written")
    ui.say()
    ui.note("Read it before sending it anywhere. Redaction is applied, but")
    ui.note("you know your codebase and the linter does not.")
    ui.say()
    ui.next_step(
        f"fill in the TODOs, then `estate contribute check {out}` to try it"
    )
    return 0


def _cmd_check(args: list[str]) -> int:
    positional = [a for a in args if not a.startswith("-")]
    if not positional:
        ui.error(
            "which profile? usage: estate contribute check <profile.yaml> [repo]"
        )
        return 64

    profile_path = Path(positional[0]).expanduser().resolve()
    if not profile_path.is_file():
        ui.error(f"{profile_path} does not exist")
        return 1

    ui.title(f"Checking {profile_path.name}")
    problems = 0

    # 1. Does it parse?
    try:
        data = yamlite.load(profile_path.read_text(encoding="utf-8"))
    except (yamlite.YamliteError, OSError) as exc:
        ui.item(ui.FAIL, "Does not parse", str(exc))
        return 1
    if not isinstance(data, dict) or not data.get("stack"):
        ui.item(ui.FAIL, "Missing a top-level `stack:` key")
        return 1
    ui.item(ui.PASS, f"Parses, stack = {data['stack']}")

    # 2. Does every regex compile?
    declared = 0
    broken: list[str] = []
    for section in ("provides", "consumes"):
        block = data.get(section) or {}
        if not isinstance(block, dict):
            continue
        for key in ("routes", "patterns"):
            for item in block.get(key) or []:
                if not isinstance(item, dict) or not item.get("regex"):
                    continue
                declared += 1
                try:
                    re.compile(str(item["regex"]))
                except re.error as exc:
                    broken.append(f"{item.get('name', '?')}: {exc}")
    if broken:
        ui.item(ui.FAIL, f"{len(broken)} regex(es) do not compile", "\n".join(broken))
        problems += 1
    elif declared:
        ui.item(ui.PASS, f"{declared} pattern(s) compile")
    else:
        ui.item(
            ui.WARN, "No patterns yet",
            "a profile with no routes and no call patterns will detect the "
            "stack but find no connections",
        )

    # 3. Is the name free?
    if data["stack"] in all_stacks():
        ui.item(
            ui.WARN, f"`{data['stack']}` already exists",
            "pick another name, or send this as an improvement to that profile",
        )

    # 4. Does it find anything real?
    if len(positional) > 1:
        target = Path(positional[1]).expanduser().resolve()
        problems += _try_against(profile_path, target)
    else:
        ui.item(
            ui.INFO, "No repo given",
            f"run `estate contribute check {profile_path.name} <repo>` to try "
            f"it against real code",
        )

    ui.summary(3 - problems, problems, 0)
    if problems:
        ui.next_step("fix the problems above, then check again")
    else:
        ui.next_step(
            "open a pull request adding it to stacks/, or paste it into an "
            "issue - see CONTRIBUTING.md"
        )
    return 1 if problems else 0


def _try_against(profile_path: Path, target: Path) -> int:
    """Load the candidate profile in isolation and run it over a repo."""
    import shutil
    import tempfile

    from . import stacks as stacks_mod
    from .discover import extract_endpoints, extract_signals, iter_source_files

    if not target.is_dir():
        ui.item(ui.FAIL, f"{target} is not a directory")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        holding = Path(tmp)
        shutil.copy2(profile_path, holding / profile_path.name)
        loaded = stacks_mod.all_stacks(holding)

    if not loaded:
        ui.item(ui.FAIL, "The profile did not load")
        return 1
    stack = next(iter(loaded.values()))

    wanted = {str(e).lower() for e in (stack.detect.get("extensions") or [])}
    files: list[tuple[Path, str]] = []
    for path in iter_source_files(target):
        if wanted and path.suffix.lower() not in wanted:
            continue
        try:
            files.append((path, path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue

    if not files:
        ui.item(
            ui.WARN, f"No matching files in {target.name}",
            "check the `extensions` list",
        )
        return 0

    endpoints, truncated = extract_endpoints(target, stack, files)
    signals = extract_signals(target, stack, files)

    ui.item(ui.PASS, f"{len(files)} file(s) matched in {target.name}")
    if endpoints:
        ui.item(
            ui.PASS, f"{len(endpoints)} endpoint(s) found",
            "\n".join(
                f"{e.method or 'ANY'} {e.path}  ({e.evidence})"
                for e in endpoints[:5]
            ),
        )
    else:
        ui.item(ui.WARN, "No endpoints found", "expected, if this stack exposes none")
    if signals:
        ui.item(
            ui.PASS, f"{len(signals)} call site(s) found",
            "\n".join(f"{s.kind}: {s.value[:60]}" for s in signals[:5]),
        )
    else:
        ui.item(
            ui.WARN, "No call sites found",
            "if this repo does call other services, the patterns are not "
            "matching yet",
        )

    ui.say()
    ui.note("Check the findings above against the code. A pattern that finds")
    ui.note("something wrong is worse than one that finds nothing.")
    return 0


def cmd_contribute(args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print(
            "estate contribute - extend Estate Agent\n\n"
            "  estate contribute stack <repo> [--name X] [--out FILE]\n"
            "      Scaffold a stack profile from a real repo. Redacted: no\n"
            "      repo names, no paths, and anything in a local\n"
            "      .publish-denylist removed.\n\n"
            "  estate contribute check <profile.yaml> [repo]\n"
            "      Validate a profile, and optionally run it against a repo\n"
            "      to see what it finds.\n\n"
            "Nothing is uploaded. See CONTRIBUTING.md for how to send it,\n"
            "including from a machine that cannot push to GitHub.\n"
        )
        return 0

    action, rest = args[0], args[1:]
    if action == "stack":
        return _cmd_stack(rest)
    if action == "check":
        return _cmd_check(rest)

    ui.error(f"unknown action `{action}` - try `stack` or `check`")
    return 64
