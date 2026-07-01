# Agent Web-Design — intégration Hermes (OVH)

Usage principal confirmé : **traitement de chartes clients**, pas de production interne WMH par
défaut. `wmh-brand.md` reste dans le corpus mais en fallback secondaire (usage interne explicite
uniquement).

## Contenu du package
```
knowledge/
├── web-design-extractor.md       # Méthodologie PRINCIPALE — extraction forensique de charte
├── design-principles.md          # Jugement esthétique autonome, anti-défauts IA
├── a11y-checklist.md             # WCAG 2.2 AA, checklist actionnable
├── design-systems-reference.md   # shadcn/Radix/HIG/Material, règle d'arbitrage
└── wmh-brand.md                  # Charte WMH interne — fallback si demande explicite
scripts/
└── extract_web_design.py         # Script d'extraction, testé sur mozilla.org (voir résultat ci-dessous)
web-design-router.json            # Config de routage — intent "extract" en workflow par défaut
```

## Le script d'extraction — validé sur données réelles

`scripts/extract_web_design.py <url> [<url2> ...] --out <stem>-charte` :
- Fetch statique HTML + CSS (aucune dépendance Playwright/Chromium pour cette étape)
- Parse toutes les déclarations CSS via `tinycss2`, compte la fréquence réelle des couleurs/polices
- Compare aux custom properties `:root` déclarées → flag la divergence

**Test réel (mozilla.org, 01/07/2026) :** le thème `:root` déclaré ne référence aucune des
couleurs de marque réellement dominantes dans le CSS (`#0060df`, `#d70022`) — seuls noir/blanc
génériques recoupaient. Divergence détectée et flaggée automatiquement. C'est exactement le cas
d'usage attendu pour une charte client : le déclaratif ment, l'usage de-facto ne ment pas.

**Limite assumée :** extraction statique seulement — sites SPA avec CSS-in-JS dynamique
(styled-components à props runtime) sous-représentés. Le fichier `web-design-extractor.md`
documente le fallback (Playwright + capture d'écran + lecture visuelle par le sous-agent) pour
ce cas, non codé dans ce script.

## Pourquoi un sous-agent plutôt que qwen3.6-plus seul
Hermes tourne sur qwen3.6-plus via OpenRouter — pas de capacité vision/goût design validée à ce
jour. Routing : qwen3.6-plus reste orchestrateur (intent parsing, state `/data`, Discord),
dispatch vers Claude Opus 4.8 (fallback Gemini 3.1 Pro) pour tout jugement esthétique — cohérent
avec ton benchmark vision models de juin 2026.

## Prérequis à valider avant activation
1. **`tinycss2`, `requests`, `beautifulsoup4`** dans l'environnement Python Hermes — légers, pas
   de deps système lourdes (contrairement à Playwright)
2. **Playwright/Chromium** — optionnel pour l'extraction de base, requis pour le fallback
   sites JS-heavy et la QA visuelle finale
3. **Figma personal access token** — si le client fournit une maquette Figma plutôt qu'un site
   live (pas de MCP côté Hermes, appel REST direct décrit dans `web-design-extractor.md`)
4. **Bucket OVH Object Storage dédié** (`web-design-refs`) pour stocker chartes extraites et
   corpus de référence par client
5. **`@axe-core/playwright`** pour le scan a11y automatisé en sortie de build

## Déploiement
1. Copier `knowledge/*.md` dans `/data/knowledge/web-design/` sur le VPS
2. Copier `scripts/extract_web_design.py` dans le repo Hermes (deps : `pip install requests beautifulsoup4 tinycss2`)
3. Charger `web-design-router.json` dans la config d'intents Hermes (`default_workflow: extract_then_build`)
4. Ajouter `!design` à l'allowlist Discord (déjà single-user, pas de changement de posture sécu)

## Non couvert par ce package
- Extraction Figma non codée (méthodologie documentée dans `web-design-extractor.md`, script à
  écrire si le volume de maquettes Figma clients le justifie)
- Pas de RAG/embeddings sur le corpus — chargement statique en system prompt, suffisant tant que
  le corpus reste petit. À revoir si tu accumules des chartes extraites par dizaines de clients.
