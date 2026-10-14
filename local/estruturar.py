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
from sessao import TIPOS

VERSAO_PROMPT = "3"   # 3 = valores, escopo, por_tema e blocos (v2.1, 06/10/2026)

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


def prompt(sessao, meu_nome):
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
    ]
    return "\n".join(linhas)


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
    chave = next((k for k in ("decisao", "acao", "pergunta", "risco", "descricao", "item") if k in a), None)
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
    if not segs:
        a = _ata.base(sessao, segs, meu)
        a["lacunas"] = _ata.lacunas(a)
        return a, "sem falas"
    texto = _ata.transcricao_texto(segs)
    dur_min = max((s["end"] for s in segs), default=0) / 60
    if dur_min > float(cfg.get("estruturar_blocos_acima_min", 60)):
        bruto, meta = _estruturar_em_blocos(sessao, segs, cfg, meu, log)
    else:
        log(f"  Estruturando a ata com o Claude ({len(texto):,} caracteres)…".replace(",", "."))
        bruto, meta = chamar_claude(prompt(sessao, meu), texto, cfg, log)
    a = _ata.montar(sessao, segs, bruto, meta, meu)
    c = _ata.contagem(a)
    log(f"    {c['decisoes']} decisões · {c['encaminhamentos']} encaminhamentos · "
        f"{c['perguntas_abertas']} perguntas · {c['riscos']} riscos · "
        f"{c['nao_verificados']} sem origem localizada · {meta.get('segundos') or 0:.0f}s")
    return a, None


def _estruturar_em_blocos(sessao, segs, cfg, meu, log=print):
    """Reunião longa: um claude -p por bloco + uma passada que consolida a prosa."""
    partes, custo, seg = [], 0.0, 0.0
    bls = blocos(segs, bloco_s=int(cfg.get("estruturar_bloco_min", 40)) * 60)
    for k, (ini, bseg) in enumerate(bls, 1):
        fim = min(ini + int(cfg.get("estruturar_bloco_min", 40)) * 60, max(s["end"] for s in segs))
        log(f"  Estruturando o bloco {k}/{len(bls)} ({_ata.fmt_t(ini)} a {_ata.fmt_t(fim)})…")
        p = prompt(sessao, meu) + (
            f"\n\nATENÇÃO: este é o trecho {k} de {len(bls)} de uma reunião mais longa "
            f"(de {_ata.fmt_t(ini)} a {_ata.fmt_t(fim)}, com um pouco de sobra antes e depois). "
            "Extraia os itens que aparecem NESTE trecho; resumo, contexto, temas e por_tema também "
            "só deste trecho.")
        bruto, meta = chamar_claude(p, _ata.transcricao_texto(bseg), cfg, log)
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
