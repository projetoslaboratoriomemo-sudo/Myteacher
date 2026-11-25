# Commute English

Curso de inglês para ouvir dirigindo: **15 minutos na ida e 15 na volta**, de segunda a sexta.
Toda semana o GitHub gera sozinho os roteiros novos (Gemini), transforma em áudio (vozes neurais
gratuitas) e publica num site que funciona como player no celular. Custo: zero.

## Como funciona cada semana

| Dia | Ida (15 min) | Volta (15 min) |
|---|---|---|
| Seg–Qui | revisão espaçada → cena nova (normal e lenta) → desmontagem pergunta/pausa/resposta → shadowing → pergunta para a volta | resposta da pergunta → só inglês → variações → cena de novo → desafio livre |
| Sexta | revisão de todas as frases da semana + algumas antigas | você interpreta um dos papéis nas 4 cenas |

As frases antigas voltam na véspera, depois de 1 semana, de ~3 semanas e de ~7 semanas (repetição espaçada).
O conteúdo segue `curriculum/syllabus.json` (12 semanas, do A1 ao B1). A partir da semana 13
o próprio Gemini planeja as semanas seguintes, subindo o nível.

## Colocar no ar (uma vez só, uns 10 minutos)

1. **Chave do Gemini:** entre em <https://aistudio.google.com/apikey> e crie uma API key
   (o nível gratuito basta; a assinatura do app Gemini é separada da API).
2. **Repositório:** crie um repositório **público** no GitHub (ex.: `commute-english`) e envie
   todos estes arquivos para a branch `main`.
3. **Secret:** no repositório, *Settings → Secrets and variables → Actions → New repository secret*.
   Nome: `GEMINI_API_KEY`. Valor: a chave do passo 1.
4. **Pages:** *Settings → Pages → Build and deployment → Source:* **GitHub Actions**.
5. **Primeira execução:** aba *Actions → Gerar e publicar episódios → Run workflow*.
   Leva uns 10–20 minutos na primeira vez (gera os roteiros e todos os áudios).
6. O link do site aparece no fim da execução (algo como `https://SEU-USUARIO.github.io/commute-english/`).
   No celular, abra e use *Adicionar à tela de início* para virar um app.

Daí em diante, todo **sábado de manhã** a semana seguinte é gerada e publicada sozinha.
Se o sábado falhar (ex.: limite do Gemini), o domingo tenta de novo.

## No carro

- Abra o site e dê o play **antes de sair**. O áudio continua com a tela bloqueada.
- O site já abre no próximo episódio que você não ouviu. Ao terminar, ele marca como ouvido e
  deixa o próximo pronto.
- Botões do volante: avançar/voltar pulam 10 segundos.
- Prefere app de podcast? Toque em *Copiar link do podcast* e adicione o feed no Pocket Casts,
  Apple Podcasts etc. (Spotify não aceita feed direto.)

## Personalizar

- `config.json`: seu nome (o narrador te cumprimenta), nível, contexto profissional, vozes,
  quantas semanas de áudio ficam no ar (`semanas_com_audio`) e duração alvo.
- `curriculum/syllabus.json`: temas, foco gramatical e cenas de cada semana.
- Vozes disponíveis do edge-tts: rode `edge-tts --list-voices` (ex.: `pt-BR-FranciscaNeural`,
  `en-GB-RyanNeural` se quiser sotaque britânico).
- Qualquer alteração enviada ao GitHub dispara uma nova publicação.

## Testar no computador (opcional)

```bash
pip install -r requirements.txt        # precisa também do ffmpeg instalado
export GEMINI_API_KEY=sua_chave
python scripts/generate_week.py        # ou --mock para testar sem chave
python scripts/render_audio.py         # ou --mock para testar sem internet
python scripts/build_site.py
python -m http.server -d public 8000   # abra http://localhost:8000
```

## Estrutura

```
config.json                 preferências do curso e vozes
curriculum/syllabus.json    plano das 12 primeiras semanas
data/weeks/semana-NN.json   roteiros gerados (ficam guardados no repositório)
scripts/generate_week.py    pede ao Gemini o conteúdo das semanas que faltam
scripts/episodes.py         monta cada episódio: pausas, repetição espaçada, duração alvo
scripts/render_audio.py     gera os MP3 (edge-tts; se falhar, Piper)
scripts/build_site.py       monta o site, a lista de episódios e o feed do podcast
site/                       o player (HTML, CSS, JS)
.github/workflows/          a automação semanal
```

## Observações

- O **edge-tts** usa as vozes neurais da Microsoft de forma não oficial. Se um dia parar de
  funcionar, o projeto troca sozinho para o **Piper** (voz open-source, um pouco mais robótica).
- No nível gratuito, o Google pode usar as requisições ao Gemini para melhorar os produtos dele.
- Só os áudios das últimas 3 semanas ficam no site (para não estourar o limite do GitHub Pages).
  Os roteiros de todas as semanas continuam disponíveis no botão "roteiro".
