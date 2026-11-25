"""Gera com o Gemini os roteiros das semanas que estão faltando.

Uso:
  python scripts/generate_week.py          # gera o que faltar até a próxima semana
  python scripts/generate_week.py --mock   # conteúdo falso, para testar sem chave
"""
import datetime as dt
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

from common import (all_phrases, config, existing_weeks, load_week, save_json,
                    syllabus, today, week_monday, week_path)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_NOVAS_POR_EXECUCAO = 2
N_CENA = (10, 14)
N_FRASES = 10
N_DESAFIO = 4


# ---------------------------------------------------------------- Gemini ----

def gemini(prompt, temperature=0.9):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Falta a variável GEMINI_API_KEY (coloque nos Secrets do GitHub).")
    cfg = config()
    models = [os.environ.get("GEMINI_MODEL") or cfg["gemini_model"], cfg.get("gemini_model_reserva")]
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
    }).encode()
    last = None
    for model in [m for m in models if m]:
        for tentativa in range(4):
            req = urllib.request.Request(
                API.format(model=model), data=body, method="POST",
                headers={"Content-Type": "application/json", "x-goog-api-key": key})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = json.load(r)
                text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
                return json.loads(text)
            except urllib.error.HTTPError as e:
                last = f"{model}: HTTP {e.code} {e.read()[:300]!r}"
                if e.code in (400, 403, 404):
                    break  # modelo inexistente ou chave inválida: tenta o modelo reserva
            except (KeyError, IndexError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as e:
                last = f"{model}: {e!r}"
            espera = 15 * (tentativa + 1)
            print(f"  ! {last} — nova tentativa em {espera}s")
            time.sleep(espera)
    raise RuntimeError(f"Gemini falhou: {last}")


# ---------------------------------------------------------------- prompts ---

def perfil():
    a = config()["aluno"]
    nome = f"O aluno se chama {a['nome']}. " if a.get("nome") else ""
    return (f"{nome}Nível inicial: {a['nivel_inicial']}. Contexto profissional: {a['contexto_profissional']}. "
            f"Interesses: {a['interesses']}.")


def plano_da_semana(n):
    plano = {s["semana"]: s for s in syllabus()}
    if n in plano:
        return plano[n]
    anteriores = []
    for i in range(max(1, n - 8), n):
        w = plano.get(i) or load_week(i)
        if w:
            anteriores.append({k: w[k] for k in ("nivel", "tema", "foco")})
    prompt = f"""Você é coordenador de um curso de inglês em áudio para ouvir dirigindo (15 min na ida e 15 na volta).
{perfil()}
Semanas anteriores (nível, tema, foco): {json.dumps(anteriores, ensure_ascii=False)}
Planeje a semana {n}. Suba o nível aos poucos (até B2), alterne temas de trabalho e de vida pessoal/viagem,
e revise estruturas gramaticais já vistas. Responda só com JSON:
{{"nivel": "B1", "tema": "...", "foco": "estrutura gramatical e funções", "cenas": ["4 títulos curtos em português"]}}"""
    p = gemini(prompt, temperature=1.0)
    p["semana"] = n
    p["cenas"] = (p.get("cenas") or [])[:4]
    assert len(p["cenas"]) == 4, "plano sem 4 cenas"
    return p


def prompt_dia(plano, dia, titulo_cena, ja_ensinadas):
    return f"""Você é um professor de inglês muito experiente criando o conteúdo de UM episódio de um curso em áudio
para brasileiros que estudam dirigindo (sem olhar para nada: só ouvir e falar em voz alta).
{perfil()}
Semana {plano['semana']} — nível {plano['nivel']} — tema: {plano['tema']} — foco: {plano['foco']}.
Dia {dia}. Cena de hoje: "{titulo_cena}".

Regras:
- Inglês americano natural e atual, frases CURTAS (no máximo 12 palavras), boas de repetir em voz alta.
- Use o foco gramatical da semana, sem explicar gramática.
- Quando fizer sentido, traga situações do contexto profissional do aluno, mas sem exagerar no jargão.
- Português do Brasil coloquial nas traduções (é o que o narrador vai falar).
- NÃO repita estas frases já ensinadas: {json.dumps(ja_ensinadas[-150:], ensure_ascii=False)}

Responda só com JSON neste formato:
{{
  "titulo": "título curto em português",
  "contexto": "uma frase em português situando a cena (quem fala, onde)",
  "cena": [{{"falante": "A", "en": "...", "pt": "..."}}, {{"falante": "B", "en": "...", "pt": "..."}}],
  "frases": [{{"en": "...", "pt": "...", "variacoes": [{{"en": "...", "pt": "..."}}, {{"en": "...", "pt": "..."}}]}}],
  "pergunta_volta": {{"pt": "pergunta em português do tipo: Como você diria que ...?", "en_modelo": "resposta modelo em inglês"}},
  "desafio": [{{"en": "pergunta aberta em inglês para o aluno", "pt": "tradução", "en_modelo": "resposta modelo curta"}}]
}}
Quantidades: "cena" com {N_CENA[0]} a {N_CENA[1]} falas alternando A e B; "frases" com exatamente {N_FRASES} frases úteis
tiradas da cena (cada uma com 2 variações que trocam palavras mantendo a estrutura); "desafio" com {N_DESAFIO} perguntas
pessoais sobre o tema que o aluno possa responder com 1 ou 2 frases."""


# ----------------------------------------------------------- validação ------

def validar_dia(d):
    erros = []
    for k in ("titulo", "contexto", "cena", "frases", "pergunta_volta", "desafio"):
        if k not in d:
            erros.append(f"falta {k}")
    if erros:
        return erros
    cena = [l for l in d["cena"] if l.get("en") and l.get("pt")]
    for l in cena:
        l["falante"] = "B" if str(l.get("falante", "A")).upper().startswith("B") else "A"
    d["cena"] = cena[:N_CENA[1]]
    if len(cena) < N_CENA[0] - 2:
        erros.append(f"cena curta ({len(cena)})")
    frases = [f for f in d["frases"] if f.get("en") and f.get("pt")]
    for f in frases:
        f["variacoes"] = [v for v in f.get("variacoes", []) if v.get("en") and v.get("pt")][:2]
    d["frases"] = frases[:N_FRASES]
    if len(frases) < N_FRASES - 2:
        erros.append(f"poucas frases ({len(frases)})")
    d["desafio"] = [q for q in d["desafio"] if q.get("en") and q.get("en_modelo")][:N_DESAFIO]
    if len(d["desafio"]) < 2:
        erros.append("desafio curto")
    pv = d["pergunta_volta"]
    if not (pv.get("pt") and pv.get("en_modelo")):
        erros.append("pergunta_volta incompleta")
    return erros


# ------------------------------------------------------------ mock ----------

def mock_dia(plano, dia, titulo):
    rnd = random.Random(plano["semana"] * 10 + dia)
    nomes = ["coffee", "meeting", "report", "airport", "hotel", "supplier", "test", "lab", "price", "car"]
    def frase(i):
        w = rnd.choice(nomes)
        return {"en": f"I need the {w} today, number {i}.",
                "pt": f"Eu preciso do {w} hoje, número {i}.",
                "variacoes": [{"en": f"She needs the {w} for tomorrow.", "pt": f"Ela precisa do {w} para amanhã."},
                              {"en": f"We need a new {w} this week.", "pt": f"Nós precisamos de um novo {w} esta semana."}]}
    return {
        "titulo": titulo, "contexto": f"Dois colegas conversam sobre {titulo.lower()}.",
        "cena": [{"falante": "AB"[i % 2], "en": f"This is line {i} about the {rnd.choice(nomes)}.",
                  "pt": f"Esta é a fala {i} da cena."} for i in range(12)],
        "frases": [frase(i) for i in range(N_FRASES)],
        "pergunta_volta": {"pt": "Como você diria que chegou atrasado por causa do trânsito?",
                           "en_modelo": "I'm late because of the traffic."},
        "desafio": [{"en": f"What do you usually do on question {i}?", "pt": f"Pergunta {i}",
                     "en_modelo": "I usually drive to work and drink a coffee."} for i in range(N_DESAFIO)],
    }


# ------------------------------------------------------------ principal -----

def gerar_semana(n, mock=False):
    plano = {"semana": n, "nivel": "A1", "tema": "Teste", "foco": "teste",
             "cenas": ["Cena um", "Cena dois", "Cena três", "Cena quatro"]} if mock and n > 12 else (
        syllabus()[n - 1] if mock else plano_da_semana(n))
    print(f"Semana {n}: {plano['tema']} ({plano['nivel']})")
    ja = [p["en"] for p in all_phrases()]
    dias = []
    for i, titulo in enumerate(plano["cenas"], start=1):
        for tentativa in range(3):
            d = mock_dia(plano, i, titulo) if mock else gemini(prompt_dia(plano, i, titulo, ja))
            erros = validar_dia(d)
            if not erros:
                break
            print(f"  ! dia {i}: {erros} — gerando de novo")
        else:
            raise RuntimeError(f"Dia {i} da semana {n} veio inválido: {erros}")
        d["dia"] = i
        dias.append(d)
        ja += [f["en"] for f in d["frases"]]
        print(f"  dia {i}: {d['titulo']} — {len(d['cena'])} falas, {len(d['frases'])} frases")
    save_json(week_path(n), {
        "semana": n, "nivel": plano["nivel"], "tema": plano["tema"], "foco": plano["foco"],
        "segunda": week_monday(n).isoformat(), "dias": dias,
    })


def main():
    mock = "--mock" in sys.argv
    feitas = existing_weeks()
    proxima = (feitas[-1] + 1) if feitas else 1
    limite = today() + dt.timedelta(days=2)  # no sábado já gera a semana que começa segunda
    novas = 0
    while week_monday(proxima) <= limite and novas < MAX_NOVAS_POR_EXECUCAO:
        gerar_semana(proxima, mock=mock)
        proxima += 1
        novas += 1
    if not novas:
        print(f"Nada a gerar: a semana {proxima} começa em {week_monday(proxima)}.")


if __name__ == "__main__":
    main()
