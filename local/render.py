# -*- coding: utf-8 -*-
"""
Renderizações da ata canônica (ata.json) — tudo gerado AQUI, na máquina.

    ata.md            para ler e para o Claude (estruturado + transcrição)
    ata.html          versão interna: tudo, inclusive lacunas e itens sem origem
    entregavel.html   só reunião de cliente: marca RYZE, só o que foi verificado,
                      só nomes confirmados

Antes da v2 a página vinha do Worker, então sem upload não havia PDF; e toda ata
saía com a marca RYZE, inclusive as da Parresia. Agora a marca segue o tipo
(decisão 1 de 30/09/2026) e a página existe mesmo sem internet.

Desenho (regra do Pedro: pouca informação, muito respiro): o que se usa depois da
reunião — decisões e encaminhamentos — vem primeiro; resumo em seguida; temas,
perguntas, riscos, lacunas e a transcrição ficam recolhidos em <details>. Na
impressão tudo abre (`impressao=True`). Borda só onde comunica estado.

A daily da Parresia (`atas/daily@1`, 19/10/2026) tem render próprio, sempre interno (nunca
entregável): "Com você" e as frentes no topo, depois por pessoa, decisões/encaminhamentos e momentos.
"""
import datetime as _dt
import html as _html

import ata as _ata
import tema as _tema
from sessao import TIPOS

e = _tema.e          # escape de HTML (o mesmo do tema)


def data_br(iso, com_hora=True):
    try:
        d = _dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
             "setembro", "outubro", "novembro", "dezembro"]
    s = f"{d.day} de {meses[d.month - 1]} de {d.year}"
    return s + (f", {d:%H:%M}" if com_hora else "")


def data_curta(iso):
    try:
        return _dt.date.fromisoformat(str(iso)[:10]).strftime("%d/%m")
    except (TypeError, ValueError):
        return iso or ""


# ── nomes ────────────────────────────────────────────────────────────────────
def _nomeador(ata, cliente):
    """rótulo → nome exibido. No entregável só nome confirmado; internamente o
    deduzido aparece com '?' até o Pedro confirmar no /ata."""
    mapa = {}
    for p in ata.get("participantes", []):
        nome = p.get("nome")
        if not nome:
            mapa[p["rotulo"]] = p["rotulo"]
        elif p.get("confirmado"):
            mapa[p["rotulo"]] = nome
        else:
            mapa[p["rotulo"]] = p["rotulo"] if cliente else f"{nome}?"

    # o Claude também escreve NOMES em dono/quem (a regra 3 do prompt pede); se o nome é
    # o de um participante ainda não confirmado, no entregável ele volta a ser o rótulo
    nao_confirmados = {p["nome"]: p["rotulo"] for p in ata.get("participantes", [])
                       if p.get("nome") and not p.get("confirmado")}
    confirmados = _ata.nomes_confirmados(ata)

    def nome(v):
        if not v:
            return None
        if v in mapa:
            return mapa[v]
        if v in nao_confirmados and v not in confirmados:
            return nao_confirmados[v] if cliente else f"{v}?"
        return v
    return nome


def _lista_participantes(ata, nome):
    vistos = []
    for p in ata.get("participantes", []):
        n = nome(p["rotulo"])
        if p.get("fatia", 1) < 0.05 and not p.get("nome"):
            continue
        if n not in vistos:
            vistos.append(n)
    return vistos


# ── HTML ─────────────────────────────────────────────────────────────────────
def html(ata, segs, cliente=False, impressao=False):
    if _ata.e_daily(ata):
        if cliente:
            raise ValueError("daily é interna: não tem entregável")
        return html_daily(ata, segs, impressao)
    nome = _nomeador(ata, cliente)
    tipo = ata.get("tipo") or "pessoal"
    tema = "ryze" if cliente else "interno"

    def itens(lista):
        its = ata.get(lista, [])
        return [i for i in its if i.get("verificado") is not False] if cliente else its

    def origem(it):
        marca = ""
        if it.get("verificado") is False:
            marca = '<span class="alerta">origem não localizada</span>'
        return f'<span class="ts">{e(it.get("t"))}</span>{marca}'

    def lacuna(txt):
        return f'<span class="lacuna">{e(txt)}</span>'

    blocos = []
    if ata.get("status") == "pendente" and not cliente:
        blocos.append('<section class="aviso-estado"><p>Esta ata ainda não foi estruturada. '
                      'A transcrição está completa abaixo; rode <code>/ata</code> no Claude '
                      'para extrair decisões e encaminhamentos.</p></section>')

    # Momentos marcados (14/10/2026): no topo da ata INTERNA. Ao cliente nunca vão — marcar é
    # ferramenta do Pedro; o que a marca achou de decisão/valor já está nas listas normais.
    todas_falas = _ata.falas(segs)
    if not cliente and ata.get("momentos"):
        blocos.append(_secao_momentos(ata["momentos"], todas_falas))

    dec = itens("decisoes")
    if dec:
        lis = []
        for d in dec:
            meta = [nome(d.get("quem")) or lacuna("quem decidiu não ficou claro")]
            if d.get("revisar_em"):           # sem data, nada (v2.1: deixou de ser lacuna, era ruído)
                meta.append(f"revisar em {data_curta(d['revisar_em'])}")
            lis.append(f'<li><p>{e(d["decisao"])}</p><div class="meta">'
                       f'{" · ".join(m if m.startswith("<") else e(m) for m in meta)}'
                       f'{origem(d)}</div></li>')
        blocos.append(f'<section><h2>Decisões</h2><ul class="itens">{"".join(lis)}</ul></section>')

    enc = itens("encaminhamentos")
    if enc:
        rows = []
        for x in enc:
            dono = nome(x.get("dono"))
            prazo = data_curta(x["prazo"]) if x.get("prazo") else None
            rows.append(
                f'<tr><td>{e(x["acao"])}<div class="meta">{origem(x)}</div></td>'
                f'<td>{e(dono) if dono else lacuna("a definir")}</td>'
                f'<td class="prazo">{e(prazo) if prazo else lacuna("a definir")}</td></tr>')
        blocos.append('<section><h2>Encaminhamentos</h2><table class="enc"><thead><tr>'
                      '<th>O quê</th><th>Quem</th><th>Até</th></tr></thead>'
                      f'<tbody>{"".join(rows)}</tbody></table></section>')

    # valor "citado" (pesquisa de preço, custo interno, exemplo) não é acordo: fica só na ata
    # interna, recolhido; ao cliente vai o combinado e o proposto
    val = [v for v in itens("valores") if v.get("natureza") != "citado"]
    citados = [v for v in itens("valores") if v.get("natureza") == "citado"] if not cliente else []
    if val:
        rows = "".join(
            f'<tr><td>{e(v["descricao"])}<div class="meta">{origem(v)}</div></td>'
            f'<td class="prazo">{e(v["valor"])}</td>'
            f'<td>{e(v.get("condicao") or "")}</td></tr>' for v in val)
        blocos.append('<section><h2>Valores</h2><table class="enc"><thead><tr>'
                      '<th>O quê</th><th>Valor</th><th>Condição</th></tr></thead>'
                      f'<tbody>{rows}</tbody></table></section>')

    # resumo e contexto são prosa livre (a auditoria não confere nomes dentro deles):
    # ao cliente só vão quando todo falante relevante está confirmado
    prosa_ok = not cliente or ata.get("status") == "revisada" or _ata.falantes_resolvidos(ata)
    if prosa_ok and (ata.get("resumo") or ata.get("contexto")):
        ctx = f'<p class="ctx">{e(ata["contexto"])}</p>' if ata.get("contexto") else ""
        res = f'<p class="lead">{e(ata["resumo"])}</p>' if ata.get("resumo") else ""
        blocos.append(f'<section><h2>Resumo</h2>{ctx}{res}</section>')
    if prosa_ok and ata.get("por_tema"):
        blocos.append('<section><h2>Por assunto</h2>' + "".join(
            f'<h3>{e(x["tema"])}</h3><p>{e(x["resumo"])}</p>' for x in ata["por_tema"]) + '</section>')

    esc = itens("escopo")
    if esc:
        grupos = {}
        for s in esc:
            grupos.setdefault(s.get("tema") or "Geral", []).append(s)
        corpo = "".join(f'<h3>{e(g)}</h3><ul class="simples">' + "".join(
            f'<li>{e(s["item"])} {origem(s)}</li>' for s in its) + "</ul>" for g, its in grupos.items())
        blocos.append(f'<section><h2>Escopo e entregas</h2>{corpo}</section>')

    mais = []
    if ata.get("temas"):
        mais.append('<h3>Temas</h3><div class="tags">' +
                    "".join(f'<span class="tag">{e(t)}</span>' for t in ata["temas"]) + "</div>")
    per = itens("perguntas_abertas")
    if per:
        mais.append('<h3>Perguntas em aberto</h3><ul class="simples">' + "".join(
            f'<li>{e(p["pergunta"])} {origem(p)}</li>' for p in per) + "</ul>")
    ris = itens("riscos")
    if ris:
        mais.append('<h3>Riscos</h3><ul class="simples">' + "".join(
            f'<li>{e(r["risco"])} {origem(r)}</li>' for r in ris) + "</ul>")
    if citados:
        mais.append('<h3>Valores citados (referência, não acordo)</h3><ul class="simples">' + "".join(
            f'<li>{e(v["descricao"])}: {e(v["valor"])} {origem(v)}</li>' for v in citados) + "</ul>")
    if not cliente and ata.get("lacunas"):
        mais.append('<h3>Lacunas a fechar</h3><ul class="simples">' + "".join(
            f'<li><b>{e(nome(l["ref"]))}</b> — {e(l["falta"])}</li>'
            for l in ata["lacunas"]) + "</ul>")
    aberto = " open" if impressao else ""
    if mais:
        blocos.append(f'<details class="mais"{aberto}><summary>Mais</summary>'
                      f'<div class="mais-corpo">{"".join(mais)}</div></details>')

    # Transcrição: inteira só na ata interna. Ao cliente vão os TRECHOS que sustentam os itens
    # verificados (v2.1): a ata de 05/10 virou um PDF de 179 páginas com 15 min de conversa
    # pessoal, a um clique de "Publicar".
    todas = todas_falas
    if cliente:
        citados = {_ata.parse_t(it.get("t")) for k, _ in _ata.LISTAS for it in itens(k)}
        mostrar = [f for f in todas if any(t is not None and abs(f["start"] - t) < 1 for t in citados)]
        titulo_tr = "Trechos citados"
    else:
        mostrar, titulo_tr = todas, "Transcrição"
    falas = []
    for f in mostrar:
        eu = f["speaker"] == "Você"
        ancora = f' id="f-{int(f["start"])}"' if not cliente else ""
        falas.append(f'<div class="fala{" eu" if eu else ""}"{ancora}><div class="quem">'
                     f'{e(nome(f["speaker"]))}<span class="ts">{_ata.fmt_t(f["start"])}</span>'
                     f'</div><div class="txt">{e(f["text"])}</div></div>')
    if falas or not cliente:
        blocos.append(f'<details class="transc"{aberto}><summary>{titulo_tr}</summary>'
                      f'<div class="falas">{"".join(falas) or "<p>Sem falas reconhecidas.</p>"}'
                      f'</div></details>')

    pessoas = _lista_participantes(ata, nome)
    meta_topo = " · ".join(x for x in [
        data_br(ata.get("data")),
        f"{ata.get('duracao_min')} min" if ata.get("duracao_min") else None,
        ", ".join(pessoas) if pessoas else None] if x)

    # v2.2: tudo no tema RYZE escuro (pedido do Pedro, 06/10/2026); a interna leva o selo de uso interno
    rotulo = TIPOS.get(tipo, tipo)
    if cliente:
        topo = _tema.capa(ata.get("titulo"), "Ata de reunião", meta_topo, selo=None)
        rodape = _tema.rodape("ata de reunião")
    else:
        proj = f" · {ata['projeto']}" if ata.get("projeto") else ""
        topo = _tema.capa(ata.get("titulo"), f"Ata · {rotulo}{proj}", meta_topo, selo="Uso interno")
        rodape = _tema.rodape("uso interno · gerado nesta máquina")

    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex"><title>{e(ata.get("titulo"))}</title>'
            f'{_tema.FONTES}<style>{_tema.CSS}{CSS_BASE}</style>'
            f'</head><body class="{tema}"><div class="wrap">{topo}{"".join(blocos)}'
            f'{rodape}</div></body></html>')


def texto_momento(mo):
    """A frase do momento, ou o porquê de não ter frase. Nunca inventa."""
    if mo.get("pendente"):
        return None, "marcado — trecho ainda não lido pelo Claude"
    if mo.get("o_que") and mo.get("citacao"):
        return mo["o_que"], None
    return None, "marcado — sem decisão clara no trecho"


def _secao_momentos(momentos, falas):
    import marcas as _marcas
    lis = []
    for mo in momentos:
        ini, _fim = _marcas.janela(mo["marca_t"])
        # o horário leva ao começo do trecho na transcrição (que abre sozinha ao seguir o link)
        alvo = next((f for f in falas if f["start"] >= ini - 5), falas[-1] if falas else None)
        hora = e(mo.get("hora") or _ata.fmt_t(mo["marca_t"]))
        hora = (f'<a class="hora" href="#f-{int(alvo["start"])}" title="ir ao trecho na transcrição">{hora}</a>'
                if alvo else f'<span class="hora">{hora}</span>')
        frase, vazio = texto_momento(mo)
        corpo = e(frase) if frase else f'<span class="lacuna">{e(vazio)}</span>'
        meta = []
        if frase:
            meta.append(f'<q>{e(mo["citacao"])}</q><span class="ts">{e(mo.get("t"))}</span>')
        if mo.get("itens"):
            meta.append("na ata: " + ", ".join(e(i) for i in mo["itens"]))
        meta_html = f'<div class="meta">{" · ".join(meta)}</div>' if meta else ""
        lis.append(f'<li><p>{hora}{corpo}</p>{meta_html}</li>')
    # a transcrição fica num <details> fechado: abre antes de pular para o trecho
    abrir = ('<script>document.addEventListener("click",function(ev){var a=ev.target.closest'
             '&&ev.target.closest("a.hora");if(!a)return;var f=document.querySelector(a.getAttribute("href"));'
             'var d=f&&f.closest("details");if(d)d.open=true;});</script>')
    return (f'<section class="momentos"><h2>Momentos marcados</h2>'
            f'<ul class="itens">{"".join(lis)}</ul>{abrir}</section>')


CSS_BASE = """
.momentos .hora{font-family:var(--mono);font-size:13px;color:var(--accent);text-decoration:none;
  margin-right:12px}
.momentos a.hora:hover{text-decoration:underline}
.momentos q{font-style:italic}
.wrap{max-width:780px;margin:0 auto;padding:48px 24px 24px}
section{margin:0 0 44px}
h1{font-family:var(--disp);font-weight:700;letter-spacing:-.5px;line-height:1.15;margin:0 0 12px;
  font-size:clamp(26px,4vw,36px)}
h2{font-family:var(--disp);font-size:13px;font-weight:600;letter-spacing:2px;text-transform:uppercase;
  color:var(--accent);margin:0 0 18px}
h3{font-size:14px;font-weight:600;margin:26px 0 10px;color:var(--ink)}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:2.5px;text-transform:uppercase;
  color:var(--accent);margin-bottom:14px}
.data{font-size:13.5px;color:var(--muted)}
.itens{list-style:none;margin:0;padding:0}
.itens li{padding:0 0 22px}
.itens li p{margin:0 0 4px;font-size:16px}
.meta{font-size:12.5px;color:var(--muted);display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}
.ts{font-family:var(--mono);font-size:11px;color:var(--muted);opacity:.8}
.lacuna{color:var(--muted);font-style:italic}
.alerta{font-size:11px;color:var(--warn);border:1px solid var(--warn);border-radius:10px;padding:0 7px}
table.enc{width:100%;border-collapse:collapse;font-size:15px}
.enc th{text-align:left;font-size:11px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;
  color:var(--muted);padding:0 12px 10px 0}
.enc td{padding:12px 12px 16px 0;vertical-align:top}
.enc td.prazo{white-space:nowrap;font-family:var(--mono);font-size:13px}
.enc td:nth-child(2){white-space:nowrap}
.ctx{color:var(--muted);font-size:14px;margin:0 0 12px}
.lead{font-size:16px;margin:0}
details{margin:0 0 20px}
summary{cursor:pointer;font-size:14px;font-weight:600;color:var(--muted);padding:10px 0;list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"+ ";font-family:var(--mono)}
details[open]>summary::before{content:"– "}
.mais-corpo{padding:4px 0 10px}
.tags{display:flex;flex-wrap:wrap;gap:8px}
.tag{font-size:12.5px;color:var(--ink);background:var(--soft);padding:4px 11px;border-radius:20px}
ul.simples{margin:0;padding-left:18px}
ul.simples li{margin:0 0 8px;font-size:14.5px}
.falas{display:flex;flex-direction:column;gap:12px;padding-top:8px}
.fala{max-width:88%}
.fala.eu{align-self:flex-end;text-align:right}
.fala .quem{font-size:12px;font-weight:600;color:var(--muted);display:flex;gap:8px;align-items:baseline}
.fala.eu .quem{justify-content:flex-end}
.fala .txt{font-size:14.5px;background:var(--soft);padding:8px 12px;border-radius:12px;display:inline-block;
  text-align:left}
.fala.eu .txt{background:var(--me)}
.aviso-estado p{margin:0;padding:14px 16px;border:1px solid var(--warn);border-radius:10px;font-size:14px}
code{font-family:var(--mono);font-size:.92em}
@media print{
  section,.itens li,tr,.fala{break-inside:avoid}
  details.transc{break-before:page}
  /* no papel, "+ Mais" não é controle de nada: some o rótulo, e a transcrição
     ganha título de seção como as outras */
  details[open]>summary::before{content:""}
  details.mais>summary{display:none}
  details.transc>summary{font-family:var(--disp);font-size:13px;font-weight:600;letter-spacing:2px;
    text-transform:uppercase;color:var(--accent);padding:0 0 8px}
}
"""

# ── Markdown ─────────────────────────────────────────────────────────────────
def markdown(ata, segs):
    if _ata.e_daily(ata):
        return markdown_daily(ata, segs)
    nome = _nomeador(ata, cliente=False)
    L = [f"# {ata.get('titulo')}", "",
         f"_{data_br(ata.get('data'))} · {ata.get('duracao_min')} min · "
         f"{TIPOS.get(ata.get('tipo'), ata.get('tipo'))}"
         f"{' · ' + ata['projeto'] if ata.get('projeto') else ''} · ata `{ata['id']}` "
         f"({ata.get('status')})_", ""]
    parts = [f"{p['rotulo']} = {p['nome'] or '?'}{'' if p.get('confirmado') else ' (a confirmar)'}"
             for p in ata.get("participantes", []) if p.get("nome") or p.get("fatia", 1) >= 0.05]
    if parts:
        L += ["**Participantes:** " + " · ".join(parts), ""]
    if ata.get("momentos"):
        L += ["## Momentos marcados", ""]
        for mo in ata["momentos"]:
            frase, vazio = texto_momento(mo)
            linha = f"- **{mo['id']}** [{mo.get('hora')}] " + (
                f"{frase} — \"{mo['citacao']}\" [{mo.get('t')}]" if frase else f"_{vazio}_")
            if mo.get("itens"):
                linha += " · na ata: " + ", ".join(mo["itens"])
            if mo.get("citacao_descartada"):
                linha += " · ⚠ citação do Claude descartada (não estava no trecho)"
            L.append(linha)
        L.append("")
    if ata.get("decisoes"):
        L += ["## Decisões", ""]
        for d in ata["decisoes"]:
            rev = f"revisar em {d['revisar_em']}" if d.get("revisar_em") else ""
            ok = "" if d.get("verificado") is not False else " ⚠ origem não localizada"
            L.append(f"- **{d['id']}** {d['decisao']} — {nome(d.get('quem')) or '?'}"
                     f"{' · ' + rev if rev else ''} · [{d.get('t')}]{ok}")
        L.append("")
    if ata.get("encaminhamentos"):
        L += ["## Encaminhamentos", "", "| | O quê | Quem | Até | Origem |", "|---|---|---|---|---|"]
        for x in ata["encaminhamentos"]:
            ok = "" if x.get("verificado") is not False else " ⚠"
            L.append(f"| {x['id']} | {x['acao']} | {nome(x.get('dono')) or '—'} | "
                     f"{x.get('prazo') or '—'} | {x.get('t')}{ok} |")
        L.append("")
    if ata.get("valores"):
        L += ["## Valores", "", "| | O quê | Valor | Condição | Origem |", "|---|---|---|---|---|"]
        for v in ata["valores"]:
            ok = "" if v.get("verificado") is not False else " ⚠"
            nat = " _(citado)_" if v.get("natureza") == "citado" else ""
            L.append(f"| {v['id']} | {v['descricao']}{nat} | {v['valor']} | {v.get('condicao') or '—'} | "
                     f"{v.get('t')}{ok} |")
        L.append("")
    if ata.get("resumo"):
        L += ["## Resumo", "", ata.get("contexto") or "", "", ata["resumo"], ""]
    for x in ata.get("por_tema", []):
        L += [f"### {x['tema']}", "", x["resumo"], ""]
    if ata.get("escopo"):
        L += ["## Escopo e entregas", ""] + [
            f"- **{s['id']}** {s['item']}" + (f" _({s['tema']})_" if s.get("tema") else "") + f" [{s.get('t')}]"
            for s in ata["escopo"]] + [""]
    for chave, titulo, campo in (("perguntas_abertas", "Perguntas em aberto", "pergunta"),
                                 ("riscos", "Riscos", "risco")):
        if ata.get(chave):
            L += [f"## {titulo}", ""] + [f"- **{i['id']}** {i[campo]} [{i.get('t')}]"
                                         for i in ata[chave]] + [""]
    if ata.get("temas"):
        L += ["**Temas:** " + " · ".join(ata["temas"]), ""]
    if ata.get("lacunas"):
        L += ["## Lacunas", ""] + [f"- {l['ref']}: {l['falta']}" for l in ata["lacunas"]] + [""]
    L += ["## Transcrição", ""]
    for f in _ata.falas(segs):
        L.append(f"**[{_ata.fmt_t(f['start'])}] {nome(f['speaker'])}:** {f['text']}")
    return "\n".join(L) + "\n"


# ── daily (19/10/2026) ──────────────────────────────────────────────────────
_TIPO_COM_VOCE = {"pedido": "pedido a você", "informacao": "para você saber", "decisao": "decisão"}
_LISTAS_PESSOA_TXT = (("fez", "Fez"), ("vai_fazer", "Vai fazer"), ("travado", "Travado"))


def _itens_da_mencao(ata, men):
    """Os itens da daily que trataram uma menção de frente (mesmo card, ou mesma frente a até 60 s)."""
    import daily as _daily
    out = []
    for k, it, _p in _daily.itens(ata):
        if k in ("decisoes", "encaminhamentos") or it.get("verificado") is False:
            continue
        t = _ata.parse_t(it.get("t"))
        perto = t is not None and abs(t - men["t_s"]) <= _daily.JANELA_CARD_S
        if (it.get("card") and it["card"] in men["cards"]) or (perto and it.get("frente") == men["frente"]):
            out.append(it["id"])
    return out


def html_daily(ata, segs, impressao=False):
    import daily as _daily
    nome = _nomeador(ata, cliente=False)

    def origem(it):
        marca = '<span class="alerta">origem não localizada</span>' if it.get("verificado") is False else ""
        return f'<span class="ts">{e(it.get("t"))}</span>{marca}'

    def card(it):
        return f'<span class="card">{e(it["card"])}</span>' if it.get("card") else ""

    def lacuna(txt):
        return f'<span class="lacuna">{e(txt)}</span>'

    blocos = []
    if ata.get("status") == "pendente":
        blocos.append('<section class="aviso-estado"><p>Esta daily ainda não foi estruturada. A transcrição '
                      'está completa abaixo; rode <code>/ata</code> no Claude.</p></section>')

    cv = ata.get("com_voce") or []
    if cv:
        lis = []
        for it in cv:
            meta = [_TIPO_COM_VOCE.get(it.get("tipo"), it.get("tipo") or ""),
                    _daily.quem(ata, None, it.get("quem")) if it.get("quem") else None,
                    it.get("frente")]
            meta_html = " · ".join(e(m) for m in meta if m)
            lis.append(f'<li><p>{e(it.get("o_que"))}</p><div class="meta">{card(it)}{meta_html}{origem(it)}</div></li>')
        blocos.append(f'<section><h2>Com você</h2><ul class="itens">{"".join(lis)}</ul></section>')
    elif ata.get("status") != "pendente":
        blocos.append('<section><h2>Com você</h2><p class="lacuna">nada dirigido a você nesta daily</p></section>')

    for f in ata.get("frentes") or []:
        if not f["mencoes"]:
            corpo = '<p class="lacuna">nada dito sobre esta frente</p>'
        else:
            lis = []
            for men in f["mencoes"]:
                ids = _itens_da_mencao(ata, men)
                if ids:
                    situ = "na ata: " + ", ".join(e(i) for i in ids)
                elif men.get("tratada") is False:
                    situ = lacuna("menção não tratada")
                else:
                    situ = ""
                cards = "".join(f'<span class="card">{e(c)}</span>' for c in men["cards"])
                lis.append(f'<li><p>{e(men["trecho"])}</p><div class="meta">{cards}{e(nome(men["rotulo"]))}'
                           f'<span class="ts">{e(men["t"])}</span>{(" · " + situ) if situ else ""}</div></li>')
            corpo = f'<ul class="itens">{"".join(lis)}</ul>'
        blocos.append(f'<section><h2>{e(f["nome"])}</h2>{corpo}</section>')

    pes = ata.get("pessoas") or []
    if pes:
        partes = []
        for p in pes:
            sub = []
            for k, rot in _LISTAS_PESSOA_TXT:
                its = p.get(k) or []
                if its:
                    sub.append(f'<h4>{rot}</h4><ul class="simples">' + "".join(
                        f'<li>{card(it)}{e(it.get("item"))} {origem(it)}</li>' for it in its) + "</ul>")
            partes.append(f'<div class="pessoa"><h3>{e(_daily.quem(ata, p.get("rotulo"), p.get("nome")))}</h3>'
                          + ("".join(sub) or '<p class="lacuna">sem item com citação</p>') + "</div>")
        blocos.append(f'<section><h2>Por pessoa</h2>{"".join(partes)}</section>')

    dec = ata.get("decisoes") or []
    if dec:
        lis = [f'<li><p>{e(d["decisao"])}</p><div class="meta">{e(nome(d.get("quem")) or "")}{origem(d)}</div></li>'
               for d in dec]
        blocos.append(f'<section><h2>Decisões</h2><ul class="itens">{"".join(lis)}</ul></section>')
    enc = ata.get("encaminhamentos") or []
    if enc:
        rows = "".join(
            f'<tr><td>{e(x["acao"])}<div class="meta">{origem(x)}</div></td>'
            f'<td>{e(nome(x.get("dono"))) if x.get("dono") else lacuna("a definir")}</td>'
            f'<td class="prazo">{e(data_curta(x["prazo"])) if x.get("prazo") else lacuna("a definir")}</td></tr>'
            for x in enc)
        blocos.append('<section><h2>Encaminhamentos</h2><table class="enc"><thead><tr>'
                      '<th>O quê</th><th>Quem</th><th>Até</th></tr></thead>'
                      f'<tbody>{rows}</tbody></table></section>')

    todas_falas = _ata.falas(segs)
    if ata.get("momentos"):
        blocos.append(_secao_momentos(ata["momentos"], todas_falas))

    mais = []
    if ata.get("resumo") or ata.get("contexto"):
        mais.append("<h3>Resumo</h3>" + (f'<p class="ctx">{e(ata["contexto"])}</p>' if ata.get("contexto") else "")
                    + (f'<p>{e(ata["resumo"])}</p>' if ata.get("resumo") else ""))
    if ata.get("rodada"):
        mais.append('<h3>Quem falou, pela rodada (pista, a confirmar no /ata)</h3><ul class="simples">' + "".join(
            f'<li><b>{e(r["rotulo"])}</b> → {e(r["nome"])}? ({r["votos"]}×) <span class="ts">{e(r["evidencias"][0])}</span></li>'
            for r in ata["rodada"]) + "</ul>")
    if ata.get("lacunas"):
        mais.append('<h3>Lacunas a fechar</h3><ul class="simples">' + "".join(
            f'<li><b>{e(nome(l["ref"]))}</b> — {e(l["falta"])}</li>' for l in ata["lacunas"]) + "</ul>")
    aberto = " open" if impressao else ""
    if mais:
        blocos.append(f'<details class="mais"{aberto}><summary>Mais</summary>'
                      f'<div class="mais-corpo">{"".join(mais)}</div></details>')

    falas = []
    for f in todas_falas:
        eu = f["speaker"] == "Você"
        falas.append(f'<div class="fala{" eu" if eu else ""}" id="f-{int(f["start"])}"><div class="quem">'
                     f'{e(nome(f["speaker"]))}<span class="ts">{_ata.fmt_t(f["start"])}</span>'
                     f'</div><div class="txt">{e(f["text"])}</div></div>')
    blocos.append(f'<details class="transc"{aberto}><summary>Transcrição</summary>'
                  f'<div class="falas">{"".join(falas) or "<p>Sem falas reconhecidas.</p>"}</div></details>')

    n_pes = len([p for p in ata.get("participantes", []) if p["rotulo"] != "Você"
                 and (p.get("nome") or p.get("fatia", 0) >= _daily.FATIA_RELEVANTE)])
    meta_topo = " · ".join(x for x in [data_br(ata.get("data")),
                                       f"{ata.get('duracao_min')} min" if ata.get("duracao_min") else None,
                                       f"{n_pes} vozes além de você" if n_pes else None] if x)
    topo = _tema.capa(ata.get("titulo"), "Daily · Parresia", meta_topo, selo="Uso interno")
    rodape = _tema.rodape("daily · uso interno · fora da medição · gerado nesta máquina")
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex"><title>{e(ata.get("titulo"))}</title>'
            f'{_tema.FONTES}<style>{_tema.CSS}{CSS_BASE}{CSS_DAILY}</style>'
            f'</head><body class="interno"><div class="wrap">{topo}{"".join(blocos)}'
            f'{rodape}</div></body></html>')


CSS_DAILY = """
.card{font-family:var(--mono);font-size:11.5px;color:var(--accent);margin-right:8px;white-space:nowrap}
.pessoa{margin:0 0 30px}
.pessoa h3{margin:0 0 6px}
h4{font-size:11px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin:14px 0 6px}
"""


def markdown_daily(ata, segs):
    import daily as _daily
    nome = _nomeador(ata, cliente=False)

    def card(it):
        return f"`{it['card']}` " if it.get("card") else ""

    def ok(it):
        return "" if it.get("verificado") is not False else " ⚠ origem não localizada"

    L = [f"# {ata.get('titulo')}", "",
         f"_{data_br(ata.get('data'))} · {ata.get('duracao_min')} min · Daily da Parresia (fora da medição) · "
         f"ata `{ata['id']}` ({ata.get('status')})_", ""]
    parts = [f"{p['rotulo']} = {p['nome'] or '?'}{'' if p.get('confirmado') else ' (a confirmar)'}"
             for p in ata.get("participantes", []) if p.get("nome") or p.get("fatia", 1) >= _daily.FATIA_RELEVANTE]
    if parts:
        L += ["**Quem falou:** " + " · ".join(parts), ""]
    L += ["## Com você", ""]
    if ata.get("com_voce"):
        for it in ata["com_voce"]:
            quem_ = _daily.quem(ata, None, it.get("quem")) if it.get("quem") else "?"
            L.append(f"- **{it['id']}** {card(it)}{it.get('o_que')} — {_TIPO_COM_VOCE.get(it.get('tipo'), it.get('tipo'))}"
                     f" · {quem_}{' · ' + it['frente'] if it.get('frente') else ''} · [{it.get('t')}]{ok(it)}")
    else:
        L.append("_nada dirigido a você_")
    L.append("")
    for f in ata.get("frentes") or []:
        L += [f"## {f['nome']}", ""]
        if not f["mencoes"]:
            L.append("_nada dito sobre esta frente_")
        for men in f["mencoes"]:
            ids = _itens_da_mencao(ata, men)
            situ = ("na ata: " + ", ".join(ids)) if ids else ("**menção não tratada**" if men.get("tratada") is False else "")
            cards = " ".join(f"`{c}`" for c in men["cards"])
            L.append(f"- [{men['t']}] {nome(men['rotulo'])}: {cards + ' ' if cards else ''}\"{men['trecho']}\""
                     + (f" · {situ}" if situ else ""))
        L.append("")
    if ata.get("pessoas"):
        L += ["## Por pessoa", ""]
        for p in ata["pessoas"]:
            L += [f"### {_daily.quem(ata, p.get('rotulo'), p.get('nome'))}", ""]
            for k, rot in _LISTAS_PESSOA_TXT:
                for it in p.get(k) or []:
                    L.append(f"- _{rot.lower()}_ **{it['id']}** {card(it)}{it.get('item')} [{it.get('t')}]{ok(it)}")
            L.append("")
    if ata.get("decisoes"):
        L += ["## Decisões", ""] + [f"- **{d['id']}** {d['decisao']} — {nome(d.get('quem')) or '?'} · [{d.get('t')}]{ok(d)}"
                                    for d in ata["decisoes"]] + [""]
    if ata.get("encaminhamentos"):
        L += ["## Encaminhamentos", "", "| | O quê | Quem | Até | Origem |", "|---|---|---|---|---|"]
        L += [f"| {x['id']} | {x['acao']} | {nome(x.get('dono')) or '—'} | {x.get('prazo') or '—'} | {x.get('t')}"
              f"{' ⚠' if x.get('verificado') is False else ''} |" for x in ata["encaminhamentos"]] + [""]
    if ata.get("momentos"):
        L += ["## Momentos marcados", ""]
        for mo in ata["momentos"]:
            frase, vazio = texto_momento(mo)
            L.append(f"- **{mo['id']}** [{mo.get('hora')}] " + (f"{frase} — \"{mo['citacao']}\" [{mo.get('t')}]"
                                                              if frase else f"_{vazio}_")
                     + (" · na ata: " + ", ".join(mo["itens"]) if mo.get("itens") else ""))
        L.append("")
    if ata.get("resumo"):
        L += ["## Resumo", "", ata.get("contexto") or "", "", ata["resumo"], ""]
    if ata.get("rodada"):
        L += ["## Quem falou, pela rodada (pista)", ""] + [
            f"- {r['rotulo']} → {r['nome']}? ({r['votos']}×): {r['evidencias'][0]}" for r in ata["rodada"]] + [""]
    if ata.get("lacunas"):
        L += ["## Lacunas", ""] + [f"- {l['ref']}: {l['falta']}" for l in ata["lacunas"]] + [""]
    L += ["## Transcrição", ""]
    for f in _ata.falas(segs):
        L.append(f"**[{_ata.fmt_t(f['start'])}] {nome(f['speaker'])}:** {f['text']}")
    return "\n".join(L) + "\n"

