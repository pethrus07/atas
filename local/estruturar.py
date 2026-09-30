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

VERSAO_PROMPT = "2"

_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
         "sábado", "domingo"]


def _data_reuniao(sessao):
    ini = sessao.m.get("inicio") or sessao.m.get("criado")
    try:
        d = _dt.datetime.fromisoformat(ini)
    except (TypeError, ValueError):
        d = _dt.datetime.now()
    return d


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
        f"- \"Você\" na transcrição é {meu_nome} (microfone dele). {papel}",
        "- \"Participante\" / \"Participante N\" é o áudio da chamada. A separação automática "
        "de vozes é imperfeita: a mesma pessoa pode aparecer sob vários rótulos, e um rótulo "
        "pode misturar pessoas.",
        ("- Participantes remotos informados por ele: " + ", ".join(remotos) +
         " (podem não ter falado todos).") if remotos else
        "- Os participantes remotos não foram informados.",
        "",
        "Regras inegociáveis:",
        "1. Nada inventado. Todo item de decisoes, encaminhamentos, perguntas_abertas e riscos "
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
        "7. Português do Brasil. Nada que não esteja na transcrição.",
    ]
    return "\n".join(linhas)


def chamar_claude(texto_prompt, transcricao, cfg, log=print):
    """Roda o claude -p e devolve (structured_output, meta). Levanta com o motivo."""
    exe = _config.claude_cli(cfg)
    if not exe:
        raise RuntimeError("claude.exe não encontrado (instale o Claude Code ou defina "
                           "'claude_cli' no config.json)")
    cmd = [exe, "-p", texto_prompt,
           "--output-format", "json",
           "--json-schema", json.dumps(_ata.ESQUEMA_CLAUDE, ensure_ascii=False),
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
    log(f"  Estruturando a ata com o Claude ({len(texto):,} caracteres)…".replace(",", "."))
    bruto, meta = chamar_claude(prompt(sessao, meu), texto, cfg, log)
    a = _ata.montar(sessao, segs, bruto, meta, meu)
    c = _ata.contagem(a)
    log(f"    {c['decisoes']} decisões · {c['encaminhamentos']} encaminhamentos · "
        f"{c['perguntas_abertas']} perguntas · {c['riscos']} riscos · "
        f"{c['nao_verificados']} sem origem localizada · {meta.get('segundos') or 0:.0f}s")
    return a, None
