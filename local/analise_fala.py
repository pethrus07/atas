# -*- coding: utf-8 -*-
"""
Raio-X da Fala — análise PESSOAL/INTERNA do Pedro a partir da transcrição.

Roda localmente depois de transcrever. Analisa só as falas do "Você",
salva um relatório por reunião e acumula um histórico para acompanhar a
evolução. NUNCA sobe para o Worker nem entra no entregável do cliente.

Saída em Projetos/atas/fala-analise/ :
  - historico.jsonl        (uma linha por reunião — fonte de verdade)
  - <stamp>_<titulo>.md    (relatório detalhado da reunião)
  - raio-x.html            (painel com todas as reuniões + tendência)
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
    linhas = [r for r in linhas if r.get("id") != reg["id"]]  # upsert
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
def _nota_vault_md(linhas):
    ult = linhas[-1]["metrics"] if linhas else {}
    def _row(r):
        m = r["metrics"]
        top = ", ".join(list(m["muletas"])[:3]) or "—"
        titulo = str(r["titulo"]).replace("|", "/")
        return (f"| {r['data']} | {titulo} | {m['dur_min']} | {m['share_fala']*100:.0f}% "
                f"| {m['conf_por_min']} | {m['muletas_por_1000']} | {top} |")
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
        f"- Reuniões monitoradas: **{len(linhas)}**", "",
        "## Reunião a reunião (últimas)",
        "| Data | Reunião | Min | Fala | Conf/min | Mul/1k | Top muletas |",
        "|---|---|---|---|---|---|---|", tab, "",
        "## Conexões",
        "- Narrativa e metas: [[fala-e-apresentacao]]",
        "- Ferramenta: [[atas]]", "- Aba: [[MOC-crescimento]]", "",
    ])


def _atualizar_vault(linhas):
    """Best-effort: grava a nota de Fala no vault do Sinapse, se ele existir.
    Vault = env SINAPSE_VAULT, senão ../../sinapse (irmão de atas). Nunca lança."""
    import os
    base = os.environ.get("SINAPSE_VAULT")
    vault = pathlib.Path(base) if base else pathlib.Path(__file__).parents[2] / "sinapse"
    destino = vault / "08-CRESCIMENTO"
    try:
        if not destino.exists():
            return None  # vault ausente nesta máquina → silencioso
        p = destino / "fala-raio-x.md"
        p.write_text(_nota_vault_md(linhas), encoding="utf-8")
        return p
    except Exception:
        return None


def processar(segments, titulo, quando, pasta=None):
    """Analisa, salva relatório .md, atualiza histórico, regenera o painel e
    alimenta o Sinapse. Retorna os caminhos gerados (None nos que falharem)."""
    pasta = pathlib.Path(pasta) if pasta else FALA_DIR
    pasta.mkdir(exist_ok=True)
    metrics = analisar(segments)
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in titulo).strip() or "reuniao"
    reg = {"id": f"{quando}|{titulo}", "data": quando, "titulo": titulo, "safe": safe,
           "metrics": metrics}
    linhas = _upsert_historico(reg, pasta)
    md = _relatorio_md(reg, pasta)
    dash = pasta / "raio-x.html"
    dash.write_text(_dashboard(linhas, pasta), encoding="utf-8")
    vault = _atualizar_vault(linhas)  # alimenta a aba Crescimento Pessoal (best-effort)
    return {"md": md, "dashboard": dash, "metrics": metrics, "vault": vault}
