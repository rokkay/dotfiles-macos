# Mis dotfiles

Dotfiles personales para macOS, orientados a desarrollo con Laravel/PHP, Drupal y Odoo sobre DDEV y Docker. Incluyen herramientas de terminal modernas, configuración de Zed y Ghostty, y una configuración de Claude Code versionada y compartida con Codex.

Basados en los [dotfiles de Freek Van der Herten](https://github.com/freekmurze/dotfiles).

## Contenido

**Primeros pasos**

- [Características](#características)
- [Instalación rápida](#instalación-rápida)
- [Qué incluye](#qué-incluye)

**Referencia**

- [Cómo funciona](#cómo-funciona): [enlaces simbólicos](#enlaces-simbólicos) · [ficheros cargados por la shell](#ficheros-cargados-por-la-shell)
- [Uso diario](#uso-diario): [navegación](#navegación) · [atajos de Laravel/PHP](#atajos-de-laravelphp) · [Git](#git) · [base de datos](#base-de-datos) · [mantenimiento](#mantenimiento)
- [Gestión de versiones](#gestión-de-versiones)
- [Gestión de paquetes](#gestión-de-paquetes)

**IA**

- [Configuración de IA](#configuración-de-ia): [instalación independiente](#instalación-independiente) · [skills](#skills) · [instrucciones](#instrucciones) · [plugins](#plugins) · [agentes](#agentes) · [hooks y DDEV worktrees](#hooks-y-ddev-worktrees) · [ajustes](#ajustes-relevantes) · [compartir con Codex](#compartir-con-codex) · [añadir skills](#añadir-skills)

**Resto**

- [Personalización](#personalización) · [Tras la instalación](#tras-la-instalación) · [Utilidades](#utilidades) · [Créditos](#créditos)

---

## Características

- **Instalación con un comando**: `bin/install` prepara la máquina completa, incluido Claude Code.
- **Configuración de IA versionada**: instrucciones, skills, agentes, hooks y ajustes de Claude Code en `config/claude/`, compartidos con Codex desde la misma fuente.
- **Worktrees de Claude Code con DDEV**: un comando `ddev worktree` y un hook que convierten cada worktree en un proyecto DDEV independiente.
- **Herramientas rápidas**: fnm, zoxide, ripgrep, bat, eza, fd.

---

## Instalación rápida

```bash
git clone git@github.com:rokkay/dotfiles-macos.git ~/.dotfiles
cd ~/.dotfiles
bin/install
```

El instalador es idempotente y pide confirmación antes de empezar y antes de instalar Claude Code y Codex.

---

## Qué incluye

### Shell y prompt

- **Oh My Zsh** con el tema agnoster y los plugins `git`, `composer`, `rsync` y `macos`.
- **zsh-autosuggestions**: sugerencias basadas en el historial.
- **zoxide**: saltos entre directorios por frecuencia de uso.
- **fzf**: buscador difuso de ficheros e historial.
- **direnv**: variables de entorno por directorio.
- **Starship**: prompt alternativo con estilo agnoster, en `config/starship.toml`.

### Herramientas de terminal

- **fnm**: gestor de versiones de Node.js.
- **bat**: `cat` con resaltado de sintaxis.
- **eza**: sustituto de `ls` con iconos.
- **ripgrep**: sustituto rápido de `grep`.
- **fd**: sustituto rápido de `find`.
- **git-delta**: diffs lado a lado con números de línea.
- **jq** / **yq**: procesado de JSON y YAML.
- **gh**: CLI de GitHub.

### Desarrollo

- **PHP** y **Composer** vía Homebrew, con las extensiones imagick, memcached, xdebug y redis.
- **Node.js** LTS gestionado con fnm.
- **Laravel Valet**, **Pint**, **Envoy** y **phpunit-watcher** como paquetes globales de Composer.
- **MySQL** arrancado como servicio.
- **Zed** como editor y **Ghostty** como terminal.
- **Claude Code** y **opencode**.

### Plugins de QuickLook

Vista previa en Finder de código, Markdown, JSON, CSV, parches y archivos comprimidos.

---

## Cómo funciona

### Enlaces simbólicos

El instalador enlaza los ficheros del repositorio en su ubicación esperada, así se versiona la configuración sin moverla de sitio.

| Enlace | Apunta a | Para qué |
|--------|----------|----------|
| `~/.zshrc` | `home/.zshrc` | Configuración principal de Zsh |
| `~/.gitconfig` | `home/.gitconfig` | Git con delta como pager |
| `~/.global-gitignore` | `home/.global-gitignore` | Patrones ignorados en todos los repos |
| `~/bin/php-format` | `bin/php-format` | Formateador PHP que usa Zed |
| `~/.config/zed/settings.json` | `config/zed/settings.json` | Ajustes de Zed |
| `~/.config/ghostty/config` | `config/ghostty/config` | Ajustes de Ghostty |
| `~/.ddev/commands/host/worktree` | `config/ddev/commands/host/worktree` | Comando global `ddev worktree` |
| `~/.claude/CLAUDE.md` | `config/claude/AGENTS.md` | Instrucciones para el agente |
| `~/.claude/settings.json` | `config/claude/settings.json` | Ajustes de Claude Code |
| `~/.claude/statusline.sh` | `config/claude/statusline.sh` | Barra de estado de Claude Code |
| `~/.claude/skills` | `config/claude/skills/` | Skills de Claude Code |
| `~/.claude/agents` | `config/claude/agents/` | Subagentes de Claude Code |
| `~/.claude/hooks` | `config/claude/hooks/` | Hooks de Claude Code |
| `~/work/projects/drupal/CLAUDE.md` | `config/claude/drupal.md` | Reglas comunes a los proyectos Drupal (solo si existe el directorio) |
| `~/.codex/AGENTS.md` | `config/claude/AGENTS.md` | Las mismas instrucciones, para Codex |
| `~/.codex/skills/*` | `config/claude/skills/*` | Un enlace por skill compartida, ver `bin/link-agent-skills` |

### Ficheros cargados por la shell

`.zshrc` carga estos ficheros sin moverlos del repositorio:

- `home/.exports`: variables de entorno.
- `home/.aliases`: alias.
- `home/.functions`: funciones.

---

## Uso diario

### Navegación

```bash
z dotfiles          # Salta a un directorio usado con frecuencia
zi                  # Selector interactivo de directorios
Ctrl+R              # Búsqueda difusa en el historial
Ctrl+T              # Búsqueda difusa de ficheros
o                   # Abre el directorio actual en Finder
l / ll / lt         # Listados con eza (largo, detallado, árbol)
```

Los alias que sustituyen `ls`, `cat` y `grep` por eza, bat y ripgrep no se cargan dentro de Claude Code (`$CLAUDECODE`), porque sus comandos esperan el comportamiento POSIX.

### Atajos de Laravel/PHP

```bash
a                   # php artisan
p                   # Pest o PHPUnit, según lo que tenga el proyecto
pf <filtro>         # Igual que p, con --filter
pp                  # php artisan test --parallel
mfs                 # php artisan migrate:fresh --seed
cu / cr / ci        # composer update / require / install
cda                 # composer dump-autoload -o
scheduler           # Ejecuta schedule:run cada 60 segundos
```

### Git

```bash
commit              # git add . y commit con mensaje generado por Claude
commit "mensaje"    # git add . y commit con ese mensaje
nah                 # git reset --hard; git clean -df
uncommit            # Deshace el último commit conservando los cambios
git-prune-local     # Borra ramas locales cuyo remoto ya no existe
clone <owner/repo>  # gh repo clone
```

### Base de datos

```bash
db create <nombre>  # Crea una base de datos MySQL
db drop <nombre>    # La elimina
db refresh <nombre> # La elimina y la vuelve a crear
db list             # Lista las bases de datos
```

### IA

```bash
c                   # claude
cy                  # claude --dangerously-skip-permissions
cxy                 # codex sin aprobaciones ni sandbox
```

### Mantenimiento

```bash
bin/update          # Actualiza el repo, Homebrew, npm y Composer
```

---

## Gestión de versiones

### Node.js (fnm)

```bash
fnm install --lts     # Instala la última LTS
fnm use lts-latest    # Usa la última LTS
fnm install 22        # Instala una versión concreta
fnm list              # Versiones instaladas
```

fnm cambia de versión automáticamente al entrar en un directorio con `.nvmrc` o `.node-version`.

### PHP y Composer (Homebrew)

```bash
brew upgrade php
brew upgrade composer
```

---

## Gestión de paquetes

Todos los paquetes de Homebrew se declaran en `config/Brewfile`. Para añadir uno:

```bash
echo 'brew "neovim"' >> ~/.dotfiles/config/Brewfile
brew bundle --file=~/.dotfiles/config/Brewfile
```

**Lista completa:**

- **Base**: node, php, composer, pkg-config, wget, httpie, ncdu, hub, gh, ack, imagemagick, mysql, yarn, ghostscript, mackup
- **Terminal**: starship, zoxide, bat, eza, ripgrep, fd, fnm, fzf, direnv, jq, yq, zsh-autosuggestions
- **Desarrollo**: opencode, claude-code, zed, ghostty
- **Fuentes**: font-meslo-lg-nerd-font
- **QuickLook**: qlcolorcode, qlstephen, qlmarkdown, quicklook-json, qlprettypatch, quicklook-csv, betterzip, suspicious-package
- **Extensiones PHP** (pecl): imagick, memcached, xdebug, redis
- **npm global**: agent-browser
- **Composer global**: laravel/pint, laravel/envoy, spatie/phpunit-watcher, laravel/valet

---

## Configuración de IA

Todo lo que necesitan los agentes vive en `config/claude/`. Claude Code y Codex lo leen desde ahí, sin copias por herramienta.

```
config/claude/
├── AGENTS.md        instrucciones globales, leídas por ambos agentes
├── drupal.md        instrucciones comunes a los proyectos Drupal
├── settings.json    ajustes, permisos, hooks y plugins de Claude Code
├── statusline.sh    barra de estado
├── agents/          subagentes propios
├── hooks/           hooks de Claude Code
└── skills/          skills
```

### Instalación independiente

Para instalar solo la parte de IA, sin el resto de los dotfiles:

```bash
~/.dotfiles/bin/install-claude-code
```

Instala la CLI de Claude Code, crea los enlaces de configuración (incluido `drupal.md` si existe `~/work/projects/drupal`) y ejecuta `bin/link-agent-skills` para compartir skills con Codex.

### Skills

Todas las skills están en `config/claude/skills/` y quedan disponibles en cuanto termina el instalador.

**Código y convenciones**

| Skill | Qué hace |
|-------|----------|
| `spatie-guidelines` | Convenciones de Spatie para PHP, Laravel, JavaScript y Vue: estilo, tipos, nombres, validación, Blade, Pest y Git |
| `laravel-inertia-react-structure` | Estructura del frontend en aplicaciones Laravel con Inertia y React |
| `vercel-react-best-practices` | Rendimiento en React y Next.js según Vercel |
| `web-design-guidelines` | Revisión de UI contra las Web Interface Guidelines |

**Docker**

| Skill | Qué hace |
|-------|----------|
| `docker-project-foundations` | Dockerizar un proyecto: Dockerfile, `compose.yaml` y `.dockerignore` |
| `docker-compose-patterns` | Servicios, health checks, dependencias, volúmenes y redes en Compose |
| `docker-build-strategies` | Builds multi-stage, caché de capas, usuarios no root y tamaño de imagen |

**Revisión y auditoría**

| Skill | Qué hace |
|-------|----------|
| `review-pr` | Revisa un PR de GitHub con `gh`, comprueba CI y lo fusiona |
| `drupal-audit` | Auditoría de un portal Drupal con cuatro subagentes en paralelo: usabilidad, contenido, rendimiento y accesibilidad. Solo se invoca a mano |

**Migraciones**

| Skill | Qué hace |
|-------|----------|
| `openupgrade` | Migra un proyecto Odoo (Community) de una versión mayor a la siguiente con OpenUpgrade, con tres puntos de control |

**Utilidades**

| Skill | Qué hace |
|-------|----------|
| `grill-me` | Interroga un plan o diseño hasta resolver cada rama de decisión |
| `pdf` | Extraer texto y tablas, crear, unir y rellenar PDFs |
| `skill-creator` | Crear, mejorar y evaluar skills |
| `competitor-alternatives` | Páginas de comparativa y alternativas a competidores para SEO |

`skills/synced/` lo gestiona Claude Code (skills sincronizadas desde la cuenta de claude.ai) y no se edita a mano.

### Instrucciones

`AGENTS.md` recoge cómo quiero que trabaje el agente en cualquier proyecto:

- Respuestas críticas y breves, con ortografía española correcta y sin rayas como puntuación.
- Borradores para clientes, JIRA, correo o chat: cortos y en español.
- `spatie-guidelines` solo en proyectos Laravel, no en Drupal ni Symfony.
- agent-browser para automatizar el navegador; Chrome o Safari cuando hace falta mi sesión.
- Worktrees solo para tareas grandes.
- Commits en inglés con Conventional Commits, sin mencionar a Claude, y PRs sin sección de pruebas.

`drupal.md` se enlaza como `CLAUDE.md` en `~/work/projects/drupal/`, así que se carga en todos los proyectos que cuelgan de ahí. Cubre parches de drupal.org (usar los rerolls de los comentarios, nunca el diff vivo de un merge request), la retirada de módulos en dos despliegues y la prohibición de volcar ficheros con credenciales. Las reglas propias de cada proyecto van en su `AGENTS.md`.

### Plugins

Activados globalmente en `settings.json`:

| Plugin | Para qué |
|--------|----------|
| `superpowers` | Flujos de trabajo: brainstorming, planes, TDD, depuración sistemática, revisión |
| `agent-browser` | Automatización del navegador |
| `frontend-design` | Diseño de interfaces |
| `claude-code-setup` | Recomendaciones de hooks, skills y MCP para un proyecto |
| `php-lsp` | Intelephense como servidor de lenguaje para PHP |

Los marketplaces extra (`impeccable`, `agent-browser`) se declaran en `extraKnownMarketplaces`.

### Agentes

Los subagentes propios están en `config/claude/agents/`.

- `laravel-feature-builder`: implementa funcionalidades completas en Laravel (modelos, controladores, migraciones, vistas y tests).

### Hooks y DDEV worktrees

Claude Code crea sus worktrees en `.claude/worktrees/<nombre>`. En un proyecto DDEV eso no basta: el worktree hereda el mismo `name` de `.ddev/config.yaml` que el proyecto principal y cualquier comando `ddev` choca con él.

`ddev worktree` (en `config/ddev/commands/host/worktree`) lo resuelve:

```bash
ddev worktree up [nombre]     # Asigna nombre propio, copia .env, arranca, composer install y clona BD y ficheros
ddev worktree down [nombre]   # Borra contenedores y BD del worktree (el worktree sigue en disco)
ddev worktree list            # Lista los worktrees y su estado
```

`up` admite `--no-db`, `--no-files`, `--no-composer` y `--no-mutagen-fix`. Desde dentro de un worktree el nombre es opcional.

El hook `hooks/ddev-worktree-guard.sh` cierra el círculo:

- **PreToolUse (Bash)**: bloquea comandos `ddev` en un worktree que aún no se ha aprovisionado y le dice al agente que ejecute `ddev worktree up`.
- **PostToolUse (EnterWorktree)**: avisa al agente de que el proyecto usa DDEV en cuanto entra en un worktree.

### Ajustes relevantes

| Ajuste | Por qué |
|--------|---------|
| `defaultMode: auto` | Un clasificador aprueba las acciones en lugar de preguntar en cada paso |
| `permissions.allow` | Herramientas habituales (git, gh, composer, artisan, npm, ddev, docker...) sin confirmación |
| `permissions.ask` | Pide confirmación antes de leer `~/.ssh`, credenciales y ficheros `.env` |
| `autoMode` | Contexto de Solucionex para el clasificador: DDEV y drush son rutinarios; despliegues y escrituras en hosts `prod` piden confirmación |
| `model` / `effortLevel` | Opus con contexto de 1M y esfuerzo alto |
| `alwaysThinkingEnabled` | Razonamiento extendido activado por defecto |
| `attribution` | Vacío: ni commits ni PRs llevan atribución a Claude |
| `pluginConfigs` (`instructionFiles`) | `claude-md-and-agents-md`: carga `CLAUDE.md` y `AGENTS.md` juntos. Sin esto, el `CLAUDE.md` de `~/work/projects/drupal/` haría que Claude ignorase el `AGENTS.md` de cada proyecto |
| `disableClaudeAiConnectors` | Deja los conectores de claude.ai fuera de la terminal |
| `cleanupPeriodDays` | Conserva las transcripciones un año |
| `statusLine` | Muestra repo, rama y porcentaje de contexto usado, en verde, amarillo o rojo |
| `tui: fullscreen` | Interfaz a pantalla completa |
| `preferredNotifChannel` | Notificaciones a través de Ghostty |

### Compartir con Codex

Claude Code (desde v2.1.277) lee `AGENTS.md` de forma nativa, pero solo como instrucciones de proyecto. Las instrucciones globales de usuario siguen siendo `~/.claude/CLAUDE.md`, así que el mismo fichero se enlaza como `~/.claude/CLAUDE.md` y como `~/.codex/AGENTS.md`.

```bash
bin/link-agent-skills
```

El script enlaza en `~/.codex/skills` las skills que funcionan en cualquier agente (`grill-me`, `review-pr`, `spatie-guidelines`) y la skill `agent-browser` del plugin de Claude. Respeta las skills propias de Codex (`.system`, `codex-primary-runtime`). Para compartir otra skill, añádela a la lista `SHARED` del script.

### Añadir skills

```bash
cd ~/.dotfiles
npx skills add <owner/repo>

# npx skills instala en ~/.agents/skills y deja un enlace relativo en
# ~/.claude/skills que, dentro del repo, queda roto. Sustitúyelo por una copia:
rm config/claude/skills/<nombre>
cp -R ~/.agents/skills/<nombre> config/claude/skills/

git add config/claude/skills/
git commit -m "feat(claude): add <nombre> skill"
```

Dos reglas que deciden si una skill se usa o no:

1. **El nombre y la descripción lo deciden todo.** Escribe la descripción con las frases que realmente escribirías al pedir la tarea.
2. **Cuerpo corto, detalle en `references/`.** El cuerpo se queda en contexto toda la sesión una vez cargado; las referencias solo se cargan cuando hacen falta.

Más skills en [skills.sh](https://skills.sh).

---

## Personalización

### Alias y funciones personales

Para configuración que no quieres versionar:

```bash
mkdir -p ~/.dotfiles-custom/shell
nano ~/.dotfiles-custom/shell/.aliases
```

`.zshrc` carga automáticamente `.exports`, `.aliases`, `.functions` y `.zshrc` de ese directorio si existen.

### Variables por proyecto

```bash
cd mi-proyecto
echo 'export DEBUG=true' > .envrc
direnv allow
```

Las variables se cargan al entrar en el directorio y se descargan al salir.

---

## Tras la instalación

1. **Restaurar ajustes** (opcional): `mackup restore` si tienes copia.
2. **Reiniciar la terminal** o ejecutar `exec zsh`.

---

## Utilidades

Scripts en `bin/`:

- **install**: instalación completa (idempotente, se puede volver a ejecutar).
- **install-claude-code**: instalación independiente de Claude Code y su configuración.
- **link-agent-skills**: enlaza las skills compartidas y `AGENTS.md` en Codex.
- **update**: actualiza el repo, Homebrew, npm y Composer.
- **php-format**: formateador para Zed. Usa Pint o PHP CS Fixer del proyecto si existen y, si no, Pint global.

---

## Créditos

Basado en los [dotfiles de Freek Van der Herten](https://github.com/freekmurze/dotfiles).
