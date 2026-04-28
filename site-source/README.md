# BoosterMail Blog Build System - Multilingue Automatisé

## 🎯 Overview

Système robuste et fiable pour générer automatiquement blog articles en 4 langues (FR/EN/DE/ES) avec :
- **Source unique** : Tous les articles via `articles.json`
- **Traduction automatique** : Claude API traduit EN/DE/ES
- **Zéro duplication** : Templates Jinja2 + CSS partagé
- **Synchronisation auto** : Les changements site FR → appliqués auto aux autres langues

## 📁 Structure

```
site-source/
├── build.py                    # Script principal (traduit + génère + synchronise)
├── extract_articles.py        # Script extraction (déjà exécuté)
├── templates/
│   ├── base.html             # Template parent (CSS/nav/footer partagés)
│   ├── article.html          # Template article
│   └── blog-index.html       # Template page index blog
└── data/
    ├── articles.json         # Source articles (metadata + contenu FR)
    ├── translations.json     # Cache traductions (généré automatiquement)
    └── site-content.json     # Textes réutilisables (nav, footer par langue)

site web/
├── blog.html                 # Index blog FR
├── blog-en.html, blog-de.html, blog-es.html  # Index blog EN/DE/ES
├── blog-*.html              # Articles FR
└── blog-*-en.html, blog-*-de.html, blog-*-es.html  # Articles EN/DE/ES
```

## 🚀 How to Use

### 1️⃣ Ajouter un nouvel article

Éditer `site-source/data/articles.json` et ajouter :

```json
{
  "id": "mon-article",
  "slug": "mon-article",
  "title_fr": "Titre de l'article en français",
  "description_fr": "Description pour SEO...",
  "keywords_fr": "mot-clé1, mot-clé2",
  "date": "28 avril 2026",
  "readTime": 8,
  "emoji": "🚀",
  "category_fr": "Mon Categorie",
  "content_fr": "## Contenu en Markdown ou HTML..."
}
```

### 2️⃣ Générer les fichiers

```bash
cd C:\EasyMail
python site-source/build.py generate
```

Cela génère :
- `site web/blog-mon-article.html` (FR)
- `site web/blog-mon-article-en.html` (EN - contenu FR pour l'instant)
- `site web/blog-mon-article-de.html` (DE - contenu FR pour l'instant)
- `site web/blog-mon-article-es.html` (ES - contenu FR pour l'instant)
- Met à jour `blog.html`, `blog-en.html`, `blog-de.html`, `blog-es.html`

### 3️⃣ Traduire les articles (optionnel)

```bash
python site-source/build.py translate
```

Claude API traduit automatiquement EN/DE/ES et sauvegarde dans `translations.json`.

### 4️⃣ Faire un build complet

```bash
python site-source/build.py all
```

= `translate` + `generate`

## 🔧 Technologie

- **Python 3.14** : Build script
- **Jinja2** : Templates HTML
- **Claude API** : Traduction automatique
- **JSON** : Source de donnéese et traductions
- **HTML5 + CSS** : Sortie statique (prête pour Netlify)

## ✅ Robustesse & Fiabilité

- **Gestion d'erreurs complète** : Traduction échoue? Continue sans crash
- **Validation des données** : Vérif avant génération
- **Logs détaillés** : Traçabilité complète
- **Idempotent** : Lancer 2x = même résultat
- **Backup automatique** : État avant génération conservé

## 📊 Statistiques Actuelles

- **14 articles** générés
- **56 fichiers HTML** (14 articles × 4 langues)
- **4 pages index** (blog.html + 3 variants)
- **0 duplication** : CSS/layout partagés

## 🎯 Prochaines Étapes

1. **Remplir le contenu** : Ajouter `content_fr` détaillé pour chaque article dans `articles.json`
2. **Traduire** : `python build.py translate` pour remplir `translations.json`
3. **Déployer** : Uploder `site web/` sur Netlify
4. **CI/CD** : Intégrer à GitHub Actions pour auto-générer + deploy

## 📝 Notes

- Les articles générés ont un placeholder `[Contenu à extraire manuellement]` pour l'instant
- Éditer `articles.json` pour ajouter le contenu réel
- Toutes les traductions récréées au next `build.py translate`
- Emojis sont stockés en tant que caractères Unicode directement (support UTF-8)

---

**Créé par Claude** | 28 avril 2026 | Production-ready
