---
name: openupgrade
description: Migrate an Odoo project from one major version to the next using OpenUpgrade. Activates when the user wants to upgrade, migrate, or move an Odoo project between major versions (e.g. 17 to 18, 18 to 19, "actualizar Odoo", "OpenUpgrade migration"). Only activates inside a project that looks like an Odoo Docker setup (presence of docker-compose.yml referencing an Odoo image or service). Single-version jump per invocation. Targets Community Edition. Three checkpoints: plan, pre-migration, post-migration.
---

# OpenUpgrade Migration Skill

Orchestrates an OpenUpgrade-based migration of an Odoo project between
two consecutive major versions, running inside Docker.

## Scope

- Single jump per invocation: `N.0` → `(N+1).0`. Multi-version cascade
  (e.g. 16 → 19) is out of scope; the user runs the skill once per jump.
- Community Edition only. Enterprise modules abort the run.
- Docker / Docker Compose environments only.

## Activation guard

Before running anything, verify all of:

1. `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, or
   `compose.yaml` exists in the working directory.
2. That compose file declares a service whose `image` contains `odoo`
   OR whose `build.args` includes a key with `ODOO` in its name
   OR which is conventionally named `web` / `odoo`.
3. `docker` is available on the host (`command -v docker`).

If any check fails, do not continue. Tell the user the skill only
supports Docker-based Odoo projects today.

## First-run setup

The scripts use a virtualenv at `<skill_root>/.venv/`. Create it once:

```sh
python3 -m venv ~/.claude/skills/openupgrade/.venv
~/.claude/skills/openupgrade/.venv/bin/pip install -r ~/.claude/skills/openupgrade/requirements.txt
```

All script invocations below use `~/.claude/skills/openupgrade/.venv/bin/python`.

## Directory map

```
~/.claude/skills/openupgrade/
├── SKILL.md
├── requirements.txt
├── .venv/
├── scripts/
│   ├── detect_versions.py
│   ├── classify_addons.py
│   ├── scaffold_custom_migration.py
│   ├── clone_oca_branches.py
│   ├── pg_clone_db.py
│   ├── snapshot_filestore.py
│   ├── render_migration_stack.py
│   ├── preflight.py
│   ├── run_migration.py
│   └── generate_report.py
└── templates/
    ├── Dockerfile.openupgrade.j2
    └── docker-compose.openupgrade.yml.j2
```

The user's project gets a sidecar directory `<project>/.openupgrade/`
containing the override file (`addons.yml`) and per-target build outputs
(`v<target_major>/Dockerfile.openupgrade`, `docker-compose.openupgrade.yml`,
`migration.log`, `openupgrade-report-*.md`).

## Override file: `<project>/.openupgrade/addons.yml`

Lets the user correct the automatic addon classification.

```yaml
addons:
  my_custom_module:
    category: custom
    notes: Hand-written; needs scaffolding.
  forked_account_module:
    category: oca_with_target
    repo: my-org/my-account-fork
    branch: "19.0"
```

Valid `category` values: `core`, `oca_with_target`, `oca_without_target`,
`third_party_with_target`, `third_party_without_target`, `custom`,
`enterprise`.

## Workflow: three checkpoints

The skill is an assistant with three mandatory pauses. **Do not skip any
of them**. Idempotency: every step inspects existing state and skips work
that is already done.

### Checkpoint 1 — PLAN

This is where the user grants the big OK. Show everything before they
approve.

1. **Detect versions and addon paths.**

   ```sh
   ~/.claude/skills/openupgrade/.venv/bin/python \
     ~/.claude/skills/openupgrade/scripts/detect_versions.py \
     --project-dir <project>
   ```

   Capture `source_version`, `target_version`, `addons_paths`. If the
   user wants a specific target, re-run with `--target X.0`.

2. **Classify addons.**

   ```sh
   ~/.claude/skills/openupgrade/.venv/bin/python \
     ~/.claude/skills/openupgrade/scripts/classify_addons.py \
     <addons_path1> <addons_path2> ... \
     --target <target_version> \
     --project-dir <project>
   ```

   If the user has many OCA addons or is on a slow network, mention that
   each upstream repo can take ~60 s to probe and the script caches
   per-repo. `--ls-remote-timeout 120` raises the per-repo cap.

   Save the JSON to `<project>/.openupgrade/v<target_major>/classification.json`
   for the report step later.

3. **Detect Enterprise modules.** If `summary.by_category.enterprise > 0`,
   abort the skill with a clear message listing the offending modules
   and a pointer to Odoo's paid upgrade service. Do not proceed.

4. **Show the Plan to the user**, including:
   - Source → target version.
   - DB clone source name → target DB name (suggested: `<source>_v<target_major>`).
   - Filestore volume source → target volume (suggested:
     `<original>_v<target_major>`).
   - For each category, the list of addons:
     - `oca_with_target` / `third_party_with_target`: what will be cloned
       and where (the script will choose
       `<addon_parent_dir>-<target_major>/`).
     - `oca_without_target` / `third_party_without_target`: **blocking**.
       Ask the user whether to fork-and-port, wait, or add an override.
     - `custom`: list of addons that will get scaffolding.
   - Optional preflight (decision 11): ask the user whether they want a
     dynamic preflight (5-15 min) or to skip it.

5. **Offer to write a starter override file** at
   `<project>/.openupgrade/addons.yml` populated with the auto-detected
   classification so the user can edit it. Do not overwrite an existing
   override file.

6. **WAIT for explicit user approval** before continuing. Approval covers
   the entire idempotent prep phase (clone OCA branches, scaffold custom
   modules, clone DB, snapshot filestore, build image). It does NOT cover
   running the migration; that is checkpoint 2.

### Prep phase (no further pauses until checkpoint 2)

Execute these in order. Each script is idempotent and exits non-zero on
failure. If any fails, stop and report.

1. **Clone OCA / third-party target branches.**

   ```sh
   ~/.claude/skills/openupgrade/.venv/bin/python \
     ~/.claude/skills/openupgrade/scripts/classify_addons.py ... \
     | ~/.claude/skills/openupgrade/.venv/bin/python \
       ~/.claude/skills/openupgrade/scripts/clone_oca_branches.py \
       --project-dir <project>
   ```

   Or pass the classification JSON file with `--input <path>`.

2. **Scaffold custom modules.**

   ```sh
   ~/.claude/skills/openupgrade/.venv/bin/python \
     ~/.claude/skills/openupgrade/scripts/scaffold_custom_migration.py \
     <path-to-each-custom-addon> ... \
     --target <target_version>
   ```

   Use `--dry-run` first; show the actions to the user; then apply.

3. **Clone the database (copy mode, decision 6 default).**

   ```sh
   ~/.claude/skills/openupgrade/.venv/bin/python \
     ~/.claude/skills/openupgrade/scripts/pg_clone_db.py \
     --project-dir <project> \
     --source <source_db> \
     --target <source_db>_v<target_major>
   ```

   If the user explicitly chose in-place earlier (decision 6 opt-in),
   skip this step and warn that rollback now requires their pre-existing
   backup.

4. **Snapshot the filestore.** First, read the volumes section of the
   project compose to discover the source volume name (the one mounted at
   `/var/lib/odoo` on the Odoo service). Then:

   ```sh
   ~/.claude/skills/openupgrade/.venv/bin/python \
     ~/.claude/skills/openupgrade/scripts/snapshot_filestore.py \
     --source-volume <project-name>_filestore \
     --dest-volume <project-name>_filestore_v<target_major>
   ```

   Docker prefixes volume names with the compose project. If the user
   sets `COMPOSE_PROJECT_NAME` or `name:` in compose, use that prefix.

5. **Render the migration stack.**

   ```sh
   ~/.claude/skills/openupgrade/.venv/bin/python \
     ~/.claude/skills/openupgrade/scripts/render_migration_stack.py \
     --project-dir <project> \
     --target <target_version> \
     --target-db <source_db>_v<target_major> \
     --filestore-volume <project>_filestore_v<target_major>
   ```

   Produces `<project>/.openupgrade/v<target_major>/Dockerfile.openupgrade`
   and `docker-compose.openupgrade.yml`. Default `--network-mode host`;
   override with the project's network if the project does not use host
   networking.

6. **(Optional) Preflight.** Run only if the user opted in at the Plan.

   ```sh
   ~/.claude/skills/openupgrade/.venv/bin/python \
     ~/.claude/skills/openupgrade/scripts/preflight.py \
     --stack-dir <project>/.openupgrade/v<target_major> \
     --project-dir <project>
   ```

   Report the resulting `modules_with_errors`. If non-empty, ask the user
   whether to fix and rerun preflight, or to continue anyway.

### Checkpoint 2 — PRE-`-u all`

Pause here. This is the last point before the destructive step.

Show the user:
- The exact `docker compose` command that will run next.
- The target DB and filestore volume that will be mutated.
- An estimated duration based on the source DB size (use
  `pg_database_size`; if unavailable, just say "could take minutes to
  hours depending on data volume").

**WAIT for explicit user approval.**

### Migration phase

```sh
~/.claude/skills/openupgrade/.venv/bin/python \
  ~/.claude/skills/openupgrade/scripts/run_migration.py \
  --stack-dir <project>/.openupgrade/v<target_major>
```

This streams logs in real time and tees them to
`<stack-dir>/migration.log`. It is long-running; do not invoke other
tools concurrently against the same database.

### Checkpoint 3 — POST-MIGRATION

Generate the structured report:

```sh
~/.claude/skills/openupgrade/.venv/bin/python \
  ~/.claude/skills/openupgrade/scripts/generate_report.py \
  --project-dir <project> \
  --target <target_version> \
  --source-db <source_db> \
  --target-db <source_db>_v<target_major> \
  --log-path <project>/.openupgrade/v<target_major>/migration.log \
  --classification <project>/.openupgrade/v<target_major>/classification.json
```

Summarise the report contents back to the user, then offer the next-step
options (promote, smoke-test, abort, debug). Do NOT clean up automatically;
the user decides.

## Failure-mode policy

- Network timeouts on `git ls-remote`: classifier returns
  `target_branch_available: null`. Raise `--ls-remote-timeout` or move
  the addon to an override.
- `pg_clone_db.py` errors: target DB is dropped to avoid leaving a
  half-written copy; original DB untouched.
- `snapshot_filestore.py` errors: target volume is removed; original
  volume untouched.
- Migration container exits non-zero: target DB and filestore stay
  intact for inspection. Re-running the migration drops them first via
  `--drop-existing` and `--force`.

## What the skill does NOT do

- Promote the migrated DB to production. The user does that manually.
- Modify the original `docker-compose.yml`. The migration stack is a
  separate compose file under `.openupgrade/v<target_major>/`.
- Migrate filestore data structure between versions. Odoo's `-u all`
  pass does that part inside the container.
- Cover Odoo Enterprise. The skill aborts if Enterprise modules are
  detected.
