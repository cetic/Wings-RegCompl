# CAHIER DES CHARGES (PRD) — v2
## SYSTÈME : PIPELINE DE PARSING AGENTIQUE DÉTERMINISTE VIA GOOGLE ADK
## CIBLE MATÉRIELLE : APPLE SILICON MAC M1 PRO (32 GO DE MÉMOIRE UNIFIÉE)

> **Note de version** : ce document reprend intégralement la v1, corrige plusieurs
> incohérences techniques (vérifiées sur la documentation et le code source
> actuels de `google-adk` et `litellm`, juillet 2026), et complète les zones
> sous-spécifiées (gestion d'erreurs, cas limites, observabilité). Les
> changements notables par rapport à la v1 sont signalés par 🔧.

---

## 0. RÉSUMÉ DES CORRECTIONS APPORTÉES

| # | Problème identifié dans la v1 | Correction |
|---|---|---|
| 1 | `[I\|V\|X\|L\|C]+` — le `\|` à l'intérieur d'une classe de caractères est traité littéralement, pas comme un OU logique | `[IVXLC]+` |
| 2 | `[i\|v\|x]+` — même bug | `[ivx]+` |
| 3 | Sandbox `network_disabled: True` **et** `pip install pypdf --quiet` dans le même conteneur — contradiction : sans réseau, `pip install` échoue | Image Docker pré-construite contenant déjà `pypdf` (build une seule fois, en amont, pas à chaque exécution) |
| 4 | Nom de fichier incohérent : cache = `parser_[uid].py`, exécution = `parser_reglementaire.py` | Un seul nom, dynamique, partout : `parser_{uid}.py` |
| 5 | Troncature du SHA-256 à « 10 caractères » non spécifiée | Prendre les 10 premiers caractères hexadécimaux du digest complet, documenté explicitement |
| 6 | `ContainerCodeExecutor` présenté comme un simple exécuteur de script batch | C'est un composant conçu pour exécuter du code **émis par le LLM en cours de conversation** ; pour une phase déterministe (script déjà validé, aucune génération LLM), il vaut mieux l'invoquer directement depuis l'orchestrateur host, sans l'envelopper dans un `LlmAgent` |
| 7 | Connexion à Ollama non spécifiée au niveau ADK | ADK ne parle pas nativement à Ollama : il faut le connecteur `LiteLlm` (`google.adk.models.lite_llm.LiteLlm`) avec le préfixe `ollama_chat/` |
| 8 | `temperature=0.0` et `num_ctx=16384` présentés comme des paramètres natifs de `LlmAgent` | Ce sont des paramètres du modèle sous-jacent : à passer via le constructeur `LiteLlm(...)` / les options Ollama, pas via `generate_content_config` (un bug connu d'ADK fait que `generate_content_config` est parfois ignoré avec les modèles `LiteLlm`) |
| 9 | Machine à états à deux états qui ne change jamais réellement de comportement | Soit on lui donne un rôle fonctionnel réel, soit on la simplifie honnêtement en pipeline linéaire |
| 10 | Aucune gestion d'échec de validation du schéma Pydantic | ADK ne réessaie pas automatiquement en cas d'échec — ajout d'une politique de retry explicite |
| 11 | Aucune gestion des PDF scannés (sans couche texte) | `pypdf.extract_text()` renvoie une chaîne vide sur un PDF scanné — ajout d'une détection + message d'erreur explicite (l'OCR est explicitement hors-scope v1) |
| 12 | Profondeur de hiérarchie non bornée par rapport aux préfixes Markdown disponibles | Limite explicite et comportement de repli défini |
| 13 | `python:3.11-alpine` | Conservé par défaut (léger, `pypdf` est pur Python) mais avec note sur les limites si des dépendances compilées sont ajoutées plus tard |

---

## 1. ARCHITECTURE GÉNÉRALE

```
[PDF cible]
     │
     ▼
┌─────────────────────────────────────────────┐
│ HOST RUNTIME : extraction des pages 1 à 15   │
│ via pypdf (échantillon représentatif)        │
└───────────────────┬───────────────────────────┘
                     │ (texte brut)
                     ▼
┌─────────────────────────────────────────────┐
│ AGENT 1 : LlmAgent (StructureAnalyzer)       │
│ Modèle : Ollama qwen2.5-coder:14b-instruct-  │
│          q4_K_M via LiteLlm("ollama_chat/…") │
│ temperature=0.0 (au niveau LiteLlm)          │
│ output_schema=UniversalStructureSchema       │
└───────────────────┬───────────────────────────┘
                     │ (JSON validé Pydantic)
                     ▼
┌─────────────────────────────────────────────┐
│ COUCHE INTERMÉDIAIRE : normalisation & cache │
│ 1. Tri hierarchy par level_index             │
│ 2. Tri noise_patterns alphabétique           │
│ 3. Hash préliminaire (SHA-256)               │
│ 4. Fusion des overrides ./custom_configs/    │
│ 5. Hash final → uid (10 hex, sur JSON fusionné)│
└──────┬───────────────────────────┬─────────────┘
       │ cache MISS 🔍             │ cache HIT ⚡
       ▼                           ▼
┌─────────────────────┐   ┌──────────────────────────┐
│ AGENT 2 : LlmAgent   │   │ Chargement direct de     │
│ (ParserEngineer)     │   │ ./cached_parsers/         │
│ → parser_{uid}.py    │   │ parser_{uid}.py           │
└──────────┬────────────┘   └──────────────┬─────────────┘
           └──────────────┬─────────────────┘
                           ▼
┌─────────────────────────────────────────────┐
│ EXÉCUTION SANDBOX (appelée directement par   │
│ l'orchestrateur host, PAS via un LlmAgent)   │
│ ContainerCodeExecutor / docker-py            │
│ image pré-construite, network désactivé      │
└───────────────────┬───────────────────────────┘
                     ▼
              [Fichier .md final]
```

---

## 2. STACK TECHNIQUE LOCALE

* **Orchestration** : Google Agent Development Kit (`google-adk`). 🔧 Épingler
  la version (`google-adk==X.Y.Z`) dans `requirements.txt` : les noms de
  classes et le comportement de `output_schema` évoluent vite d'une version à
  l'autre (le comportement avec `tools` a par exemple changé entre les
  versions récentes).
* **Validation des données** : `pydantic` (v2.0+).
* **Inférence locale** : serveur **Ollama**, modèle
  `qwen2.5-coder:14b-instruct-q4_K_M` (nom cohérent partout dans ce document —
  la v1 l'abrégeait parfois en `qwen2.5-coder:14b`, ce qui pointe vers un tag
  différent sur le registre Ollama).
  * Occupation mémoire estimée : ~9 Go, laissant ~23 Go pour le buffering de
    fichiers volumineux et le daemon Docker.
  * 🔧 **Connexion via ADK** : ADK ne pilote pas Ollama nativement. Il faut
    passer par le connecteur `LiteLlm` :
    ```python
    from google.adk.agents import LlmAgent
    from google.adk.models.lite_llm import LiteLlm

    structure_model = LiteLlm(
        model="ollama_chat/qwen2.5-coder:14b-instruct-q4_K_M",  # préfixe ollama_chat, pas ollama
        temperature=0.0,
    )
    ```
    Variable d'environnement requise : `OLLAMA_API_BASE=http://localhost:11434`.
    Le paramètre `num_ctx` est une option Ollama, pas un champ natif d'ADK ; il
    se transmet via les paramètres additionnels du client Ollama/LiteLLM (à
    vérifier contre la version installée de `litellm`), pas comme argument de
    `LlmAgent`.
  * 🔧 Ne pas compter sur `generate_content_config=types.GenerateContentConfig(temperature=0.0)`
    au niveau de `LlmAgent` : il existe des rapports de bugs où ce réglage est
    ignoré avec des modèles `LiteLlm`. Préférer `LiteLlm(model=..., temperature=0.0)`
    directement.
* **Dépendance host** : `pypdf` pour l'échantillonnage.
* **Isolation** : Docker Desktop pour Mac, image `python:3.11-alpine`
  (rapide, légère ; `pypdf` étant pur Python, alpine ne pose pas de problème
  de compilation — si des dépendances compilées sont ajoutées plus tard,
  bascule recommandée vers `python:3.11-slim` pour éviter les soucis de
  wheels manquants sous musl).

---

## 3. CONTRATS DE DONNÉES PYDANTIC

```python
from pydantic import BaseModel, Field

class HeadingLevel(BaseModel):
    level_index: int = Field(
        description="Profondeur numérique stricte du niveau de titre (0 = racine, ex. Annexe/Chapitre)."
    )
    markdown_prefix: str = Field(
        description="Syntaxe Markdown exacte à préfixer. Jetons autorisés : '# ', '## ', '### ', '#### ', ' - ', '   * '."
    )
    regex_pattern: str = Field(
        description="Expression régulière Python valide, capturant le marqueur de titre en tout début de ligne."
    )

class UniversalStructureSchema(BaseModel):
    document_type: str = Field(
        description="Catégorisation générique reflétant la famille légale du gabarit de texte."
    )
    hierarchy: list[HeadingLevel] = Field(
        description="Hiérarchie structurelle complète découverte à l'analyse."
    )
    noise_patterns: list[str] = Field(
        description="Inventaire de regex ciblant artefacts de mise en page, en-têtes répétés, pagination, tampons de métadonnées."
    )
```

🔧 **Limite de profondeur** : `markdown_prefix` n'offre que 6 jetons
(`# … #### `, ` - `, `   * `). Si `hierarchy` contient plus de 6 niveaux
distincts, les niveaux au-delà du 6e doivent retomber sur `   * ` (dernier
niveau de liste) plutôt que de planter — à documenter explicitement dans le
prompt de l'Agent 1 et à valider par un test unitaire sur le script généré.

### Exemple de résultat cible (Part-IS) — corrigé

```json
{
  "document_type": "EU_Amending_Regulation_With_Annexes",
  "hierarchy": [
    {"level_index": 0, "markdown_prefix": "# ", "regex_pattern": "^ANNEX\\s+[IVXLC]+"},
    {"level_index": 1, "markdown_prefix": "## ", "regex_pattern": "^(?:IS\\.[A-Z]+\\.\\d+|\\d+[A-Z]+\\.[A-Z]\\.\\d+)"},
    {"level_index": 2, "markdown_prefix": "### ", "regex_pattern": "^\\([a-z]\\)\\s+"},
    {"level_index": 3, "markdown_prefix": "#### ", "regex_pattern": "^\\(\\d+\\)\\s+"},
    {"level_index": 4, "markdown_prefix": " - ", "regex_pattern": "^\\([ivx]+\\)\\s+"}
  ],
  "noise_patterns": [
    "\\d+\\.\\d+\\.\\d+\\s+Official Journal of the European Union.*",
    "L\\s+\\d+/\\d+\\s+Official Journal.*"
  ]
}
```

(`[IVXLC]+` et `[ivx]+` remplacent les classes de caractères invalides de la
v1, qui contenaient des `|` littéraux au lieu d'une alternance de caractères.)

---

## 4. PHASES D'IMPLÉMENTATION

### PHASE 1 — Découverte de structure (`StructureAnalyzer`)

1. Lecture des pages 1 à 15 via `pypdf` côté host.
   🔧 **Cas limite** : si `page.extract_text()` renvoie une chaîne vide pour
   la totalité des 15 pages, le PDF est probablement scanné (pas de couche
   texte). Le pipeline doit s'arrêter avec un message explicite plutôt que de
   transmettre un échantillon vide au LLM. L'OCR est explicitement **hors
   scope v1** — à noter comme extension future si nécessaire.
2. `LlmAgent` configuré avec le modèle `LiteLlm` décrit en section 2,
   `output_schema=UniversalStructureSchema`.
   🔧 Même avec `output_schema`, la documentation ADK recommande de rappeler
   le format attendu dans l'`instruction` du prompt — `output_schema` biaise
   fortement le modèle vers du JSON valide mais ne le garantit pas à 100 %.
3. **Gestion d'échec** 🔧 : ADK lève une `pydantic.ValidationError` si la
   sortie ne respecte pas le schéma, sans retry automatique. Envelopper
   l'appel dans une politique de retry explicite (ex. 3 tentatives avec
   reformulation du prompt), puis échec propre avec log détaillé si tout
   échoue.
4. **Contrainte de prompt** : le LLM ne doit ni commenter ni expliquer, il
   ne fait que remplir les champs Pydantic.

### PHASE 2 — Cache, déterminisme, correction humaine

1. **Normalisation** : tri ascendant de `hierarchy` par `level_index`, tri
   alphabétique de `noise_patterns`.
2. **Hash préliminaire** : sérialisation JSON minifiée triée → SHA-256
   complet (appelé `prelim_hash` ci-après, pour le distinguer du hash final).
3. **Interception humaine** : recherche de `./custom_configs/config_[prelim_hash].json` ;
   si trouvé, fusion/override des tableaux en mémoire.
4. **Hash final** : re-sérialisation de l'objet fusionné → SHA-256 complet →
   `uid` = **les 10 premiers caractères hexadécimaux** de ce digest. 🔧 À
   40 bits d'entropie, le risque de collision reste négligeable pour un
   volume de quelques milliers de gabarits ; si le volume de documents
   distincts devient très important, passer à 12–16 caractères.
5. **Routage cache** :
   * `./cached_parsers/parser_{uid}.py` présent → `[CACHE HIT ⚡]`, saut
     direct en Phase 4.
   * Absent → `[CACHE MISS 🔍]`, Phase 3.

### PHASE 3 — Compilation logicielle (`ParserEngineer`)

1. `LlmAgent` de synthèse logicielle, ciblant le schéma de structure.
2. Sortie : script Python autonome, orienté objet, implémentant le patron
   ci-dessous.

```python
# PATRON ALGORITHMIQUE ABSTRAIT DU PARSEUR GÉNÉRÉ
import re
from enum import Enum, auto
from pypdf import PdfReader

class ParserState(Enum):
    LOOKING_FOR_CONTENT = auto()
    READING_BODY = auto()

class DocumentStateMachineParser:
    def __init__(self, hierarchy, noise_patterns):
        self.hierarchy = hierarchy
        self.noise_patterns = noise_patterns
        self.current_state = ParserState.LOOKING_FOR_CONTENT

    def run_pipeline(self, pdf_path, output_md_path):
        reader = PdfReader(pdf_path)
        markdown_buffer = []

        for page in reader.pages:
            raw_text = page.extract_text()
            if not raw_text:
                continue

            for line in raw_text.splitlines():
                cleaned_line = line.strip()

                for noise_regex in self.noise_patterns:
                    cleaned_line = re.sub(noise_regex, "", cleaned_line).strip()

                if not cleaned_line:
                    continue

                cleaned_line = cleaned_line.lstrip("'").rstrip("'").rstrip(";")

                matched_header = False
                for level in self.hierarchy:
                    if re.match(level["regex_pattern"], cleaned_line):
                        markdown_buffer.append(f"\n{level['markdown_prefix']}{cleaned_line}\n")
                        self.current_state = ParserState.LOOKING_FOR_CONTENT
                        matched_header = True
                        break

                if not matched_header:
                    markdown_buffer.append(f"{cleaned_line} ")
                    self.current_state = ParserState.READING_BODY

        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(markdown_buffer))
```

🔧 **Remarque honnête sur la machine à états** : dans le patron ci-dessus,
`ParserState` change de valeur mais aucune branche de code ne se comporte
différemment selon l'état courant — ce n'est donc pas fonctionnellement une
machine à états, juste un pipeline linéaire ligne par ligne avec une étiquette
décorative. Deux options :
* **Simplifier honnêtement** : retirer `ParserState` si aucun comportement
  différencié n'est prévu.
* **Lui donner un rôle réel** : par exemple, en `READING_BODY`, fusionner la
  ligne courante avec la précédente sans retour à la ligne (reconstruction de
  paragraphes coupés par la pagination PDF) — ce qui est justement un problème
  réel et non résolu par le patron actuel (chaque ligne de corps de texte
  devient un fragment séparé par un espace, sans réel merge de paragraphe).

### PHASE 4 — Exécution sandbox (`ContainerCodeExecutor`)

🔧 **Point d'architecture important** : `ContainerCodeExecutor` (et les
autres exécuteurs de code d'ADK) sont conçus pour exécuter du code **émis en
direct par un `LlmAgent`** au fil de la conversation (le flux ADK détecte un
bloc de code dans la réponse du modèle et l'exécute automatiquement). Ici, le
script à exécuter est déjà entièrement déterminé et validé (chargé depuis le
cache ou fraîchement généré en Phase 3) — il n'y a aucune génération de code
à la volée. Deux approches possibles :

* **(a) Recommandée** : instancier `ContainerCodeExecutor` (ou piloter
  directement le SDK `docker-py`) depuis le code d'orchestration host, sans
  passer par un `LlmAgent`. Plus simple, plus rapide, zéro coût/latence LLM
  inutile, comportement 100 % déterministe.
* **(b)** Envelopper dans un `LlmAgent` minimal dont l'unique instruction est
  d'invoquer l'exécuteur — ajoute de la complexité et une source
  d'indéterminisme sans bénéfice pour cette étape purement mécanique.

🔧 **Correction réseau/dépendances** : `network_disabled=True` est
incompatible avec un `pip install` au runtime. La bonne pratique (confirmée
par les mainteneurs d'ADK sur des cas similaires) est de **pré-construire une
image Docker** contenant déjà `pypdf`, construite une seule fois en amont
(ex. étape de setup/CI), et de référencer cette image locale dans la
configuration de l'exécuteur — aucune installation réseau au moment de
l'exécution.

```dockerfile
# Dockerfile.parser-sandbox — construit une seule fois, en amont
FROM python:3.11-alpine
RUN pip install --no-cache-dir pypdf
WORKDIR /sandbox
```

* **Configuration du sandbox** :
  * `image`: `"parser-sandbox:latest"` (image locale pré-construite, voir
    Dockerfile ci-dessus — plus de `python:3.11-alpine` nu avec install à la
    volée).
  * `network_disabled`: `True`.
  * `timeout_seconds`: `300`. 🔧 Vérifier le nom exact de ce champ contre la
    version installée d'`adk-python` — les paramètres des exécuteurs de code
    évoluent régulièrement d'une version à l'autre du SDK.
* **Payload d'exécution** : injection du PDF binaire complet + du script
  `parser_{uid}.py` (nom cohérent avec la Phase 2, plus de
  `parser_reglementaire.py`), écriture du `.md` final directement sur disque
  host via volume monté ou flux de sortie du conteneur.

---

## 5. BONNES PRATIQUES — PERFORMANCE, SÉCURITÉ, EXPLOITATION

1. **Optimisation mémoire** : le LLM reste un architecte structurel /
   micro-compilateur ; la traduction batch se fait en Python natif dans le
   sandbox.
2. **Nettoyages atomiques** : blocs `try...except...finally` systématiques ;
   aucune structure de montage temporaire ne doit persister sur le host.
3. **Cas limites regex** : ancrage explicite en `^` pour éviter de confondre
   citations internes (ex. `(1) OJ L 311`) avec de vrais titres de niveau
   racine.
4. 🔧 **Observabilité** : logger, pour chaque exécution, le `document_type`
   détecté, le `uid` utilisé (cache hit/miss), la durée de chaque phase, et
   le nombre de lignes non matchées par la hiérarchie (proxy simple de la
   qualité du parsing). Sans ces métriques, il est difficile de diagnostiquer
   pourquoi un document produit un `.md` de mauvaise qualité.
5. 🔧 **Validation de sortie** : avant de considérer un run comme réussi,
   vérifier a minima que le `.md` produit n'est pas vide et contient au moins
   un titre de niveau 0. Un échec silencieux (sandbox qui tourne, ne lève pas
   d'exception, mais produit un fichier vide car la regex racine ne matche
   jamais) est le mode de défaillance le plus probable de ce système.
6. 🔧 **Versionnage du cache** : si le schéma `UniversalStructureSchema`
   évolue (ajout d'un champ, changement de sémantique), les `uid` calculés
   avant et après ne changeront pas mécaniquement — prévoir un préfixe de
   version dans le nom de cache (ex. `parser_v2_{uid}.py`) pour éviter de
   charger un script généré sous un schéma obsolète.

---

## 6. POINTS OUVERTS (à trancher avant l'implémentation)

* **OCR** : confirmé hors-scope v1 (voir Phase 1) — à valider explicitement
  si des PDF scannés sont attendus dans le corpus réel.
* **Fusion de paragraphes coupés par la pagination** : le patron actuel ne
  reconstruit pas les paragraphes fragmentés entre deux pages — à trancher
  selon la Phase 3 (voir remarque sur la machine à états).
* **Stratégie de retry sur `ValidationError`** : nombre de tentatives et
  comportement en cas d'échec définitif (log + skip du document ? arrêt du
  batch entier ?) à définir selon le contexte d'usage (traitement d'un
  document isolé vs. traitement par lot).
