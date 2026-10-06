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


_ZONA_BOA = {"viva", "com ênfase", "bom"}


def _regua(it):
    """Faixas coloridas da medida, com a marca de onde o valor caiu."""
    lo, hi = it["escala"]
    def pos(x):
        return max(0.0, min(100.0, 100 * (x - lo) / (hi - lo)))
    segs, rots = [], []
    for a, b, nome, _ in it["zonas"]:
        larg = pos(b) - pos(a)
        cls = "boa" if nome in _ZONA_BOA else ("neutra" if it["chave"] == "tom_hz" else "fora")
        segs.append(f'<div class="z {cls}" style="width:{larg:.2f}%"></div>')
        rots.append(f'<span style="width:{larg:.2f}%">{e(nome)}</span>')
    marca = f'<div class="marca" style="left:{pos(it["valor"]):.2f}%"></div>'
    return (f'<div class="regua">{"".join(segs)}{marca}</div>'
            f'<div class="regua-rot">{"".join(rots)}</div>')


def _secao_voz(v):
    import analise_fala
    itens, evolucao = analise_fala.leitura_voz(v)
    cartoes = []
    for it in itens:
        cls = "boa" if it["zona"] in _ZONA_BOA else ("neutra" if it["chave"] == "tom_hz" else "fora")
        voce = f'<p class="voce"><b>Você:</b> {e(it["zona"])}'
        voce += f' — {e(it["efeito"])}.</p>' if it["efeito"] else ".</p>"
        dica = f'<p class="dica"><b>O que fazer:</b> {e(it["dica"])}</p>' if it["dica"] else ""
        cartoes.append(
            f'<div class="voz-item"><div class="voz-top"><div><div class="lb">{e(it["nome"])}</div>'
            f'<div class="vl">{e(it["valor"])} <small>{e(it["unidade"])}</small></div></div>'
            f'<span class="zona {cls}">{e(it["zona"])}</span></div>{_regua(it)}'
            f'<p class="oq">{e(it["o_que_e"])}</p>{voce}{dica}</div>')
    corpo = ['<section><h2>Voz</h2><p class="sub">Medida no áudio do seu microfone, só nos trechos em que '
             f'você fala ({v.get("amostra_min")} min de amostra espalhados pela reunião). As faixas são '
             'referências práticas de fala em reunião, não diagnóstico.</p>', "".join(cartoes)]
    bl = v.get("blocos") or []
    if len(bl) >= 2:
        rot = [f"{b['de_min']}′" for b in bl]
        corpo.append('<h3>A voz ao longo da reunião</h3>'
                     + "".join(f'<p class="leitura">{e(t)}</p>' for t in evolucao)
                     + '<h3>Tom (Hz) por bloco de 30 min</h3>'
                     + _barras([b["tom_hz"] for b in bl], rot, roxo=True)
                     + '<h3>Entonação (semitons) por bloco de 30 min</h3>'
                     + _barras([b["entonacao_st"] for b in bl], rot))
    corpo.append("</section>")
    return "".join(corpo)


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
        corpo.append(_secao_voz(v))

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
.voz-item{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:0 0 14px}
.voz-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.voz-item .lb{font-family:var(--mono);font-size:9.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted)}
.voz-item .vl{font-family:var(--disp);font-weight:700;font-size:28px;color:#fff;line-height:1.1;margin-top:4px}
.voz-item .vl small{font-size:14px;color:var(--muted);font-weight:500}
.zona{font-family:var(--mono);font-size:11px;letter-spacing:1px;text-transform:uppercase;padding:4px 10px;
  border-radius:20px;white-space:nowrap}
.zona.boa{background:var(--roxo-soft);color:#C4B5FD}
.zona.fora{background:rgba(240,138,93,.14);color:var(--warn)}
.zona.neutra{background:var(--soft);color:var(--ink)}
.regua{position:relative;display:flex;height:10px;border-radius:5px;overflow:visible;margin:16px 0 4px}
.regua .z{height:10px}
.regua .z:first-child{border-radius:5px 0 0 5px}.regua .z:last-child{border-radius:0 5px 5px 0}
.regua .z.boa{background:rgba(139,92,246,.55)}
.regua .z.fora{background:rgba(240,138,93,.35)}
.regua .z.neutra{background:#2E2E2E}
.regua .z.neutra:nth-child(2){background:#3A3A3A}
.regua .marca{position:absolute;top:-5px;width:4px;height:20px;margin-left:-2px;background:var(--accent);
  border-radius:2px;box-shadow:0 0 0 2px var(--bg)}
.regua-rot{display:flex;margin-bottom:10px}
.regua-rot span{font-family:var(--mono);font-size:9.5px;color:var(--dim);text-align:center;overflow:hidden;
  white-space:nowrap;text-overflow:ellipsis}
.voz-item p{margin:6px 0 0;font-size:14px}
.voz-item .oq{color:var(--muted)}
.voz-item .dica{color:#C4B5FD}
.leitura{background:var(--surface);border-left:3px solid var(--roxo-l);border-radius:0 10px 10px 0;
  padding:10px 14px;margin:0 0 10px;font-size:14.5px}
"""
