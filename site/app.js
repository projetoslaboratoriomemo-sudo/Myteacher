(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const DIAS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
  const VELOCIDADES = [1, 0.9, 0.8, 1.1];

  // ---------- armazenamento local (protegido contra navegadores que bloqueiam) ----------
  const store = {
    get(k, d) { try { const v = localStorage.getItem("ce:" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("ce:" + k, JSON.stringify(v)); } catch {} },
  };
  let feitos = new Set(store.get("feitos", []));
  let velocidade = store.get("velocidade", 1);
  let semanas = [], episodios = [], atual = null;

  const fmt = (s) => {
    s = Math.max(0, Math.round(s || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };
  const dataCurta = (iso) => {
    const d = new Date(iso + "T12:00:00");
    return `${DIAS[d.getDay()]}, ${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
  };

  async function carregar() {
    try {
      const r = await fetch("episodes.json", { cache: "no-store" });
      const dados = await r.json();
      semanas = dados.semanas || [];
    } catch (e) {
      $("ep-semana").textContent = "Não consegui carregar os episódios";
      $("ep-titulo").textContent = "Verifique a conexão e recarregue a página.";
      return;
    }
    episodios = semanas.flatMap((s) => s.episodios).filter((e) => e.audio);
    if (!episodios.length) {
      $("ep-semana").textContent = "Ainda não há episódios";
      $("ep-titulo").textContent = "A primeira semana será gerada em breve.";
      $("play").disabled = true;
      return;
    }
    const salvo = store.get("atual", null);
    const proximo = episodios.find((e) => !feitos.has(e.id));
    selecionar((salvo && !feitos.has(salvo) && episodios.find((e) => e.id === salvo)) || proximo || episodios[episodios.length - 1]);
    desenharLista();
  }

  function selecionar(ep, tocar = false) {
    if (!ep) return;
    atual = ep;
    store.set("atual", ep.id);
    const sem = semanas.find((s) => s.semana === ep.semana);
    $("ep-semana").textContent = `Semana ${ep.semana} · ${sem.nivel} · ${sem.tema}`;
    $("ep-titulo").textContent = ep.titulo;
    $("ep-info").textContent = `Programado para ${dataCurta(ep.data)} · ${fmt(ep.duracao)}`;
    audio.src = ep.audio;
    audio.playbackRate = velocidade;
    const pos = store.get("pos:" + ep.id, 0);
    audio.addEventListener("loadedmetadata", function f() {
      audio.removeEventListener("loadedmetadata", f);
      if (pos > 5 && pos < audio.duration - 10) audio.currentTime = pos;
      audio.playbackRate = velocidade;
    });
    atualizarFeito();
    mediaSession();
    desenharLista();
    if (tocar) audio.play().catch(() => {});
  }

  function relativo(delta) {
    const i = episodios.indexOf(atual) + delta;
    if (i >= 0 && i < episodios.length) selecionar(episodios[i]);
  }

  function marcar(ep, valor) {
    valor ? feitos.add(ep.id) : feitos.delete(ep.id);
    store.set("feitos", [...feitos]);
    atualizarFeito();
    desenharLista();
  }

  function atualizarFeito() {
    const ok = atual && feitos.has(atual.id);
    $("feito").classList.toggle("marcado", !!ok);
    $("feito").textContent = ok ? "✓ Ouvido" : "✓ Já ouvi";
    const total = semanas.reduce((n, s) => n + s.episodios.length, 0);
    $("progresso-geral").textContent = `${feitos.size} de ${total} episódios`;
  }

  // ---------- lista de semanas ----------
  function desenharLista() {
    const cont = $("semanas");
    const abertas = new Set([...cont.querySelectorAll("details[open]")].map((d) => d.dataset.s));
    cont.innerHTML = "";
    [...semanas].reverse().forEach((s) => {
      const det = document.createElement("details");
      det.dataset.s = s.semana;
      if (abertas.has(String(s.semana)) || (atual && atual.semana === s.semana)) det.open = true;
      const feitosSem = s.episodios.filter((e) => feitos.has(e.id)).length;
      det.innerHTML = `<summary><span><span class="tema">Semana ${s.semana}: ${esc(s.tema)}</span><br>
        <span class="miudo">${esc(s.nivel)} · ${esc(s.foco)}</span></span>
        <span class="miudo">${feitosSem}/${s.episodios.length}</span></summary>`;
      s.episodios.forEach((e) => {
        const row = document.createElement("div");
        row.className = "ep" + (atual && atual.id === e.id ? " atual" : "");
        row.innerHTML = `<span class="check">${feitos.has(e.id) ? "✓" : ""}</span>
          <button class="nome" ${e.audio ? "" : "disabled"}>${esc(e.titulo)}</button>
          <span class="dur">${e.audio ? fmt(e.duracao) : "arquivado"}</span>
          <button class="rot">roteiro</button>`;
        row.querySelector(".nome").onclick = () => { selecionar(e); window.scrollTo({ top: 0, behavior: "smooth" }); };
        row.querySelector(".rot").onclick = () => abrirRoteiro(e);
        det.appendChild(row);
      });
      cont.appendChild(det);
    });
  }

  function abrirRoteiro(e) {
    $("dlg-titulo").textContent = e.titulo;
    $("dlg-corpo").innerHTML = e.roteiro.map((l) => l.v === "narrador"
      ? `<p class="pt">${esc(l.txt)}</p>`
      : `<p class="en" data-v="${l.v === "professor" ? "EN" : l.v}">${esc(l.txt)}</p>`).join("");
    $("dlg-roteiro").showModal();
  }
  $("dlg-fechar").onclick = () => $("dlg-roteiro").close();

  function esc(t) {
    return String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  // ---------- controles ----------
  $("play").onclick = () => (audio.paused ? audio.play() : audio.pause());
  $("voltar10").onclick = () => (audio.currentTime = Math.max(0, audio.currentTime - 10));
  $("avancar10").onclick = () => (audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 10));
  $("anterior").onclick = () => relativo(-1);
  $("proximo").onclick = () => relativo(1);
  $("feito").onclick = () => atual && marcar(atual, !feitos.has(atual.id));
  $("velocidade").textContent = velocidade + "×";
  $("velocidade").onclick = () => {
    velocidade = VELOCIDADES[(VELOCIDADES.indexOf(velocidade) + 1) % VELOCIDADES.length];
    audio.playbackRate = velocidade;
    store.set("velocidade", velocidade);
    $("velocidade").textContent = velocidade + "×";
  };
  $("seek").oninput = (e) => { if (audio.duration) audio.currentTime = (e.target.value / 100) * audio.duration; };

  let ultimoSalvo = 0;
  audio.addEventListener("timeupdate", () => {
    if (!audio.duration) return;
    $("seek").value = (audio.currentTime / audio.duration) * 100;
    $("t-atual").textContent = fmt(audio.currentTime);
    $("t-total").textContent = fmt(audio.duration);
    if (Math.abs(audio.currentTime - ultimoSalvo) > 5) {
      ultimoSalvo = audio.currentTime;
      store.set("pos:" + atual.id, audio.currentTime);
    }
    if ("mediaSession" in navigator && navigator.mediaSession.setPositionState) {
      try { navigator.mediaSession.setPositionState({ duration: audio.duration, position: audio.currentTime, playbackRate: audio.playbackRate }); } catch {}
    }
  });
  const iconePlay = (tocando) => {
    $("ico-play").hidden = tocando;
    $("ico-pause").hidden = !tocando;
    $("play").setAttribute("aria-label", tocando ? "Pausar" : "Tocar");
  };
  audio.addEventListener("play", () => iconePlay(true));
  audio.addEventListener("pause", () => { iconePlay(false); if (atual) store.set("pos:" + atual.id, audio.currentTime); });
  audio.addEventListener("ended", () => {
    store.set("pos:" + atual.id, 0);
    marcar(atual, true);
    relativo(1); // carrega o próximo, sem tocar sozinho
  });

  function mediaSession() {
    if (!("mediaSession" in navigator) || !atual) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: atual.titulo, artist: `Commute English · Semana ${atual.semana}`,
      artwork: [{ src: "icon-512.png", sizes: "512x512", type: "image/png" }],
    });
    const h = {
      play: () => audio.play(), pause: () => audio.pause(),
      seekbackward: () => $("voltar10").onclick(), seekforward: () => $("avancar10").onclick(),
      previoustrack: () => $("voltar10").onclick(), // no volante, "anterior" volta 10s (mais útil dirigindo)
      nexttrack: () => $("avancar10").onclick(),
    };
    for (const [k, fn] of Object.entries(h)) { try { navigator.mediaSession.setActionHandler(k, fn); } catch {} }
  }

  $("copiar-feed").onclick = async () => {
    const url = new URL("feed.xml", location.href).href;
    try { await navigator.clipboard.writeText(url); $("copiar-feed").textContent = "Link copiado!"; }
    catch { prompt("Copie o link do podcast:", url); }
  };

  carregar();
})();
