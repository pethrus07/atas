# -*- coding: utf-8 -*-
"""
Páginas do Raio-X da Fala no tema RYZE escuro (v2.2, 06/10/2026). USO INTERNO.

- `pagina_reuniao`: tudo de UMA reunião — metas, como você falou, cansaço por bloco, voz,
  postura (sujeito, certeza, promessa no reflexo, concessão, corte), as frases para revisar e,
  se a avaliação interna já existir, a negociação e a postura que ela escreveu.
- `painel`: todas as reuniões, com a evolução de cada métrica e o link para cada página.

"Ele evoluindo significa eu evoluindo": o Pedro pediu o Raio-X "com mais análises, como você
fez, postura e etc." — este é o lugar onde ele lê isso.
"""
import re

import tema as _t

e = _t.e
_TIPO = {"cliente": "cliente", "parresia": "Parresia", "carreira": "carreira", "pessoal": "pessoal/estudo"}


def _mmss(s):
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def _kpi(rotulo, valor, meta=None, ok=None):
    cls = "" if ok is None else (" ok" if ok else " fora")
    mt = f'<div class="mt">{"✓ " if ok else "! " if ok is False else ""}{e(meta)}</div>' if meta else ""
    return f'<div class="kpi{cls}"><div class="lb">{e(rotulo)}</div><div class="vl">{e(valor)}</div>{mt}</div>'


def _barras(valores, rotulos, roxo=False, fmt=str):
    mx = max(valores) if valores else 1
    mx = mx or 1
    bs = "".join(f'<div class="b{" roxo" if roxo else ""}" style="height:{max(4, round(80 * v / mx))}px">'
                 f'<span>{e(fmt(v))}</span></div>' for v in valores)
    eixo = "".join(f"<span>{e(r)}</span>" for r in rotulos)
    return f'<div class="barras">{bs}</div><div class="eixo">{eixo}</div>'


def _chips(d, limite=10):
    return '<div class="chips">' + "".join(
        f'<span class="chip">{e(k)}<b>{v}</b></span>' for k, v in list(d.items())[:limite]) + "</div>"


def secoes_avaliacao(md, quais=("## 3.", "## 4.")):
    """Recorta da avaliação interna as seções pedidas (negociação e postura, por padrão)."""
    if not md:
        return ""
    partes = re.split(r"(?m)^(?=## )", md)
    return "\n".join(p for p in partes if p.startswith(quais))


def pagina_reuniao(reg, avaliacao_md=None):
    m = reg["metrics"]
    r = m.get("ritmo") or {}
    p = m.get("postura") or {}
    v = m.get("voz")
    sub = " · ".join(x for x in [str(reg.get("data", ""))[:16].replace("T", " "), f"{m.get('dur_min')} min",
                                  _TIPO.get(reg.get("tipo"), "")] if x)
    corpo = [_t.capa(reg.get("titulo") or "Reunião", "Raio-X da Fala", sub)]

    metas = m.get("metas") or []
    if metas:
        fora = sum(1 for x in metas if not x[3])
        corpo.append(f'<section><h2>Metas · {len(metas) - fora} de {len(metas)} batidas</h2><div class="kpis">'
                     + "".join(_kpi(n, val, f"meta {meta}", ok) for n, val, meta, ok in metas) + "</div></section>")

    if r:
        corpo.append('<section><h2>Como você falou</h2><div class="kpis">'
                     + _kpi("Sua fatia de fala", f"{m['share_fala'] * 100:.0f}%")
                     + _kpi("Ritmo", f"{r.get('ppm')} pal/min", f"{r.get('fala_min')} min falando")
                     + _kpi("Turnos", r.get("turnos"), f"médio de {r.get('turno_medio_s')} s")
                     + _kpi("Maior monólogo", f"{r.get('maior_monologo_s')} s",
                            f"em {_mmss(r.get('maior_monologo_em'))}")
                     + _kpi("Interrupções", f"{r.get('interrompeu')} / {r.get('foi_interrompido')}",
                            "você interrompeu / foi interrompido")
                     + _kpi("Resposta", f"{r.get('resposta_media_s')} s" if r.get("resposta_media_s") is not None
                            else "—", "do fim da fala dele até a sua")
                     + _kpi("Perguntas reais", r.get("perguntas_reais"), 'sem contar "entendeu?"')
                     + _kpi("Confirmações", f"{m['conf_por_min']}/min", f"{m['conf_total']} no total")
                     + "</div></section>")

    bl = m.get("blocos") or []
    if len(bl) >= 2:
        rot = [f"{b['de_min']}′" for b in bl]
        primeiro, ultimo = bl[0]["muletas_por_1000"], bl[-1]["muletas_por_1000"]
        var = round(100 * (ultimo - primeiro) / primeiro) if primeiro else 0
        leitura = (f"As muletas foram de {primeiro} para {ultimo} por mil palavras ({var:+d}%) do começo ao fim."
                   if var else "As muletas ficaram estáveis do começo ao fim.")
        corpo.append('<section><h2>Ao longo da reunião (cansaço)</h2>'
                     f'<p class="sub">{e(leitura)} Blocos de 30 minutos.</p>'
                     '<h3>Muletas a cada 1000 palavras</h3>'
                     + _barras([b["muletas_por_1000"] for b in bl], rot)
                     + '<h3>Confirmações por minuto</h3>'
                     + _barras([b["conf_por_min"] for b in bl], rot, roxo=True)
                     + '<h3>Ritmo (palavras por minuto)</h3>'
                     + _barras([b["ppm"] for b in bl], rot, fmt=lambda x: round(x)) + "</section>")

    if v:
        ent = v["entonacao_st"]
        leitura = ("soa monótona" if ent < 1.5 else "tem pouca variação" if ent < 2.2
                   else "é viva" if ent <= 4.5 else "varia muito (pode soar agitada)")
        corpo.append('<section><h2>Voz</h2><div class="kpis">'
                     + _kpi("Entonação", f"{ent} st", f"sua fala {leitura}")
                     + _kpi("Volume", f"{v['volume_db']} dBFS", f"variação de {v['volume_variacao_db']} dB")
                     + _kpi("Tom", f"{v['tom_hz']} Hz", f"amostra de {v['amostra_min']} min")
                     + "</div></section>")

    if p:
        sujeito = (f"{round(p['sujeito_claro'] * 100)}% \"eu\"" if p.get("sujeito_claro") is not None else "—")
        corpo.append('<section><h2>Postura</h2><div class="kpis">'
                     + _kpi("Sujeito", sujeito, f"{p['eu']} \"eu\" × {p['a_gente']} \"a gente\"")
                     + _kpi("Promessa no reflexo", p["promessa_total"], '"já dá", "já existe", "é só"…')
                     + _kpi("Certeza absoluta", p["certeza_total"], '"com certeza", "obviamente"…')
                     + _kpi("Concordância reflexa", p["concessao_total"], '"tranquilo", "sem problema"…')
                     + _kpi("Cortes", p["cortes"], 'falas que começam com "Não. Não."')
                     + "</div>")
        if p.get("frases_revisar"):
            corpo.append('<h3>Frases para revisar</h3><p class="sub">Onde houve promessa ou certeza '
                         'absoluta: é ali que nasce afirmação errada para o cliente. Confira cada uma.</p>'
                         + "".join(f'<div class="frase"><span class="ts">{_mmss(f["t"])}</span>{e(f["texto"])}</div>'
                                   for f in p["frases_revisar"]))
        corpo.append("</section>")

    palavras = []
    if m.get("confirmacoes"):
        palavras.append("<h3>Pedidos de confirmação</h3>" + _chips({f"{k}?": v for k, v in m["confirmacoes"].items()}))
    if m.get("muletas"):
        palavras.append("<h3>Muletas</h3>" + _chips(m["muletas"]))
    if m.get("bordoes"):
        palavras.append("<h3>Bordões</h3>" + _chips(m["bordoes"]))
    if palavras:
        corpo.append("<section><h2>Palavras</h2>" + "".join(palavras) + "</section>")

    trecho = secoes_avaliacao(avaliacao_md)
    if trecho:
        corpo.append('<section><h2>Da avaliação interna</h2><div class="nota">Negociação e postura, como a '
                     'avaliação interna desta reunião escreveu. A avaliação completa (afirmações '
                     'conferidas e valores) está na pasta da reunião.</div>'
                     + _t.markdown_html(trecho) + "</section>")

    corpo.append(_t.rodape("Raio-X da Fala · uso interno"))
    return _t.pagina(f"Raio-X · {reg.get('titulo')}", "".join(corpo), css_extra=_CSS_MD)


def painel(linhas, link_de=None):
    """Todas as reuniões. `link_de(reg)` devolve o nome do arquivo da página da reunião (ou None)."""
    ult = linhas[-1]["metrics"] if linhas else {}
    def serie(f):
        return [f(r["metrics"]) for r in linhas[-12:]]
    rot = [str(r.get("data", ""))[5:10].replace("-", "/") for r in linhas[-12:]]
    corpo = [_t.capa("Raio-X da Fala", "Evolução", f"{len(linhas)} reuniões monitoradas · dado pessoal, nunca vai ao cliente")]
    kp = ['<section><h2>Agora (última reunião)</h2><div class="kpis">',
          _kpi("Fatia de fala", f"{ult.get('share_fala', 0) * 100:.0f}%", "meta 35% a 55%"),
          _kpi("Confirmações/min", ult.get("conf_por_min", "—"), "meta até 0,5"),
          _kpi("Muletas/1k", ult.get("muletas_por_1000", "—"), "meta até 30"),
          _kpi("Ritmo", f"{(ult.get('ritmo') or {}).get('ppm', '—')} pal/min", "meta 130 a 180"),
          _kpi("Entonação", f"{(ult.get('voz') or {}).get('entonacao_st', '—')} st", "2 a 4 = fala viva"),
          "</div></section>"]
    corpo += kp
    corpo.append('<section><h2>Tendência (últimas 12)</h2>'
                 '<h3>Confirmações por minuto</h3>' + _barras(serie(lambda m: m.get("conf_por_min", 0)), rot, roxo=True)
                 + '<h3>Muletas a cada 1000 palavras</h3>' + _barras(serie(lambda m: m.get("muletas_por_1000", 0)), rot)
                 + '<h3>Fatia de fala (%)</h3>' + _barras(serie(lambda m: round(m.get("share_fala", 0) * 100)), rot)
                 + "</section>")
    linhas_tab = []
    for r in reversed(linhas):
        m = r["metrics"]
        nome = e(r.get("titulo"))
        alvo = link_de(r) if link_de else None
        if alvo:
            nome = f'<a href="{e(alvo)}">{nome}</a>'
        rr = m.get("ritmo") or {}
        linhas_tab.append(f"<tr><td>{e(str(r.get('data', ''))[:10])}</td><td>{nome}</td>"
                          f"<td class='n'>{m.get('dur_min')}</td><td class='n'>{m.get('share_fala', 0) * 100:.0f}%</td>"
                          f"<td class='n'>{m.get('conf_por_min')}</td><td class='n'>{m.get('muletas_por_1000')}</td>"
                          f"<td class='n'>{rr.get('ppm', '—')}</td></tr>")
    corpo.append('<section><h2>Reunião a reunião</h2><table class="t"><thead><tr><th>Data</th><th>Reunião</th>'
                 '<th>Min</th><th>Fala</th><th>Conf/min</th><th>Mul/1k</th><th>Ritmo</th></tr></thead><tbody>'
                 + "".join(linhas_tab) + "</tbody></table></section>")
    corpo.append(_t.rodape("Raio-X da Fala · fala-analise/ · não sincronizado"))
    return _t.pagina("Raio-X da Fala — RYZE (interno)", "".join(corpo))


# Markdown da avaliação dentro da página escura (tabelas, listas e citações)
_CSS_MD = """
.nota+*{margin-top:18px}
section table{width:100%;border-collapse:collapse;font-size:13.5px;margin:10px 0 18px;background:var(--surface);
  border:1px solid var(--line)}
section th{background:#000;color:var(--accent);font-family:var(--mono);font-size:9.5px;letter-spacing:1px;
  text-transform:uppercase;padding:9px 10px;text-align:left;font-weight:500}
section td{padding:9px 10px;border-bottom:1px solid #202020;vertical-align:top}
section li{margin:0 0 6px}
section h2+h3{margin-top:6px}
blockquote{margin:0 0 16px;padding:10px 14px;border-left:3px solid var(--roxo-l);background:var(--roxo-soft);
  border-radius:0 10px 10px 0;color:var(--ink)}
hr{border:none;border-top:1px solid var(--line);margin:28px 0}
strong{color:#fff}
"""
