# -*- coding: utf-8 -*-
"""
Transcrição → ata estruturada, pelo Claude (decisão 2 de 30/09/2026).

Chama o Claude Code em modo não interativo (`claude -p`) com a transcrição no stdin
e um JSON Schema fechado (`--json-schema`), sem ferramentas, sem MCP, sem as
configurações do usuário e sem persistir sessão. Não precisa de chave de API: usa o
login do Claude Code desta máquina. Não tem o limite de 40 000 caracteres do
Workers AI, e a transcrição não passa por nenhum serviço além do Claude.

O que o Claude devolve é CANDIDATO: `ata.montar()` audita cada item contra a
transcrição antes de virar ata (ver ata.py). Se o Claude falhar, a reunião não se
perde — sai uma ata `pendente` (só transcrição + participantes) e o motivo fica na
etapa `estrutura` do sessao.json, visível na tela.
"""
import datetime as _dt
import json
import subprocess
import tempfile
import time

import ata as _ata
import config as _config
import marcas as _marcas
from sessao import TIPOS

VERSAO_PROMPT = "4"   # 3 = valores, escopo, por_tema e blocos (v2.1, 06/10/2026); 4 = momentos marcados (14/10)
VERSAO_PROMPT_DAILY = "daily-1"   # 19/10/2026: esquema atas/daily@1 (daily da Parresia)

_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
         "sábado", "domingo"]


def _data_reuniao(sessao):
    ini = sessao.m.get("inicio") or sessao.m.get("criado")
    try:
        d = _dt.datetime.fromisoformat(ini)
    except (TypeError, ValueError):
        d = _dt.datetime.now()
    return d


def _linhas_celular(sessao, meu_nome, papel):
    """Reunião presencial gravada no celular: um canal só, todo mundo no mesmo áudio. Quem é o
    Pedro foi estimado pela voz e ainda não foi confirmado por ele (14/10/2026)."""
    cel = sessao.m.get("celular") or {}
    tem_voce = bool(cel.get("rotulo"))
    if tem_voce and cel.get("voce_confirmado"):
        quem = f"- \"Você\" na transcrição é {meu_nome} (confirmado por ele). {papel}"
    elif tem_voce:
        quem = (f"- \"Você\" na transcrição é PROVAVELMENTE {meu_nome}, estimado pela voz e ainda "
                f"não confirmado. Se o texto mostrar que outro rótulo é {meu_nome} (ele é chamado pelo "
                f"nome e responde), diga isso em `falantes`. {papel}")
    else:
        quem = (f"- Não deu para saber pela voz qual rótulo é {meu_nome}: ele é um dos "
                f"\"Participante N\". Deduza em `falantes` só com evidência. {papel}")
    return [
        "- Reunião PRESENCIAL gravada no celular: um áudio só, com todas as vozes juntas, separadas "
        "por uma máquina que erra (a mesma pessoa pode aparecer sob vários rótulos, e um rótulo "
        "pode misturar pessoas).",
        quem,
    ]


def prompt(sessao, meu_nome, marcas=None):
    """`marcas`: [(id, marca)] que este pedaço da reunião tem de tratar (marcas.identificadas /
    marcas.do_bloco). None = todas as da sessão."""
    if marcas is None:
        marcas = _marcas.identificadas(sessao.m.get("marcas") or [])
    d = _data_reuniao(sessao)
    remotos = sessao.participantes_remotos()
    tipo = sessao.tipo
    papel = {
        "parresia": f"{meu_nome} é o Product Owner da Parresia; decisões e encaminhamentos "
                    "desta reunião alimentam o log de decisões e o backlog dele.",
        "cliente": f"{meu_nome} é o consultor/fornecedor (RYZE); os demais são o cliente. "
                   "Esta ata pode ser enviada ao cliente: tom profissional.",
        "carreira": f"Reunião sobre a carreira de {meu_nome}.",
        "pessoal": "Reunião pessoal ou de estudo.",
        "pendente": "O tipo da reunião ainda não foi escolhido: escreva neutro, como ata interna.",
    }.get(tipo, "")
    linhas = [
        "Você vai produzir a ATA ESTRUTURADA de uma reunião. A transcrição completa chega no "
        "stdin, uma fala por linha, no formato `[mm:ss] Rótulo: texto`.",
        "",
        "Contexto da reunião:",
        f"- Título: {sessao.m.get('titulo')}",
        f"- Data: {d:%Y-%m-%d} ({_DIAS[d.weekday()]})",
        f"- Tipo: {TIPOS.get(tipo, tipo)}" + (f" · projeto: {sessao.m['projeto']}"
                                               if sessao.m.get("projeto") else ""),
        *(_linhas_celular(sessao, meu_nome, papel) if sessao.celular else [
            f"- \"Você\" na transcrição é {meu_nome} (microfone dele). {papel}",
            "- \"Participante\" / \"Participante N\" é o áudio da chamada. A separação automática "
            "de vozes é imperfeita: a mesma pessoa pode aparecer sob vários rótulos, e um rótulo "
            "pode misturar pessoas."]),
        ("- Participantes remotos informados por ele: " + ", ".join(remotos) +
         " (podem não ter falado todos).") if remotos else
        "- Os participantes remotos não foram informados.",
        "",
        "Regras inegociáveis:",
        "1. Nada inventado. Todo item de decisoes, encaminhamentos, perguntas_abertas, riscos, valores e escopo "
        "leva `citacao` — um trecho COPIADO LITERALMENTE de UMA fala da transcrição (8 a 30 "
        "palavras, sem reticências, sem corrigir o texto) — e `t`, o timestamp [mm:ss] dessa "
        "fala, sem colchetes.",
        "2. O que não foi dito é null. Não deduza prazo, dono nem data de revisão. `prazo` só "
        "se um prazo foi dito: converta para AAAA-MM-DD a partir da data da reunião e copie a "
        "expressão exata em `prazo_dito` (ex.: \"até sexta\", \"dia 15\"). O mesmo vale para "
        "`revisar_em` / `revisar_em_dito` nas decisões.",
        f"3. `dono` / `quem`: o nome da pessoa quando identificável; \"{meu_nome}\" para as "
        "falas de \"Você\"; o rótulo (\"Participante 2\") se só o rótulo é conhecido; null se "
        f"não se sabe. Só as falas de \"Você\" são de {meu_nome}: uma tarefa que ele pede a "
        "outra pessoa tem como dono essa pessoa, não ele.",
        "4. Decisão = algo que ficou decidido ou combinado (não sugestão nem ideia em "
        "discussão). Encaminhamento = ação que alguém assumiu ou recebeu. Pergunta em aberto = "
        "dúvida que ficou sem resposta. Risco = problema ou ameaça apontada. Listas vazias são "
        "melhores que itens fracos.",
        "5. `falantes`: um item por rótulo que aparece na transcrição, com o nome real quando "
        "houver evidência (a pessoa se apresenta, é chamada pelo nome e responde, ou é a única "
        "informada que combina) e a evidência em `evidencia` (\"[mm:ss] trecho\"). Sem "
        "evidência, nome null. Vários rótulos podem ser a mesma pessoa.",
        "6. `resumo`: 4 a 8 frases concretas (nomes, números e prazos ditos; datas no texto "
        "como dd/mm, nunca AAAA-MM-DD). `contexto`: 1 ou 2 frases (objetivo e quem "
        "participou). `temas`: 3 a 8 itens curtos.",
        "7. `valores`: todo valor em dinheiro combinado, proposto ou recusado (preço, parcela, "
        "mensalidade, desconto, custo), com `valor` como foi dito (\"R$ 550\", \"500 por mês\") e "
        "`condicao` quando houver (\"quando subir na Play Store\", \"em até 15 dias\"). Valor é o "
        "item que mais se perde num resumo: não deixe nenhum de fora. `natureza`: \"combinado\" "
        "(fechado entre as partes), \"proposto\" (oferecido ou pedido, sem acordo) ou \"citado\" "
        "(referência: preço de mercado, custo interno, pesquisa, exemplo hipotético).",
        "8. `escopo`: cada funcionalidade, entregável ou item de trabalho que entrou (ou foi "
        "pedido) numa entrega, um por item, com o `tema`/projeto a que pertence. Listas de "
        "funcionalidades ditas em sequência viram vários itens.",
        "9. `por_tema`: um resumo de 2 a 5 frases para CADA assunto/projeto tratado (a reunião "
        "pode cobrir vários). Conversa pessoal ou fora de pauta (política, vida pessoal) NÃO "
        "entra em resumo, tema nem item.",
        "10. Português do Brasil. Nada que não esteja na transcrição.",
        *_marcas.linhas_prompt(marcas),
    ]
    return "\n".join(linhas)


def esquema(com_momentos):
    """O esquema da ata; com marca, `momentos` passa a ser obrigatório (sem marca, fica de fora do
    pedido e o Claude não perde tempo com ele)."""
    if not com_momentos:
        return _ata.ESQUEMA_CLAUDE
    e = dict(_ata.ESQUEMA_CLAUDE)
    e["required"] = list(e["required"]) + ["momentos"]
    return e


# ── reunião longa: estrutura por blocos (v2.1) ────────────────────────────────
# Em 05/10/2026 uma reunião de 190 min foi estruturada numa passada só, em 86 s, e ficaram de
# fora os valores, a lista de funcionalidades e metade das regras combinadas. Acima do limiar,
# cada bloco de ~40 min (com sobreposição, para não cortar um assunto no meio) é estruturado
# sozinho, os itens são somados sem repetição e uma passada curta consolida a prosa.
ESQUEMA_PROSA = {
    "type": "object",
    "properties": {"contexto": _ata._S, "resumo": _ata._S, "temas": {"type": "array", "items": _ata._S},
                   "por_tema": _ata.ESQUEMA_CLAUDE["properties"]["por_tema"],
                   "temas_escopo": {"type": "array", "items": {"type": "object", "properties": {
                       "de": _ata._S, "para": _ata._S}, "required": ["de", "para"]}}},
    "required": ["contexto", "resumo", "temas", "por_tema", "temas_escopo"],
}


def blocos(segs, bloco_s=2400, sobra_s=120):
    """Fatia os segmentos em janelas de `bloco_s` com `sobra_s` de sobreposição."""
    fim = max((s["end"] for s in segs), default=0)
    out, ini = [], 0.0
    while ini < fim:
        out.append((ini, [s for s in segs if s["start"] < ini + bloco_s + sobra_s and s["end"] > ini - sobra_s]))
        ini += bloco_s
    return out


def _mesmo_item(a, b):
    """Dois candidatos são o mesmo item? Mesma citação, ou a mesma fala (±30 s) com o texto
    principal quase igual — a sobreposição entre blocos produz os dois casos."""
    ca, cb = _ata.norm(a.get("citacao")), _ata.norm(b.get("citacao"))
    if ca and ca == cb:
        return True
    ta, tb = _ata.parse_t(a.get("t")), _ata.parse_t(b.get("t"))
    if ta is None or tb is None or abs(ta - tb) > 30:
        return False
    chave = next((k for k in ("decisao", "acao", "pergunta", "risco", "descricao", "item", "o_que") if k in a), None)
    pa, pb = set(_ata.norm(a.get(chave)).split()), set(_ata.norm(b.get(chave)).split())
    return bool(pa and pb) and len(pa & pb) / len(pa | pb) >= 0.6


def alinhar_temas(junto, mapa):
    """Cada bloco batiza o mesmo assunto de um jeito ("Hardware", "Hardware IoT"): o escopo
    passa a usar os temas finais de `por_tema`, pelo mapa da consolidação. Nome que o mapa não
    cobre fica como está (melhor um tema a mais que um item no tema errado)."""
    finais = {x.get("tema") for x in junto.get("por_tema", [])}
    de_para = {m["de"]: m["para"] for m in mapa if m.get("para") in finais}
    for s in junto.get("escopo", []):
        s["tema"] = de_para.get(s.get("tema"), s.get("tema"))


def juntar(partes):
    """Soma as saídas dos blocos: listas sem repetição, falantes com nome ganham."""
    out = {k: [] for k, _ in _ata.LISTAS}
    falantes = {}
    for p in partes:
        for k, _ in _ata.LISTAS:
            for it in p.get(k, []):
                if not any(_mesmo_item(it, x) for x in out[k]):
                    out[k].append(it)
        for f in p.get("falantes", []):
            atual = falantes.get(f.get("rotulo"))
            if not atual or (f.get("nome") and not atual.get("nome")):
                falantes[f.get("rotulo")] = f
    out["falantes"] = list(falantes.values())
    # cada marca foi pedida a UM bloco só (marcas.do_bloco); se outro bloco a devolveu mesmo assim,
    # vale a primeira resposta com citação
    mom = {}
    for p in partes:
        for x in p.get("momentos") or []:
            if x.get("marca") not in mom or (x.get("citacao") and not mom[x["marca"]].get("citacao")):
                mom[x.get("marca")] = x
    out["momentos"] = list(mom.values())
    return out


def chamar_claude(texto_prompt, transcricao, cfg, log=print, esquema=None):
    """Roda o claude -p e devolve (structured_output, meta). Levanta com o motivo."""
    exe = _config.claude_cli(cfg)
    if not exe:
        raise RuntimeError("claude.exe não encontrado (instale o Claude Code ou defina "
                           "'claude_cli' no config.json)")
    cmd = [exe, "-p", texto_prompt,
           "--output-format", "json",
           "--json-schema", json.dumps(esquema or _ata.ESQUEMA_CLAUDE, ensure_ascii=False),
           "--tools", "",
           "--no-session-persistence",
           "--strict-mcp-config",
           "--setting-sources", ""]
    if cfg.get("claude_modelo"):
        cmd += ["--model", cfg["claude_modelo"]]
    t0 = time.time()
    # cwd descartável: nada de CLAUDE.md de projeto entrando na conversa
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(cmd, input=transcricao.encode("utf-8"), capture_output=True,
                           cwd=tmp, timeout=int(cfg.get("claude_timeout_s", 1200)))
    saida = r.stdout.decode("utf-8", "replace")
    try:
        dado = json.loads(saida)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude saiu com código {r.returncode} sem JSON: "
                           f"{(saida or r.stderr.decode('utf-8', 'replace'))[-500:]}")
    if dado.get("is_error") or not isinstance(dado.get("structured_output"), dict):
        raise RuntimeError(f"claude não devolveu a ata: {str(dado.get('result'))[:500]}")
    modelos = list((dado.get("modelUsage") or {}).keys())
    principal = max(modelos, key=lambda k: dado["modelUsage"][k].get("outputTokens", 0)) \
        if modelos else None
    meta = {"por": "claude-code", "modelo": principal, "em": _dt.datetime.now().astimezone()
            .isoformat(timespec="seconds"), "segundos": round(time.time() - t0, 1),
            "custo_usd": dado.get("total_cost_usd"), "versao_prompt": VERSAO_PROMPT}
    return dado["structured_output"], meta


def estruturar(sessao, segs, cfg, log=print):
    """Devolve a ata canônica (estruturada, ou pendente com o motivo)."""
    meu = cfg.get("meu_nome", "Pedro")
    from sessao import fora_da_medicao
    if fora_da_medicao(sessao) and segs:
        return estruturar_daily(sessao, segs, cfg, log)
    if not segs:
        a = _ata.base(sessao, segs, meu)
        a["lacunas"] = _ata.lacunas(a)
        return a, "sem falas"
    texto = _ata.transcricao_texto(segs)
    dur_min = max((s["end"] for s in segs), default=0) / 60
    if dur_min > float(cfg.get("estruturar_blocos_acima_min", 60)):
        bruto, meta = _estruturar_em_blocos(sessao, segs, cfg, meu, log)
    else:
        mk = _marcas.identificadas(sessao.m.get("marcas") or [])
        log(f"  Estruturando a ata com o Claude ({len(texto):,} caracteres".replace(",", ".")
            + (f", {len(mk)} momento(s) marcado(s)" if mk else "") + ")…")
        bruto, meta = chamar_claude(prompt(sessao, meu, mk), texto, cfg, log, esquema=esquema(bool(mk)))
    a = _ata.montar(sessao, segs, bruto, meta, meu)
    c = _ata.contagem(a)
    log(f"    {c['decisoes']} decisões · {c['encaminhamentos']} encaminhamentos · "
        f"{c['perguntas_abertas']} perguntas · {c['riscos']} riscos · "
        f"{c['nao_verificados']} sem origem localizada · {meta.get('segundos') or 0:.0f}s")
    return a, None


def _estruturar_em_blocos(sessao, segs, cfg, meu, log=print):
    """Reunião longa: um claude -p por bloco + uma passada que consolida a prosa."""
    partes, custo, seg = [], 0.0, 0.0
    bloco_s = int(cfg.get("estruturar_bloco_min", 40)) * 60
    bls = blocos(segs, bloco_s=bloco_s)
    for k, (ini, bseg) in enumerate(bls, 1):
        fim = min(ini + bloco_s, max(s["end"] for s in segs))
        # cada marca vai ao bloco em que ela caiu (a sobra de 120 s cobre a janela de 45 s / 15 s)
        mk = _marcas.do_bloco(sessao.m.get("marcas") or [], ini, bloco_s, ultimo=k == len(bls))
        log(f"  Estruturando o bloco {k}/{len(bls)} ({_ata.fmt_t(ini)} a {_ata.fmt_t(fim)})"
            + (f" com {len(mk)} momento(s) marcado(s)" if mk else "") + "…")
        p = prompt(sessao, meu, mk) + (
            f"\n\nATENÇÃO: este é o trecho {k} de {len(bls)} de uma reunião mais longa "
            f"(de {_ata.fmt_t(ini)} a {_ata.fmt_t(fim)}, com um pouco de sobra antes e depois). "
            "Extraia os itens que aparecem NESTE trecho; resumo, contexto, temas e por_tema também "
            "só deste trecho.")
        bruto, meta = chamar_claude(p, _ata.transcricao_texto(bseg), cfg, log, esquema=esquema(bool(mk)))
        partes.append(bruto)
        custo += meta.get("custo_usd") or 0
        seg += meta.get("segundos") or 0
    junto = juntar(partes)
    log("  Consolidando o resumo dos blocos…")
    entrada = json.dumps([{k: p.get(k) for k in ("contexto", "resumo", "temas", "por_tema")} for p in partes]
                         + [{"decisoes": [d.get("decisao") for d in junto["decisoes"]],
                             "valores": [f"{v.get('descricao')}: {v.get('valor')}" for v in junto["valores"]],
                             "temas_do_escopo": sorted({s.get("tema") for s in junto["escopo"] if s.get("tema")})}],
                         ensure_ascii=False)
    pc = ("Você recebe, em JSON no stdin, os resumos de cada trecho de UMA reunião longa e a lista "
          "das decisões e valores já extraídos. Escreva a prosa da ATA INTEIRA: `contexto` (1-2 "
          "frases), `resumo` (5 a 10 frases concretas, com os números e prazos ditos, datas como "
          "dd/mm), `temas` (3 a 8 itens curtos) e `por_tema` (um resumo de 2 a 5 frases por "
          "assunto/projeto, juntando o que os trechos disseram do mesmo assunto). Conversa pessoal "
          "ou fora de pauta não entra. Nada que não esteja nos resumos. Português do Brasil. "
          "Por fim, `temas_escopo`: para cada nome em `temas_do_escopo`, diga em `para` qual dos "
          "temas de `por_tema` ele é (os trechos deram nomes diferentes ao mesmo assunto).")
    prosa, meta = chamar_claude(pc, entrada, cfg, log, esquema=ESQUEMA_PROSA)
    custo += meta.get("custo_usd") or 0
    seg += meta.get("segundos") or 0
    junto.update({k: prosa.get(k) for k in ("contexto", "resumo", "temas", "por_tema")})
    alinhar_temas(junto, prosa.get("temas_escopo") or [])
    meta.update({"segundos": round(seg, 1), "custo_usd": round(custo, 4), "blocos": len(bls)})
    return junto, meta


# ── daily da Parresia (19/10/2026): esquema e prompt próprios ─────────────────
# Mesma regra da ata normal (citação literal, nada inventado, auditada no código), outro recorte:
# quem disse o quê sobre qual card, o que é com o Pedro e as frentes que ele acompanha.
_S, _SN = _ata._S, _ata._SN
_ITEM_DAILY = {"type": "object", "properties": {"item": _S, "card": _SN, "t": _S, "citacao": _S},
               "required": ["item", "card", "t", "citacao"]}
ESQUEMA_DAILY = {
    "type": "object",
    "properties": {
        "falantes": _ata.ESQUEMA_CLAUDE["properties"]["falantes"],
        "contexto": _S,
        "resumo": _S,
        "pessoas": {"type": "array", "items": {"type": "object", "properties": {
            "nome": _SN, "rotulo": _S,
            "fez": {"type": "array", "items": _ITEM_DAILY},
            "vai_fazer": {"type": "array", "items": _ITEM_DAILY},
            "travado": {"type": "array", "items": _ITEM_DAILY}},
            "required": ["nome", "rotulo", "fez", "vai_fazer", "travado"]}},
        "com_voce": {"type": "array", "items": {"type": "object", "properties": {
            "o_que": _S, "quem": _SN, "card": _SN, "frente": _SN,
            "tipo": {"type": "string", "enum": ["pedido", "informacao", "decisao"]},
            "t": _S, "citacao": _S},
            "required": ["o_que", "quem", "card", "frente", "tipo", "t", "citacao"]}},
        "decisoes": _ata.ESQUEMA_CLAUDE["properties"]["decisoes"],
        "encaminhamentos": _ata.ESQUEMA_CLAUDE["properties"]["encaminhamentos"],
        "momentos": _ata.ESQUEMA_CLAUDE["properties"]["momentos"],
    },
    "required": ["falantes", "contexto", "resumo", "pessoas", "com_voce", "decisoes", "encaminhamentos"],
}


def esquema_daily(com_momentos):
    if not com_momentos:
        return ESQUEMA_DAILY
    e = dict(ESQUEMA_DAILY)
    e["required"] = list(e["required"]) + ["momentos"]
    return e


def prompt_daily(sessao, meu_nome, equipe, frentes, mencoes, rodada, marcas=None):
    """O prompt da daily. `mencoes` (as falas que tocam as frentes) e `rodada` (vocativo → rótulo)
    saem dos passos determinísticos de daily.py; vão como lista obrigatória e como pista."""
    if marcas is None:
        marcas = _marcas.identificadas(sessao.m.get("marcas") or [])
    d = _data_reuniao(sessao)
    remotos = sessao.participantes_remotos()
    L = [
        "Você vai produzir a ATA DE UMA DAILY (reunião diária interna da Parresia). A transcrição completa "
        "chega no stdin, uma fala por linha, no formato `[mm:ss] Rótulo: texto`.",
        "",
        "Contexto:",
        f"- Título: {sessao.m.get('titulo')} · data {d:%Y-%m-%d} ({_DIAS[d.weekday()]})",
        "- É uma rodada: uma pessoa (normalmente o Otávio) chama cada um pelo nome, e cada um conta o que "
        "fez, o que vai fazer e o que está travado, quase sempre citando cards do ClickUp (SUP-NNN).",
        f"- \"Você\" na transcrição é {meu_nome} (microfone dele). Ele é o Product Owner / QA e fala pouco na "
        "daily. O objetivo desta ata é ele achar depois QUEM disse O QUÊ sobre QUAL card.",
        "- \"Participante N\" é o áudio da chamada, separado por uma máquina que erra: uma pessoa pode estar em "
        "vários rótulos, e um rótulo pode misturar pessoas.",
        "- Equipe (o universo de nomes; só use um destes, ou um nome dito na transcrição): " + ", ".join(equipe),
        ("- Participantes informados por ele: " + ", ".join(remotos) + " (uma lista incompleta, não a contagem).")
        if remotos else "- Os participantes não foram informados (é o normal na daily).",
    ]
    if rodada:
        L += ["", "PISTAS DA RODADA (calculadas pelo código: vocativo seguido de outro rótulo começando a falar). "
              "São pistas, não verdade; use em `falantes` e em `pessoas` só se o texto confirmar:"]
        for r in rodada[:30]:
            outros = (" · também chamado de " + ", ".join(f"{n} ({v}x)" for n, v in r["outros"].items())) if r["outros"] else ""
            L.append(f"- {r['rotulo']} → {r['nome']} ({r['votos']}x){outros}: {r['evidencias'][0]}")
    if frentes:
        L += ["", "FRENTES QUE ELE ACOMPANHA (tudo o que tocar nelas é com ele, mesmo que não tenha sido dito a ele):"]
        for f in frentes:
            L.append(f"- {f['nome']}: cards {', '.join(f['cards']) or '—'}; palavras {', '.join(f['palavras']) or '—'}")
    if mencoes:
        L += ["", "FALAS QUE TOCAM ESSAS FRENTES (lista obrigatória, achada pelo código). Cada uma que traga "
              "informação, pedido, decisão ou status TEM de virar item em `com_voce` (com `frente`) e, se for da "
              "rodada de alguém, também em `pessoas`. Card dito que não virar item será cobrado como lacuna:"]
        for m in mencoes[:80]:
            cards = f"; cards {', '.join(m['cards'])}" if m["cards"] else ""
            L.append(f"- [{m['t']}] {m['rotulo']} ({m['frente']}{cards}): \"{m['trecho']}\"")
    L += [
        "",
        "Regras inegociáveis:",
        "1. Nada inventado. Todo item (de pessoas, com_voce, decisoes, encaminhamentos) leva `citacao` — um "
        "trecho COPIADO LITERALMENTE de UMA fala da transcrição (8 a 30 palavras, sem reticências, sem corrigir "
        "o texto) — e `t`, o timestamp [mm:ss] dessa fala, sem colchetes.",
        "2. `card`: \"SUP-NNN\" só se o número do card foi DITO nessa fala ou logo perto dela; senão null. Não "
        "deduza card pelo assunto (o código confere e apaga card não dito).",
        "3. `pessoas`: um item por pessoa que deu status na rodada (inclusive quem falou pouco), na ordem em que "
        "falaram. `rotulo` = o rótulo da transcrição; `nome` = o nome real quando houver evidência, senão null. "
        "`fez` = o que concluiu/fez desde a última daily; `vai_fazer` = o que vai fazer agora; `travado` = o que "
        "está bloqueado, esperando alguém ou com problema. Itens curtos e concretos, um por assunto.",
        f"4. `com_voce`: o que foi dirigido a {meu_nome} (chamado pelo nome, pedido a ele, pergunta a ele, algo "
        "que depende dele) OU toca as frentes acima. `tipo`: pedido (alguém pede algo a ele), informacao (algo "
        "que ele precisa saber), decisao (algo decidido que o afeta). `quem` = quem disse (nome se conhecido, "
        "senão o rótulo); `frente` = o nome da frente acima ou null. O que ele mesmo disse não é com_voce, salvo "
        "se for uma decisão.",
        "5. `decisoes` e `encaminhamentos`: só os REAIS (algo decidido ou combinado; ação que alguém assumiu com "
        "dono). Status de rodada não é encaminhamento: vai em `pessoas`. `prazo` só se dito, em AAAA-MM-DD, com a "
        "expressão exata em `prazo_dito`; o mesmo para `revisar_em`/`revisar_em_dito`. "
        f"Só as falas de \"Você\" são de {meu_nome}: tarefa que ele pede a outra pessoa tem dono essa pessoa.",
        "6. `falantes`: um item por rótulo, com o nome real quando houver evidência (é chamado pelo nome e "
        "responde — as pistas da rodada —, se apresenta, ou fala de si na primeira pessoa com o nome) e a "
        "evidência em `evidencia` (\"[mm:ss] trecho\"). Sem evidência, nome null. Vários rótulos podem ser a "
        "mesma pessoa.",
        "7. `resumo`: 3 a 6 frases concretas (quem, o quê, cards e prazos ditos; datas como dd/mm). `contexto`: "
        "1 frase. Conversa pessoal ou fora de pauta não entra.",
        "8. Português do Brasil. Nada que não esteja na transcrição. Listas vazias são melhores que itens fracos.",
        *_marcas.linhas_prompt(marcas),
    ]
    return "\n".join(L)


def juntar_daily(partes):
    """Soma as saídas dos blocos da daily: pessoas pelo rótulo (itens sem repetição), com_voce,
    decisões e encaminhamentos sem repetição, falantes com nome ganham, momentos como na ata normal."""
    import daily as _daily
    pessoas, ordem = {}, []
    out = {"com_voce": [], "decisoes": [], "encaminhamentos": []}
    falantes = {}
    for p in partes:
        for pe in p.get("pessoas", []):
            chave = pe.get("rotulo") or pe.get("nome")
            if chave not in pessoas:
                pessoas[chave] = {"nome": pe.get("nome"), "rotulo": pe.get("rotulo"),
                                  **{k: [] for k, _ in _daily.LISTAS_PESSOA}}
                ordem.append(chave)
            alvo = pessoas[chave]
            if pe.get("nome") and not alvo.get("nome"):
                alvo["nome"] = pe["nome"]
            for k, _ in _daily.LISTAS_PESSOA:
                for it in pe.get(k) or []:
                    if not any(_mesmo_item(it, x) for x in alvo[k]):
                        alvo[k].append(it)
        for k in out:
            for it in p.get(k, []):
                if not any(_mesmo_item(it, x) for x in out[k]):
                    out[k].append(it)
        for f in p.get("falantes", []):
            atual = falantes.get(f.get("rotulo"))
            if not atual or (f.get("nome") and not atual.get("nome")):
                falantes[f.get("rotulo")] = f
    out["pessoas"] = [pessoas[c] for c in ordem]
    out["falantes"] = list(falantes.values())
    out["momentos"] = juntar(partes)["momentos"]
    return out


ESQUEMA_PROSA_DAILY = {"type": "object", "properties": {"contexto": _S, "resumo": _S},
                       "required": ["contexto", "resumo"]}


def estruturar_daily(sessao, segs, cfg, log=print):
    """A daily: passos determinísticos (rodada e frentes) → Claude com o esquema da daily → daily.montar
    (auditoria: citação, card a ±60 s, menção não tratada). Acima de `daily_blocos_acima_min`, em blocos."""
    import daily as _daily
    meu = cfg.get("meu_nome", "Pedro")
    equipe = _daily.equipe_do_config(cfg)
    frentes = _daily.frentes_do_config(cfg)
    fl = _ata.falas(segs)
    men = _daily.mencoes(fl, frentes)
    rod = _daily.rodada(segs, equipe, meu)
    dur_min = max((s["end"] for s in segs), default=0) / 60
    if dur_min > float(cfg.get("daily_blocos_acima_min", 100)):
        partes, custo, seg = [], 0.0, 0.0
        bloco_s = int(cfg.get("estruturar_bloco_min", 40)) * 60
        bls = blocos(segs, bloco_s=bloco_s)
        fim_total = max(s["end"] for s in segs)
        for k, (ini, bseg) in enumerate(bls, 1):
            fim = min(ini + bloco_s, fim_total)
            mk = _marcas.do_bloco(sessao.m.get("marcas") or [], ini, bloco_s, ultimo=k == len(bls))
            men_b = [m for m in men if ini - 120 <= m["t_s"] < ini + bloco_s + 120]
            rot_b = _daily.rodada(bseg, equipe, meu)
            log(f"  Estruturando a daily, bloco {k}/{len(bls)} ({_ata.fmt_t(ini)} a {_ata.fmt_t(fim)})…")
            pr = prompt_daily(sessao, meu, equipe, frentes, men_b, rot_b, mk) + (
                f"\n\nATENÇÃO: este é o trecho {k} de {len(bls)} da daily (de {_ata.fmt_t(ini)} a "
                f"{_ata.fmt_t(fim)}, com um pouco de sobra). Extraia só o que aparece NESTE trecho.")
            bruto, meta = chamar_claude(pr, _ata.transcricao_texto(bseg), cfg, log, esquema=esquema_daily(bool(mk)))
            partes.append(bruto)
            custo += meta.get("custo_usd") or 0
            seg += meta.get("segundos") or 0
        bruto = juntar_daily(partes)
        entrada = json.dumps([{k: p.get(k) for k in ("contexto", "resumo")} for p in partes], ensure_ascii=False)
        prosa, meta = chamar_claude(
            "Você recebe, em JSON no stdin, o contexto e o resumo de cada trecho de UMA daily longa. Escreva o "
            "`contexto` (1 frase) e o `resumo` (4 a 8 frases concretas: quem, o quê, cards e prazos ditos; datas "
            "como dd/mm) da daily inteira. Nada que não esteja nos resumos. Português do Brasil.",
            entrada, cfg, log, esquema=ESQUEMA_PROSA_DAILY)
        bruto.update({k: prosa.get(k) for k in ("contexto", "resumo")})
        meta.update({"segundos": round(seg + (meta.get("segundos") or 0), 1),
                     "custo_usd": round(custo + (meta.get("custo_usd") or 0), 4), "blocos": len(bls)})
    else:
        mk = _marcas.identificadas(sessao.m.get("marcas") or [])
        texto = _ata.transcricao_texto(segs)
        log(f"  Estruturando a daily com o Claude ({len(texto):,} caracteres".replace(",", ".")
            + f", {len(men)} fala(s) de frente, {len(rod)} pista(s) da rodada)…")
        bruto, meta = chamar_claude(prompt_daily(sessao, meu, equipe, frentes, men, rod, mk), texto, cfg, log,
                                    esquema=esquema_daily(bool(mk)))
    meta["versao_prompt"] = VERSAO_PROMPT_DAILY
    a = _daily.montar(sessao, segs, bruto, meta, meu, cfg)
    c = _daily.contagem(a)
    log(f"    {_daily.resumo_contagem(c)} · {meta.get('segundos') or 0:.0f}s")
    return a, None

