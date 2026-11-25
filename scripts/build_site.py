"""Monta a pasta public/: site, episodes.json (lista de episódios) e feed.xml (podcast)."""
import datetime as dt
import os
import shutil
from email.utils import format_datetime
from xml.sax.saxutils import escape

from common import PUBLIC, SITE_SRC, existing_weeks, load_json, save_json
from episodes import episodios_da_semana


def transcricao(segs):
    linhas, ultimo = [], None
    for s in segs:
        if s["t"] == "say":
            linha = {"v": s["v"], "txt": s["txt"]}
            if linha != ultimo:  # não repete a mesma fala duas vezes seguidas
                linhas.append(linha)
            ultimo = linha
    return linhas


def main():
    PUBLIC.mkdir(exist_ok=True)
    for item in SITE_SRC.iterdir():
        alvo = PUBLIC / item.name
        if item.is_dir():
            shutil.copytree(item, alvo, dirs_exist_ok=True)
        else:
            shutil.copy2(item, alvo)

    duracoes = load_json(PUBLIC / "audio" / "duracoes.json", {})
    semanas = []
    for n in existing_weeks():
        wk, eps = episodios_da_semana(n)
        segunda = dt.date.fromisoformat(wk["segunda"])
        lista = []
        for i, (ep_id, titulo, segs) in enumerate(eps):
            dia = int(ep_id[1]) - 1
            data = segunda + dt.timedelta(days=dia)
            tem_audio = f"{n}/{ep_id}" in duracoes
            lista.append({
                "id": f"s{n:02d}-{ep_id}", "semana": n, "ordem": i, "titulo": titulo,
                "data": data.isoformat(), "turno": "ida" if ep_id.endswith("ida") else "volta",
                "audio": f"audio/semana-{n:02d}/{ep_id}.mp3" if tem_audio else None,
                "duracao": duracoes.get(f"{n}/{ep_id}"),
                "roteiro": transcricao(segs),
            })
        semanas.append({"semana": n, "tema": wk["tema"], "nivel": wk["nivel"], "foco": wk["foco"],
                        "segunda": wk["segunda"], "episodios": lista})
    save_json(PUBLIC / "episodes.json", {"gerado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                         "semanas": semanas})
    escrever_feed(semanas)
    print(f"Site montado em {PUBLIC} com {len(semanas)} semana(s).")


def escrever_feed(semanas):
    base = (os.environ.get("SITE_URL") or "").rstrip("/") + "/"
    itens = []
    for wk in semanas:
        for ep in wk["episodios"]:
            if not ep["audio"]:
                continue
            hora = 6 if ep["turno"] == "ida" else 12
            quando = dt.datetime.fromisoformat(ep["data"]).replace(
                hour=hora + 3, minute=ep["ordem"], tzinfo=dt.timezone.utc)
            tamanho = (PUBLIC / ep["audio"]).stat().st_size
            itens.append(f"""    <item>
      <title>{escape(f"S{wk['semana']:02d} · {ep['titulo']}")}</title>
      <guid isPermaLink="false">{ep['id']}</guid>
      <pubDate>{format_datetime(quando)}</pubDate>
      <enclosure url="{escape(base + ep['audio'])}" length="{tamanho}" type="audio/mpeg"/>
      <itunes:duration>{ep['duracao'] or 0}</itunes:duration>
      <description>{escape(f"Semana {wk['semana']} ({wk['nivel']}) — {wk['tema']}")}</description>
    </item>""")
    itens.reverse()
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Commute English</title>
    <link>{escape(base)}</link>
    <language>pt-br</language>
    <description>Inglês para ouvir dirigindo: 15 minutos na ida, 15 na volta.</description>
    <itunes:image href="{escape(base)}icon-512.png"/>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(itens)}
  </channel>
</rss>
"""
    (PUBLIC / "feed.xml").write_text(xml, encoding="utf-8")


if __name__ == "__main__":
    main()
