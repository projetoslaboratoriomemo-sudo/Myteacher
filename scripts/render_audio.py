"""Gera os MP3 das últimas semanas a partir dos roteiros.

Motor de voz: edge-tts (vozes neurais, gratuito). Se falhar, usa Piper (open-source, roda local).
Uso:
  python scripts/render_audio.py          # normal
  python scripts/render_audio.py --mock   # tons no lugar de voz, para testar sem internet
"""
import asyncio
import hashlib
import json
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

from common import PUBLIC, TTS_CACHE, config, existing_weeks, save_json
from episodes import episodios_da_semana

RATE = 24000
MOCK = "--mock" in sys.argv
CLIPS = TTS_CACHE / "clips"
EPIS = TTS_CACHE / "episodes"
MODELS = TTS_CACHE / "models"
usados = set()


def ff(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def to_wav(src, dst):
    ff("-i", str(src), "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", str(dst))


# ------------------------------------------------------------- motores ------

class Edge:
    nome = "edge"

    def __init__(self, cfg):
        import edge_tts  # noqa: F401
        self.vozes = cfg["tts"]["vozes_edge"]
        self.lenta = cfg["tts"].get("velocidade_lenta", "-25%")

    async def _one(self, sem, voz, txt, lento, dst):
        import edge_tts
        async with sem:
            tmp = dst.with_suffix(".mp3")
            for tentativa in range(4):
                try:
                    await edge_tts.Communicate(txt, voz, rate=self.lenta if lento else "+0%").save(str(tmp))
                    to_wav(tmp, dst)
                    tmp.unlink(missing_ok=True)
                    return True
                except Exception as e:  # rede, limite etc.
                    print(f"  ! edge-tts ({e!r}) tentativa {tentativa + 1}")
                    await asyncio.sleep(3 * (tentativa + 1))
            return False

    def gerar(self, pedidos):
        async def run():
            sem = asyncio.Semaphore(6)
            return await asyncio.gather(*[self._one(sem, self.vozes[v], t, l, d) for v, t, l, d in pedidos])
        return asyncio.run(run())


class Piper:
    nome = "piper"
    BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

    def __init__(self, cfg):
        from piper import PiperVoice
        self.vozes, self.cache = cfg["tts"]["vozes_piper"], {}
        pct = int(cfg["tts"].get("velocidade_lenta", "-25%").strip("%"))
        self.escala_lenta = 1 / (1 + pct / 100)
        self.PiperVoice = PiperVoice

    def _modelo(self, nome):
        if nome not in self.cache:
            lang = nome.split("_")[0]
            region_lang = nome.split("-")[0]
            voz, qual = nome.split("-")[1], nome.split("-")[2]
            MODELS.mkdir(parents=True, exist_ok=True)
            onnx = MODELS / f"{nome}.onnx"
            for suf in (".onnx", ".onnx.json"):
                alvo = MODELS / f"{nome}{suf}"
                if not alvo.exists():
                    url = f"{self.BASE}{lang}/{region_lang}/{voz}/{qual}/{nome}{suf}"
                    print(f"  baixando voz {url}")
                    urllib.request.urlretrieve(url, alvo)
            self.cache[nome] = self.PiperVoice.load(str(onnx))
        return self.cache[nome]

    def gerar(self, pedidos):
        from piper import SynthesisConfig
        ok = []
        for v, txt, lento, dst in pedidos:
            try:
                voice = self._modelo(self.vozes[v])
                tmp = dst.with_suffix(".raw.wav")
                with wave.open(str(tmp), "wb") as w:
                    voice.synthesize_wav(txt, w, syn_config=SynthesisConfig(
                        length_scale=self.escala_lenta if lento else 1.0))
                to_wav(tmp, dst)
                tmp.unlink(missing_ok=True)
                ok.append(True)
            except Exception as e:
                print(f"  ! piper: {e!r}")
                ok.append(False)
        return ok


class Mock:
    nome = "mock"

    def gerar(self, pedidos):
        freq = {"narrador": 220, "professor": 440, "A": 330, "B": 550}
        for v, txt, lento, dst in pedidos:
            dur = (0.4 + len(txt.split()) / 2.6) / (0.78 if lento else 1)
            ff("-f", "lavfi", "-i", f"sine=frequency={freq[v]}:duration={dur:.2f}", "-af", "volume=0.2",
               "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", str(dst))
        return [True] * len(pedidos)


def motores(cfg):
    if MOCK:
        return [Mock()]
    lista = []
    ordem = ["edge", "piper"] if cfg["tts"].get("motor", "edge") == "edge" else ["piper", "edge"]
    for nome in ordem:
        try:
            lista.append(Edge(cfg) if nome == "edge" else Piper(cfg))
        except Exception as e:
            print(f"  ! motor {nome} indisponível: {e!r}")
    return lista


# ------------------------------------------------------------- áudio --------

def chave(*partes):
    return hashlib.sha1("|".join(map(str, partes)).encode()).hexdigest()[:20]


def ler_pcm(path):
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


def silencio(seg):
    return b"\x00\x00" * int(RATE * max(0.0, seg))


def chime():
    path = CLIPS / "chime.wav"
    if not path.exists():
        ff("-f", "lavfi", "-i", "sine=frequency=880:duration=0.16", "-f", "lavfi",
           "-i", "sine=frequency=1320:duration=0.22", "-filter_complex",
           "[0][1]concat=n=2:v=0:a=1,afade=t=out:st=0.25:d=0.13,volume=0.18",
           "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", str(path))
    usados.add(path)
    return silencio(0.35) + ler_pcm(path) + silencio(0.45)


def sintetizar_tudo(todos_segs, engines):
    """Gera (com cache) todos os clipes de fala necessários. Retorna {(v,txt,lento): path}."""
    CLIPS.mkdir(parents=True, exist_ok=True)
    motor_id = engines[0].nome if engines else "nenhum"
    mapa, faltando = {}, []
    for segs in todos_segs:
        for s in segs:
            if s["t"] != "say":
                continue
            k = (s["v"], s["txt"], s["lento"])
            if k in mapa:
                continue
            path = CLIPS / f"{chave(motor_id, *k)}.wav"
            mapa[k] = path
            if not path.exists():
                faltando.append((s["v"], s["txt"], s["lento"], path))
    print(f"  {len(mapa)} falas únicas, {len(faltando)} novas para sintetizar ({motor_id})")
    for eng in engines:
        if not faltando:
            break
        for i in range(0, len(faltando), 60):
            lote = faltando[i:i + 60]
            eng.gerar(lote)
            print(f"    {min(i + 60, len(faltando))}/{len(faltando)}")
        faltando = [p for p in faltando if not p[3].exists()]
        if faltando and eng is not engines[-1]:
            print(f"  ! {len(faltando)} falas falharam no {eng.nome}; tentando o próximo motor")
    if faltando:
        raise RuntimeError(f"{len(faltando)} falas não foram geradas; exemplo: {faltando[0][1]!r}")
    usados.update(mapa.values())
    return mapa


def montar(segs, clipes, destino, titulo):
    h = chave(json.dumps(segs, ensure_ascii=False), *sorted(str(p) for p in set(clipes.values())))
    EPIS.mkdir(parents=True, exist_ok=True)
    pronto = EPIS / f"{h}.mp3"
    info = EPIS / f"{h}.json"
    usados.update([pronto, info])
    destino.parent.mkdir(parents=True, exist_ok=True)
    if pronto.exists() and info.exists():
        destino.write_bytes(pronto.read_bytes())
        return json.loads(info.read_text())["duracao"]
    pcm, ultimo = bytearray(silencio(0.6)), 0.0
    for s in segs:
        if s["t"] == "say":
            fala = ler_pcm(clipes[(s["v"], s["txt"], s["lento"])])
            ultimo = len(fala) / 2 / RATE
            pcm += fala + silencio(0.25)
        elif s["t"] == "pause":
            pcm += silencio(s["s"])
        elif s["t"] == "echo":
            pcm += silencio(ultimo * s["k"] + s["mais"])
        elif s["t"] == "pause_for":
            pcm += silencio((0.4 + len(s["txt"].split()) / 2.6) * 1.5 + 1.5)
        elif s["t"] == "chime":
            pcm += chime()
    pcm += silencio(1.0)
    tmp = EPIS / f"{h}.wav"
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(pcm))
    ff("-i", str(tmp), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(RATE), "-ac", "1",
       "-codec:a", "libmp3lame", "-b:a", "48k", "-metadata", f"title={titulo}",
       "-metadata", "artist=Commute English", str(pronto))
    tmp.unlink()
    dur = len(pcm) / 2 / RATE
    info.write_text(json.dumps({"duracao": dur}))
    destino.write_bytes(pronto.read_bytes())
    return dur


def limpar_cache():
    removidos = 0
    for p in list(CLIPS.glob("*.wav")) + list(EPIS.glob("*")):
        if p not in usados:
            p.unlink()
            removidos += 1
    if removidos:
        print(f"  cache: {removidos} arquivos antigos removidos")


def main():
    cfg = config()
    semanas = existing_weeks()[-cfg.get("semanas_com_audio", 3):]
    if not semanas:
        print("Nenhuma semana gerada ainda.")
        return
    engines = motores(cfg)
    if not engines:
        sys.exit("Nenhum motor de voz disponível (instale edge-tts ou piper-tts).")
    todos = {n: episodios_da_semana(n)[1] for n in semanas}
    clipes = sintetizar_tudo([s for eps in todos.values() for _, _, s in eps], engines)
    duracoes = {}
    for n, eps in todos.items():
        for ep_id, titulo, segs in eps:
            destino = PUBLIC / "audio" / f"semana-{n:02d}" / f"{ep_id}.mp3"
            dur = montar(segs, clipes, destino, f"Semana {n} · {titulo}")
            duracoes[f"{n}/{ep_id}"] = round(dur)
            print(f"  semana {n} {ep_id}: {dur / 60:.1f} min")
    save_json(PUBLIC / "audio" / "duracoes.json", duracoes)
    limpar_cache()


if __name__ == "__main__":
    main()
