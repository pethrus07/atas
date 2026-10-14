# -*- coding: utf-8 -*-
"""
A ata canônica — `ata.json`, schema `atas/ata@1`.

Tudo o que sai de uma reunião (página, PDF, .md, índice, o /ata, o log de decisões)
é RENDERIZAÇÃO deste arquivo. Ele é dado, não prosa.

    participantes   [{rotulo, nome, origem, confirmado, evidencia}]
    contexto, resumo, temas[]
    decisoes        [{id D1.., decisao, quem, contexto, revisar_em, revisar_em_dito,
                      t, citacao, verificado, problemas[]}]
    encaminhamentos [{id E1.., acao, dono, prazo, prazo_dito, t, citacao, verificado, problemas[]}]
    perguntas_abertas [{id P1.., pergunta, t, citacao, verificado, problemas[]}]
    riscos          [{id R1.., risco, t, citacao, verificado, problemas[]}]
    valores         [{id V1.., descricao, valor, condicao, t, citacao, verificado, problemas[]}]
    escopo          [{id S1.., item, tema, t, citacao, verificado, problemas[]}]
    por_tema        [{tema, resumo}]  — prosa por assunto (v2.1, 06/10/2026: a reunião de 3 h com o
                      Valter tratou de 3 projetos, e valores e lista de funcionalidades não tinham lugar)
    lacunas         [{ref, falta}]   — calculado, nunca escrito à mão
    gerado          {por, modelo, em, segundos, custo_usd, versao_prompt}
    status          pendente | estruturada | revisada

**Nada inventado** (R3). Todo item traz `citacao` (trecho literal) e `t` (timestamp
da fala). `auditar()` confere cada um contra a transcrição:
  - citação não encontrada           → `verificado: false` (não vai ao cliente)
  - citação achada em outra fala     → `t` corrigido, anotado em `problemas`
  - prazo/revisão sem a expressão dita localizada → o campo vira null (lacuna)
  - dono que não aparece em lugar nenhum          → anotado em `problemas`
O que não foi dito aparece como LACUNA, não como dado. Um campo que o Pedro
preencher depois da reunião entra em `manual: ["prazo", ...]` e não é auditado — é
dado dele, não da transcrição.

O formato das decisões é o mesmo do log `qa-parresia/rotinas/decisoes.jsonl`
({data, decisao, contexto, quem, destrava, revisar_em}) mais a `origem` — para o
log de decisões e o painel de PO consumirem direto (ver `decisao_para_log`).
"""
import re
import unicodedata

SCHEMA_ATA = "atas/ata@1"

# Esquema entregue ao Claude (--json-schema). Só o que ele produz; ids, verificação
# e lacunas são responsabilidade do código.
_S = {"type": "string"}
_SN = {"type": ["string", "null"]}
ESQUEMA_CLAUDE = {
    "type": "object",
    "properties": {
        "falantes": {"type": "array", "items": {"type": "object", "properties": {
            "rotulo": _S, "nome": _SN, "evidencia": _SN}, "required": ["rotulo", "nome", "evidencia"]}},
        "contexto": _S,
        "resumo": _S,
        "temas": {"type": "array", "items": _S},
        "decisoes": {"type": "array", "items": {"type": "object", "properties": {
            "decisao": _S, "quem": _SN, "contexto": _SN, "revisar_em": _SN,
            "revisar_em_dito": _SN, "t": _S, "citacao": _S},
            "required": ["decisao", "quem", "contexto", "revisar_em", "revisar_em_dito", "t",
                         "citacao"]}},
        "encaminhamentos": {"type": "array", "items": {"type": "object", "properties": {
            "acao": _S, "dono": _SN, "prazo": _SN, "prazo_dito": _SN, "t": _S, "citacao": _S},
            "required": ["acao", "dono", "prazo", "prazo_dito", "t", "citacao"]}},
        "perguntas_abertas": {"type": "array", "items": {"type": "object", "properties": {
            "pergunta": _S, "t": _S, "citacao": _S}, "required": ["pergunta", "t", "citacao"]}},
        "riscos": {"type": "array", "items": {"type": "object", "properties": {
            "risco": _S, "t": _S, "citacao": _S}, "required": ["risco", "t", "citacao"]}},
        "valores": {"type": "array", "items": {"type": "object", "properties": {
            "descricao": _S, "valor": _S, "condicao": _SN,
            "natureza": {"type": "string", "enum": ["combinado", "proposto", "citado"]},
            "t": _S, "citacao": _S},
            "required": ["descricao", "valor", "condicao", "natureza", "t", "citacao"]}},
        "escopo": {"type": "array", "items": {"type": "object", "properties": {
            "item": _S, "tema": _SN, "t": _S, "citacao": _S},
            "required": ["item", "tema", "t", "citacao"]}},
        "por_tema": {"type": "array", "items": {"type": "object", "properties": {
            "tema": _S, "resumo": _S}, "required": ["tema", "resumo"]}},
    },
    "required": ["falantes", "contexto", "resumo", "temas", "decisoes", "encaminhamentos",
                 "perguntas_abertas", "riscos", "valores", "escopo", "por_tema"],
}

LISTAS = [("decisoes", "D"), ("encaminhamentos", "E"), ("perguntas_abertas", "P"),
          ("riscos", "R"), ("valores", "V"), ("escopo", "S")]


# ── tempo e texto ────────────────────────────────────────────────────────────
def fmt_t(seg):
    s = max(0, int(seg or 0))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_t(t):
    if t is None:
        return None
    partes = str(t).strip().strip("[]").split(":")
    try:
        nums = [int(float(p)) for p in partes]
    except ValueError:
        return None
    seg = 0
    for n in nums:
        seg = seg * 60 + n
    return seg


def norm(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9]+", " ", t.lower())
    return t.strip()


# ── falas: a transcrição do jeito que o Claude lê e a auditoria confere ─────
def falas(segs, juntar_ate_s=2.0):
    """Funde trechos consecutivos do mesmo falante (pausa < juntar_ate_s) numa fala.
    O Claude cita de UMA fala; a auditoria confere contra estas mesmas falas."""
    out = []
    for s in sorted(segs, key=lambda x: x["start"]):
        if out and out[-1]["speaker"] == s["speaker"] and s["start"] - out[-1]["end"] <= juntar_ate_s:
            out[-1]["text"] += " " + s["text"]
            out[-1]["end"] = s["end"]
        else:
            out.append({"speaker": s["speaker"], "start": s["start"], "end": s["end"],
                        "text": s["text"]})
    return out


def transcricao_texto(segs):
    return "\n".join(f"[{fmt_t(f['start'])}] {f['speaker']}: {f['text']}" for f in falas(segs))


def rotulos(segs):
    vistos = []
    for s in sorted(segs, key=lambda x: x["start"]):
        if s["speaker"] not in vistos:
            vistos.append(s["speaker"])
    return vistos


# ── participantes ────────────────────────────────────────────────────────────
def participantes_iniciais(segs, meu_nome, remotos):
    """O que se sabe sem IA: 'Você' é o Pedro; se só um remoto foi informado e o
    loopback não foi separado, 'Participante' é ele."""
    rots = rotulos(segs)
    tempo = {}
    for s in segs:
        tempo[s["speaker"]] = tempo.get(s["speaker"], 0.0) + max(0.0, s["end"] - s["start"])
    total = sum(tempo.values()) or 1.0
    out = []
    for r in rots:
        if r == "Você":
            out.append({"rotulo": r, "nome": meu_nome, "origem": "eu", "confirmado": True,
                        "evidencia": None, "fatia": round(tempo.get(r, 0) / total, 3)})
        elif r == "Participante" and len(remotos) == 1:
            out.append({"rotulo": r, "nome": remotos[0], "origem": "informado",
                        "confirmado": True, "evidencia": "único participante remoto informado",
                        "fatia": round(tempo.get(r, 0) / total, 3)})
        else:
            out.append({"rotulo": r, "nome": None, "origem": None, "confirmado": False,
                        "evidencia": None, "fatia": round(tempo.get(r, 0) / total, 3)})
    return out


def nomes_por_rotulo(ata):
    return {p["rotulo"]: (p.get("nome") or p["rotulo"]) for p in ata.get("participantes", [])}


# ── auditoria ────────────────────────────────────────────────────────────────
def _contem(agulha, palheiro):
    """Contém com limite de palavra: "dia 1" não casa em "dia 15", "mana" não casa em
    "semana" (achados da revisão adversarial de 30/09/2026)."""
    a, p = norm(agulha), norm(palheiro)
    return bool(a) and f" {a} " in f" {p} "


def _achar(citacao, fl, t_seg):
    """Índice da fala que contém a citação (preferindo a mais próxima de t).

    Reticências separam partes; TODAS precisam estar na mesma fala, em qualquer
    tamanho — antes, parte com menos de 3 palavras era descartada, e um "até sexta"
    inventado passava colado a um trecho real."""
    c = norm(citacao)
    if len(c.split()) < 3:
        return None
    alvos = [norm(x) for x in re.split(r"\s*(?:\.\.\.|…)\s*", citacao or "") if norm(x)]
    cands = [i for i, f in enumerate(fl) if all(_contem(a, f["text"]) for a in alvos)]
    if not cands:
        return None
    if t_seg is None:
        return cands[0]
    return min(cands, key=lambda i: abs(fl[i]["start"] - t_seg))


def _expressao_perto(expr, fl, i, raio_s=120):
    """A expressão ("até sexta", "dia 10") foi dita até `raio_s` segundos da fala citada?
    Raio em TEMPO, não em falas: com o loopback fatiado, 30 s viram dez 'falas'."""
    if not norm(expr):
        return False
    t = fl[i]["start"]
    return any(_contem(expr, f["text"]) for f in fl if abs(f["start"] - t) <= raio_s)


_DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5,
                "domingo": 6}
_NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
            "sete": 7, "oito": 8, "nove": 9, "dez": 10, "quinze": 15, "vinte": 20, "trinta": 30}
_NUM = r"(?:\d{1,3}|" + "|".join(_NUMEROS) + r")"

# prazo relativo ("15 dias", "uns 4 5 dias", "duas semanas"), sobre o texto já passado por norm().
# Usado pela auditoria (_data_coerente) e pelo Raio-X (expressao_de_prazo, 14/10/2026).
_RE_RELATIVO = re.compile(r"\b(\d{1,3}|" + "|".join(_NUMEROS) + r")(?: (?:a |ou )?(\d{1,3}|"
                          + "|".join(_NUMEROS) + r"))? (dia|dias|semana|semanas)\b")
_SEMANA = "|".join(_DIAS_SEMANA)
_RE_PRAZO = re.compile(
    r"\b(?:hoje|amanha|depois de amanha"
    r"|(?:semana|mes) que vem|proxim[ao] (?:semana|mes|" + _SEMANA + r")"
    r"|(?:fim|final) d[oae] (?:dia|semana|mes|tarde|manha)|ate o (?:fim|final)"
    r"|(?:" + _SEMANA + r") feira"
    r"|(?:ate|nessa|nesta|essa|esta|no|na) (?:" + _SEMANA + r")"
    r"(?! (?:versao|vez|parte|etapa|fase|opcao|tela|pagina|reuniao|coisa|pergunta))"
    r"|dia \d{1,2}|ate (?:o )?dia " + _NUM +
    r"|(?:antes|depois) do almoco|(?:hoje|amanha) (?:a|de) (?:tarde|noite|manha)"
    r"|(?:em|daqui a|daqui|ate|uns|umas|dentro de) " + _NUM + r"(?: (?:a |ou )?" + _NUM + r")?"
    r" (?:dia|dias|semana|semanas|hora|horas|mes|meses)"
    r"|(?:essa|esta|nessa|nesta) semana|(?:esse|este|nesse|neste) mes)\b")
_RE_DATA_CHEIA = re.compile(r"(?<!\d)\d{1,2}/\d{1,2}(?:/\d{2,4})?(?!\d)")


def expressao_de_prazo(texto):
    """A expressão de prazo dita no texto ("até sexta", "amanhã", "em 15 dias", "dia 10", "15/10"),
    ou None. Só ACHA a expressão; converter em data e conferir é com _data_coerente. O Raio-X usa
    para medir compromisso com prazo (14/10/2026)."""
    m = _RE_DATA_CHEIA.search(str(texto or ""))
    if m:
        return m.group(0)
    m = _RE_PRAZO.search(norm(texto))
    return m.group(0) if m else None


def _data_coerente(iso, dito, data_reuniao):
    """A data convertida bate com o que foi dito e com a data da reunião?
    Confere o que dá para conferir sem inventar: fica entre a reunião e 400 dias depois;
    "dia N" / "N/M" batem o dia (e o mês); dia da semana dito bate o dia da semana."""
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat(str(iso))
    except ValueError:
        return False
    try:
        base = _dt.date.fromisoformat(str(data_reuniao)[:10])
    except (TypeError, ValueError):
        base = None
    if base and not (base - _dt.timedelta(days=1) <= d <= base + _dt.timedelta(days=400)):
        return False
    n = norm(dito)
    dias = (d - base).days if base else 0
    # prazo relativo: "15 dias", "uns 4 5 dias", "quinze dias", "duas semanas" (v2.1). Conta da
    # data da reunião; numa faixa ("4 5 dias"), vale o maior; tolerância de 1 dia para cada lado
    rel = _RE_RELATIVO.search(n)
    if rel and base:
        num = lambda s: int(s) if s and s.isdigit() else _NUMEROS.get(s)
        qtd = max(x for x in (num(rel.group(1)), num(rel.group(2))) if x is not None)
        alvo = qtd * (7 if rel.group(3).startswith("semana") else 1)
        return abs(dias - alvo) <= 1
    m = re.search(r"\b(\d{1,2}) (\d{1,2})\b", n)          # 15/10 vira "15 10" no norm
    if m and (d.day, d.month) != (int(m.group(1)), int(m.group(2))):
        return False
    m = re.search(r"\bdia (\d{1,2})\b", n)
    if m and not re.search(r"\b\d{1,2} \d{1,2}\b", n):
        # "dia 15" sem mês = o próximo dia 15, não um dia 15 qualquer
        if d.day != int(m.group(1)) or dias > 62:
            return False
    for nome, wd in _DIAS_SEMANA.items():
        if re.search(rf"\b{nome}\b", n) and (d.weekday() != wd or dias > 14):
            return False
    return True


def auditar(ata, segs):
    fl = falas(segs)
    blob = " ".join(f["text"] for f in fl)
    conhecidos = {norm(p.get("nome")) for p in ata.get("participantes", []) if p.get("nome")}
    conhecidos |= {norm(p["rotulo"]) for p in ata.get("participantes", [])}
    conhecidos |= {norm(x) for x in ata.get("_remotos", [])}
    conhecidos.discard("")

    for lista, _pref in LISTAS:
        for it in ata.get(lista, []):
            probs = []
            t_seg = parse_t(it.get("t"))
            i = _achar(it.get("citacao"), fl, t_seg)
            if i is None:
                it["verificado"] = False
                probs.append("citação não localizada na transcrição")
            else:
                it["verificado"] = True
                t_real = fmt_t(fl[i]["start"])
                if t_seg is None or abs(fl[i]["start"] - t_seg) > 5:
                    probs.append(f"timestamp corrigido de {it.get('t')} para {t_real}")
                    it["t"] = t_real
            manual = set(it.get("manual") or [])     # campos definidos pelo Pedro depois
            for campo, dito in (("prazo", "prazo_dito"), ("revisar_em", "revisar_em_dito")):
                if campo not in it or not it.get(campo) or campo in manual:
                    continue
                # a expressão tem de estar DITA perto da fala — a citação sozinha não basta,
                # porque é o próprio Claude que a escreve
                ok = (i is not None and _expressao_perto(it.get(dito), fl, i)
                      and _data_coerente(it[campo], it.get(dito), ata.get("data")))
                if not ok:
                    probs.append(f"{campo} '{it[campo]}' removido: a expressão dita "
                                 f"('{it.get(dito)}') não foi localizada ou não bate com a data")
                    it[campo] = None
            for campo in ("dono", "quem"):
                v = it.get(campo)
                if v and campo not in manual and norm(v) not in conhecidos and not _contem(v, blob):
                    probs.append(f"{campo} '{v}' não aparece na transcrição nem nos participantes")
            it["problemas"] = probs
    ata["lacunas"] = lacunas(ata)
    return ata


def nomes_confirmados(ata):
    """Pessoas cuja identidade o Pedro sabe: 'Você', remoto único informado, confirmados."""
    return {p["nome"] for p in ata.get("participantes", []) if p.get("nome") and p.get("confirmado")}


def falantes_resolvidos(ata):
    """Todo falante relevante tem nome confirmado? É a condição para resumo e contexto —
    prosa livre, que a auditoria não confere — irem ao cliente."""
    citados = {it.get(c) for k, _ in LISTAS for it in ata.get(k, []) for c in ("dono", "quem")}
    for p in ata.get("participantes", []):
        relevante = p.get("fatia", 1) >= 0.05 or p["rotulo"] in citados
        if relevante and not (p.get("nome") and p.get("confirmado")):
            return False
    return True


def lacunas(ata):
    out = []
    citados = {it.get(c) for k, _ in LISTAS for it in ata.get(k, []) for c in ("dono", "quem")}
    for p in ata.get("participantes", []):
        # rótulo com fala ínfima (cauda do diarizador) não vira lacuna — só ruído
        relevante = p.get("fatia", 1) >= 0.05 or p["rotulo"] in citados
        if not p.get("nome"):
            if relevante:
                out.append({"ref": p["rotulo"], "falta": "nome do falante"})
        elif not p.get("confirmado"):
            out.append({"ref": p["rotulo"], "falta": f"confirmar que é {p['nome']}"})
    for e in ata.get("encaminhamentos", []):
        if not e.get("dono"):
            out.append({"ref": e["id"], "falta": "dono"})
        if not e.get("prazo"):
            out.append({"ref": e["id"], "falta": "prazo"})
    # decisão sem data de revisão NÃO vira lacuna (v2.1): na ata de 05/10 eram 15 de 26 e
    # escondiam a que importava. A sugestão de revisão fica com o /ata.
    for lista, _ in LISTAS:
        for it in ata.get(lista, []):
            if it.get("verificado") is False:
                out.append({"ref": it["id"], "falta": "trecho de origem (não localizado)"})
    return out


# ── montagem ─────────────────────────────────────────────────────────────────
def base(sessao, segs, meu_nome):
    m = sessao.m
    dur = max((s["end"] for s in segs), default=0)
    return {
        "schema": SCHEMA_ATA,
        "id": m["id"],
        "titulo": m.get("titulo"),
        "tipo": m.get("tipo"),
        "projeto": m.get("projeto") or None,
        "data": m.get("inicio") or m.get("criado"),
        "duracao_min": round(max(dur, sessao.duracao_s()) / 60),
        "participantes": participantes_iniciais(segs, meu_nome, sessao.participantes_remotos()),
        "contexto": None, "resumo": None, "temas": [],
        "decisoes": [], "encaminhamentos": [], "perguntas_abertas": [], "riscos": [],
        "valores": [], "escopo": [], "por_tema": [],
        "lacunas": [], "gerado": None, "revisado": None, "status": "pendente",
    }


def montar(sessao, segs, bruto, gerado, meu_nome):
    """Ata canônica a partir da saída do Claude + o que o código já sabe."""
    ata = base(sessao, segs, meu_nome)
    ata["_remotos"] = sessao.participantes_remotos()
    ata["contexto"] = bruto.get("contexto")
    ata["resumo"] = bruto.get("resumo")
    ata["temas"] = [t for t in bruto.get("temas", []) if t]
    ata["por_tema"] = [x for x in bruto.get("por_tema", []) if x.get("tema") and x.get("resumo")]
    # nomes deduzidos: nunca por cima do que já está confirmado
    por_rotulo = {f.get("rotulo"): f for f in bruto.get("falantes", [])}
    for p in ata["participantes"]:
        f = por_rotulo.get(p["rotulo"])
        if p["confirmado"] or not f or not f.get("nome"):
            continue
        p.update({"nome": f["nome"], "origem": "deduzido", "confirmado": False,
                  "evidencia": f.get("evidencia")})
    for lista, pref in LISTAS:
        itens = []
        for n, it in enumerate(bruto.get(lista, []), 1):
            it = dict(it)
            it["id"] = f"{pref}{n}"
            itens.append(it)
        ata[lista] = itens
    ata["gerado"] = gerado
    ata["status"] = "estruturada"
    auditar(ata, segs)
    ata.pop("_remotos", None)
    return ata


def contagem(ata):
    return {k: len(ata.get(k, [])) for k, _ in LISTAS} | {
        "nao_verificados": sum(1 for k, _ in LISTAS for it in ata.get(k, [])
                               if it.get("verificado") is False),
        "lacunas": len(ata.get("lacunas", []))}


def decisao_para_log(ata, d):
    """Uma decisão da ata no formato do log de decisões (decisoes.jsonl)."""
    nomes = nomes_por_rotulo(ata)
    return {
        "data": (ata.get("data") or "")[:10],
        "decisao": d["decisao"],
        "contexto": d.get("contexto") or ata.get("contexto"),
        "quem": nomes.get(d.get("quem"), d.get("quem")),
        "destrava": None,
        "revisar_em": d.get("revisar_em"),
        "origem": {"ata": ata["id"], "t": d.get("t"), "citacao": d.get("citacao")},
    }
