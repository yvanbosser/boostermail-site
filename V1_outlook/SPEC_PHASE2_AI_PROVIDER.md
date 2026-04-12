# Spec Phase 2 — ai_provider.py (Abstraction IA)

*Interface commune pour changer de modèle IA sans toucher à app.py.*

---

## Principe

```
app.py
  └── provider = get_ai_provider(user_settings)
      └── provider.generate_reply(...)  ← même appel quel que soit le modèle
```

app.py ne sait jamais quel modèle IA tourne. Le choix est stocké en DB (table settings, clé `ai_model`) et configurable dans la page Profil.

---

## Interface commune

```python
class AIProvider:
    """Interface abstraite pour les modèles IA."""

    def generate_reply(self, system_prompt, user_prompt, max_tokens=1000,
                       temperature=0.3, stream=True) → Iterator[str] | str:
        """Génère une réponse email. Si stream=True, retourne un itérateur de chunks."""
        raise NotImplementedError

    def refine_reply(self, system_prompt, user_prompt, max_tokens=1000,
                     temperature=0.3, stream=True) → Iterator[str] | str:
        """Modifie un brouillon selon une instruction."""
        raise NotImplementedError

    def analyze_contact(self, system_prompt, user_prompt,
                        max_tokens=2000, temperature=0.2) → str:
        """Analyse un correspondant et retourne un profil JSON."""
        raise NotImplementedError

    def scan_echeances(self, system_prompt, user_prompt,
                       max_tokens=2000, temperature=0.2) → str:
        """Scanne des mails pour détecter des échéances."""
        raise NotImplementedError

    def suggest_folder(self, system_prompt, user_prompt,
                       max_tokens=500, temperature=0.1) → str:
        """Suggère un dossier de classement."""
        raise NotImplementedError

    def analyze_style(self, system_prompt, user_prompt,
                      max_tokens=4000, temperature=0.2) → str:
        """Analyse le style d'écriture (onboarding)."""
        raise NotImplementedError
```

---

## Implémentations

### claude_provider.py (défaut)

```python
class ClaudeProvider(AIProvider):
    def __init__(self, api_key):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"

    def generate_reply(self, system_prompt, user_prompt, max_tokens=1000,
                       temperature=0.3, stream=True):
        if stream:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            ) as stream:
                for text in stream.text_stream:
                    yield text
        else:
            response = self.client.messages.create(...)
            return response.content[0].text
```

### openai_provider.py (alternatif)

```python
class OpenAIProvider(AIProvider):
    def __init__(self, api_key, model="gpt-4.1-mini"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model  # "gpt-4.1-mini" ou "gpt-5.4-mini"

    def generate_reply(self, system_prompt, user_prompt, max_tokens=1000,
                       temperature=0.3, stream=True):
        if stream:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=True
            )
            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        else:
            response = self.client.chat.completions.create(...)
            return response.choices[0].message.content
```

---

## Factory

```python
def get_ai_provider(settings: dict) → AIProvider:
    model = settings.get('ai_model', 'claude-sonnet')

    if model == 'claude-sonnet':
        return ClaudeProvider(api_key=settings['anthropic_api_key'])
    elif model == 'gpt-4.1-mini':
        return OpenAIProvider(api_key=settings['openai_api_key'], model='gpt-4.1-mini')
    elif model == 'gpt-5.4-mini':
        return OpenAIProvider(api_key=settings['openai_api_key'], model='gpt-5.4-mini')
    else:
        return ClaudeProvider(api_key=settings['anthropic_api_key'])  # fallback
```

---

## Migration depuis claude_ai.py

L'actuel `claude_ai.py` contient la logique de construction des prompts (system prompt, blocs A/B/C/D/D2/E/F) ET les appels API Anthropic.

**Séparation** :
- La logique de construction des prompts reste dans `claude_ai.py` (renommé ou conservé)
- Les appels API sont abstraits dans `ai_provider.py`
- `claude_ai.py` utilise `provider.generate_reply(system_prompt, user_prompt)` au lieu d'appeler directement `anthropic.Anthropic`

Ainsi le system prompt WOW, les blocs de contexte, le scoring — tout reste identique. Seul le "tuyau" vers l'IA change.

---

## Page Profil — Choix du modèle

```
Modèle IA
├── ● Claude Sonnet (recommandé)
│     Meilleure qualité, style le plus fidèle
├── ○ GPT-4.1 mini
│     Meilleur rapport qualité-prix
└── ○ GPT-5.4 mini
      Bonne qualité, un peu plus cher
```

Sauvegarde immédiate en DB (table settings, clé `ai_model`).
Prise en compte dès la prochaine génération (pas besoin de redémarrer).

---

## Points d'attention

- Les prompts sont optimisés pour Claude. Un travail d'adaptation des prompts sera nécessaire pour OpenAI (formats légèrement différents, system prompt vs instructions).
- Les températures peuvent varier entre modèles (0.3 chez Claude ≠ 0.3 chez GPT en comportement).
- Le streaming SSE fonctionne de la même manière (itérateur de chunks texte).
- Les retry sur erreur Overloaded/RateLimited doivent être implémentés par provider.
