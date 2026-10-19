# -*- coding: utf-8 -*-
"""
Daily da Parresia (19/10/2026) — a ata `atas/daily@1` e os passos determinísticos dela.

Pedido do Pedro: dailies de mais de 1 h, 7 ou mais pessoas (o número varia), uma rodada em que o
Otávio chama cada um pelo nome. Ele fala pouco (09/10: 8,9% da fala) e quer achar depois QUEM
disse O QUÊ sobre QUAL card — em 19/10 uma informação do Rogério sobre o SUP-953 só existia numa
daily não gravada. Não quer digitar participante nome a nome. Detalhe: docs/ARQUITETURA.md §21.

    falantes / participantes   como na ata@1 (rótulo → nome, confirmado só pelo Pedro)
    contexto, resumo
    pessoas      [{nome, rotulo, fez[], vai_fazer[], travado[]}]
                 cada item {id F1/A1/T1.., item, card, t, citacao, verificado, problemas[]}
    com_voce     [{id C1.., o_que, quem, card, frente, tipo: pedido|informacao|decisao, t, citacao, ...}]
                 o que foi dirigido ao Pedro ou toca as frentes que ele acompanha
    decisoes, encaminhamentos   como na ata@1 (só os reais; decisões vão ao decisoes.jsonl pelo /ata)
    momentos     as marcas Ctrl+Alt+M, o mesmo mecanismo de marcas.py
    frentes      [{nome, cards, mencoes: [{t, rotulo, trecho, cards, palavras, tratada}]}]  — calculado
    rodada       [{rotulo, nome, votos, evidencias[], outros{}}]  — calculado: pista, nunca confirmação
    equipe, frentes_rastreadas   o que a ata usou do config (a auditoria refaz as contas sem o config)
    lacunas, gerado, status

Garantias, todas no código (não no prompt):
  - **Nada inventado**: a citação de todo item é conferida contra a transcrição (`ata.auditar_item`,
    a mesma das atas normais).
  - **Card conferido**: `SUP-NNN` só fica se o número for dito na fala citada ou a até ±60 s dela;
    senão vira null + lacuna. (O Claude adora completar card que "deve ser".)
  - **Menção não tratada**: card de frente rastreada dito na reunião que não virou item verificado vira
    lacuna — é exatamente a informação do Rogério que se perdeu em 19/10.
  - **Rodada**: vocativo ("Rogério, e você?", "fala, Rogério", "Rogério?") seguido de troca de rótulo
    em até ~10 s propõe rótulo → nome, com a evidência. É pista para o Claude e para o /ata; o nome só
    fica confirmado quando o Pedro confirma.
  - Fora de toda medição: ver `sessao.fora_da_medicao` (pipeline, analise_fala, avaliar, app, atas.py).
"""
import re
import unicodedata

import ata as _ata

SCHEMA = _ata.SCHEMA_DAILY
LISTAS_PESSOA = (("fez", "F"), ("vai_fazer", "A"), ("travado", "T"))
LISTAS_ATA = (("decisoes", "D"), ("encaminhamentos", "E"))
TIPOS_COM_VOCE = ("pedido", "informacao", "decisao")
JANELA_CARD_S = 60          # o card tem de ser dito na fala citada ou a até 60 s dela
TROCA_S = 10                # vocativo → outro rótulo começa a falar em até 10 s
FATIA_RELEVANTE = 0.015     # na daily, quem fala 1 min em 1 h já é gente (a ata normal usa 5%)
_RE_CARD = re.compile(r"\bSUP[\s\-_]*(\d{2,5})\b", re.I)


# ── texto ───────────────────────────────────────────────────────────────────
def _sem_acento(t):
    """Minúsculo e sem acento, MANTENDO a pontuação (o vocativo depende da vírgula e do '?')."""
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


def normalizar_card(v):
    """'sup 953', 'SUP-953', 'Sup_953' → 'SUP-953'; o resto → None."""
    m = _RE_CARD.search(str(v or ""))
    return f"SUP-{int(m.group(1))}" if m else None


def _numero(card):
    return card.split("-", 1)[1]


def card_na_fala(card, texto):
    """O card foi dito neste texto? Vale "SUP 953"/"SUP-953" e o número sozinho ("o 953"): na fala o
    prefixo some quase sempre. Número dito por extenso não é reconhecido (limite conhecido)."""
    n = _numero(card)
    return _ata._contem(f"sup {n}", texto) or _ata._contem(n, texto)


def _perto(fl, i, janela_s):
    """As falas a até `janela_s` da fala i (pelas bordas dela), inclusive ela."""
    ini, fim = fl[i]["start"] - janela_s, fl[i]["end"] + janela_s
    return [f for f in fl if f["end"] >= ini and f["start"] <= fim]


def card_dito_perto(card, fl, i, janela_s=JANELA_CARD_S):
    return any(card_na_fala(card, f["text"]) for f in _perto(fl, i, janela_s))


def _trecho(texto, alvo=None, raio=110):
    """Um pedaço da fala em volta do que foi achado (para a lista do prompt e para a busca)."""
    texto = str(texto or "")
    pos = -1
    if alvo:
        m = re.search(re.escape(_sem_acento(alvo)), _sem_acento(texto))
        pos = m.start() if m else -1
    if pos < 0 or len(texto) <= 2 * raio:
        return texto if len(texto) <= 2 * raio else texto[:2 * raio].rstrip() + "…"
    ini = max(0, pos - raio)
    fim = min(len(texto), pos + raio)
    return ("…" if ini else "") + texto[ini:fim].strip() + ("…" if fim < len(texto) else "")


# ── frentes rastreadas ──────────────────────────────────────────────────────
def frentes_do_config(cfg):
    out = []
    for fr in (cfg or {}).get("frentes_rastreadas") or []:
        if not fr.get("nome"):
            continue
        cards = [c for c in (normalizar_card(x) for x in fr.get("cards") or []) if c]
        out.append({"nome": fr["nome"], "palavras": [p for p in fr.get("palavras") or [] if str(p).strip()],
                    "cards": list(dict.fromkeys(cards))})
    return out


def mencoes(fl, frentes):
    """As falas que tocam cada frente (um card dela ou uma palavra dela), na ordem do tempo. Passo
    determinístico: é a lista que o Claude TEM de tratar, e a base da lacuna "menção não tratada"."""
    out = []
    for f in fl:
        for fr in frentes:
            cards = [c for c in fr["cards"] if card_na_fala(c, f["text"])]
            palavras = [p for p in fr["palavras"] if _ata._contem(p, f["text"])]
            if cards or palavras:
                alvo = _numero(cards[0]) if cards else palavras[0]
                out.append({"frente": fr["nome"], "t": _ata.fmt_t(f["start"]), "t_s": f["start"],
                            "rotulo": f["speaker"], "trecho": _trecho(f["text"], alvo),
                            "cards": cards, "palavras": palavras})
    return out


# ── rodada: vocativo + troca de rótulo ─────────────────────────────────────
_CHAMA_DEPOIS = (r"e voce|e ai|sua vez|tua vez|pode falar|pode ir|pode comecar|pode seguir|manda ai|"
                 r"com voce|contigo|vai la|fala ai|me fala|sua atualizacao|seu status|como (?:e que )?(?:ta|esta)|"
                 r"quer complementar|quer falar|alguma coisa|algo mais")
_CHAMA_ANTES = (r"fala|vai|e voce|e ai|agora|sua vez|tua vez|bora|manda ai|vamos la|passa pr[oa]|"
                r"passando pr[oa]|vamos com|vamos pr[oa]|chamar")


def _padroes_vocativo(nome):
    n = re.escape(_sem_acento(nome))
    return [
        re.compile(rf"\b{n}\s*[,.!]?\s*(?:{_CHAMA_DEPOIS})\b"),                 # "Rogério, e você?"
        re.compile(rf"\b(?:{_CHAMA_ANTES})\s*,?\s*(?:o |a |ai |ai, |la )?{n}\b"),  # "fala, Rogério"
        re.compile(rf"(?:^|[.?!]\s*|\b(?:o|e)\s*,?\s*)ai\s*,\s*{n}\b"),        # "Aí, Augusto, …" (com vírgula: "aí o Caio chegou" não)
        # "Rogério?" — mas não "falou com o Rogério?" (pergunta SOBRE ele)
        re.compile(rf"(?<!\bo )(?<!\ba )(?<!\bdo )(?<!\bda )(?<!\bpro )(?<!\bpra )(?<!\bcom )\b{n}\s*\?"),
    ]


def vocativos(texto, equipe, meu_nome=None):
    """Os nomes da equipe chamados no texto (vocativo), na ordem em que aparecem."""
    sa = _sem_acento(texto)
    achados = []
    for nome in equipe:
        if meu_nome and _sem_acento(nome) == _sem_acento(meu_nome):
            continue
        for rx in _padroes_vocativo(nome):
            m = rx.search(sa)
            if m:
                achados.append((m.start(), nome))
                break
    return [n for _, n in sorted(achados)]


def rodada(segs, equipe, meu_nome="Pedro", troca_s=TROCA_S, max_evid=3):
    """Propõe rótulo → nome pela rodada: um trecho com vocativo ("Rogério, e você?") seguido, em até
    `troca_s`, de OUTRO rótulo começando a falar. Trabalha nos trechos (não nas falas fundidas): o
    vocativo costuma fechar um trecho. "Você" nunca é proposto (é o Pedro, já se sabe).
    Devolve [{rotulo, nome, votos, evidencias[], outros{nome: votos}}], o rótulo com mais votos primeiro."""
    if not equipe:
        return []
    ss = sorted(segs, key=lambda s: s["start"])
    votos = {}
    for k, s in enumerate(ss):
        nomes = vocativos(s["text"], equipe, meu_nome)
        if not nomes:
            continue
        nome = nomes[-1]                      # o último chamado no trecho é quem fala a seguir
        prox = None
        for x in ss[k + 1:]:
            if x["start"] > s["end"] + troca_s:
                break
            if x["speaker"] == s["speaker"]:
                break                         # quem chamou continuou falando: não é passagem de vez
            prox = x
            break
        if not prox or prox["speaker"] == "Você":
            continue
        ev = (f"[{_ata.fmt_t(s['start'])}] {s['speaker']}: \"{_trecho(s['text'], nome, 60)}\" → "
              f"[{_ata.fmt_t(prox['start'])}] {prox['speaker']} começa a falar")
        por = votos.setdefault(prox["speaker"], {})
        por.setdefault(nome, []).append(ev)
    out = []
    for rot, por in votos.items():
        ordem = sorted(por.items(), key=lambda kv: -len(kv[1]))
        nome, evs = ordem[0]
        out.append({"rotulo": rot, "nome": nome, "votos": len(evs), "evidencias": evs[:max_evid],
                    "outros": {n: len(e) for n, e in ordem[1:]}})
    out.sort(key=lambda r: (-r["votos"], r["rotulo"]))
    return out


# ── a ata ───────────────────────────────────────────────────────────────────
def equipe_do_config(cfg):
    import config as _config
    return list((cfg or {}).get("daily_equipe") or _config.PADROES["daily_equipe"])


def base(sessao, segs, meu_nome, dur=None, cfg=None):
    """A ata daily vazia (status pendente). Equipe e frentes vêm do config e ficam gravadas na ata."""
    import config as _config
    cfg = cfg if cfg is not None else _config.carregar()
    m = sessao.m
    dur = dur if dur is not None else max((s["end"] for s in segs), default=0)
    a = {
        "schema": SCHEMA,
        "id": m["id"],
        "titulo": m.get("titulo"),
        "tipo": m.get("tipo"),
        "formato": m.get("formato"),
        "projeto": m.get("projeto") or None,
        "data": m.get("inicio") or m.get("criado"),
        "duracao_min": round(max(dur, sessao.duracao_s()) / 60),
        "participantes": _ata.participantes_iniciais(segs, meu_nome, sessao.participantes_remotos(),
                                                     _ata._voce_a_confirmar(sessao), daily=True),
        "contexto": None, "resumo": None,
        "pessoas": [], "com_voce": [], "decisoes": [], "encaminhamentos": [],
        "momentos": [_ata._momento_vazio(i, mk) for i, mk in _ata._marcas_identificadas(m.get("marcas"))],
        "equipe": equipe_do_config(cfg),
        "frentes_rastreadas": frentes_do_config(cfg),
        "frentes": [], "rodada": [],
        "lacunas": [], "gerado": None, "revisado": None, "status": "pendente",
    }
    _calcular(a, segs)
    return a


def _meu_nome(ata):
    return next((p.get("nome") for p in ata.get("participantes", []) if p["rotulo"] == "Você"), None) or "Pedro"


def itens(ata):
    """Todos os itens auditáveis da daily: (lista, item, pessoa ou None)."""
    for p in ata.get("pessoas", []):
        for k, _ in LISTAS_PESSOA:
            for it in p.get(k) or []:
                yield k, it, p
    for it in ata.get("com_voce", []):
        yield "com_voce", it, None
    for k, _ in LISTAS_ATA:
        for it in ata.get(k, []):
            yield k, it, None


def _calcular(ata, segs):
    """Frentes (menções) e rodada: refeitos do zero a cada auditoria, a partir da transcrição e do que a
    ata guardou do config. Nunca escritos pelo Claude."""
    fl = _ata.falas(segs)
    fr = ata.get("frentes_rastreadas") or []
    todas = mencoes(fl, fr)
    ata["frentes"] = [{"nome": f["nome"], "cards": f["cards"],
                       "mencoes": [m for m in todas if m["frente"] == f["nome"]]} for f in fr]
    ata["rodada"] = rodada(segs, ata.get("equipe") or [], _meu_nome(ata))
    return fl


def _conferir_card(it, fl, i):
    probs = it.setdefault("problemas", [])
    if "card" in set(it.get("manual") or []):
        return
    c = it.get("card")
    if not c:
        it["card"] = None
        return
    n = normalizar_card(c)
    if n is None:
        motivo = f"card '{c}' fora do padrão SUP-NNN"
    elif i is None:
        motivo = f"card {n} sem fala citada para conferir"
    elif not card_dito_perto(n, fl, i):
        motivo = f"card {n} não foi dito na fala citada nem a até {JANELA_CARD_S} s dela"
    else:
        it["card"] = n
        it.pop("card_removido", None)
        return
    probs.append(motivo + ": removido")
    it["card"] = None
    it["card_removido"] = n or str(c)


def _tratada(ata, men, card):
    """A menção (card dito numa fala) virou item verificado? Vale um item com o mesmo card em qualquer
    ponto, ou um item da mesma frente a até 60 s da fala da menção."""
    cards_frente = next((f["cards"] for f in ata.get("frentes", []) if f["nome"] == men["frente"]), [])
    for k, it, _p in itens(ata):
        if k in ("decisoes", "encaminhamentos") or it.get("verificado") is False:
            continue
        if it.get("card") == card:
            return True
        t = _ata.parse_t(it.get("t"))
        if (t is not None and abs(t - men["t_s"]) <= JANELA_CARD_S
                and (it.get("frente") == men["frente"] or it.get("card") in cards_frente)):
            return True
    return False


def auditar(ata, segs):
    fl = _calcular(ata, segs)
    blob, conhecidos = _ata.contexto_auditoria(ata, fl)
    conhecidos |= {_ata.norm(n) for n in ata.get("equipe") or []}
    for k, it, _p in itens(ata):
        i = _ata.auditar_item(it, fl, blob, conhecidos, ata.get("data"))
        if k not in ("decisoes", "encaminhamentos"):
            _conferir_card(it, fl, i)
        if k == "com_voce" and it.get("tipo") not in TIPOS_COM_VOCE:
            it["tipo"] = "informacao"
    for f in ata.get("frentes", []):
        for men in f["mencoes"]:
            # só menção com CARD vira lacuna; a de palavra ("frota") é pista para o Claude, não cobrança
            men["tratada"] = all(_tratada(ata, men, c) for c in men["cards"]) if men["cards"] else None
    _ata.auditar_momentos(ata, fl)
    for mo in ata.get("momentos") or []:          # a marca liga também aos itens da daily
        import marcas as _marcas
        extra = [it["id"] for k, it, _p in itens(ata) if k not in ("decisoes", "encaminhamentos")
                 and it.get("verificado") is not False and _ata.parse_t(it.get("t")) is not None
                 and _marcas.dentro(_ata.parse_t(it["t"]), mo["marca_t"], folga_s=0)]
        mo["itens"] = list(dict.fromkeys((mo.get("itens") or []) + extra))
    ata["lacunas"] = lacunas(ata)
    return ata


def lacunas(ata):
    citados = {it.get(c) for _k, it, _p in itens(ata) for c in ("dono", "quem")}
    citados |= {p.get("rotulo") for p in ata.get("pessoas", [])}
    out = _ata.lacunas_participantes(ata, citados, FATIA_RELEVANTE)
    por_rotulo = {p["rotulo"]: p for p in ata.get("participantes", [])}
    for r in ata.get("rodada") or []:              # a rodada e o texto discordam: o Pedro decide
        p = por_rotulo.get(r["rotulo"])
        if p and p.get("nome") and not p.get("confirmado") and _ata.norm(p["nome"]) != _ata.norm(r["nome"]):
            out.append({"ref": r["rotulo"], "falta": f"a rodada aponta {r['nome']} ({r['votos']}×), a ata deduziu "
                                                    f"{p['nome']}: confirmar quem é"})
    for e in ata.get("encaminhamentos", []):
        if not e.get("dono"):
            out.append({"ref": e["id"], "falta": "dono"})
        if not e.get("prazo"):
            out.append({"ref": e["id"], "falta": "prazo"})
    for _k, it, _p in itens(ata):
        if it.get("verificado") is False:
            out.append({"ref": it["id"], "falta": "trecho de origem (não localizado)"})
        if it.get("card_removido"):
            out.append({"ref": it["id"], "falta": f"card {it['card_removido']} citado pelo Claude mas não dito "
                                                  f"perto da fala (conferir)"})
    for f in ata.get("frentes", []):
        for men in f["mencoes"]:
            if men.get("tratada") is False:
                for c in men["cards"]:
                    if not _tratada(ata, men, c):
                        out.append({"ref": f"[{men['t']}]", "falta": f"menção não tratada: {c} ({f['nome']}), "
                                                                     f"{men['rotulo']}: \"{men['trecho'][:90]}\""})
    return out


def contagem(ata):
    todos = list(itens(ata))
    men = [m for f in ata.get("frentes", []) for m in f["mencoes"]]
    return {
        "pessoas": len(ata.get("pessoas", [])),
        "itens": sum(1 for k, _it, _p in todos if k in dict(LISTAS_PESSOA)),
        "com_voce": len(ata.get("com_voce", [])),
        "decisoes": len(ata.get("decisoes", [])),
        "encaminhamentos": len(ata.get("encaminhamentos", [])),
        "nao_verificados": sum(1 for _k, it, _p in todos if it.get("verificado") is False),
        "cards_removidos": sum(1 for _k, it, _p in todos if it.get("card_removido")),
        "mencoes": len(men),
        "mencoes_nao_tratadas": sum(1 for m in men if m.get("tratada") is False),
        "lacunas": len(ata.get("lacunas", [])),
    }


def resumo_contagem(c):
    return (f"{c['pessoas']} pessoas · {c['itens']} itens · {c['com_voce']} com você · "
            f"{c['nao_verificados']} sem origem · {c['lacunas']} lacunas")


def montar(sessao, segs, bruto, gerado, meu_nome, cfg=None):
    """A ata daily canônica a partir da saída do Claude + o que o código já sabe."""
    a = base(sessao, segs, meu_nome, cfg=cfg)
    a["_remotos"] = sessao.participantes_remotos()
    a["contexto"] = bruto.get("contexto")
    a["resumo"] = bruto.get("resumo")
    por_rotulo = {f.get("rotulo"): f for f in bruto.get("falantes", [])}
    for p in a["participantes"]:
        f = por_rotulo.get(p["rotulo"])
        if p["confirmado"] or not f or not f.get("nome"):
            continue
        p.update({"nome": f["nome"], "origem": "deduzido", "confirmado": False, "evidencia": f.get("evidencia")})
    cont = {pref: 0 for _k, pref in LISTAS_PESSOA}
    pessoas = []
    for p in bruto.get("pessoas", []):
        novo = {"nome": p.get("nome"), "rotulo": p.get("rotulo")}
        for k, pref in LISTAS_PESSOA:
            novo[k] = []
            for it in p.get(k) or []:
                cont[pref] += 1
                novo[k].append({**dict(it), "id": f"{pref}{cont[pref]}"})
        pessoas.append(novo)
    a["pessoas"] = pessoas
    a["com_voce"] = [{**dict(it), "id": f"C{n}"} for n, it in enumerate(bruto.get("com_voce", []), 1)]
    for k, pref in LISTAS_ATA:
        a[k] = [{**dict(it), "id": f"{pref}{n}"} for n, it in enumerate(bruto.get(k, []), 1)]
    _ata.sincronizar_momentos(a, sessao.m.get("marcas"), bruto.get("momentos") or [])
    a["gerado"] = gerado
    a["status"] = "estruturada"
    auditar(a, segs)
    a.pop("_remotos", None)
    return a


# ── nomes e busca ───────────────────────────────────────────────────────────
def quem(ata, rotulo=None, nome=None):
    """Como mostrar quem falou: o nome confirmado; senão "Rótulo (nome?)"; senão o rótulo. `nome` (o
    que o Claude escreveu num item) só vale com "?" se ninguém confirmou."""
    parts = ata.get("participantes", [])
    p = next((x for x in parts if rotulo and x["rotulo"] == rotulo), None)
    if p is None and nome:                        # o Claude escreveu o rótulo no lugar do nome
        p = next((x for x in parts if x["rotulo"] == nome), None)
    if p is not None:
        if p.get("nome") and p.get("confirmado"):
            return p["nome"]
        palpite = p.get("nome") or (nome if nome and nome != p["rotulo"] else None)
        return f"{p['rotulo']} ({palpite}?)" if palpite else p["rotulo"]
    if not nome:
        return rotulo or "?"
    if any(x.get("nome") == nome and x.get("confirmado") for x in parts):
        return nome
    q = next((x for x in parts if x.get("nome") == nome), None)
    return f"{q['rotulo']} ({nome}?)" if q else f"{nome}?"


def buscar(ata, segs, termo, pessoa=None, frente=None):
    """As menções a `termo` numa daily: itens da ata (pessoas, com você, decisões, encaminhamentos) e,
    se a ata não tiver nada, a transcrição. Devolve [{t, quem, card, onde, texto}]."""
    alvo = _ata.norm(termo)
    card_alvo = normalizar_card(termo)
    pes = _ata.norm(pessoa) if pessoa else None
    out = []

    def bate_pessoa(q):
        return not pes or pes in _ata.norm(q)

    fr = next((f for f in ata.get("frentes_rastreadas") or [] if frente and _ata.norm(f["nome"]) == _ata.norm(frente)),
              None)

    def bate_frente(it):
        if not frente:
            return True
        return (_ata.norm(it.get("frente")) == _ata.norm(frente)
                or (fr is not None and it.get("card") in fr["cards"]))

    def bate_texto(*partes):
        txt = " ".join(str(x or "") for x in partes)
        return (card_alvo and card_alvo in {normalizar_card(x) for x in re.findall(r"SUP[\s\-_]*\d+", txt, re.I)}) \
            or alvo in _ata.norm(txt)

    for p in ata.get("pessoas", []):
        q = quem(ata, p.get("rotulo"), p.get("nome"))
        for k, rot in (("fez", "fez"), ("vai_fazer", "vai fazer"), ("travado", "travado")):
            for it in p.get(k) or []:
                if bate_pessoa(q) and bate_frente(it) and bate_texto(it.get("item"), it.get("card"), it.get("citacao")):
                    out.append({"t": it.get("t"), "quem": q, "card": it.get("card"), "onde": f"{it['id']} {rot}",
                                "texto": it.get("item"), "verificado": it.get("verificado")})
    for it in ata.get("com_voce", []):
        q = quem(ata, None, it.get("quem")) if it.get("quem") else "?"
        if bate_pessoa(q) and bate_frente(it) and bate_texto(it.get("o_que"), it.get("card"), it.get("citacao"), it.get("frente")):
            out.append({"t": it.get("t"), "quem": q, "card": it.get("card"), "onde": f"{it['id']} com você",
                        "texto": it.get("o_que"), "verificado": it.get("verificado")})
    for k, campo, quem_campo in (("decisoes", "decisao", "quem"), ("encaminhamentos", "acao", "dono")):
        for it in ata.get(k, []):
            q = quem(ata, None, it.get(quem_campo)) if it.get(quem_campo) else "?"
            if bate_pessoa(q) and not frente and bate_texto(it.get(campo), it.get("citacao")):
                out.append({"t": it.get("t"), "quem": q, "card": None, "onde": it["id"], "texto": it.get(campo),
                            "verificado": it.get("verificado")})
    if not out:                                   # reserva: a transcrição
        nomes = {p["rotulo"]: quem(ata, p["rotulo"]) for p in ata.get("participantes", [])}
        for f in _ata.falas(segs):
            q = nomes.get(f["speaker"], f["speaker"])
            achou = (card_alvo and card_na_fala(card_alvo, f["text"])) or alvo in _ata.norm(f["text"])
            na_frente = not frente or (fr is not None and (
                any(card_na_fala(c, f["text"]) for c in fr["cards"])
                or any(_ata._contem(w, f["text"]) for w in fr["palavras"])))
            if achou and bate_pessoa(q) and na_frente:
                cards = [c for c in ([card_alvo] if card_alvo else []) if card_na_fala(c, f["text"])]
                out.append({"t": _ata.fmt_t(f["start"]), "quem": q, "card": cards[0] if cards else None,
                            "onde": "transcrição", "texto": _trecho(f["text"], _numero(card_alvo) if card_alvo else termo),
                            "verificado": None})
    out.sort(key=lambda x: _ata.parse_t(x.get("t")) or 0)
    return out
