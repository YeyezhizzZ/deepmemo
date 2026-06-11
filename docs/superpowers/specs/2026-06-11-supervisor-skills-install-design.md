# Supervisor-Skills Install — Design

**Date:** 2026-06-11
**Status:** Draft (awaiting user review)
**Owner:** Claude (brainstorming) → writing-plans → implementation

## Goal

Install the 7 AI skills shipped by [HKUSTDial/Supervisor-Skills](https://github.com/HKUSTDial/Supervisor-Skills) into the DeepMemo `.claude/skills/` directory so Claude Code can discover and invoke them automatically, and so they participate in the existing `skills-manager` audit/optimize pipeline.

This is a **local operational install** (the entire `.claude/` is gitignored), made reproducible by a committed install script.

## Scope

- **In scope:** Clone the upstream repo, expose its 7 `plugins/phd-research/skills/<name>/SKILL.md` files as Claude Code skills via symlinks, register each in `skills.db`, and document the install.
- **Out of scope:** Modifying the upstream SKILL.md content, adding the upstream `handbook/` or `docs/en/handbook/` theory chapters, registering skills globally (`~/.claude/skills/`), changing `skills-manager` itself.

## Upstream Inventory

7 skills, each a folder with a `SKILL.md` frontmatter file:

| Folder | Purpose (from upstream description) |
|---|---|
| `idea-evaluator` | Score a research idea on the 5-dim Higher/Faster/Stronger/Cheaper/Broader framework |
| `vibe-research-workflow` | AI-assisted full research workflow (Coding/Figure/Writing) |
| `intro-drafter` | Draft a high-quality Intro outline from motivation |
| `tech-paper-template` | Step-by-step logic chain for a technical full paper |
| `benchmark-paper-template` | Logic + experimental design for benchmark/eval papers |
| `pre-submission-reviewer` | Top-venue reviewer pass on draft + grammar checklist |
| `figure-designer` | Design advice for motivation/overview/experiment figures |

Upstream license: **CC BY-NC-SA 4.0** (non-commercial, attribution, share-alike). The install copies the upstream SKILL.md files (verbatim, via symlink) and exposes them as Claude Code skills inside DeepMemo, which is the user's personal knowledge base. Attribution is provided via `ATTRIBUTION.md` (see C4). The user is responsible for ensuring their use of the skills complies with the license.

## Target Architecture

```
DeepMemo/.claude/
├── skills/
│   ├── .upstream/
│   │   └── Supervisor-Skills/        # git clone (local-only, gitignored)
│   │       └── plugins/phd-research/skills/
│   │           ├── idea-evaluator/SKILL.md
│   │           ├── vibe-research-workflow/SKILL.md
│   │           ├── intro-drafter/SKILL.md
│   │           ├── tech-paper-template/SKILL.md
│   │           ├── benchmark-paper-template/SKILL.md
│   │           ├── pre-submission-reviewer/SKILL.md
│   │           └── figure-designer/SKILL.md
│   ├── idea-evaluator            → .upstream/Supervisor-Skills/.../idea-evaluator
│   ├── vibe-research-workflow    → .upstream/.../vibe-research-workflow
│   ├── intro-drafter             → .upstream/.../intro-drafter
│   ├── tech-paper-template       → .upstream/.../tech-paper-template
│   ├── benchmark-paper-template  → .upstream/.../benchmark-paper-template
│   ├── pre-submission-reviewer   → .upstream/.../pre-submission-reviewer
│   ├── figure-designer           → .upstream/.../figure-designer
│   └── (existing local skills unchanged)
└── ATTRIBUTION.md                # CC BY-NC-SA 4.0 attribution (local-only)
```

A committed helper at `scripts/install_supervisor_skills.sh` performs the install and is re-runnable on a fresh clone.

## Components

### C1. Install script — `scripts/install_supervisor_skills.sh`

**Responsibility:** bring the upstream into `.claude/skills/.upstream/`, expose the 7 skills via symlinks, and register each in `skills.db`.

**Interface:**

```bash
./scripts/install_supervisor_skills.sh            # full install (clone + symlinks + register)
./scripts/install_supervisor_skills.sh --verify   # checks filesystem + db, exits non-zero on any failure
```

**Inputs:** none (uses `REPO_URL` and `SKILL_NAMES` constants in the script).

**Outputs:**
- Mutates `.claude/skills/.upstream/Supervisor-Skills/` (clones if absent, `git pull --ff-only` if present).
- Creates/updates 7 symlinks in `.claude/skills/`.
- Writes 7 rows to `.claude/skills.db` (table: `skills`).

**Idempotency contract:** re-running must be a no-op (except the `git pull`). All operations use `INSERT OR REPLACE` or `ln -snf`.

**Failure semantics:** `set -euo pipefail`; abort on any error before mutating state when possible.

### C2. Symlinks — 7 entries in `.claude/skills/`

**Responsibility:** make the upstream skill folders discoverable by Claude Code's skill loader (which expects `<name>/SKILL.md` one level under `.claude/skills/`).

**Safety:** if an existing path at the target is **not** a symlink, the script aborts with an explicit error rather than overwriting a real directory.

### C3. skills.db rows — 7 entries

| Column | Value |
|---|---|
| `id` | `supervisor-<name>` (e.g. `supervisor-idea-evaluator`) |
| `name` | `<name>` (matches folder) |
| `description` | first ~500 chars of the upstream `description:` frontmatter |
| `version` | inherits default `1.0` |
| `created_at` | CURRENT_DATE |

The `supervisor-` prefix reserves a namespace, makes the source obvious in `query all` output, and prevents future collisions with first-party skills.

### C4. ATTRIBUTION.md — `.claude/ATTRIBUTION.md` (local-only)

**Responsibility:** satisfy the CC BY-NC-SA 4.0 attribution requirement. This file is created by the install script and is required (not optional).

**Content:** upstream project name, repository URL, copyright holder (HKUST(GZ) / Yuyu Luo), license name and link, list of contributors acknowledged in upstream README (吴垠, 李伯岩, 谢宇鹏), statement that derivative works (the symlinked install) inherit the same license.

## Data Flow

```
User runs ./scripts/install_supervisor_skills.sh
        │
        ├─► git clone / pull .upstream/Supervisor-Skills/
        │
        ├─► for each of 7 skills:
        │     ln -snf .upstream/.../skills/<name> .claude/skills/<name>
        │     python3 skills-manager/skills_db.py register supervisor-<name> <name> <desc>
        │
        └─► echo "OK: 7 Supervisor-Skills installed and registered."

User runs ./scripts/install_supervisor_skills.sh --verify
        │
        ├─► for each of 7 skills:
        │     test -f .claude/skills/<name>/SKILL.md
        │     awk-extract `name:` from frontmatter, assert == <name>
        │
        └─► python3 skills-manager/skills_db.py query all | grep "supervisor-"
              (asserts 7 lines)

User starts a new Claude Code session
        │
        └─► SessionStart hook loads USER.md, MEMORY.md, then
            Claude Code scans .claude/skills/ → discovers 7 new symlinked skills
```

## Error Handling

| Failure mode | Behavior |
|---|---|
| `git clone` fails (no network, 404) | Script aborts via `set -e`. No symlink/db mutation occurs. |
| `git pull --ff-only` fails (upstream diverged from local) | Script aborts. User runs `git -C .upstream/Supervisor-Skills reset --hard origin/main` (or removes the directory) and reruns. |
| Existing real directory at `.claude/skills/<name>` | Script aborts with explicit error message naming the conflict. Does **not** delete or overwrite. |
| `skills-manager` script missing or non-executable | Script aborts. Fix the broken module, then rerun. |
| Empty `description` in upstream frontmatter | `register` accepts `""`; skill still appears in `skills.db` with empty description. |
| `.claude/` is gitignored | Not a failure. Install is local-only; the install script is committed in `scripts/`, so the install is reproducible from a fresh clone (re-clone the upstream, re-create symlinks, re-register). |

## Testing / Verification

Five checks, in order:

1. **Filesystem (script-internal):** after install, 7 symlinks exist and each resolves to a real `SKILL.md`. Implemented as a `for` loop with `test -f`; failure exits non-zero.

2. **Frontmatter consistency (script-internal):** the `name:` field in each `SKILL.md` matches its folder name. Catches upstream renames that would silently break discovery.

3. **DB presence (script-internal):** `python3 .claude/skills/skills-manager/skills_db.py query all` lists all 7 `supervisor-*` ids. Implemented as `grep -c "^## supervisor-"` matching 7.

4. **`--verify` mode:** the above three checks are also exposed as `./scripts/install_supervisor_skills.sh --verify` for post-install smoke tests or CI.

5. **Repo-level regression:** `uv run python scripts/verify.py --mode quick` to make sure no existing test broke. (Defensive — the install doesn't touch `src/`, `tests/`, or `pyproject.toml`.)

6. **Manual Claude Code smoke test:** start a new session, say "evaluate this research idea: <one-line stub>". Expect the `idea-evaluator` skill to be picked up and the upstream 5-dim scoring prompt to drive the response.

## What this design does NOT do

- Does not modify any upstream `SKILL.md` content. Symlinks mean upstream changes flow in on `git pull` without any merge work.
- Does not install globally. Other projects on this machine won't see these skills until they're also exposed under `~/.claude/skills/`.
- Does not vendor the `handbook/` theory chapters. Skills are self-contained prompts.
- Does not change `skills-manager` itself.
- Does not commit any of `.claude/` to git. Only `scripts/install_supervisor_skills.sh` is committed.

## Open Questions

None at this time. All clarifying questions resolved during brainstorming.
