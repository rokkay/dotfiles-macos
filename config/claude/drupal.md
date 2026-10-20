## Drupal projects

Shared rules for every project under `~/work/projects/drupal/`. Project-specific rules live in each repo's `AGENTS.md`.

### Patches

When a core or contrib patch stops applying, read the drupal.org issue comments before writing one. Contributors often post branch-specific rerolls (e.g. `-10.6.x.patch`) that are already tested. Pin that static `https://www.drupal.org/files/issues/...` URL in `composer.json`. Only reroll a patch yourself under `patches/` if no comment offers one.

Never reference a live merge request diff (`https://git.drupalcode.org/project/drupal/-/merge_requests/N.diff`) in `composer.json`. Its content changes on every reroll, so builds break without any local change.

### Removing a module

Split the removal across two deploys by default:

1. Ship the config change that uninstalls the module (`core.extension.yml` without the entry, plus deletion of its config files). The module code must still be present so `drush cim` can run its uninstall hooks.
2. Remove the package from `composer.json`, refresh `composer.lock` and drop related patches.

If both go in the same deploy, `composer install` removes the code before `drush cim` runs and the deploy fails with "module not found". Only combine them if I explicitly ask for one deploy.

### Secrets

Never print or copy to local any file holding credentials (`settings.php`, `settings.*.php`, `.env`, `.env.make`), not even "masked" with sed. Masking regexes have leaked passwords before (BSD sed does not support `\s`). Process those files on the remote host and print only counts or specific non-secret lines.
