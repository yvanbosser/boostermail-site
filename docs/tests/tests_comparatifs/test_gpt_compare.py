"""
Test comparatif : GPT-5.4 mini vs GPT-5.4 nano vs GPT-4.1 mini
Utilise le prompt exact capture par EasyMail (_test_prompt.txt)
"""
import os
import time
from openai import OpenAI

client = OpenAI(api_key="REDACTED_OPENAI_KEY")

prompt_path = os.path.join(os.path.dirname(__file__), "_test_prompt.txt")
if not os.path.exists(prompt_path):
    print("ERREUR: _test_prompt.txt introuvable.")
    print("Ouvrez un mail dans EasyMail, cliquez Generer, puis relancez ce script.")
    exit(1)

with open(prompt_path, "r", encoding="utf-8") as f:
    content = f.read()

parts = content.split("=== USER PROMPT ===")
system_prompt = parts[0].replace("=== SYSTEM PROMPT ===\n", "").strip()
user_prompt = parts[1].strip() if len(parts) > 1 else ""

print(f"System prompt: {len(system_prompt)} chars")
print(f"User prompt: {len(user_prompt)} chars")
print(f"Total: ~{(len(system_prompt) + len(user_prompt))//4} tokens")
print()

MODELS = [
    ("GPT-5 mini", "gpt-5-mini", 0.25, 2.00, False),
    ("GPT-5.4 mini", "gpt-5.4-mini", 0.75, 4.50, True),
    ("GPT-5.4 nano", "gpt-5.4-nano", 0.15, 0.60, True),
    ("GPT-4.1 mini", "gpt-4.1-mini", 0.40, 1.60, True),
]

for name, model_id, price_in, price_out, supports_temp in MODELS:
    print("=" * 60)
    print(f"{name} (${price_in}/${price_out} per 1M tokens)")
    print("=" * 60)
    t0 = time.time()
    try:
        params = {
            "model": model_id,
            "max_completion_tokens": 1200,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        if supports_temp:
            params["temperature"] = 0.3
        response = client.chat.completions.create(**params)
        result = response.choices[0].message.content
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens
        cost = tokens_in * price_in / 1_000_000 + tokens_out * price_out / 1_000_000
        print(f"Temps: {time.time()-t0:.1f}s | Tokens: {tokens_in} in + {tokens_out} out | Cout: ${cost:.4f}")
        print("-" * 60)
        print(result)
        print()
        safe_name = model_id.replace(".", "").replace("-", "_")
        with open(os.path.join(os.path.dirname(__file__), f"_result_{safe_name}.txt"), "w", encoding="utf-8") as f:
            f.write(result)
    except Exception as e:
        print(f"ERREUR: {e}")
        print()

print("=" * 60)
print("Comparez ces reponses avec la reponse Sonnet dans EasyMail.")
print("=" * 60)
