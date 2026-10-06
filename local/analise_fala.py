# -*- coding: utf-8 -*-
"""
Raio-X da Fala — análise PESSOAL/INTERNA do Pedro a partir da transcrição.

Roda localmente depois de transcrever. Analisa só as falas do "Você",
salva um relatório por reunião e acumula um histórico para acompanhar a
evolução. NUNCA sobe para o Worker nem entra no entregável do cliente.

Saída em Projetos/atas/fala-analise/ (fora do git, só nesta máquina):
  - historico.jsonl        (uma linha por reunião — fonte de verdade)
  - <stamp>_<titulo>.md    (relatório detalhado da reunião)
  - raio-x.html            (painel com todas as reuniões + tendência)

e a nota `sinapse/08-CRESCIMENTO/fala-raio-x.md`, que **não leva o título da reunião**:
título costuma ter nome de cliente ou assunto da Parresia, e o vault é outro
repositório. Na nota cada reunião aparece por data + tipo (v2, 30/09/2026).
"""
import json
import pathlib
import re
from collections import Counter

FALA_DIR = pathlib.Path(__file__).parent.parent / "fala-analise"
_WORD = re.compile(r"[a-zàáâãéêíóôõúûüç]+")

MULETAS = ["aí", "tá", "assim", "cara", "tipo", "então", "pô", "enfim", "sabe",
           "beleza", "basicamente", "literalmente", "exatamente", "praticamente",
           "realmente", "óbvio", "digamos", "mano", "simplesmente", "olha"]
FRASES = ["a gente", "por exemplo", "e aí", "tipo assim", "no caso", "quer dizer",
          "na verdade", "meio que", "ou seja", "é o seguinte", "de certa forma",
          "cada vez mais", "mais ou menos", "e tal"]
TAGS = ["entendeu", "certo", "né", "tá", "não é", "sabe", "correto", "beleza", "saca"]


def _toks(texto):
    return _WORD.findall(texto.lower())


def analisar(segments):
    """Calcula as métricas de fala a partir dos segmentos (speaker/start/text)."""
    voce = [s for s in segments if s.get("speaker") == "Você"]
    outro = [s for s in segments if s.get("speaker") != "Você"]
    blob = " ".join(s.get("text", "") for s in voce).lower()
    pals = _toks(blob)
    total = len(pals) or 1
    pals_outro = sum(len(_toks(s.get("text", ""))) for s in outro)
    dur_min = round(max((s.get("start", 0) for s in segments), default=0) / 60)

    stop = set("""a o e que de do da em um uma os as dos das no na nos nas por para com se eu
    você ele ela nós eles isso isto é são foi ser tem ter vai vou tá está já mais muito bem
    então aí né tipo assim cara certo entendeu sabe pô lá pra pro dele dela como mas ou também
    só até sem sobre entre quando qual quem porque a gente vamos esse essa este esta não sim
    ah eh me te se meu seu sua minha nesse dessa isso aqui ali""".split())
    conteudo = Counter(p for p in pals if p not in stop and len(p) > 2)

    confirm = {t: len(re.findall(r"\b" + re.escape(t) + r"\s*[?.,]", blob)) for t in TAGS}
    confirm = {k: v for k, v in confirm.items() if v > 0}
    conf_total = sum(confirm.values())
    muletas = {m: pals.count(m) for m in MULETAS}
    muletas = {k: v for k, v in sorted(muletas.items(), key=lambda x: -x[1]) if v > 0}
    bordoes = {f: len(re.findall(r"\b" + re.escape(f) + r"\b", blob)) for f in FRASES}
    bordoes = {k: v for k, v in sorted(bordoes.items(), key=lambda x: -x[1]) if v > 0}
    hedge = len(re.findall(r"\bacho que\b", blob))

    return {
        "dur_min": dur_min,
        "turnos_voce": len(voce),
        "turnos_outro": len(outro),
        "palavras_voce": len(pals),
        "palavras_outro": pals_outro,
        "vocab_unico": len(set(pals)),
        "share_fala": round(total / (total + pals_outro), 3) if (total + pals_outro) else 0,
        "conf_total": conf_total,
        "conf_por_min": round(conf_total / dur_min, 2) if dur_min else 0,
        "confirmacoes": dict(sorted(confirm.items(), key=lambda x: -x[1])),
        "muletas_por_1000": round(1000 * sum(muletas.values()) / total, 1),
        "muletas": muletas,
        "bordoes": bordoes,
        "hedge": hedge,
        "top_conteudo": conteudo.most_common(20),
    }


# ── v2.1 (06/10/2026): ritmo, turnos, interrupções, cansaço, voz e metas ─────
# O Pedro pediu "a análise da minha voz, da minha fala" de volta e mais completa. Tudo sai do que
# já existe: os tempos de cada fala (transcrição) e o áudio do microfone (só o canal dele).
_TAGS_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in TAGS) + r")\s*\?\s*$")

METAS_PADRAO = {
    "share_fala": [0.35, 0.55],       # fatia de fala: nem sumir nem dominar
    "conf_por_min": 0.5,              # "entendeu?/certo?" por minuto (era 3,11 em jul; ~0 em ago)
    "muletas_por_1000": 30,           # meta de [[fala-e-apresentacao]]: abaixo de 30, rumo a 20
    "ppm": [130, 180],                # palavras por minuto nos seus turnos: conversa clara sem arrastar
    "maior_monologo_s": 120,          # explicar demais: acima de 2 min sem deixar o outro entrar
}


def _turnos(segments, junta_s=1.5):
    """Funde falas seguidas da mesma pessoa (pausa < junta_s e ninguém no meio) em turnos."""
    out = []
    for s in sorted(segments, key=lambda x: x.get("start", 0)):
        quem = "Você" if s.get("speaker") == "Você" else "outro"
        if out and out[-1]["quem"] == quem and s["start"] - out[-1]["end"] < junta_s:
            out[-1]["end"] = max(out[-1]["end"], s["end"])
            out[-1]["palavras"] += len(_toks(s.get("text", "")))
        else:
            out.append({"quem": quem, "start": s["start"], "end": s["end"],
                        "palavras": len(_toks(s.get("text", "")))})
    return out


def ritmo_e_turnos(segments):
    voce = [s for s in segments if s.get("speaker") == "Você"]
    outro = [s for s in segments if s.get("speaker") != "Você"]
    turnos = _turnos(segments)
    meus = [t for t in turnos if t["quem"] == "Você"]
    # ritmo pelo TURNO (inclui as pausas curtas): é o que o ouvinte sente. Pela soma dos trechos
    # transcritos dava 225 pal/min na reunião de 05/10 — os trechos não contam as pausas.
    fala_s = sum(t["end"] - t["start"] for t in meus)
    pals = sum(t["palavras"] for t in meus)
    maior = max(meus, key=lambda t: t["end"] - t["start"], default=None)
    # interrupção = começar a falar com o outro ainda falando (sobreposição real > 0,5 s)
    def sobrepoe(t, lista):
        return any(o["start"] < t["start"] - 0.5 and o["end"] > t["start"] + 0.5 for o in lista)
    interrompeu = sum(1 for t in meus if sobrepoe(t, outro))
    interrompido = sum(1 for t in turnos if t["quem"] == "outro" and sobrepoe(t, voce))
    # tempo de resposta: do fim da fala do outro até o começo da sua (só quando é você respondendo)
    resp = []
    for a, b in zip(turnos, turnos[1:]):
        if a["quem"] == "outro" and b["quem"] == "Você" and 0 <= b["start"] - a["end"] <= 8:
            resp.append(b["start"] - a["end"])
    perguntas = sum(1 for s in voce if s.get("text", "").strip().endswith("?")
                    and not _TAGS_RE.search(s.get("text", "").lower().strip()))
    return {
        "ppm": round(pals / (fala_s / 60), 1) if fala_s else 0,
        "fala_min": round(fala_s / 60, 1),
        "turnos": len(meus),
        "turno_medio_s": round(sum(t["end"] - t["start"] for t in meus) / len(meus), 1) if meus else 0,
        "maior_monologo_s": round(maior["end"] - maior["start"]) if maior else 0,
        "maior_monologo_em": round(maior["start"]) if maior else None,
        "interrompeu": interrompeu,
        "foi_interrompido": interrompido,
        "resposta_media_s": round(sum(resp) / len(resp), 2) if resp else None,
        "perguntas_reais": perguntas,
    }


def por_bloco(segments, bloco_min=30):
    """As métricas de palavra por bloco de tempo: mostra o cansaço (a reunião de 05/10 foi das 23 h às 2 h)."""
    if not segments:
        return []
    fim = max(s.get("end", 0) for s in segments)
    out, ini = [], 0.0
    while ini < fim:
        bs = [s for s in segments if ini <= s.get("start", 0) < ini + bloco_min * 60]
        voce = [s for s in bs if s.get("speaker") == "Você"]
        if voce:
            m = analisar(bs)
            m["dur_min"] = bloco_min
            m["conf_por_min"] = round(m["conf_total"] / bloco_min, 2)
            r = ritmo_e_turnos(bs)
            out.append({"de_min": round(ini / 60), "ate_min": round(min(ini / 60 + bloco_min, fim / 60)),
                        "palavras": m["palavras_voce"], "conf_por_min": m["conf_por_min"],
                        "muletas_por_1000": m["muletas_por_1000"], "ppm": r["ppm"],
                        "share_fala": m["share_fala"]})
        ini += bloco_min * 60
    return out


def _pcm_do_audio(caminho):
    """int16 mono 16 kHz do canal do microfone: o .pcm da gravação (memória mapeada) ou, depois de
    aposentado, o .opus decodificado pelo ffmpeg. None se não houver como ler."""
    import numpy as np
    import shutil
    import subprocess
    p = pathlib.Path(caminho) if caminho else None
    if not p or not p.exists():
        return None
    if p.suffix == ".pcm":
        return np.memmap(p, dtype=np.int16, mode="r")
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    r = subprocess.run([ff, "-v", "error", "-i", str(p), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.int16) if r.returncode == 0 and r.stdout else None


def voz(segments, caminho_mic, sr=16000, max_min=20):
    """Volume e entonação da SUA voz, medidos no áudio do microfone, só nos trechos em que você fala.
    Amostra até `max_min` minutos espalhados pela reunião (3 h de áudio inteiro é desperdício).
    Entonação = variação do tom em semitons: perto de 1 soa monótono; 2 a 4, fala viva."""
    import numpy as np
    x = _pcm_do_audio(caminho_mic)
    if x is None or len(x) < sr:
        return None
    voce = [s for s in segments if s.get("speaker") == "Você" and s["end"] - s["start"] >= 1.0]
    if not voce:
        return None
    total = sum(s["end"] - s["start"] for s in voce)
    passo = max(1, int(total / (max_min * 60)))
    amostra = voce[::passo]
    janela, salto = int(0.04 * sr), int(0.02 * sr)
    db, f0 = [], []
    lag_min, lag_max = sr // 400, sr // 75                    # tom de voz entre 75 e 400 Hz
    for s in amostra:
        seg = np.asarray(x[int(s["start"] * sr):int(s["end"] * sr)], dtype=np.float32) / 32768.0
        if len(seg) < janela:
            continue
        n = 1 + (len(seg) - janela) // salto
        idx = np.arange(janela)[None, :] + salto * np.arange(n)[:, None]
        q = seg[idx] * np.hanning(janela)
        rms = np.sqrt((q ** 2).mean(axis=1)) + 1e-9
        d = 20 * np.log10(rms)
        voz_on = d > (np.percentile(d, 60) if len(d) > 4 else d.min())   # só os quadros com voz
        db.extend(d[voz_on].tolist())
        espec = np.fft.rfft(q[voz_on], n=2 * janela)
        ac = np.fft.irfft(np.abs(espec) ** 2)[:, :janela]
        ac = ac / (ac[:, :1] + 1e-12)
        faixa = ac[:, lag_min:lag_max]
        lag = faixa.argmax(axis=1) + lag_min
        sonoro = faixa.max(axis=1) > 0.45                     # periodicidade clara = vogal
        f0.extend((sr / lag[sonoro]).tolist())
    if len(db) < 50 or len(f0) < 50:
        return None
    db, f0 = np.array(db), np.array(f0)
    med = float(np.median(f0))
    st = 12 * np.log2(f0 / med)
    st = st[np.abs(st) < 12]                                  # erro de oitava fora
    return {"volume_db": round(float(np.median(db)), 1),
            "volume_variacao_db": round(float(np.std(db)), 1),
            "tom_hz": round(med),
            "entonacao_st": round(float(np.std(st)), 2),
            "amostra_min": round(sum(s["end"] - s["start"] for s in amostra) / 60, 1)}


def avaliar_metas(m, metas=None):
    """[(métrica, valor, meta em texto, ok?)] para o relatório, o painel e a janela."""
    mt = {**METAS_PADRAO, **(metas or {})}
    r = m.get("ritmo") or {}
    linhas = []
    lo, hi = mt["share_fala"]
    linhas.append(("Fatia de fala", f"{m['share_fala']*100:.0f}%", f"{lo*100:.0f}% a {hi*100:.0f}%",
                   lo <= m["share_fala"] <= hi))
    linhas.append(("Confirmações por minuto", m["conf_por_min"], f"até {mt['conf_por_min']}",
                   m["conf_por_min"] <= mt["conf_por_min"]))
    linhas.append(("Muletas a cada 1000 palavras", m["muletas_por_1000"], f"até {mt['muletas_por_1000']}",
                   m["muletas_por_1000"] <= mt["muletas_por_1000"]))
    if r.get("ppm"):
        a, b = mt["ppm"]
        linhas.append(("Ritmo (palavras por minuto)", r["ppm"], f"{a} a {b}", a <= r["ppm"] <= b))
    if r.get("maior_monologo_s") is not None:
        linhas.append(("Maior monólogo", f"{r['maior_monologo_s']} s", f"até {mt['maior_monologo_s']} s",
                       r["maior_monologo_s"] <= mt["maior_monologo_s"]))
    return linhas


def _mmss(s):
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def _stamp(quando):
    return re.sub(r"[^0-9]", "", quando)[:12] or "000000000000"


def _upsert_historico(reg, pasta):
    hist_path = pasta / "historico.jsonl"
    linhas = []
    if hist_path.exists():
        for ln in hist_path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                linhas.append(json.loads(ln))
            except Exception:
                pass
    # Upsert pela chave data|título: reprocessar a mesma reunião corrige a linha
    # em vez de duplicá-la, senão a tendência do painel ficaria torta.
    linhas = [r for r in linhas if r.get("id") != reg["id"]]
    linhas.append(reg)
    linhas.sort(key=lambda r: r.get("data", ""))
    hist_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in linhas) + "\n",
        encoding="utf-8",
    )
    return linhas


def _relatorio_md(reg, pasta):
    m = reg["metrics"]
    L = [f"# Raio-X da Fala — {reg['titulo']}", "",
         f"_{reg['data']} · {m['dur_min']} min · USO INTERNO (não enviar ao cliente)_", "",
         "## Panorama",
         f"- Suas falas: **{m['turnos_voce']}** turnos / **{m['palavras_voce']}** palavras "
         f"(**{m['share_fala']*100:.0f}%** da reunião)",
         f"- Vocabulário único: {m['vocab_unico']}",
         f"- Pedidos de confirmação: **{m['conf_total']}** (~{m['conf_por_min']}/min)",
         f"- Muletas: {m['muletas_por_1000']} a cada 1000 palavras",
         f"- Hedge ('acho que'): {m['hedge']}", "",
         "## Perguntas-muleta (confirmação)"]
    for k, v in m["confirmacoes"].items():
        L.append(f"- {k}? — {v}")
    L += ["", "## Muletas (palavra solta)"]
    for k, v in m["muletas"].items():
        L.append(f"- {k} — {v}")
    L += ["", "## Bordões (frase)"]
    for k, v in m["bordoes"].items():
        L.append(f"- {k} — {v}")
    L += ["", "## Palavras de conteúdo mais repetidas"]
    for k, v in m["top_conteudo"]:
        L.append(f"- {k} — {v}")
    r = m.get("ritmo")
    if r:
        L += ["", "## Ritmo e turnos",
              f"- Ritmo: **{r['ppm']}** palavras por minuto de fala ({r['fala_min']} min falando)",
              f"- Turnos: {r['turnos']} · turno médio {r['turno_medio_s']} s · maior monólogo "
              f"**{r['maior_monologo_s']} s** (em {_mmss(r['maior_monologo_em'])})",
              f"- Interrupções: você interrompeu **{r['interrompeu']}** vezes; foi interrompido {r['foi_interrompido']}",
              f"- Tempo médio para responder: {r['resposta_media_s']} s" if r.get("resposta_media_s") is not None
              else "- Tempo médio para responder: —",
              f"- Perguntas de verdade (sem contar \"entendeu?\"): {r['perguntas_reais']}"]
    if m.get("blocos"):
        L += ["", "## Ao longo da reunião (cansaço)", "", "| Trecho | Fala | Ritmo | Conf/min | Mul/1k |",
              "|---|---|---|---|---|"]
        for b in m["blocos"]:
            L.append(f"| {b['de_min']}–{b['ate_min']} min | {b['share_fala']*100:.0f}% | {b['ppm']} | "
                     f"{b['conf_por_min']} | {b['muletas_por_1000']} |")
    v = m.get("voz")
    if v:
        L += ["", "## Voz (áudio do microfone)",
              f"- Volume mediano: {v['volume_db']} dBFS (variação {v['volume_variacao_db']} dB)",
              f"- Tom mediano: {v['tom_hz']} Hz",
              f"- Entonação: **{v['entonacao_st']} semitons** de variação "
              "(perto de 1 soa monótono; 2 a 4 é fala viva)",
              f"- Amostra: {v['amostra_min']} min das suas falas, espalhados pela reunião"]
    if m.get("metas"):
        L += ["", "## Metas", "", "| | Agora | Meta | |", "|---|---|---|---|"]
        for nome, val, meta, ok in m["metas"]:
            L.append(f"| {nome} | {val} | {meta} | {'✅' if ok else '⚠️'} |")
    p = pasta / f"{_stamp(reg['data'])}_{reg['safe']}.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _dashboard(linhas, pasta):
    """Painel HTML (RYZE, interno) com todas as reuniões + tendência das KPIs."""
    def bars(vals, fmt, cor):
        mx = max(vals) if vals else 1
        mx = mx or 1
        out = []
        for v in vals:
            h = max(4, round(46 * v / mx))
            out.append(f'<div class="bar" style="height:{h}px;background:{cor}" '
                       f'title="{fmt(v)}"></div>')
        return f'<div class="spark">{"".join(out)}</div>'

    share = [r["metrics"]["share_fala"] for r in linhas]
    conf = [r["metrics"]["conf_por_min"] for r in linhas]
    ult = linhas[-1]["metrics"] if linhas else {}

    rows = ""
    for r in linhas:
        m = r["metrics"]
        top_mul = ", ".join(f"{k} ({v})" for k, v in list(m["muletas"].items())[:3]) or "—"
        rows += (f"<tr><td>{_esc(r['data'])}</td><td>{_esc(r['titulo'])}</td>"
                 f"<td class='n'>{m['dur_min']}</td>"
                 f"<td class='n'>{m['share_fala']*100:.0f}%</td>"
                 f"<td class='n'>{m['conf_por_min']}</td>"
                 f"<td class='n'>{m['muletas_por_1000']}</td>"
                 f"<td class='mul'>{_esc(top_mul)}</td></tr>")

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>Raio-X da Fala — RYZE (interno)</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#0D0D0D;color:#EBEBEB;font-family:'Plus Jakarta Sans',sans-serif;line-height:1.6}}
.wrap{{max-width:960px;margin:0 auto;padding:34px 24px 60px}}
.top{{display:flex;align-items:center;gap:12px;margin-bottom:6px}}
.top svg{{height:30px}}.top .wm{{font-family:'Space Grotesk';font-weight:700;letter-spacing:4px;font-size:15px}}
.badge{{margin-left:auto;font-family:'JetBrains Mono';font-size:10px;letter-spacing:1.5px;text-transform:uppercase;
  color:#FFD666;border:1px solid rgba(255,183,0,.3);padding:4px 10px;border-radius:20px}}
h1{{font-family:'Space Grotesk';font-weight:700;font-size:28px;letter-spacing:-.5px;margin:14px 0 2px}}
.sub{{color:#8A8A8A;font-size:13px;margin-bottom:28px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:26px}}
.kpi{{background:#171717;border:1px solid #262626;border-radius:14px;padding:18px}}
.kpi .lb{{font-family:'JetBrains Mono';font-size:9.5px;letter-spacing:1.5px;text-transform:uppercase;color:#CC9200}}
.kpi .vl{{font-family:'Space Grotesk';font-weight:700;font-size:30px;color:#fff;margin-top:6px}}
.kpi .spark{{display:flex;align-items:flex-end;gap:3px;height:48px;margin-top:12px}}
.bar{{flex:1;border-radius:2px;min-width:5px}}
.kpi .hint{{font-size:11px;color:#6B6B6B;margin-top:8px}}
table{{width:100%;border-collapse:collapse;font-size:13px;background:#171717;border:1px solid #262626;border-radius:12px;overflow:hidden}}
thead th{{background:#000;color:#FFB700;font-family:'JetBrains Mono';font-size:9.5px;letter-spacing:1px;text-transform:uppercase;padding:11px 12px;text-align:left}}
td{{padding:11px 12px;border-bottom:1px solid #222;vertical-align:top;color:#D4D4D4}}
tr:last-child td{{border-bottom:none}}
td.n{{font-family:'JetBrains Mono';text-align:right;white-space:nowrap;color:#fff}}
td.mul{{color:#8A8A8A;font-size:12px}}
.foot{{color:#525252;font-size:11px;font-family:'JetBrains Mono';margin-top:22px}}
h2{{font-family:'Space Grotesk';font-size:16px;margin:32px 0 12px}}
</style></head><body><div class="wrap">
<div class="top">
  <svg viewBox="0 0 400 520" xmlns="http://www.w3.org/2000/svg"><path d="M308.484 282.06L244.072 357.593H211L231.18 392H350.77L400 520H244.159L171.652 352.605L177.931 342.661L225 254.736L211.896 226.997L191.439 180.558L159.957 267.483L127.315 354.301L112.868 394.729H139.992L194.254 520H0L200 0L308.484 282.06Z" fill="#FFB700"/></svg>
  <span class="wm">RYZE</span><span class="badge">Uso interno</span>
</div>
<h1>Raio-X da Fala</h1>
<div class="sub">Como você fala nas reuniões — evolução ao longo do tempo. Dado pessoal, nunca vai ao cliente.</div>
<div class="kpis">
  <div class="kpi"><div class="lb">Sua fatia de fala</div><div class="vl">{ult.get('share_fala',0)*100:.0f}%</div>
    {bars(share, lambda v:f"{v*100:.0f}%", "#FFB700")}<div class="hint">meta: aproximar de 50%</div></div>
  <div class="kpi"><div class="lb">Confirmações / min</div><div class="vl">{ult.get('conf_por_min',0)}</div>
    {bars(conf, lambda v:str(v), "#8B5CF6")}<div class="hint">"entendeu? / certo?" — quanto menor, melhor</div></div>
  <div class="kpi"><div class="lb">Muletas / 1000 palavras</div><div class="vl">{ult.get('muletas_por_1000',0)}</div>
    <div class="hint">aí, tá, tipo, cara…</div></div>
  <div class="kpi"><div class="lb">Ritmo (palavras/min)</div><div class="vl">{(ult.get('ritmo') or {}).get('ppm','—')}</div>
    <div class="hint">maior monólogo: {(ult.get('ritmo') or {}).get('maior_monologo_s','—')} s · interrompeu {(ult.get('ritmo') or {}).get('interrompeu','—')}×</div></div>
  <div class="kpi"><div class="lb">Entonação (semitons)</div><div class="vl">{(ult.get('voz') or {}).get('entonacao_st','—')}</div>
    <div class="hint">perto de 1 soa monótono; 2 a 4 é fala viva</div></div>
  <div class="kpi"><div class="lb">Reuniões monitoradas</div><div class="vl">{len(linhas)}</div>
    <div class="hint">o painel cresce a cada ata</div></div>
</div>
<h2>Reunião a reunião</h2>
<table><thead><tr><th>Data</th><th>Reunião</th><th>Min</th><th>Sua fala</th><th>Conf/min</th><th>Mul/1k</th><th>Top muletas</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="foot">Gerado localmente · fala-analise/ · não sincronizado · RYZE</div>
</div></body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Alimenta o segundo cérebro (Sinapse): escreve uma nota AUTO-gerada de Fala no
# vault a cada reunião → aba Crescimento Pessoal. A narrativa/metas ficam na nota
# escrita à mão (fala-e-apresentacao); esta é só o retrato de dados, sobrescrevível.
_TIPO_ROTULO = {"cliente": "cliente", "parresia": "Parresia", "carreira": "carreira",
                "pessoal": "pessoal/estudo"}


def _nota_vault_md(linhas):
    ult = linhas[-1]["metrics"] if linhas else {}
    def _row(r):
        m = r["metrics"]
        top = ", ".join(list(m["muletas"])[:3]) or "—"
        tipo = _TIPO_ROTULO.get(r.get("tipo"), "—")
        ppm = (m.get("ritmo") or {}).get("ppm") or "—"
        return (f"| {str(r['data'])[:16]} | {tipo} | {m['dur_min']} | {m['share_fala']*100:.0f}% "
                f"| {m['conf_por_min']} | {m['muletas_por_1000']} | {ppm} | {top} |")
    tab = "\n".join(_row(r) for r in linhas[-8:])
    return "\n".join([
        "---", "tipo: nota", "area: crescimento",
        "tags: [comunicacao, fala, raio-x, auto-gerado]", "status: em-progresso",
        f"atualizado: {linhas[-1]['data'] if linhas else ''}", "---", "",
        "# 📈 Raio-X da Fala (auto)", "",
        "> ⚙️ **Nota auto-gerada** pelo sistema [[atas]] a cada reunião — não editar à mão. "
        "A narrativa e as metas ficam em [[fala-e-apresentacao]]. Dado pessoal, nunca vai ao cliente.", "",
        "## Agora",
        f"- Fatia de fala: **{ult.get('share_fala', 0)*100:.0f}%** (meta ~50%)",
        f"- Confirmações/min: **{ult.get('conf_por_min', 0)}** (menor = melhor)",
        f"- Muletas / 1000 palavras: **{ult.get('muletas_por_1000', 0)}**",
        f"- Ritmo: **{(ult.get('ritmo') or {}).get('ppm', '—')}** palavras/min · maior monólogo "
        f"**{(ult.get('ritmo') or {}).get('maior_monologo_s', '—')} s** · interrompeu "
        f"**{(ult.get('ritmo') or {}).get('interrompeu', '—')}** vezes",
        (f"- Voz: entonação **{ult['voz']['entonacao_st']} semitons** (perto de 1 = monótono)"
         if ult.get("voz") else "- Voz: sem áudio do microfone nesta reunião"),
        f"- Reuniões monitoradas: **{len(linhas)}**", "",
        "## Reunião a reunião (últimas)",
        "| Data | Tipo | Min | Fala | Conf/min | Mul/1k | Ritmo | Top muletas |",
        "|---|---|---|---|---|---|---|---|", tab, "",
        "## Conexões",
        "- Narrativa e metas: [[fala-e-apresentacao]]",
        "- Ferramenta: [[atas]]", "- Aba: [[MOC-crescimento]]", "",
    ])


def _atualizar_vault(linhas):
    """Grava a nota de Fala no vault do Sinapse, se ele existir.
    Vault = env SINAPSE_VAULT, senão ../../sinapse (irmão de atas). Devolve o caminho,
    None se o vault não existe nesta máquina; um erro de escrita LEVANTA (a etapa
    raio_x do pipeline registra) — na v1 era engolido em silêncio."""
    import os
    base = os.environ.get("SINAPSE_VAULT")
    vault = pathlib.Path(base) if base else pathlib.Path(__file__).parents[2] / "sinapse"
    destino = vault / "08-CRESCIMENTO"
    if not destino.exists():
        return None  # vault ausente nesta máquina
    p = destino / "fala-raio-x.md"
    p.write_text(_nota_vault_md(linhas), encoding="utf-8")
    return p


def processar(segments, titulo, quando, pasta=None, tipo=None, sessao_id=None, vault=True,
              audio_mic=None, metas=None):
    """Analisa, salva relatório .md, atualiza histórico, regenera o painel e
    alimenta o Sinapse. Retorna os caminhos gerados (vault=None se não gravou).
    v2.1: ritmo/turnos/interrupções, blocos de 30 min, voz (se `audio_mic` existir) e metas."""
    pasta = pathlib.Path(pasta) if pasta else FALA_DIR
    pasta.mkdir(exist_ok=True)
    metrics = analisar(segments)
    metrics["ritmo"] = ritmo_e_turnos(segments)
    metrics["blocos"] = por_bloco(segments) if metrics["dur_min"] >= 45 else []
    try:
        metrics["voz"] = voz(segments, audio_mic) if audio_mic else None
    except Exception as e:                       # voz é bônus: nunca derruba o Raio-X
        metrics["voz"] = None
        metrics["voz_erro"] = f"{type(e).__name__}: {e}"
    metrics["metas"] = avaliar_metas(metrics, metas)
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in titulo).strip() or "reuniao"
    reg = {"id": sessao_id or f"{quando}|{titulo}", "data": quando, "titulo": titulo,
           "safe": safe, "tipo": tipo, "metrics": metrics}
    linhas = _upsert_historico(reg, pasta)
    md = _relatorio_md(reg, pasta)
    dash = pasta / "raio-x.html"
    dash.write_text(_dashboard(linhas, pasta), encoding="utf-8")
    nota = _atualizar_vault(linhas) if vault else None
    return {"md": md, "dashboard": dash, "metrics": metrics, "vault": nota}


def reescrever_nota(pasta=None, tipos=None):
    """Regrava a nota do vault a partir do histórico, completando o `tipo` das
    linhas antigas com `tipos` ({id_do_historico: tipo}). Usado na migração v2."""
    pasta = pathlib.Path(pasta) if pasta else FALA_DIR
    hist = pasta / "historico.jsonl"
    if not hist.exists():
        return None
    linhas = [json.loads(ln) for ln in hist.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for r in linhas:
        if tipos and not r.get("tipo") and r.get("id") in tipos:
            r["tipo"] = tipos[r["id"]]
    hist.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in linhas) + "\n",
                    encoding="utf-8")
    return _atualizar_vault(linhas)
