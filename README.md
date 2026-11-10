# FontLicenseClassifier

Dépôt GitHub : **https://github.com/Les-Doubles-A/FontLicenseClassifier**

Application de bureau (Python 3.12) qui analyse des milliers de fichiers de
polices `.ttf`/`.otf` et tente de retrouver automatiquement leur licence
(OFL, Apache, GPL, MIT, Domaine public, Usage commercial, Usage personnel,
Shareware, ou `Unknown` si la confiance est insuffisante).

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

Python 3.12 recommande (fontTools, CustomTkinter et aiohttp le supportent
pleinement). Testable des Python 3.10 si besoin.

## Ce que l'application fait reellement (et ses limites assumees)

Le cahier des charges demandait une recherche automatique sur Google,
GitHub, Font Squirrel, DaFont, etc. Il faut etre transparent sur ce qui est
techniquement fiable :

- **Aucun moteur de recherche generaliste (Google en tete) n'offre d'API de
  recherche gratuite et stable.** Scraper directement les pages de resultats
  Google viole ses conditions d'utilisation et se fait bloquer en quelques
  requetes a peine — ce n'est donc **pas** implemente ici, contrairement a
  ce qu'un prototype "jouet" pourrait laisser croire.
- A la place, l'application combine **4 sources complementaires**, de la
  plus fiable a la plus incertaine :

  | # | Source | Cout reseau | Fiabilite |
  |---|--------|-------------|-----------|
  | 1 | Metadonnees embarquees dans le fichier (`fontTools`, table `name` : `licenseDescription`, `copyright`, `trademark`, `licenseURL`...) | Aucun (local) | Tres elevee — c'est une declaration de la fonderie elle-meme |
  | 2 | Base locale de polices connues (`data/known_licenses.json`, enrichie automatiquement par le cache SQLite) | Aucun (local) | Elevee |
  | 3 | Depot officiel `google/fonts` sur GitHub (API GitHub `contents`, dossiers `ofl/`, `apache/`, `ufl/`) | Faible (1 appel API) | Elevee |
  | 4 | Recherche web ciblee (`site:` sur Google Fonts, GitHub, FontSquirrel, DaFont, FontSpace, Adobe Fonts, Fontesk, 1001 Fonts, Open Foundry, The League of Moveable Type, via le point d'acces HTML public de DuckDuckGo) | Variable | **Best-effort** : les extraits de resultats sont des indices, pas une preuve juridique |

  Les sources 3 et 4 ne sont interrogees **que si** les sources locales (1
  et 2) n'ont pas deja donne un resultat suffisamment confiant — ce qui
  reduit enormement le nombre de requetes reseau necessaires sur une
  bibliotheque de 10 000+ polices, et permet un fonctionnement 100%
  hors-ligne si l'utilisateur desactive la recherche web dans l'interface.
- **Aucune licence n'est jamais affirmee avec un score de confiance faible** :
  en dessous du seuil configurable (`CONFIDENCE_THRESHOLD`, 55% par defaut
  dans `app/config.py`), le resultat est `Unknown`.
- Ceci reste un outil d'aide a la decision, pas une source d'autorite
  juridique : pour un usage commercial sensible, verifiez toujours la
  licence exacte aupres de la fonderie.

## Architecture

```
FontLicenseClassifier/
├── main.py                      # point d'entree
├── app/
│   ├── config.py                 # constantes, seuils, chemins
│   └── pipeline.py                # orchestration scan -> cache -> classification -> rapports
├── scanner/
│   └── font_scanner.py            # extraction fontTools (Family, Designer, Version, Copyright...)
├── license_detector/
│   ├── models.py                   # Evidence / ClassificationResult
│   ├── patterns.py                 # motifs regex par categorie de licence
│   ├── embedded_detector.py         # source 1 : metadonnees embarquees
│   ├── known_fonts_db.py            # source 2 : base locale + cache SQLite
│   ├── google_fonts_source.py       # source 3 : depot GitHub google/fonts
│   ├── web_search_source.py         # source 4 : recherche web multi-sites (best-effort)
│   └── classifier.py                # agregation des indices + score de confiance
├── database/
│   └── db.py                        # cache SQLite (point 7) + reprise apres interruption (point 9)
├── reports/
│   └── report_generator.py           # rapport.csv / rapport.xlsx / rapport.html (point 6)
├── integrations/
│   └── fontcheck_bridge.py            # export vers licenses.json de FontCheck (point 5)
├── gui/
│   └── main_window.py                 # interface CustomTkinter (point 1)
├── utils/
│   └── logging_config.py               # journalisation complete (point 10)
├── data/
│   └── known_licenses.json              # base de polices connues (seed extensible)
└── tests/                                # tests unitaires (pytest)
```

## Integration avec FontCheck

L'outil `FontCheck` fourni (navigateur de polices installees, Tkinter)
stocke un statut de licence par famille dans
`%APPDATA%/FontCheck/licenses.json` (`"personnel"`, `"commercial"`,
`"libre"`, ou absent = `"inconnu"`).

A la fin de chaque lot d'analyse, `integrations/fontcheck_bridge.py`
fusionne les resultats a confiance suffisante (>= 60%) dans ce meme
fichier, en respectant deux regles :

1. **Une famille deja renseignee manuellement dans FontCheck n'est jamais
   ecrasee** — l'utilisateur garde le dernier mot.
2. Une police classee `Unknown`, ou dont la confiance est trop faible,
   n'est pas ecrite : elle reste `inconnu` dans FontCheck.

Ouvrir FontCheck apres une analyse suffit donc a voir apparaitre les badges
`PERS` / `COMM` / `OFL` deja renseignes.

## Performances (point 9 du cahier des charges)

- Le **scan disque** (`scanner/font_scanner.py`) est parallelise par un
  `ThreadPoolExecutor` (I/O disque, `MAX_CONCURRENT_FONT_PARSES` threads).
- La **classification reseau** (`license_detector/`) est asynchrone
  (`asyncio` + `aiohttp`), avec un `asyncio.Semaphore` limitant le nombre
  de requetes simultanees (`MAX_CONCURRENT_HTTP_REQUESTS`) et un delai
  minimal entre deux requetes (`HTTP_MIN_DELAY_SECONDS`) pour rester
  respectueux des services distants.
- Le **cache SQLite** (`database/db.py`) evite de refaire une recherche
  deja effectuee (par empreinte SHA-256 du fichier, insensible au
  renommage) et persiste un etat de reprise (`resume_state.json`) : si
  l'application est fermee au milieu d'un lot de 10 000 polices, la
  relancer sur le meme dossier reprend la ou elle s'etait arretee.

## Journalisation (point 10)

Chaque execution ecrit un fichier log horodate dans
`%APPDATA%/FontLicenseClassifier/logs/`, contenant : erreurs de lecture,
temps d'analyse par police, requetes de recherche effectuees, licence
retenue et raison du classement.

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

Les tests couvrent la reconnaissance de motifs, la detection par
metadonnees embarquees, la base de polices connues, le moteur de decision
du classifieur, l'extraction fontTools (sur une police generee a la volee)
et la generation des rapports. Ils ne necessitent aucune connexion
internet.

## Compiler en .exe (Windows)

Un fichier `FontLicenseClassifier.spec` et un script `build.ps1` sont
fournis pour generer un executable autonome avec PyInstaller.

```powershell
.\build.ps1
```

L'executable est cree dans `dist\FontLicenseClassifier.exe`. Voir le
detail des etapes et des pieges frequents plus bas dans la conversation.

## Personnaliser le classement

- `app/config.py` : seuil de confiance, nombre de requetes simultanees,
  activation/desactivation de la recherche web.
- `license_detector/patterns.py` : ajouter des motifs de reconnaissance
  pour une categorie de licence.
- `data/known_licenses.json` : ajouter des familles de polices connues
  (le cache SQLite s'enrichit aussi automatiquement au fil des analyses a
  haute confiance).

<!-- installeur-release -->
## Installation

Téléchargez **`FontLicenseClassifier-Setup-1.0.0.exe`** depuis la [dernière release](https://github.com/Les-Doubles-A/FontLicenseClassifier/releases/latest), puis lancez-le.

L'installation se fait pour l'utilisateur courant, sans droits administrateur (par défaut dans `%LOCALAPPDATA%\Programs\FontLicenseClassifier`), avec un raccourci dans le menu Démarrer et une désinstallation depuis les Paramètres Windows.

L'installeur n'est pas signé : si Windows SmartScreen l'affiche, cliquez sur « Informations complémentaires » puis « Exécuter quand même ».

### Recréer l'installeur

Compiler l'application (`build.ps1 (PyInstaller)`), puis lancer [Inno Setup 6](https://jrsoftware.org/isinfo.php) : `iscc installer\FontLicenseClassifier.iss`. Le setup est créé dans `installer\Output\`.
