---
name: drupal-audit
description: Use when the user asks for a portal review, audit or improvement analysis of a Drupal site covering usability, content, performance and accessibility, with findings checked against local and production.
disable-model-invocation: true
argument-hint: "[extra focus or notes]"
---

# Drupal portal audit

Analyze this Drupal project to find opportunities to improve the portal. Coordinate four subagents in parallel, one per focus area:

1. Usability
2. Content and information
3. Performance
4. Accessibility

Each subagent must stick to its assigned focus. Share these instructions with all of them and ask them to return findings with evidence. Do not edit the code or the configuration.

Extra notes from the user for this run, if any: $ARGUMENTS

## Preparation (before launching the subagents)

Identify the environments:

- Production: the public URL and the Drush alias (check `drush/sites/*.site.yml`, `README`, `AGENTS.md` or equivalents). Check that the alias responds with `drush <alias> status` (with whatever prefix the project uses, for example `ddev`).
- Local: check that the site starts and that the database is a recent copy of production. To find out how recent it is, look at the date of the most recent content or the most recent login. State that date in the report.
- If the local copy does not exist, is old, or does not match production, propose syncing it with `drush sql:sync <prod-alias> @self` and ask for confirmation before running it, because it overwrites the local database. Production is always the source and never the target. Check that the project's Drush policies block production targets using the real alias, and if they don't, flag it in the report.
- `sql:sync` leaves a database dump on the production server (usually `~/drush-backups/`). Do not delete it. Report its path so the user can decide.
- If the files (images, documents) are not available locally, note it as a limitation or use whatever mechanism the project has (for example `stage_file_proxy`). Do not sync files without confirmation.
- Before testing anything locally, check that external integrations do not act on real services. Email must be captured (Mailpit or equivalent), and newsletter, CRM, payment or API keys must be disabled or point to a sandbox. If you cannot guarantee this, do not submit forms or trigger actions that would fire them.
- If you cannot identify or connect to an environment, ask before continuing.

## Where each check is done

- Repository code and configuration: local.
- Authenticated journeys, roles and permissions, forms, flows that write data, and content review: local, on the production copy.
- Anything that depends on infrastructure (response times, cache headers and layers, CDN, CSS/JS aggregation, compression, served images, redirects, configuration that differs from the repository): production, read-only and as an anonymous user.
- If the local development configuration changes behavior (caches disabled, aggregation disabled, development modules), do not trust local performance results. Verify them in production.
- State for each finding which environment it was verified in.

## Instructions for each subagent

- Inspect the project and detect the Drupal version, custom and contributed modules, the theme, and the configuration relevant to your focus.
- Base the analysis on the version and Drupal patterns you find in the project.
- Cite the files and lines that support each finding. Explain which portal experience or task it affects.
- Separate what is confirmed by the code from what requires testing the running portal. Do not present as fact a problem that is only possible according to the code.
- For each finding, report: what happens, evidence, how to reproduce or verify it, affected user, impact, recommended improvement, priority, confidence, estimated effort, and what kind of check confirms it (code, local test, or production test).
- Point out limitations and pending checks. Avoid generic recommendations.
- Write your findings in Spanish (es_ES), with correct Spanish spelling (accents, `ñ`, `¿`, `¡`), in plain words a 10-year-old could follow. Keep file paths, line numbers and commands exactly as they are, but explain in simple terms what they mean and why they matter.

If the portal has access for registered users, the usability subagent must also check, locally, a journey with a profile different from the usual editor. Use `drush user:login` (ULI) to log in as existing users with different roles. Prefer test accounts, if there are any. Check the role with `drush user:information` before testing. Do not bypass access controls or change accounts or roles to force a journey. If it cannot run the test, it must review roles, permissions and access controls in the code and make clear what remains unchecked. The other subagents must point out role and permission differences when they are relevant to their focus.

If a subagent stops with an error before returning its findings, relaunch it once with the same instructions. If it fails again, list its focus area as not covered in the report.

## Rules for local

- You may browse, submit forms and test flows, as long as the external integrations check from the preparation is satisfied.
- Do not change configuration, roles or permissions, because the analysis has to reflect production. If a test needs test data, note what you created.
- Do not pass `-y`, `-n` or `--yes` to Drush commands that ask for confirmation. `config:import --diff -n` answers yes and imports. Use `config:status` to see differences.
- The copy contains real personal data. Do not copy it into the report (emails, usernames, IPs, private content) and do not include ULI links or their tokens.

## Rules for production

It has real users and real data, and any action affects them:

- Read-only and anonymous only. Do not log in, do not submit forms, and do not create, edit or delete content. Anything that needs writing or authentication is tested locally.
- No load or stress testing. At most one request per second per subagent. You may use Lighthouse, `curl -I` and browser tools. If there is a cache layer (Varnish, CDN, Drupal page cache), note for each measurement whether the response came from cache according to the headers. Do not add parameters to bypass the cache except for occasional, justified requests.
- Drush against production: only `sql:sync` with production as the source (with the confirmation from the preparation) and read commands such as `status`, `pm:list`, `config:get`, `config:status`, `role:list` and `watchdog:show`. Any command that writes or affects performance is forbidden, in particular `cache:rebuild`, `config:import`, `config:export`, `sql:query`, `sql:cli`, `sql:drop`, `php:eval`, `php:script`, `state:set`, `user:*`, `cron`, `queue:run`, `updatedb`, `deploy`, `pm:install` and `pm:uninstall`. If you are unsure whether a command writes, do not run it.
- If a check would require breaking any of these rules, do not do it. Leave it as a pending check and explain why.

Adapt these instructions to what you find in the project (local environment tool, cache layer, integrations, forms with external effects), but without relaxing the production rules or the protection of integrations in local.

## Final report

Combine the reports without adding findings that lack evidence. Deduplicate repeated problems, point out discrepancies between subagents, and sort the improvement opportunities by priority. State the date of the local copy used and which checks should be done next.

Write the whole report in Spanish (es_ES), with correct Spanish spelling (accents, `ñ`, `¿`, `¡`). Use words a 10-year-old could follow: short sentences, no unexplained jargon, and a simple explanation of every technical term the first time it appears. Keep file paths, line numbers, commands and exact names unchanged so the evidence stays checkable, but always say in plain words what they show.

Publish the report as an artifact in the same way as https://claude.ai/artifact/BEhDmYLTVKL8omvMSRjSCG (read it with the Artifact tool for its structure and style). The report has these sections, in this order:

1. Header: `dominio · Drupal <versión> · <fecha>`, the title `Revisión del portal <nombre>`, and a short plain-words intro.
2. **Resumen rápido**: facts for the local copy date, the production URL, the number of findings after merging, and the most urgent issue.
3. **Palabras que usamos en este informe**: a glossary of every technical term used.
4. **Cómo lo revisamos**: the four reviewers, what was done locally and in production, and the code / local / producción labels.
5. **Todos los hallazgos, por prioridad**: a table (#, hallazgo, prioridad, esfuerzo, comprobado en) with filter buttons by area (Seguridad, Usabilidad, Contenido, Rendimiento, Accesibilidad). IDs A1… for Alta, B1… for Media, C1… for Baja. Esfuerzo S (hours), M (1 to 3 days), L (more).
6. **Detalle**: one card per finding with what happens, evidence, how to check it, who it affects, impact, fix, confidence, effort, environment and status.
7. **Donde los ayudantes vieron las cosas de forma distinta**: discrepancies and how they were resolved.
8. **Qué hicimos en los entornos**: syncs, dumps left on servers, test data created, any mistakes made, and temporary files to delete.
9. **Qué falta por comprobar y qué mirar después**.
