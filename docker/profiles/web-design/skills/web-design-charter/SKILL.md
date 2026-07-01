---
name: web-design-charter
description: "Extraction forensique de charte web à partir d'un site client (couleurs/typo réelles vs déclarées), jugement esthétique, checklist a11y WCAG 2.2 AA, et référence design systems. Déclencher pour : analyser/extraire la charte d'un site, auditer un design, critiquer une UI, vérifier l'accessibilité, ou produire une charte avant intégration."
version: 1.0.0
author: WMH Project
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [design, web-design, charte, brand, accessibility, a11y, css, design-system]
---

# web-design-charter

Compétences design pour le profil **web-design** : extraire la charte de-facto
d'un site client, juger la qualité esthétique, contrôler l'accessibilité, et
arbitrer avec les design systems de référence.

**Principe directeur : `theme != brand`.** Les custom properties `:root` déclarées
sont souvent génériques ; la vraie marque vit dans l'usage réel (couleurs/polices
effectivement appliquées, pondérées par fréquence). Toujours réconcilier déclaré
vs de-facto et **signaler la divergence**.

## Base de connaissance (à lire selon l'intent)
- `knowledge/web-design-extractor.md` — **méthodologie principale** : extraction
  forensique de charte (statique + fallback Playwright/vision pour SPA).
- `knowledge/design-principles.md` — jugement esthétique autonome, anti-défauts IA.
- `knowledge/a11y-checklist.md` — WCAG 2.2 AA, checklist actionnable.
- `knowledge/design-systems-reference.md` — shadcn/Radix/HIG/Material + arbitrage.
- `knowledge/wmh-brand.md` — charte WMH interne (**fallback**, usage interne explicite
  uniquement ; par défaut on traite des chartes clients).

## Extraction de charte (script)
```
python3 scripts/extract_web_design.py <url> [<url2> ...] --out <stem>-charte
```
- Fetch statique HTML+CSS, parse toutes les déclarations (`tinycss2`), compte la
  fréquence réelle des couleurs/polices, compare à `:root` et flag la divergence.
- Dépendances : `requests`, `beautifulsoup4`, `tinycss2` (présentes dans l'image).
- Limite : sites SPA / CSS-in-JS runtime sous-représentés → bascule sur le fallback
  Playwright + lecture visuelle décrit dans `web-design-extractor.md`.

## Jugement esthétique / vision
Le profil web-design tourne sur **Gemini 3.1 Pro** (voir `config.yaml`), retenu pour
le jugement esthétique/vision. `web-design-router.json` documente le routage d'intents
d'origine (référence). Ne pas régresser vers un modèle sans capacité vision validée
sans A/B test.

## Sortie attendue
Une charte structurée (couleurs hex + rôles, échelle typo, tokens, écarts déclaré/
de-facto signalés) et, si demandé, un audit a11y actionnable. Fidélité au réel avant
toute reconstruction.
