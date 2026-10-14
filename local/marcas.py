# -*- coding: utf-8 -*-
"""
Marcar momento (14/10/2026) — o Pedro aperta um atalho na hora em que algo importa, e a ata dá
peso àquele trecho. Ideia do Granola.

    sessao.json  "marcas": [{"t": 750.2, "criado": "2026-10-14T15:12:30-03:00", "origem": "atalho"}]

`t` = segundos desde o início da gravação (a mesma régua dos timestamps da transcrição: o PCM é
alinhado ao relógio pelo gravador, com silêncio no lugar de buraco). `origem`: atalho · botao ·
depois (`atas.py marcar`) · celular (`importar --marcas`). Sem rótulo: na hora da call, qualquer
coisa além de um toque atrapalha.

Um tipo só de marca. Duplo toque = "importante" foi descartado de propósito: é um gesto escondido,
fácil de errar com a cabeça na conversa, e a marca já É o "importante". Toques repetidos em até
`REPIQUE_S` contam como uma marca só (tecla que repete, ou o Pedro apertando duas vezes "para
garantir").

O trecho de cada marca é `JANELA_ANTES_S` antes e `JANELA_DEPOIS_S` depois: ele aperta DEPOIS de
ouvir a coisa, então quase tudo o que importa está antes.
"""
import ata as _ata
from sessao import agora_iso

JANELA_ANTES_S = 45
JANELA_DEPOIS_S = 15
REPIQUE_S = 2.0
ORIGENS = ("atalho", "botao", "depois", "celular")


def lista(sessao):
    return list(sessao.m.get("marcas") or [])


def adicionar(sessao, t, origem="atalho", salvar=True):
    """Grava a marca no sessao.json (escrita atômica com fsync, como o resto da gravação).
    Devolve a marca, ou None se caiu no repique de uma marca vizinha."""
    t = round(max(0.0, float(t)), 1)
    marcas = sessao.m.setdefault("marcas", [])
    if any(abs(m["t"] - t) < REPIQUE_S for m in marcas):
        return None
    m = {"t": t, "criado": agora_iso(), "origem": origem if origem in ORIGENS else "depois"}
    marcas.append(m)
    marcas.sort(key=lambda x: x["t"])
    if salvar:
        sessao.salvar()
    return m


def ler_horarios(textos):
    """"12:30", "1:02:03", "40:10" (ou "12:30,40:10" de uma vez) → segundos. Levanta ValueError."""
    out = []
    for txt in textos:
        for parte in str(txt).replace(";", ",").split(","):
            parte = parte.strip()
            if not parte:
                continue
            if ":" not in parte:
                raise ValueError(f"horário inválido: {parte!r} (use mm:ss ou h:mm:ss)")
            seg = _ata.parse_t(parte)
            if seg is None or any(not x.strip().isdigit() for x in parte.split(":")):
                raise ValueError(f"horário inválido: {parte!r} (use mm:ss ou h:mm:ss)")
            if any(int(x) >= 60 for x in parte.split(":")[1:]):
                raise ValueError(f"horário inválido: {parte!r} (minuto e segundo vão até 59)")
            out.append(float(seg))
    return out


def identificadas(marcas):
    """[(id, marca)] na ordem do tempo: M1, M2… O id é posicional (a ordem do tempo), recalculado
    a cada leitura — uma marca acrescentada depois renumera as seguintes, e a ata acompanha."""
    return [(f"M{i}", m) for i, m in enumerate(sorted(marcas, key=lambda x: x["t"]), 1)]


def janela(t):
    return max(0.0, t - JANELA_ANTES_S), t + JANELA_DEPOIS_S


def dentro(t_fala, t_marca, folga_s=5):
    """A fala (pelo início) está no trecho da marca? A folga cobre fala que começou um pouco antes
    da janela e o arredondamento do Whisper."""
    ini, fim = janela(t_marca)
    return ini - folga_s <= t_fala <= fim + folga_s


def do_bloco(marcas, ini, bloco_s, ultimo):
    """As marcas que pertencem ao bloco [ini, ini+bloco_s) da estrutura em blocos (reunião longa).
    Cada marca cai em UM bloco só; o que passar do fim vai para o último. A sobra de 120 s dos
    blocos cobre a janela de 45 s antes / 15 s depois."""
    return [(i, m) for i, m in identificadas(marcas)
            if ini <= m["t"] < ini + bloco_s or (ultimo and m["t"] >= ini + bloco_s)]


def linhas_prompt(ids_marcas):
    """O pedaço do prompt do Claude que trata das marcas (vazio se não houver)."""
    if not ids_marcas:
        return []
    out = ["", "MOMENTOS MARCADOS: durante a reunião ele apertou um atalho nos instantes abaixo, logo "
           "DEPOIS de ouvir algo importante. O trecho de cada marca vai de 45 s antes a 15 s depois:"]
    for i, m in ids_marcas:
        a, b = janela(m["t"])
        out.append(f"- {i} em [{_ata.fmt_t(m['t'])}] → trecho de [{_ata.fmt_t(a)}] a [{_ata.fmt_t(b)}]")
    out += [
        "Estes trechos são PRIORIDADE: toda decisão, valor, compromisso (encaminhamento) ou prazo dito "
        "neles TEM de estar nas listas normais (decisoes, encaminhamentos, valores…), com a citação "
        "literal como sempre.",
        "Em `momentos`, um item por marca da lista acima, com o id dela em `marca`:`o_que` = em uma frase, o que de "
        "importante foi dito no trecho; `tipo` = decisao, valor, compromisso, prazo, pergunta, risco ou "
        "informacao; `t` e `citacao` = a fala do trecho que sustenta, COPIADA LITERALMENTE (8 a 30 "
        "palavras), como nas outras listas. Se o trecho não tem nada claro (conversa solta, ruído), "
        "`tipo` = \"nada\" e `o_que`, `t` e `citacao` = null. Nunca invente para preencher.",
    ]
    return out

