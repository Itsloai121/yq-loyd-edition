# yq security review – the simple version

**What was checked:** the `yq` tool (a small command-line program that reads YAML/XML/TOML and passes it to `jq`), version 4.4.0, from `yq-loyd edition.rar`.
**Checked against:** *DevSecOps Checklist (Expanded Edition).pdf*.

## The short story

- The code itself is in **good shape**. No passwords or keys are hidden in it or in its history, it doesn't run dangerous code from YAML files, and all 160 original tests passed.
- **It never opens any network port.** I searched the code and checked at runtime: there is no server, no listener, nothing that connects to the internet.
- Most problems were in the **build/release setup** (GitHub Actions) and in **missing safety nets**, not in the program itself.
- I fixed what could be fixed safely and **locked all network ports in code** (details below).

## What was wrong, and how I fixed it

### 1. Build tools were not "locked" to an exact version (supply-chain risk)
- **Problem:** The GitHub workflows used things like `actions/checkout@v7`. A tag like `v7` can be moved by whoever owns that action. If they get hacked, malicious code runs in *your* build and release.
- **Fix:** Every action is now pinned to its exact commit hash (with the version in a comment). Dependabot (new) will keep them updated.
- **Files:** `.github/workflows/ci.yml`, `release.yml`, new `.github/dependabot.yml`

### 2. The build had more permissions than it needed
- **Problem:** The test workflow didn't say what the build token may do, so it got GitHub's default (can be too much).
- **Fix:** Added `permissions: contents: read` at the top of both workflows. Only the publish step gets the extra "id-token: write" it really needs.

### 3. The build kept the repo login saved on disk
- **Problem:** `actions/checkout` stores a token by default, so later steps (or a bad action) could read it.
- **Fix:** Added `persist-credentials: false`.

### 4. An old, vulnerable PyYAML version was allowed
- **Problem:** `pyproject.toml` allowed PyYAML 5.3.1, which has a known security hole (PYSEC-2021-142 / CVE-2020-14343). yq itself uses PyYAML's *safe* mode, so yq wasn't directly exposed, but people could install it with the bad version.
- **Fix:** Minimum is now `PyYAML >= 5.4`.

### 5. No automatic security scanning
- **Problem:** Nothing checked the code or the libraries for known problems on every change.
- **Fix:** New workflow `.github/workflows/security.yml` runs Bandit (code scan), pip-audit (known vulnerable libraries) and zizmor (workflow scan) on every push and once a week.

### 6. Network ports – locked in code ("hard-coded")
- **Finding:** yq has **no open ports** to begin with.
- **Fix anyway:** New file `yq/_netguard.py`. The moment `yq`, `xq` or `tomlq` starts, it permanently blocks every internet (IPv4/IPv6) socket in that process. After that, nothing inside the program can listen on, bind to, or connect through a port – not even a library by accident. There is **no switch or setting to turn it off**. Normal use (pipes, files, jq) is not affected.
- **Tests:** 2 new tests prove that creating, binding, connecting and DNS lookups all fail.
- **Honest limit:** this protects the yq process only. For a hard guarantee also run it with no network (for example `docker run --network none`).

### 7. Windows line endings made every file look "changed"
- **Problem:** The archive had Windows (CRLF) line endings, so git showed all 33 files as modified.
- **Fix:** Added `.gitattributes` to keep Linux (LF) endings. The fixed copy I give you is clean.

## Things I found but did NOT change (and why)

| Issue | Why left alone | What to do |
|---|---|---|
| **Crash on extremely nested YAML** (about 25,000+ levels of `[[[[…`) makes the PyYAML C library segfault. Only that one run dies; nothing is leaked. | The bug is inside PyYAML/libyaml, not yq. A proper fix means changing how yq parses (the project rules forbid custom parsers). | Don't feed untrusted YAML without limits (e.g. `ulimit`, container, timeout). Report to PyYAML. |
| **`--in-place` editing has no backup** and isn't atomic | Intentional upstream design; the docs already warn about it. | Keep your own backup or use git before using `-i`. |
| `jq` is found through `PATH` | Normal behaviour for a wrapper tool. | Make sure `PATH` is trusted. |
| Bandit "low" notes (use of `assert`, `try/except/pass`) | Style-level, no real risk here. | Optional cleanup. |
| Package says it supports Python 3.8–3.9, but tests only run on 3.10+ | Changing supported versions is a project decision. | Raise the minimum or add those to the test matrix. |
| No lockfile, SBOM, artifact signing | Bigger projects-level work (L2/L3 in the checklist). | Next step in the rollout plan. |
| MFA, branch protection, CODEOWNERS | These are GitHub **settings**, not files – I can't see them from a zip. | Turn them on in the GitHub org/repo settings. |

## What looked good (no change needed)

- No secrets in the files or full git history.
- YAML tags like `!!python/object/apply:os.system` are **not executed** (tested – treated as plain data).
- "YAML bomb" (aliases that explode in size) is **stopped** with a clear error.
- XML external entity attack (XXE) is **blocked** (`entities are disabled`).
- jq is started **without a shell**, so no command injection.
- Releases to PyPI already use short-lived OIDC login (no stored password).

## Before / after

| Check | Before | After |
|---|---|---|
| Tests | 160 pass | 162 pass (2 new) |
| zizmor (workflow scan) | 9 unpinned actions + 3 permission + 1 credential warning | **0 findings** |
| Bandit medium/high | 0 | 0 |
| Libraries with known CVEs | allowed PyYAML 5.3.1 | none allowed |
| Open network ports | none | none, and now **impossible** |
| ruff lint/format | clean | clean |

The full details are in the PDF report.
