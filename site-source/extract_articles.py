#!/usr/bin/env python3
"""
Extraction robuste des articles existants depuis site web/
Génère articles.json et translations.json
"""

import json
import re
import os
from pathlib import Path
from html.parser import HTMLParser

SITE_WEB = Path("C:/EasyMail/site web")
SOURCE_DIR = Path("C:/EasyMail/site-source")

class ArticleParser(HTMLParser):
    """Parse HTML article pour extraire metadata et contenu"""
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.keywords = ""
        self.read_time = ""
        self.date = ""
        self.category = ""
        self.content = ""
        self.in_article = False
        self.in_title = False
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "meta":
            name = attrs_dict.get("name", "")
            prop = attrs_dict.get("property", "")
            content = attrs_dict.get("content", "")

            if name == "description":
                self.description = content
            elif name == "keywords":
                self.keywords = content

        elif tag == "title":
            self.in_title = True

        elif tag == "h1":
            self.current_tag = "h1"

        elif tag == "article":
            self.in_article = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.current_tag = None

    def handle_data(self, data):
        data = data.strip()
        if not data:
            return

        if self.in_title and not self.title:
            self.title = data[:100]
        elif self.current_tag == "h1" and not self.title:
            self.title = data

    @staticmethod
    def extract_from_file(filepath):
        """Parse un fichier HTML article"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            parser = ArticleParser()
            parser.feed(content)

            # Extraire date et temps de lecture avec regex
            date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4})', content)
            read_time_match = re.search(r'(\d+)\s*min', content)

            return {
                'title': parser.title or "Unknown Title",
                'description': parser.description,
                'keywords': parser.keywords,
                'date': date_match.group(0) if date_match else "2026-04-22",
                'read_time': int(read_time_match.group(1)) if read_time_match else 8
            }
        except Exception as e:
            print(f"⚠️  Erreur parsing {filepath}: {e}")
            return None

def extract_all_articles():
    """Extrait tous les articles français"""
    articles_map = {}

    # Lister tous les fichiers blog-*.html (sauf -en, -de, -es)
    article_files = sorted([
        f for f in SITE_WEB.glob("blog-*.html")
        if f.name not in ["blog.html", "blog-en.html", "blog-de.html", "blog-es.html"]
        and not any(suffix in f.name for suffix in ["-en.html", "-de.html", "-es.html"])
    ])

    print(f"📄 Extraction de {len(article_files)} articles...")

    for filepath in article_files:
        # Extraire le slug (blog-slug.html → slug)
        slug = filepath.stem.replace("blog-", "").replace("-fr", "")

        # Ne traiter que la version FR (pas -fr explicite)
        if "-fr" in filepath.stem:
            continue

        if slug in articles_map:
            continue

        metadata = ArticleParser.extract_from_file(filepath)
        if not metadata:
            continue

        articles_map[slug] = {
            "id": slug,
            "slug": slug,
            "title_fr": metadata['title'],
            "description_fr": metadata['description'],
            "keywords_fr": metadata['keywords'],
            "date": metadata['date'],
            "readTime": metadata['read_time'],
            "emoji": "📝",  # Default emoji (user can override)
            "category_fr": "Article",  # Default (user can override)
            "content_fr": "<!-- CONTENU À EXTRAIRE MANUELLEMENT -->"
        }
        print(f"  ✓ {slug}")

    return articles_map

def generate_articles_json(articles_map):
    """Crée articles.json"""
    articles_json = {
        "articles": list(articles_map.values()),
        "metadata": {
            "version": "1.0",
            "generated": "2026-04-28",
            "total_articles": len(articles_map),
            "languages": ["fr", "en", "de", "es"]
        }
    }

    output_file = SOURCE_DIR / "data" / "articles.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(articles_json, f, ensure_ascii=False, indent=2)

    print(f"\n✅ articles.json créé: {output_file}")
    print(f"   {len(articles_map)} articles extraits")
    return articles_json

def generate_translations_json(articles_map):
    """Crée translations.json vide (à remplir par traduction)"""
    translations = {
        "en": {},
        "de": {},
        "es": {}
    }

    output_file = SOURCE_DIR / "data" / "translations.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    print(f"✅ translations.json créé (vide, prêt pour traduction)")

if __name__ == "__main__":
    try:
        articles = extract_all_articles()
        generate_articles_json(articles)
        generate_translations_json(articles)
        print("\n✅ Extraction terminée avec succès!")
    except Exception as e:
        print(f"❌ Erreur: {e}")
        exit(1)
