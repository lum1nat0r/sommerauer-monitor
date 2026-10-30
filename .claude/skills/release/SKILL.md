---
name: release
description: Release-Prozess für Sommerauer Monitor von Versionsbump über Prüfungen, Tag vX.Y.Z und Container-Workflow bis GitHub-Release und Nachprüfung. Nutzen bei "release", "Version veröffentlichen", "Tag setzen", "vX.Y.Z", "GitHub-Release erstellen".
---

# Release Sommerauer Monitor

Dieser Skill beschreibt den vollständigen Release-Weg. Er ist eine Arbeitsanleitung,
kein Freibrief: **Tags, Pushes und GitHub-Releases sind nach außen wirksam.**
Vor jedem dieser Schritte explizite Freigabe des Betreibers einholen (AGENTS.md:
"Tags/Releases erstellen" ist ohne Freigabe nicht erlaubt). Der Betreiber hat die
Veröffentlichung in `docs/ENTSCHEIDUNGEN.md` an eine Lizenz-/Abnahmefreigabe gebunden.

Gegeben sei die Zielversion `X.Y.Z` (ohne `v`). Git-Tag ist `vX.Y.Z`, Image-Tag ist `X.Y.Z`.

## 0. Vorbedingungen prüfen (nur lesend)

```bash
git status --short                       # muss leer sein, außer bewusst vorbereiteten Release-Dateien
git fetch origin
git branch --show-current                # Release-Arbeit auf release/X.Y.Z, Tag später nur von main
gh issue view 13 --json state --jq .state   # muss CLOSED sein (Release-Job-Voraussetzung)
test -s LICENSE && echo "LICENSE ok"
git tag --list "vX.Y.Z"                  # muss leer sein
git ls-remote --tags origin "vX.Y.Z"     # muss leer sein
```

Stopp, wenn ein Punkt nicht erfüllt ist. Ein bereits existierender Tag wird **nicht**
verschoben oder überschrieben.

## 1. Versionsbump (Branch `release/X.Y.Z`)

Alle Stellen müssen dieselbe Version tragen. Der Release-Job prüft nur
`pyproject.toml`, der Rest ist sonst inkonsistent:

| Datei | Stelle |
|---|---|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `uv.lock` | Eintrag des Projekts (`version = "X.Y.Z"`) |
| `package.json` | `"version"` |
| `package-lock.json` | zwei `"version"`-Einträge oben |
| `backend/main.py` | `FastAPI(..., version="X.Y.Z")` |
| `Dockerfile` | `ARG APP_VERSION=X.Y.Z` |
| `compose.yaml` | `APP_VERSION:-X.Y.Z` (Build-Arg und Image) |
| `compose.unraid.yaml` | Image-Default und Kommentar zu Release |
| `.env.example` | `APP_VERSION=X.Y.Z` |
| `unraid-template.xml` | `<Repository>…:X.Y.Z</Repository>` |
| `README.md`, `docs/UNRAID.md`, `NEXT_STEPS.md` | Versions- und Tagangaben |

Kontrolle, dass keine alte Version übrig ist:

```bash
grep -rn "OLD_VERSION" --exclude-dir=node_modules --exclude-dir=.git .
```

`reports/RESULTS.md` um die Ergebnisse dieses Releases ergänzen. Simulator- und
Live-Ergebnisse getrennt halten; nur bereinigte Zusammenfassungen öffentlich.

## 2. Lokale Verifikation (Offline, synthetisch)

```bash
uv sync --locked
uv run ruff check .
uv run pytest
npm ci
npm run build
bash scripts/smoke_image.sh     # braucht Docker; sonst als nicht ausgeführt dokumentieren
```

Der Workflow führt dieselben Schritte erneut aus. Keine Live-Tests am Gerät, keine
Modbus-Zugriffe; CI und Release sind rein offline.

## 3. Commit und PR

- Commit nur auf dem Release-Branch, nur Release-bezogene Dateien stagen.
- Commit-Nachricht kurz: `Release vX.Y.Z: <Kurzbeschreibung>`.
- Push des Branches, PR nach `main` mit `Closes`-Verweis, falls ein Issue betroffen ist.
- PR **nicht selbst mergen**; das macht der Betreiber.
- PR-Checks (Container-Image-Build ohne Push) abwarten. Nur bei grünen Checks weiter.

## 4. Tag setzen (nur nach Freigabe, nur von `main`)

Voraussetzung: PR ist gemergt. Der Release-Job verlangt, dass der Tag-Commit ein
Vorfahre von `origin/main` ist.

```bash
git checkout main && git pull --ff-only origin main
git tag -a vX.Y.Z -m "Release vX.Y.Z" <merge-commit-sha>
git push origin vX.Y.Z
```

Annotierter Tag (`-a`), wie bei den bisherigen Releases. Kein `latest`, kein `main`-Tag.
Tag nicht verschieben. Falls der Tag falsch ist: Löschen eines gepushten Tags ist
destruktiv und nur nach eigener Freigabe zulässig.

## 5. Container-Workflow beobachten

```bash
gh run list --workflow image.yml --limit 3
gh run watch <run-id> --exit-status
```

Der Release-Job prüft Tag-Format, `LICENSE`, Version in `pyproject.toml`,
Commit-Zugehörigkeit zu `main`, geschlossenes Issue #13, Tests, Build, Container-Smoke-Test
und pusht `ghcr.io/lum1nat0r/sommerauer-monitor:X.Y.Z`. Bei Fehler: Logs lesen,
Ursache dokumentieren, nichts ohne Freigabe neu taggen.

## 6. GitHub-Release erstellen (nur nach Freigabe)

Der Workflow erstellt **kein** GitHub-Release, nur das Image. Das Release ist ein
eigener Schritt (so wurde v0.3.1 angelegt):

```bash
gh release create vX.Y.Z --verify-tag --title "vX.Y.Z" --notes-file <notes.md>
```

Release-Notes nur aus geprüften Fakten: Änderungen, Image-Referenz
`ghcr.io/lum1nat0r/sommerauer-monitor:X.Y.Z`, Release-Commit, Links zu den
Workflow-Läufen, tatsächlich ausgeführte Prüfungen, Grenzen. Keine Messwerte oder
Geräteergebnisse erfinden. Die Notes-Datei gehört in den Scratchpad, nicht ins Repo.

Ein Release mit `--draft` anlegen, wenn der Betreiber vorher prüfen will.

## 7. Nachprüfung

```bash
gh release view vX.Y.Z --json tagName,isDraft,isPrerelease,targetCommitish
gh api /repos/lum1nat0r/sommerauer-monitor/git/refs/tags/vX.Y.Z
docker buildx imagetools inspect ghcr.io/lum1nat0r/sommerauer-monitor:X.Y.Z   # nur wenn GHCR-Paket öffentlich
```

- Anonymer Pull ist erst belegt, wenn das GHCR-Paket öffentlich ist. Bis dahin
  Paket als privat dokumentieren. Sichtbarkeit nur nach Freigabe ändern.
- Ergebnis ehrlich berichten: Was ist geprüft, was nicht. Das Betreiber-Deployment
  bleibt manuell mit gesichertem `/data`.

## Abbruch- und Rollback-Wege

- Vor Tag-Push: Branch-Änderungen per neuem Commit korrigieren, nichts löschen.
- Nach Tag-Push, Workflow fehlgeschlagen: Ursache beheben, neuen Release-Stand als
  nächste Version planen, statt den Tag zu verschieben.
- Nach Image-Push: Image nicht still überschreiben; neue Version veröffentlichen.
