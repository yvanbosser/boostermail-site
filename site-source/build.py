#!/usr/bin/env python3
"""
Build System pour Blog BoosterMail Multilingue
Gère traduction + génération HTML + synchronisation
"""

import json
import argparse
import sys
import time
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
from anthropic import Anthropic, APITimeoutError, RateLimitError

# Configuration chemins
SOURCE_DIR = Path(__file__).parent
DATA_DIR = SOURCE_DIR / "data"
TEMPLATES_DIR = SOURCE_DIR / "templates"
SITE_WEB_DIR = Path("C:/EasyMail/site web")
CONFIG_PATH = Path("C:/EasyMail/config.json")

# Configuration langues
LANGUAGES = ["fr", "en", "de", "es"]
LANG_NAMES = {"fr": "French", "en": "English", "de": "German", "es": "Spanish"}
LANG_CODES = {"fr": "fr", "en": "en", "de": "de", "es": "es"}
OG_LOCALES = {"fr": "fr_FR", "en": "en_US", "de": "de_DE", "es": "es_ES"}

class Logger:
    """Logger simple avec colors"""
    @staticmethod
    def info(msg): print(f"ℹ️  {msg}")
    @staticmethod
    def success(msg): print(f"✅ {msg}")
    @staticmethod
    def warning(msg): print(f"⚠️  {msg}")
    @staticmethod
    def error(msg): print(f"❌ {msg}")
    @staticmethod
    def progress(current, total, label=""):
        pct = int((current / total) * 100) if total > 0 else 0
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"  [{bar}] {pct}% ({current}/{total}) {label}", end="\r")

class Validator:
    """Valide données avant traitement"""
    @staticmethod
    def validate_articles_json(articles):
        """Valide structure articles.json"""
        required_fields = ["id", "slug", "title_fr", "description_fr", "date", "readTime"]

        for i, article in enumerate(articles):
            for field in required_fields:
                if field not in article:
                    raise ValueError(f"Article #{i} '{article.get('id', 'UNKNOWN')}': champ requis '{field}' manquant")

            if not isinstance(article["readTime"], int):
                raise ValueError(f"Article '{article['id']}': readTime doit être un entier, got {type(article['readTime'])}")

        Logger.success(f"Validé {len(articles)} articles")

    @staticmethod
    def validate_site_content(content):
        """Valide structure site-content.json"""
        required_langs = ["fr", "en", "de", "es"]
        required_sections = ["nav", "blog_hero", "footer"]

        for section in required_sections:
            if section not in content:
                raise ValueError(f"Section '{section}' manquante dans site-content.json")

            for lang in required_langs:
                if lang not in content[section]:
                    raise ValueError(f"Langue '{lang}' manquante dans {section}")

        Logger.success("site-content.json valide")

class ConfigManager:
    """Gère la configuration du projet"""
    @staticmethod
    def load_api_key():
        """Charge la clé API Claude depuis config.json"""
        try:
            if not CONFIG_PATH.exists():
                Logger.error(f"config.json manquant à {CONFIG_PATH}")
                raise FileNotFoundError(f"config.json non trouvé")

            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)

            api_key = config.get("ANTHROPIC_API_KEY")
            if not api_key:
                Logger.error("ANTHROPIC_API_KEY non trouvé dans config.json")
                raise ValueError("API key manquante")

            return api_key
        except Exception as e:
            Logger.error(f"Impossible charger config: {e}")
            sys.exit(1)

class ArticleManager:
    """Gère le chargement et validation des articles"""
    @staticmethod
    def load_articles():
        """Charge articles.json"""
        try:
            articles_file = DATA_DIR / "articles.json"
            with open(articles_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("articles", [])
        except Exception as e:
            Logger.error(f"Erreur chargement articles.json: {e}")
            sys.exit(1)

    @staticmethod
    def load_translations():
        """Charge translations.json"""
        try:
            trans_file = DATA_DIR / "translations.json"
            if not trans_file.exists():
                return {"en": {}, "de": {}, "es": {}}

            with open(trans_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            Logger.warning(f"Erreur chargement translations.json: {e}")
            return {"en": {}, "de": {}, "es": {}}

    @staticmethod
    def load_site_content():
        """Charge site-content.json (textes globaux)"""
        try:
            content_file = DATA_DIR / "site-content.json"
            with open(content_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            Logger.error(f"Erreur chargement site-content.json: {e}")
            sys.exit(1)

class Translator:
    """Gère traduction via Claude API"""
    def __init__(self, api_key):
        self.client = Anthropic(api_key=api_key)

    def translate_article(self, article, target_langs=["en", "de", "es"]):
        """Traduit un article depuis FR vers target_langs avec retry logic"""
        translations = {}

        for target_lang in target_langs:
            max_retries = 3
            retry_count = 0
            backoff_seconds = 1

            while retry_count < max_retries:
                try:
                    Logger.info(f"Traduction {article['slug']} → {LANG_NAMES[target_lang]}...")

                    prompt = f"""You are an expert translator for a professional email productivity website.

TASK: Translate the following article metadata from French to {LANG_NAMES[target_lang]}.

RULES:
- Preserve structure exactly: return JSON with same keys
- Translate ONLY the values, NOT the keys
- Keep professional tone
- Localize dates to {target_lang} format
- Do NOT add or remove any fields
- Return valid JSON

ARTICLE:
{{
  "title": "{article.get('title_fr', '')}",
  "description": "{article.get('description_fr', '')}",
  "keywords": "{article.get('keywords_fr', '')}",
  "category": "{article.get('category_fr', 'Article')}"
}}

RESPONSE (JSON only, no markdown):"""

                    # Call avec timeout de 30s
                    message = self.client.messages.create(
                        model="claude-opus-4-1-20250805",
                        max_tokens=500,
                        timeout=30.0,
                        messages=[{"role": "user", "content": prompt}]
                    )

                    response_text = message.content[0].text.strip()
                    if response_text.startswith("```"):
                        response_text = "\n".join(response_text.split("\n")[1:-1])

                    translated = json.loads(response_text)
                    translations[target_lang] = translated
                    Logger.success(f"  {article['slug']} → {target_lang}")
                    break  # Success, exit retry loop

                except (RateLimitError, APITimeoutError) as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        Logger.warning(f"  Rate limit/timeout {target_lang}, retry {retry_count}/{max_retries} in {backoff_seconds}s...")
                        time.sleep(backoff_seconds)
                        backoff_seconds *= 2  # Exponential backoff
                    else:
                        Logger.warning(f"  Max retries atteint {target_lang}: {e}")
                        translations[target_lang] = {}

                except json.JSONDecodeError as e:
                    Logger.warning(f"  JSON parse error {target_lang}: {e}")
                    translations[target_lang] = {}
                    break

                except Exception as e:
                    Logger.warning(f"  Erreur traduction {target_lang}: {e}")
                    translations[target_lang] = {}
                    break

        return translations

class HTMLGenerator:
    """Génère fichiers HTML depuis templates"""
    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(['html', 'xml'])
        )
        self.site_content = ArticleManager.load_site_content()

        # Valider le contenu du site
        try:
            Validator.validate_site_content(self.site_content)
        except ValueError as e:
            Logger.error(f"Validation site-content.json échouée: {e}")
            raise

    def generate_blog_articles(self, articles, translations):
        """Génère les fichiers article HTML"""
        count = 0

        for article in articles:
            for lang in LANGUAGES:
                try:
                    # Récupérer le contenu traduit
                    if lang == "fr":
                        title = article.get("title_fr")
                        description = article.get("description_fr")
                        keywords = article.get("keywords_fr")
                        category = article.get("category_fr", "Article")
                    else:
                        trans = translations.get(lang, {}).get(article["id"], {})
                        title = trans.get("title") or article.get("title_fr")
                        description = trans.get("description") or article.get("description_fr")
                        keywords = trans.get("keywords") or article.get("keywords_fr")
                        category = trans.get("category") or article.get("category_fr", "Article")

                    # Préparer données
                    template_data = {
                        "title": title,
                        "description": description,
                        "keywords": keywords,
                        "category": category,
                        "emoji": article.get("emoji", "📝"),
                        "date_formatted": article.get("date", "2026-04-22"),
                        "date_iso": self._to_iso_date(article.get("date")),
                        "read_time": article.get("readTime", 8),
                        "canonical_url": f"blog-{article['slug']}{'-' + lang if lang != 'fr' else ''}.html",
                        "og_locale": OG_LOCALES[lang],
                        "lang_code": lang,
                        "nav": self.site_content["nav"][lang],
                        "footer": self.site_content["footer"][lang],
                        "content_html": "<p>[Contenu à extraire manuellement]</p>"
                    }

                    # Générer HTML
                    template = self.env.get_template("article.html")
                    html = template.render(template_data)

                    # Sauvegarder
                    output_file = SITE_WEB_DIR / f"blog-{article['slug']}{'-' + lang if lang != 'fr' else ''}.html"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(html)

                    count += 1

                except Exception as e:
                    Logger.warning(f"Erreur génération {article['slug']} ({lang}): {e}")

        Logger.success(f"Généré {count} fichiers article HTML")

    def generate_blog_indexes(self, articles, translations):
        """Génère les pages index blog (blog.html, blog-en.html, etc.)"""
        count = 0

        for lang in LANGUAGES:
            try:
                # Préparer articles avec contenu traduit
                articles_data = []

                for article in articles:
                    if lang == "fr":
                        title = article.get("title_fr")
                        description = article.get("description_fr")
                        category = article.get("category_fr", "Article")
                    else:
                        trans = translations.get(lang, {}).get(article["id"], {})
                        title = trans.get("title") or article.get("title_fr")
                        description = trans.get("description") or article.get("description_fr")
                        category = trans.get("category") or article.get("category_fr", "Article")

                    articles_data.append({
                        "slug": article["slug"],
                        "title": title,
                        "description": description,
                        "category": category,
                        "emoji": article.get("emoji", "📝"),
                        "date_formatted": article.get("date"),
                        "read_time": article.get("readTime", 8)
                    })

                # Textes de la page
                blog_hero = self.site_content["blog_hero"][lang]
                nav = self.site_content["nav"][lang]
                footer = self.site_content["footer"][lang]

                read_more = "Lire l'article" if lang == "fr" else "Read article" if lang == "en" else "Artikel lesen" if lang == "de" else "Leer artículo"

                template_data = {
                    "page_title": blog_hero["title"],
                    "page_description": blog_hero["description"],
                    "blog_hero": blog_hero,
                    "articles": articles_data,
                    "lang_code": lang,
                    "nav": nav,
                    "footer": footer,
                    "read_more": read_more
                }

                # Générer HTML
                template = self.env.get_template("blog-index.html")
                html = template.render(template_data)

                # Sauvegarder
                filename = f"blog{'-' + lang if lang != 'fr' else ''}.html"
                output_file = SITE_WEB_DIR / filename
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(html)

                Logger.success(f"Généré {filename}")
                count += 1

            except Exception as e:
                Logger.error(f"Erreur génération blog index ({lang}): {e}")

        Logger.success(f"Généré {count} pages index blog")

    @staticmethod
    def _to_iso_date(date_str):
        """Convertit date FR vers ISO format"""
        try:
            # Format: "22 avril 2026" → "2026-04-22"
            months = {
                "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
                "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
            }
            if isinstance(date_str, str) and date_str:
                parts = date_str.lower().split()
                if len(parts) >= 3:
                    day = int(parts[0])
                    month = months.get(parts[1], 1)
                    year = int(parts[2])
                    return f"{year}-{month:02d}-{day:02d}"
            return "2026-04-22"
        except:
            return "2026-04-22"

class CLI:
    """Interface ligne de commande"""
    def __init__(self):
        self.api_key = ConfigManager.load_api_key()
        self.translator = Translator(self.api_key)
        self.generator = HTMLGenerator()

    def translate(self):
        """Traduit articles manquants"""
        Logger.info("=== TRADUCTION ===")

        articles = ArticleManager.load_articles()
        translations = ArticleManager.load_translations()

        # Valider les données avant traduction
        try:
            Validator.validate_articles_json(articles)
        except ValueError as e:
            Logger.error(f"Validation échouée: {e}")
            sys.exit(1)

        Logger.info(f"Chargé {len(articles)} articles")

        articles_to_translate = [a for a in articles if a["id"] not in translations.get("en", {})]
        Logger.info(f"À traduire: {len(articles_to_translate)} articles")

        for idx, article in enumerate(articles_to_translate, 1):
            article_id = article["id"]
            Logger.progress(idx, len(articles_to_translate), f"Traduction {article_id}")

            # Traduire
            trans = self.translator.translate_article(article)

            # Sauvegarder
            for lang, data in trans.items():
                if lang not in translations:
                    translations[lang] = {}
                translations[lang][article_id] = data

            trans_file = DATA_DIR / "translations.json"
            with open(trans_file, 'w', encoding='utf-8') as f:
                json.dump(translations, f, ensure_ascii=False, indent=2)

        print()  # Newline après la barre de progression
        Logger.success("Traduction terminée")

    def generate(self):
        """Génère fichiers HTML"""
        Logger.info("=== GÉNÉRATION HTML ===")

        articles = ArticleManager.load_articles()
        translations = ArticleManager.load_translations()

        # Valider les données avant génération
        try:
            Validator.validate_articles_json(articles)
            site_content = ArticleManager.load_site_content()
            Validator.validate_site_content(site_content)
        except ValueError as e:
            Logger.error(f"Validation échouée: {e}")
            sys.exit(1)

        # Créer dossier output si besoin
        SITE_WEB_DIR.mkdir(exist_ok=True)

        # Générer
        self.generator.generate_blog_articles(articles, translations)
        self.generator.generate_blog_indexes(articles, translations)

        Logger.success("Génération HTML terminée")

    def all(self):
        """Exécute translate + generate"""
        self.translate()
        self.generate()

def main():
    parser = argparse.ArgumentParser(description="Build System Blog BoosterMail Multilingue")
    parser.add_argument(
        "action",
        choices=["translate", "generate", "all"],
        help="Action à exécuter"
    )

    args = parser.parse_args()

    try:
        cli = CLI()

        if args.action == "translate":
            cli.translate()
        elif args.action == "generate":
            cli.generate()
        elif args.action == "all":
            cli.all()

        Logger.success("\n✅ Build réussi!")

    except KeyboardInterrupt:
        Logger.warning("\nInterruption utilisateur")
        sys.exit(1)
    except Exception as e:
        Logger.error(f"\n{e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
