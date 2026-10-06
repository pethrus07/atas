# -*- coding: utf-8 -*-
"""
Avaliação interna da reunião (v2.1, pedido do Pedro em 06/10/2026). USO INTERNO, nunca vai ao
cliente: o render não lê este arquivo, e ele não entra em ata.json nem no entregável.

"Ele evoluindo significa eu evoluindo." Depois de uma negociação de 3 h com o Valdir, o resumo da
ata foi "superficial demais": o Pedro quer, junto da ata,
  1. as AFIRMAÇÕES DELE conferidas, sobretudo as erradas, com o timestamp e o que é verdade;
  2. se os VALORES fecham contra o piso de hora dele;
  3. se a NEGOCIAÇÃO fez sentido (ancoragem, concessões com ou sem troca, escopo × preço);
  4. a POSTURA, com os números do Raio-X da Fala;
  5. o que CORRIGIR com o cliente (promessas erradas que ele vai testar).

Para conferir afirmação é preciso olhar código, memória e números medidos — então o Claude roda
com ferramentas SÓ DE LEITURA (Read, Grep, Glob) dentro de ~/Projetos e da memória do Claude Code.
Modelo de saída: atas-salvas/2026-10-05_2303_alinhamento-valdir/avaliacao-interna.md (feito à mão).
"""
import datetime as _dt
import json
import pathlib
import subprocess
import time

import ata as _ata
import config as _config

VERSAO = "1"
ARQUIVO = "avaliacao-interna.md"
TIPOS_AVALIADOS = ("cliente", "parresia")


def deve_avaliar(sessao, segs, cfg):
    if not cfg.get("avaliar", True) or sessao.tipo not in TIPOS_AVALIADOS:
        return False
    dur = max((s["end"] for s in segs), default=0)
    return dur >= 60 * float(cfg.get("avaliar_acima_min", 15))


def _fala(m):
    """O Raio-X em texto curto, para o prompt (as metas e o cansaço)."""
    if not m:
        return "Raio-X da Fala indisponível."
    L = [f"- {n}: {v} (meta {meta}) {'ok' if ok else 'FORA DA META'}" for n, v, meta, ok in m.get("metas", [])]
    r = m.get("ritmo") or {}
    if r:
        L.append(f"- Interrompeu {r.get('interrompeu')}×, foi interrompido {r.get('foi_interrompido')}×; "
                 f"maior monólogo {r.get('maior_monologo_s')} s; perguntas reais {r.get('perguntas_reais')}")
    if m.get("confirmacoes"):
        L.append("- Confirmações: " + ", ".join(f"{k}? {v}" for k, v in m["confirmacoes"].items()))
    if m.get("muletas"):
        L.append("- Muletas: " + ", ".join(f"{k} {v}" for k, v in list(m["muletas"].items())[:8]))
    if m.get("blocos"):
        L.append("- Muletas/1k por bloco de 30 min: " + " → ".join(str(b["muletas_por_1000"]) for b in m["blocos"]))
    if m.get("voz"):
        L.append(f"- Voz: entonação {m['voz']['entonacao_st']} semitons, volume {m['voz']['volume_db']} dBFS")
    return "\n".join(L)


def prompt(sessao, ata, metricas, cfg):
    meu = cfg.get("meu_nome", "Pedro")
    neg = cfg.get("negociacao") or {}
    piso = neg.get("piso_hora", 70)
    itens = []
    for k, rot in (("decisoes", "decisao"), ("valores", "descricao"), ("escopo", "item"),
                   ("encaminhamentos", "acao")):
        for it in ata.get(k, []):
            extra = f" = {it.get('valor')}" if k == "valores" else ""
            itens.append(f"- [{it.get('t')}] {k[:-1] if k != 'escopo' else 'escopo'}: {it.get(rot)}{extra}")
    return "\n".join([
        f"Você vai escrever a AVALIAÇÃO INTERNA de uma reunião de {meu}, para ELE ler. Nunca vai ao "
        "cliente. A transcrição completa chega no stdin, uma fala por linha: `[h:mm:ss] Rótulo: texto`. "
        f"\"Você\" é {meu} (microfone dele); o resto é o áudio da chamada.",
        "",
        f"Reunião: {sessao.m.get('titulo')} · tipo {sessao.tipo} · {ata.get('duracao_min')} min · "
        f"{(ata.get('data') or '')[:10]}.",
        "",
        "O que a ata já registrou (decisões, valores, escopo, encaminhamentos):",
        "\n".join(itens) or "(nada)",
        "",
        "Raio-X da Fala desta reunião (medido):",
        _fala(metricas),
        "",
        "Você tem ferramentas SÓ DE LEITURA (Read, Grep, Glob). O diretório atual é ~/Projetos, com os "
        f"repositórios de {meu}. A memória do assistente dele (projetos, preços, decisões, preferências) "
        "está no diretório adicional da memória: leia o MEMORY.md e os arquivos que importarem para esta "
        "reunião ANTES de avaliar.",
        "",
        "Escreva em Markdown, português do Brasil, frases curtas, com estas seções:",
        "",
        "# Avaliação interna · <título> (<data>)",
        "> USO INTERNO. Não vai ao cliente.",
        "## Veredito em uma linha",
        f"## 1. As afirmações de {meu}, conferidas",
        f"Percorra as falas de \"Você\" e confira as afirmações de FATO (técnicas, de preço, de prazo, "
        "do que um sistema faz ou não faz, do que já foi feito). Use o código (Grep/Read nos repositórios) "
        "e a memória. Três listas:",
        "### ❌ Erradas e que importam — tabela: Quando | O que disse | O que é | Por que importa",
        "### ⚠️ Meio certas ou não conferidas",
        "### ✅ Certas",
        "### O que mandar ao cliente para corrigir (itens curtos)",
        "Regra: só chame de errado o que você CONFERIU (diga onde: arquivo, memória, número). O que não "
        "deu para conferir vai em \"não conferidas\", nunca em erradas. Não invente número.",
        "## 2. Os valores fizeram sentido?",
        f"Para cada valor combinado: o que entra, uma estimativa do tempo de {meu} (diga que é estimativa) "
        f"e o valor por hora resultante, comparado ao piso de R$ {piso}/h. Use as tabelas de preço que "
        "estiverem na memória. Diga o que está abaixo do piso e o que fazer.",
        "## 3. A negociação fez sentido?",
        "**Funcionou** e **Custou caro**: ancoragem, concessões com ou sem contrapartida, escopo fechado "
        "antes ou depois do preço, custo interno revelado, contradições.",
        "## 4. Postura",
        "**Pontos fortes** e **O que trabalhar**, usando os números do Raio-X (confirmações/min, muletas, "
        "ritmo, interrupções, cansaço por bloco) e frases literais com timestamp. Inclua conversa fora de "
        "pauta se ela tomou tempo da negociação.",
        "**Para a próxima reunião**: 3 a 5 regras práticas.",
        "",
        "Cite timestamps [h:mm:ss]. Seja direto e honesto: o objetivo é ele melhorar, não ser elogiado.",
    ])


def avaliar(sessao, segs, ata, metricas, cfg, log=print):
    """Gera avaliacao-interna.md. Devolve (caminho, meta). Levanta com o motivo se falhar."""
    exe = _config.claude_cli(cfg)
    if not exe:
        raise RuntimeError("claude.exe não encontrado")
    projetos = pathlib.Path(cfg.get("projetos_dir") or pathlib.Path.home() / "Projetos")
    memoria = pathlib.Path(cfg.get("memoria_dir") or (pathlib.Path.home() / ".claude" / "projects"
                                                      / "C--Users-olive" / "memory"))
    texto = "\n".join(f"[{_ata.fmt_t(f['start'])}] {f['speaker']}: {f['text']}" for f in _ata.falas(segs))
    cmd = [exe, "-p", prompt(sessao, ata, metricas, cfg),
           "--output-format", "json",
           "--tools", "Read,Grep,Glob",            # só leitura: conferir, nunca alterar
           "--allowedTools", "Read,Grep,Glob",     # sem janela: sem isso, o pedido de permissão trava
           "--no-session-persistence",
           "--strict-mcp-config",
           "--setting-sources", ""]
    if memoria.exists():
        cmd += ["--add-dir", str(memoria)]
    if cfg.get("claude_modelo"):
        cmd += ["--model", cfg["claude_modelo"]]
    log(f"  Avaliação interna (Claude lendo código e memória; pode levar alguns minutos)…")
    t0 = time.time()
    r = subprocess.run(cmd, input=texto.encode("utf-8"), capture_output=True, cwd=str(projetos),
                       timeout=int(cfg.get("avaliar_timeout_s", 2400)))
    saida = r.stdout.decode("utf-8", "replace")
    try:
        dado = json.loads(saida)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude saiu com código {r.returncode} sem JSON: "
                           f"{(saida or r.stderr.decode('utf-8', 'replace'))[-400:]}")
    corpo = (dado.get("result") or "").strip()
    if dado.get("is_error") or len(corpo) < 400:
        raise RuntimeError(f"claude não devolveu a avaliação: {corpo[:300]}")
    meta = {"em": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "segundos": round(time.time() - t0, 1), "custo_usd": dado.get("total_cost_usd"),
            "versao": VERSAO}
    rodape = (f"\n\n---\n_Gerada automaticamente pelo Atas em {meta['em'][:16].replace('T', ' ')} "
              f"({meta['segundos']:.0f} s). Confira antes de agir: o /ata revisa e completa._\n")
    destino = sessao.caminho(ARQUIVO)
    if destino.exists():                           # nunca por cima de uma revisada à mão
        destino = sessao.caminho(f"avaliacao-interna.auto-{time.strftime('%Y%m%d-%H%M%S')}.md")
    destino.write_text(corpo + rodape, encoding="utf-8")
    return destino, meta
