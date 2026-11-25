"""Transforma o conteúdo de uma semana em roteiros de áudio (lista de segmentos).

Segmentos:
  {"t": "say", "v": "narrador|professor|A|B", "txt": "...", "lento": bool}
  {"t": "pause", "s": segundos}
  {"t": "echo", "k": fator, "mais": segundos}   # silêncio proporcional à fala anterior (para repetir)
  {"t": "chime"}                                  # sinal sonoro entre blocos
"""
import random

from common import DIAS_PT, all_phrases, config, load_week

PISTAS = ["Como se diz: {pt}", "Em inglês: {pt}", "{pt}", "Fale em inglês: {pt}", "E agora: {pt}"]
PAUSA_PENSAR = 4.5
PAUSA_DESAFIO = 12


def say(v, txt, lento=False):
    return {"t": "say", "v": v, "txt": txt.strip(), "lento": lento}


def pause(s):
    return {"t": "pause", "s": s}


def echo(k=1.3, mais=1.0):
    return {"t": "echo", "k": k, "mais": mais}


CHIME = {"t": "chime"}


def sem_ponto(txt):
    return txt.strip().rstrip(".!?")


# --------------------------------------------------------- revisão espaçada --

def revisao_espacada(semana, dia, n=6):
    """Frases antigas: da véspera, de 1 semana, de ~3 semanas e de ~7 semanas atrás."""
    rnd = random.Random(semana * 100 + dia)
    todas = [p for p in all_phrases(upto_week=semana)
             if (p["semana"], p["dia"]) < (semana, dia)]
    if not todas:
        return []
    def de(filtro, k):
        pool = [p for p in todas if filtro(p)]
        return rnd.sample(pool, min(k, len(pool)))
    escolha = []
    escolha += de(lambda p: p["semana"] == semana and p["dia"] == dia - 1, 2)
    escolha += de(lambda p: p["semana"] == semana - 1, 2)
    escolha += de(lambda p: semana - 4 <= p["semana"] <= semana - 2, 1)
    escolha += de(lambda p: p["semana"] <= semana - 5, 1)
    resto = [p for p in todas if p not in escolha]
    rnd.shuffle(resto)
    escolha += resto[: max(0, n - len(escolha))]
    return escolha[:n]


def bloco_pergunta_resposta(frases, rnd, devagar=True):
    segs = []
    for f in frases:
        segs += [say("narrador", rnd.choice(PISTAS).format(pt=sem_ponto(f["pt"]))), pause(PAUSA_PENSAR),
                 say("professor", f["en"]), echo()]
        if devagar:
            segs += [say("professor", f["en"], lento=True), echo()]
    return segs


def cena(linhas, lento=False):
    return [say(l["falante"], l["en"], lento=lento) for l in linhas]


# ------------------------------------------------------------ episódios -----

def completar(segs, pool, rnd, texto="Rodada extra, mais rápida. Português, e você responde em inglês."):
    """Acrescenta perguntas rápidas até o episódio chegar perto da duração alvo."""
    alvo = config().get("duracao_alvo_min", 15) * 60 - 20
    fim = segs.pop()  # a despedida fica no final
    if pool and estimar(segs) < alvo - 30:
        segs += [CHIME, say("narrador", texto)]
        pool = list(pool)
        i = 0
        while estimar(segs) < alvo and i < len(pool) * 2:
            if i % len(pool) == 0:
                rnd.shuffle(pool)
            segs += bloco_pergunta_resposta([pool[i % len(pool)]], rnd, devagar=False)
            i += 1
    segs.append(fim)
    return segs


def ida(wk, d):
    rnd = random.Random(wk["semana"] * 1000 + d["dia"])
    nome = config()["aluno"].get("nome")
    ola = f"Bom dia{', ' + nome if nome else ''}!"
    segs = [say("narrador", f"{ola} Semana {wk['semana']}, {DIAS_PT[d['dia'] - 1]}-feira. "
                            f"Hoje: {sem_ponto(d['titulo'])}. Lembre: só ouça e fale em voz alta. Olho na estrada.")]
    rev = revisao_espacada(wk["semana"], d["dia"])
    if rev:
        segs += [CHIME, say("narrador", "Revisão relâmpago. Eu falo em português, você responde em inglês.")]
        segs += bloco_pergunta_resposta(rev, rnd, devagar=False)
    segs += [CHIME, say("narrador", f"Agora ouça a cena. {d['contexto']}"), pause(1)]
    segs += cena(d["cena"])
    segs += [pause(1.5), say("narrador", "De novo, mais devagar."), pause(0.8)]
    segs += cena(d["cena"], lento=True)
    segs += [CHIME, say("narrador", "Vamos desmontar a cena. Eu digo em português, você tenta em inglês, "
                                    "depois repete comigo.")]
    segs += bloco_pergunta_resposta(d["frases"], rnd)
    segs += [CHIME, say("narrador", "Hora do shadowing. Escute cada fala e repita logo em seguida, "
                                    "imitando o ritmo e a entonação.")]
    for l in d["cena"]:
        segs += [say(l["falante"], l["en"]), echo(1.2, 1.2)]
    segs += [CHIME, say("narrador", "Agora a cena inteira. Tente falar junto, em cima da gravação."), pause(1)]
    segs += cena(d["cena"])
    pv = d["pergunta_volta"]
    segs += [CHIME, say("narrador", f"Pergunta para a volta: {pv['pt']} Pense nisso durante o dia. "
                                    "Bom trabalho e até a volta!")]
    return completar(segs, d["frases"] + rev, rnd)


def volta(wk, d):
    rnd = random.Random(wk["semana"] * 2000 + d["dia"])
    pv = d["pergunta_volta"]
    segs = [say("narrador", f"Boa tarde! Volta do dia {d['dia']}: {sem_ponto(d['titulo'])}. "
                            f"Hoje de manhã eu perguntei: {pv['pt']} Responda agora, em voz alta."),
            pause(6), say("narrador", "Uma resposta possível:"), say("professor", pv["en_modelo"]), echo(),
            say("professor", pv["en_modelo"]), echo()]
    segs += [CHIME, say("narrador", "Agora só inglês. Escute e repita.")]
    for f in d["frases"]:
        segs += [say("professor", f["en"]), echo(), say("professor", f["en"]), echo(1.1, 0.6)]
    segs += [CHIME, say("narrador", "Variações: a mesma estrutura com outras palavras. Eu digo em português, "
                                    "você monta em inglês.")]
    variacoes = [v for f in d["frases"] for v in f["variacoes"]]
    segs += bloco_pergunta_resposta(variacoes, rnd, devagar=False)
    segs += [CHIME, say("narrador", "Ouça a cena mais uma vez. Agora você já entende tudo."), pause(1)]
    segs += cena(d["cena"])
    segs += [CHIME, say("narrador", "Desafio livre. Eu faço uma pergunta, você responde do seu jeito, "
                                    "com frases curtas. Não existe resposta errada.")]
    for q in d["desafio"]:
        segs += [say("professor", q["en"]), pause(1), say("professor", q["en"], lento=True),
                 pause(PAUSA_DESAFIO), say("narrador", "Por exemplo:"), say("professor", q["en_modelo"]), echo()]
    segs += [CHIME, say("narrador", "Fim da volta. Amanhã tem mais. Bom descanso!")]
    anteriores = [f for x in wk["dias"] if x["dia"] < d["dia"] for f in x["frases"]]
    return completar(segs, d["frases"] + anteriores, rnd,
                     "Rodada extra: frases de hoje e dos dias anteriores.")


def sexta_ida(wk):
    rnd = random.Random(wk["semana"] * 3000)
    frases = [f for d in wk["dias"] for f in rnd.sample(d["frases"], min(6, len(d["frases"])))]
    rnd.shuffle(frases)
    antigas = [p for p in all_phrases(upto_week=wk["semana"] - 1)]
    extra = rnd.sample(antigas, min(6, len(antigas)))
    segs = [say("narrador", f"Bom dia! Sexta-feira, revisão da semana {wk['semana']}: {wk['tema']}. "
                            "Hoje não tem nada novo. Eu falo em português, você responde em inglês.")]
    segs += [CHIME] + bloco_pergunta_resposta(frases, rnd)
    if extra:
        segs += [CHIME, say("narrador", "Agora algumas de semanas anteriores.")]
        segs += bloco_pergunta_resposta(extra, rnd, devagar=False)
    segs += [CHIME, say("narrador", "Ótima semana de estudo. Na volta, você vai interpretar um papel nas cenas.")]
    resto = [f for d in wk["dias"] for f in d["frases"] if f not in frases]
    return completar(segs, resto, rnd, "Rodada extra com as outras frases da semana.")


def sexta_volta(wk):
    segs = [say("narrador", "Boa tarde! Última volta da semana. Para cada cena, primeiro você escuta. "
                            "Depois você faz o papel da segunda pessoa: eu dou a dica em português "
                            "e você fala em inglês.")]
    for d in wk["dias"]:
        segs += [CHIME, say("narrador", f"Cena: {sem_ponto(d['titulo'])}."), pause(0.8)]
        segs += cena(d["cena"])
        segs += [pause(1.2), say("narrador", "Sua vez. Você é a segunda pessoa."), pause(0.8)]
        for l in d["cena"]:
            if l["falante"] == "A":
                segs.append(say("A", l["en"]))
            else:
                segs += [say("narrador", sem_ponto(l["pt"])), {"t": "pause_for", "txt": l["en"]},
                         say("B", l["en"]), pause(0.8)]
    segs += [CHIME, say("narrador", "Fim da semana! Bom fim de semana, e segunda tem conteúdo novo.")]
    return completar(segs, [v for d in wk["dias"] for f in d["frases"] for v in f["variacoes"]],
                     random.Random(wk["semana"] * 4000), "Para fechar, variações da semana.")


def episodios_da_semana(n):
    """Retorna lista de (id, titulo, segmentos) da semana n."""
    wk = load_week(n)
    eps = []
    for d in wk["dias"]:
        nome_dia = DIAS_PT[d["dia"] - 1].capitalize()
        eps.append((f"d{d['dia']}-ida", f"{nome_dia} · Ida · {sem_ponto(d['titulo'])}", ida(wk, d)))
        eps.append((f"d{d['dia']}-volta", f"{nome_dia} · Volta · {sem_ponto(d['titulo'])}", volta(wk, d)))
    eps.append(("d5-ida", "Sexta · Ida · Revisão da semana", sexta_ida(wk)))
    eps.append(("d5-volta", "Sexta · Volta · Interpretando as cenas", sexta_volta(wk)))
    return wk, eps


# ---------------------------------------------- estimativa de duração -------

def estimar(segs):
    """Duração aproximada em segundos (sem gerar áudio)."""
    total, ultimo = 0.0, 0.0
    for s in segs:
        if s["t"] == "say":
            palavras = len(s["txt"].split())
            ultimo = 0.4 + palavras / (2.6 if s["v"] != "narrador" else 2.9)
            if s["lento"]:
                ultimo /= 0.78
            total += ultimo + 0.25
        elif s["t"] == "pause":
            total += s["s"]
        elif s["t"] == "echo":
            total += ultimo * s["k"] + s["mais"]
        elif s["t"] == "pause_for":
            total += (0.4 + len(s["txt"].split()) / 2.6) * 1.5 + 1.5
        elif s["t"] == "chime":
            total += 1.0
    return total
