"""Caminhos, configuração e utilidades compartilhadas."""
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
SYLLABUS_PATH = ROOT / "curriculum" / "syllabus.json"
DATA = ROOT / "data"
WEEKS_DIR = DATA / "weeks"
STATE_PATH = DATA / "state.json"
PUBLIC = ROOT / "public"
SITE_SRC = ROOT / "site"
TTS_CACHE = ROOT / ".tts-cache"

DIAS_PT = ["segunda", "terça", "quarta", "quinta", "sexta"]


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def config():
    return load_json(CONFIG_PATH)


def syllabus():
    return load_json(SYLLABUS_PATH, {"semanas": []})["semanas"]


def today():
    # Horário de Brasília, sem depender de pytz
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).date()


def state():
    """Guarda a data de início do curso (segunda-feira da semana 1)."""
    st = load_json(STATE_PATH)
    if st is None:
        t = today()
        # Sábado/domingo: começa na próxima segunda. Durante a semana: na segunda desta semana.
        if t.weekday() >= 5:
            start = t + dt.timedelta(days=7 - t.weekday())
        else:
            start = t - dt.timedelta(days=t.weekday())
        st = {"inicio": start.isoformat()}
        save_json(STATE_PATH, st)
    return st


def week_monday(n):
    start = dt.date.fromisoformat(state()["inicio"])
    return start + dt.timedelta(days=7 * (n - 1))


def week_path(n):
    return WEEKS_DIR / f"semana-{n:02d}.json"


def existing_weeks():
    return sorted(int(p.stem.split("-")[1]) for p in WEEKS_DIR.glob("semana-*.json"))


def load_week(n):
    return load_json(week_path(n))


def all_phrases(upto_week=None):
    """Todas as frases já ensinadas: lista de dicts com en, pt, semana, dia."""
    out = []
    for n in existing_weeks():
        if upto_week is not None and n > upto_week:
            continue
        wk = load_week(n)
        for day in wk["dias"]:
            for ph in day["frases"]:
                out.append({**ph, "semana": n, "dia": day["dia"]})
    return out
