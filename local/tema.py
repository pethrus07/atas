# -*- coding: utf-8 -*-
"""
Tema RYZE escuro de tudo que o Atas mostra (v2.2, pedido do Pedro em 06/10/2026: "tema escuro,
RYZE branded, tudo — do resumo às análises"). Ata interna, entregável do cliente, Raio-X da Fala e
avaliação interna usam os MESMOS tokens, para parecerem um produto só.

Identidade RYZE: preto #0D0D0D (base), dourado #FFB700 (destaque), roxo #6A28C9 (tecnologia);
Space Grotesk (títulos), Plus Jakarta Sans (corpo), JetBrains Mono (rótulos e números).
O PDF sai escuro também: página sem margem branca (@page margin 0) e a cor de fundo impressa.
"""
import html as _html

MARCA = "RYZE"
SITE = "ryzecode.com.br"

FONTES = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700'
          '&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" '
          'rel="stylesheet">')

_SETA = ("M308.484 282.06L244.072 357.593H211L231.18 392H350.77L400 520H244.159L171.652 352.605"
         "L177.931 342.661L225 254.736L211.896 226.997L191.439 180.558L159.957 267.483L127.315 354.301"
         "L112.868 394.729H139.992L194.254 520H0L200 0L308.484 282.06Z")


def logo(cor="#FFB700", altura="28px"):
    return (f'<svg viewBox="0 0 400 520" style="height:{altura};width:auto;display:block" '
            f'aria-hidden="true"><path d="{_SETA}" fill="{cor}"/></svg>')


def e(x):
    return _html.escape("" if x is None else str(x))


TOKENS = """
:root{--bg:#0D0D0D;--surface:#141414;--soft:#1A1A1A;--line:#262626;--ink:#EDEDED;--muted:#8A8A8A;
  --dim:#5C5C5C;--accent:#FFB700;--accent-ink:#CC9200;--accent-soft:rgba(255,183,0,.12);
  --roxo:#6A28C9;--roxo-l:#8B5CF6;--roxo-soft:rgba(139,92,246,.16);--warn:#F08A5D;--ok:#8B5CF6;
  --me:rgba(255,183,0,.10);
  --sans:'Plus Jakarta Sans',-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --disp:'Space Grotesk',var(--sans);--mono:'JetBrains Mono',ui-monospace,Consolas,monospace}
"""

# peças comuns: capa, cartões de número, barras, selos e o comportamento no papel
CSS = TOKENS + """
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact;background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.6;
  -webkit-font-smoothing:antialiased}
a{color:var(--accent)}
.wrap{max-width:820px;margin:0 auto;padding:44px 24px 24px}
.capa{position:relative;overflow:hidden;background:var(--surface);border:1px solid var(--line);
  border-radius:20px;padding:38px 40px 34px;margin-bottom:44px}
.capa::after{content:"";position:absolute;right:-90px;top:-70px;width:330px;height:330px;
  background:linear-gradient(145deg,rgba(106,40,201,.35),rgba(106,40,201,0) 65%);
  clip-path:polygon(35% 0,100% 0,100% 65%);pointer-events:none}
.capa .mark-bg{position:absolute;right:-30px;bottom:-56px;opacity:.06;pointer-events:none}
.capa-top{display:flex;align-items:center;gap:12px;margin-bottom:30px;position:relative;z-index:1}
.wordmark{font-family:var(--disp);font-weight:700;letter-spacing:5px;font-size:15px}
.selo{margin-left:auto;font-family:var(--mono);font-size:10px;letter-spacing:1.6px;text-transform:uppercase;
  color:var(--accent);border:1px solid rgba(255,183,0,.35);padding:4px 10px;border-radius:20px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:2.5px;text-transform:uppercase;
  color:var(--accent);margin-bottom:12px}
h1{font-family:var(--disp);font-weight:700;letter-spacing:-.6px;line-height:1.12;margin:0 0 10px;
  font-size:clamp(26px,4vw,38px);color:#FAFAFA}
h2{font-family:var(--disp);font-size:13px;font-weight:600;letter-spacing:2px;text-transform:uppercase;
  color:var(--accent);margin:0 0 18px}
h3{font-family:var(--disp);font-size:16px;font-weight:600;margin:24px 0 10px;color:#FAFAFA}
.data,.sub{font-size:13.5px;color:var(--muted)}
section{margin:0 0 44px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.kpi.fora{border-color:rgba(240,138,93,.55)}
.kpi.ok{border-color:rgba(139,92,246,.5)}
.kpi .lb{font-family:var(--mono);font-size:9.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted)}
.kpi .vl{font-family:var(--disp);font-weight:700;font-size:28px;color:#fff;margin-top:4px;line-height:1.1}
.kpi .mt{font-size:11.5px;color:var(--muted);margin-top:6px}
.kpi.fora .mt{color:var(--warn)}
.kpi.ok .mt{color:#C4B5FD}
.barras{display:flex;align-items:flex-end;gap:6px;height:90px;margin:8px 0 6px}
.barras .b{flex:1;background:var(--accent);border-radius:3px 3px 0 0;min-width:10px;position:relative}
.barras .b.roxo{background:var(--roxo-l)}
.barras .b span{position:absolute;top:-17px;left:0;right:0;text-align:center;font-family:var(--mono);
  font-size:10px;color:var(--muted)}
.eixo{display:flex;gap:6px}
.eixo span{flex:1;text-align:center;font-family:var(--mono);font-size:9.5px;color:var(--dim)}
table.t{width:100%;border-collapse:collapse;font-size:14px;background:var(--surface);border:1px solid var(--line);
  border-radius:12px;overflow:hidden}
.t th{background:#000;color:var(--accent);font-family:var(--mono);font-size:9.5px;letter-spacing:1px;
  text-transform:uppercase;padding:10px 12px;text-align:left;font-weight:500}
.t td{padding:10px 12px;border-bottom:1px solid #202020;vertical-align:top}
.t tr:last-child td{border-bottom:none}
.t td.n{font-family:var(--mono);text-align:right;white-space:nowrap;color:#fff}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{font-size:12.5px;background:var(--soft);border:1px solid var(--line);padding:4px 11px;border-radius:20px}
.chip b{font-family:var(--mono);color:var(--accent);font-weight:600;margin-left:6px}
.frase{background:var(--surface);border-left:3px solid var(--accent);border-radius:0 10px 10px 0;
  padding:10px 14px;margin:0 0 10px;font-size:14.5px}
.frase .ts{margin-right:8px}
.ts{font-family:var(--mono);font-size:11px;color:var(--muted)}
.nota{background:var(--roxo-soft);border:1px solid rgba(139,92,246,.35);border-radius:12px;padding:14px 16px;
  font-size:14px}
.rodape{display:flex;align-items:center;gap:9px;padding:36px 0 8px;color:var(--dim);font-size:11.5px;
  font-family:var(--mono)}
code{font-family:var(--mono);font-size:.92em;color:#FFD666}
/* no papel continua escuro: sem margem branca em volta */
@page{size:A4;margin:0}
@media print{
  html,body{background:var(--bg)}
  .wrap{max-width:none;padding:14mm 15mm 10mm}
  section,.kpi,.frase,tr{break-inside:avoid}
}
"""


def capa(titulo, eyebrow="", sub="", selo="Uso interno"):
    s = f'<span class="selo">{e(selo)}</span>' if selo else ""
    return (f'<header class="capa"><div class="mark-bg">{logo("#FFB700", "230px")}</div>'
            f'<div class="capa-top">{logo("#FFB700", "28px")}<span class="wordmark">{MARCA}</span>{s}</div>'
            f'<div class="eyebrow">{e(eyebrow)}</div><h1>{e(titulo)}</h1>'
            f'<div class="data">{e(sub)}</div></header>')


def rodape(texto="gerado nesta máquina"):
    return f'<footer class="rodape">{logo("#5C5C5C", "13px")}<span>{MARCA} · {SITE} · {e(texto)}</span></footer>'


def pagina(titulo, corpo, css_extra="", wrap_largura=None):
    largura = f'<style>.wrap{{max-width:{wrap_largura}px}}</style>' if wrap_largura else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex"><title>{e(titulo)}</title>{FONTES}'
            f'<style>{CSS}{css_extra}</style>{largura}</head><body><div class="wrap">{corpo}</div></body></html>')


def markdown_html(md):
    """Markdown → HTML (tabelas e listas). Sem a biblioteca, cai para texto pré-formatado."""
    import re
    # o Claude escreve "**Funcionou**\n- item": sem linha em branco antes, o Markdown emenda a lista
    md = re.sub(r"(?m)^(?!\s*(?:[-*+] |\d+\. |\|))(\S.*)\n(?=\s*(?:[-*+] |\d+\. ))", r"\1\n\n", md)
    try:
        import markdown as _md
        return _md.markdown(md, extensions=["tables", "sane_lists"])
    except ImportError:
        return f'<pre style="white-space:pre-wrap">{e(md)}</pre>'
