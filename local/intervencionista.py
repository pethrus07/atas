# -*- coding: utf-8 -*-
"""
Ao vivo intervencionista (22/10/2026, docs/MELHORIAS.md §22, docs/ARQUITETURA.md §22).

Pedido do Pedro depois de usar o ao vivo com o Claude lendo o `ao-vivo.md` pelo chat ("muito muito
bom"): um modo que fica ouvindo o tempo todo e traz a resposta SEM ele pedir. Decisão de 21/10: ele
liga reunião a reunião (como o ao vivo), desligado por padrão, em qualquer tipo.

    ao-vivo.md (o ao vivo já escreve incremental)
      → esta thread lê só as linhas novas, a cada `leitura_s`
      → FILTRO DETERMINÍSTICO, sem IA: só passa o que pede ajuda
            pergunta dirigida ao Pedro   (nome dele + "?", ou "você" + "?" logo antes de uma fala dele)
            card / frente rastreada      (SUP-NNN, ou card/palavra de `frentes_rastreadas`)
            valor, número, prazo         (R$, reais, "15 mil", "20%", "dia 10", "15 dias"…)
            projeto conhecido            (nome de projeto/cliente do config ou do Sinapse 03-PROJETOS)
         na daily só os dois primeiros ("com você" e frentes), nunca tudo
      → com gatilho, e dentro do teto e do intervalo: `claude -p` com ferramentas SÓ DE LEITURA
        (Read, Grep, Glob em ~/Projetos e na memória, como a avaliação interna) → no máximo 2 linhas
        com a fonte, ou "não sei" (regra 3 do CLAUDE.md: nada inventado)
      → um cartão pequeno no canto inferior direito, sempre por cima, que nunca rouba o foco, não toca
        som e some sozinho em ~25 s (ou com um clique)
      → cada chamada vai para `intervencoes.jsonl` na pasta da sessão (o /ata lê)

Nunca fala, nunca envia nada para fora da máquina além da própria chamada ao Claude (o mesmo que a
ata e a avaliação já fazem), nunca escreve fora da pasta da sessão.

Custos sob controle: sem gatilho, nada é chamado; teto de chamadas por reunião (`max_chamadas`,
padrão 20) e intervalo mínimo entre chamadas (`intervalo_min_s`, 45 s); uma chamada por vez (a thread
espera a resposta antes de ler de novo). Gatilho que chega no intervalo fica na fila (só o mais
importante, e só enquanto tiver menos de `validade_s` de idade).
"""
import datetime as _dt
import json
import pathlib
import re
import subprocess
import threading
import time
import unicodedata

import ata as _ata

ARQUIVO = "intervencoes.jsonl"
VERSAO_PROMPT = "interv-1"
PADRAO = {
    "max_chamadas": 20,          # teto por reunião (cota do plano)
    "intervalo_min_s": 45,       # entre o início de uma chamada e o da próxima
    "leitura_s": 5,              # de quanto em quanto tempo o ao-vivo.md é relido
    "validade_s": 90,            # gatilho na fila mais velho que isso (no tempo da reunião) é descartado
    "cartao_s": 25,              # o cartão some sozinho
    "timeout_s": 120,            # uma chamada que passa disso é cortada (a resposta já não serve)
    "modelo": None,              # None = o claude_modelo do config, ou o padrão da conta
    "esforco": "low",            # --effort do claude: resposta curta, rápida
    "projetos": [],              # nomes extras de projeto/cliente (os do Sinapse 03-PROJETOS entram sozinhos)
    "nomes": [],                 # apelidos do Pedro além do meu_nome ("Pethrus"…)
    "mostrar_nao_sei": False,    # "não sei" vai só para o registro, não para a tela
    "repetir_s": 300,            # o mesmo projeto/card/valor não dispara de novo antes disso
}
PRIORIDADE = {"pergunta": 0, "card": 1, "valor": 2, "projeto": 3}
ROTULO_GATILHO = {"pergunta": "Pergunta para você", "card": "Card", "valor": "Valor ou prazo",
                  "projeto": "Projeto"}
PENDENTE = object()              # pergunta com "você" que ainda não tem a fala seguinte

_RE_LINHA = re.compile(r"^\[(\d{1,2}(?::\d{2}){1,2})\]\s+([^:\[\]]{1,40}?):\s+(.+)$")
_SEGUNDA_PESSOA = re.compile(r"\b(?:voce|voces|vc|ce|tu|contigo|te)\b")
# valor: dinheiro, porcentagem, "N mil"; número com palavra de valor/prazo por perto
_RE_DINHEIRO = re.compile(
    r"r\$\s*\d|\b\d[\d.,]*\s*(?:mil\s+)?(?:reais|real|conto|contos|pila)\b|\bmil\s+reais\b"
    r"|\b\d[\d.,]*\s*mil\b")
# porcentagem sozinha ("100% local", "5% personalizado") era ruído no ao vivo de 19/10: só conta com
# palavra de valor perto ("desconto de 20%"), pelo _RE_NUMERO + _PALAVRAS_VALOR
_RE_NUMERO = re.compile(r"\b\d{2,}(?:[.,]\d+)?\b")
_PALAVRAS_VALOR = re.compile(
    r"\b(?:valor|valores|preco|precos|custa|custo|custou|cobr\w*|pag\w*|parcela\w*|mensalidade\w*"
    r"|orcamento\w*|por hora|horas|dias|semanas|meses|prazo\w*|entrega\w*|desconto\w*|investimento)\b")
# "por que eu te digo isso?": pergunta retórica, não é com ele
_RETORICA = re.compile(r"\bpor ?que\b.*\b(?:te|vou te|quero te) (?:digo|dizer|falo|falar|explicar)\b")
_PRAZO_FRACO = {"hoje", "amanha", "depois de amanha"}     # comum demais na conversa para chamar o Claude
_MARCADOR_FATO = re.compile(
    r"\b(?:ja|ainda|ta|esta|estao|ficou|ficaram|foi|foram|vai|vao|tem|funciona\w*|pront[oa]s?|publica\w*"
    r"|subiu|subir|no ar|entreg\w*|aprova\w*|falta\w*|parou|quebr\w*|erro|bug|lancad\w*|lanca\w*)\b")


def _sem_acento(t):
    """Minúsculo e sem acento, mantendo a pontuação ('?' e 'R$' importam aqui)."""
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


def config(cfg):
    return {**PADRAO, **((cfg or {}).get("intervencionista") or {})}


# ── leitura incremental do ao-vivo.md ───────────────────────────────────────
def ler_novas(caminho, offset):
    """Falas completas escritas depois de `offset` (bytes) → ([{t, rotulo, texto}], novo offset).
    Só linhas inteiras (até o último \\n): o ao vivo pode estar no meio de uma escrita. Cabeçalho e as
    linhas `[mm:ss] ★ MARCA` (sem "Rótulo:") ficam fora."""
    p = pathlib.Path(caminho)
    if not p.exists():
        return [], offset
    with open(p, "rb") as f:
        f.seek(offset)
        bruto = f.read()
    fim = bruto.rfind(b"\n")
    if fim < 0:
        return [], offset
    falas = []
    for ln in bruto[:fim + 1].decode("utf-8", "replace").splitlines():
        m = _RE_LINHA.match(ln.strip())
        if m:
            falas.append({"t": float(_ata.parse_t(m.group(1))), "rotulo": m.group(2).strip(),
                          "texto": m.group(3).strip()})
    return falas, offset + fim + 1


# ── nomes de projeto ───────────────────────────────────────────────────────
def _vault():
    import os
    base = os.environ.get("SINAPSE_VAULT")
    return pathlib.Path(base) if base else pathlib.Path(__file__).parents[2] / "sinapse"


def nomes_de_projeto(cfg, vault=None, excluir=()):
    """Nomes de projeto/cliente que valem como gatilho: `intervencionista.projetos` do config + o título
    (H1) e o nome do arquivo de cada nota de `03-PROJETOS` do Sinapse (sem os históricos e o MOC).
    "Ware IoT (ex-Celiware IHM) — IHM portátil" vira "Ware IoT" e "Celiware IHM". Nomes de pessoa
    (participantes, o próprio Pedro) ficam fora: seriam ditos o tempo todo."""
    termos = list(config(cfg).get("projetos") or [])
    pasta = pathlib.Path(vault or _vault()) / "03-PROJETOS"
    if pasta.exists():
        for p in sorted(pasta.glob("*.md")):
            if p.stem.startswith("MOC") or "-historico-" in p.stem:
                continue
            termos.append(p.stem.replace("-", " "))
            try:
                h1 = next((ln[2:] for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("# ")), "")
            except OSError:
                h1 = ""
            principal = re.split(r"\s+[—–-]\s+", h1)[0]
            termos += re.findall(r"\(ex-([^)]+)\)", principal)
            termos.append(re.sub(r"\s*\(.*?\)", "", principal))
    fora = {_ata.norm(x) for x in excluir if x}
    vistos, out = set(), []
    for t in termos:
        n = _ata.norm(t)
        if len(n) >= 4 and n not in vistos and n not in fora:
            vistos.add(n)
            out.append(t.strip())
    return out


# ── o filtro determinístico ────────────────────────────────────────────────
def _e_voce(rotulo):
    return rotulo.strip().lower() in ("você", "voce")


# pedido de confirmação no fim da frase ("…, você entendeu?", "…, né?"): não é pergunta, é tique (no
# ao vivo de 19/10, 133 "perguntas" em 4h47, a maioria "você entendeu?"). Mesma lista do Raio-X + extras.
_TAG_FINAL = re.compile(r"(?:^|\s)(?:voce entendeu|entendeu|certo|ne|ta|nao e|sabe|correto|beleza|saca|ta ligado"
                        r"|ta bom|ok|viu|concorda|confere|fechou|pode ser|nao)$")


def perguntas_de_verdade(texto, nomes=()):
    """As frases terminadas em "?" que não são só um pedido de confirmação no fim ("…, você entendeu,
    Pedro?" também é tique: o vocativo no fim é tirado antes de olhar a tag)."""
    out = []
    vocativos = [_ata.norm(x) for x in nomes if x]
    for frase in re.findall(r"[^.?!]*\?", str(texto or "")):
        n = _ata.norm(frase)
        for v in vocativos:
            if n.endswith(" " + v):
                n = n[:-len(v) - 1]
        if n and not _TAG_FINAL.search(n) and not _RETORICA.search(n):
            out.append(frase.strip())
    return out


def _pergunta_para_mim(falas, i, nomes):
    """Motivo (str), PENDENTE ou None. Pergunta do outro lado com o nome do Pedro, ou com "você" e a
    fala seguinte é do Pedro (ele foi chamado a responder). No ao vivo só há "Você" e "Participante".
    "…, você entendeu?" e "…, né?" não contam (tique de confirmação, não pergunta)."""
    f = falas[i]
    if _e_voce(f["rotulo"]):
        return None
    pergs = perguntas_de_verdade(f["texto"], nomes)
    if not pergs:
        return None
    if any(_ata._contem(x, p) for x in nomes for p in pergs):
        return "pergunta com o seu nome"
    if not any(_SEGUNDA_PESSOA.search(_ata.norm(p)) for p in pergs):
        return None
    prox = next((g for g in falas[i + 1:] if g["t"] >= f["t"]), None)
    if prox is None:
        return PENDENTE
    if _e_voce(prox["rotulo"]) and prox["t"] - f["t"] <= 30:
        return "pergunta para você"
    return None


def _valor(texto):
    """O valor/número/prazo dito (o pedaço que casou), ou None."""
    s = _sem_acento(texto)
    m = _RE_DINHEIRO.search(s)
    if m:
        return m.group(0).strip()
    prazo = _ata.expressao_de_prazo(texto)
    if prazo and _ata.norm(prazo) not in _PRAZO_FRACO:
        return prazo
    n = _ata.norm(texto)
    for m in _RE_NUMERO.finditer(n):
        perto = n[max(0, m.start() - 40):m.end() + 40]
        if _PALAVRAS_VALOR.search(perto):
            return m.group(0)
    return None


def _card(texto, frentes):
    """(card ou nome da frente, motivo) ou None. SUP-NNN em qualquer reunião; card ou palavra de
    frente rastreada (`frentes_rastreadas`, a mesma lista da daily)."""
    import daily
    c = daily.normalizar_card(texto)
    if c:
        fr = next((x["nome"] for x in frentes if c in x["cards"]), None)
        return c, f"card {c}" + (f" (frente {fr})" if fr else "")
    men = daily.mencoes([{"text": texto, "start": 0.0, "speaker": ""}], frentes)
    if men:
        x = men[0]
        alvo = x["cards"][0] if x["cards"] else x["palavras"][0]
        return x["frente"], f"frente {x['frente']} ({alvo})"
    return None


def _projeto(texto, projetos):
    if len(_ata.norm(texto).split()) < 6:
        return None
    nome = next((p for p in projetos if _ata._contem(p, texto)), None)
    if nome and _MARCADOR_FATO.search(_ata.norm(texto)):
        return nome
    return None


def gatilhos(falas, inicio, nomes, frentes, projetos, daily=False):
    """Os gatilhos das falas[inicio:] (as novas), e os índices de perguntas ainda PENDENTES (sem a
    fala seguinte). Cada gatilho: {tipo, chave, motivo, t, rotulo, trecho, i}. Na daily só pergunta e
    card/frente (o resto da daily não é com ele)."""
    out, pendentes = [], []
    for i in range(inicio, len(falas)):
        f = falas[i]
        base = {"t": f["t"], "rotulo": f["rotulo"], "trecho": f["texto"], "i": i}
        p = _pergunta_para_mim(falas, i, nomes)
        if p is PENDENTE:
            pendentes.append(i)
        elif p:
            out.append({**base, "tipo": "pergunta", "chave": f"pergunta@{f['t']:.0f}", "motivo": p})
            continue
        c = _card(f["texto"], frentes)
        if c:
            out.append({**base, "tipo": "card", "chave": f"card:{c[0]}", "motivo": c[1]})
            continue
        if daily:
            continue
        v = _valor(f["texto"])
        if v:
            out.append({**base, "tipo": "valor", "chave": f"valor:{_ata.norm(v)}", "motivo": f"valor ou prazo dito: {v}"})
            continue
        pr = _projeto(f["texto"], projetos)
        if pr:
            out.append({**base, "tipo": "projeto", "chave": f"projeto:{_ata.norm(pr)}",
                        "motivo": f"afirmação sobre {pr}"})
    return out, pendentes


def reavaliar_pendentes(falas, pendentes, nomes):
    """As perguntas que esperavam a fala seguinte: as que agora têm resposta do Pedro viram gatilho;
    as que ainda não têm continuam pendentes; o resto cai."""
    out, ainda = [], []
    for i in pendentes:
        p = _pergunta_para_mim(falas, i, nomes)
        if p is PENDENTE:
            ainda.append(i)
        elif p:
            f = falas[i]
            out.append({"t": f["t"], "rotulo": f["rotulo"], "trecho": f["texto"], "i": i, "tipo": "pergunta",
                        "chave": f"pergunta@{f['t']:.0f}", "motivo": p})
    return out, ainda


# ── a fila, o teto e o intervalo ─────────────────────────────────────────────
class Controle:
    """Decide QUANDO chamar: teto por reunião, intervalo mínimo, uma chamada por vez, sem repetir a
    mesma chave em `repetir_s`, e a fila com um gatilho só (o mais importante; empate = o mais novo).
    Relógio injetável para os testes."""

    def __init__(self, c, relogio=time.monotonic):
        self.max = int(c["max_chamadas"])
        self.intervalo = float(c["intervalo_min_s"])
        self.validade = float(c["validade_s"])
        self.repetir = float(c["repetir_s"])
        self.relogio = relogio
        self.chamadas = 0
        self.ultima = None               # relógio do início da última chamada
        self.em_curso = False
        self.fila = None
        self.vistas = {}                 # chave → t (tempo da reunião) da última vez que chamou

    def oferecer(self, g):
        ult = self.vistas.get(g["chave"])
        if ult is not None and g["t"] - ult < self.repetir:
            return False
        if self.fila is None or (PRIORIDADE[g["tipo"]], -g["t"]) <= (PRIORIDADE[self.fila["tipo"]], -self.fila["t"]):
            self.fila = g
        return True

    def teto(self):
        return self.chamadas >= self.max

    def proximo(self, t_agora):
        """O gatilho a chamar agora, ou None. `t_agora` = tempo da reunião da última fala lida."""
        if self.fila is not None and t_agora - self.fila["t"] > self.validade:
            self.fila = None                 # velho demais: a conversa já seguiu
        if self.fila is None or self.em_curso or self.teto():
            return None
        if self.ultima is not None and self.relogio() - self.ultima < self.intervalo:
            return None
        g, self.fila = self.fila, None
        self.chamadas += 1
        self.ultima = self.relogio()
        self.em_curso = True
        self.vistas[g["chave"]] = g["t"]
        return g

    def terminou(self):
        self.em_curso = False


# ── a chamada ao Claude ─────────────────────────────────────────────────────
ESQUEMA = {"type": "object", "additionalProperties": False,
           "properties": {"sabe": {"type": "boolean"}, "resposta": {"type": "string"},
                          "fonte": {"type": "string"}},
           "required": ["sabe", "resposta", "fonte"]}


def _dirs(cfg):
    projetos = pathlib.Path(cfg.get("projetos_dir") or pathlib.Path.home() / "Projetos")
    memoria = pathlib.Path(cfg.get("memoria_dir") or (pathlib.Path.home() / ".claude" / "projects"
                                                      / "C--Users-olive" / "memory"))
    return projetos, memoria


def prompt(g, contexto, sessao_m, cfg):
    meu = cfg.get("meu_nome", "Pedro")
    projetos, memoria = _dirs(cfg)
    linhas = "\n".join(f"[{_ata.fmt_t(f['t'])}] {f['rotulo']}: {f['texto']}" for f in contexto)
    return "\n".join([
        f"Você acompanha AO VIVO uma reunião de {meu} e só fala quando tem um FATO útil. A transcrição é "
        f"preliminar (modelo pequeno, sem separar pessoas): \"Você\" é {meu}; \"Participante\" é o outro lado.",
        f"Reunião: {sessao_m.get('titulo') or '(sem título)'} · tipo {sessao_m.get('tipo')}"
        + (f" · projeto {sessao_m['projeto']}" if sessao_m.get("projeto") else "")
        + (f" · com {', '.join(sessao_m['participantes'])}" if sessao_m.get("participantes") else "") + ".",
        "",
        "Últimas falas:",
        linhas,
        "",
        f"Um filtro automático marcou a fala de [{_ata.fmt_t(g['t'])}]: {g['motivo']}.",
        "",
        f"Traga, em NO MÁXIMO 2 linhas curtas (até 200 caracteres), a informação que {meu} precisa agora "
        "para responder ou conferir isso: o que já foi combinado, o valor/prazo registrado, o estado do "
        "projeto ou do card. Em `fonte`, o arquivo de onde tirou (caminho curto).",
        "Regras: NADA inventado. Só vale o que você LEU agora num arquivo. Se não achar em poucas leituras, "
        "`sabe` = false e `resposta` = \"não sei\". Não resuma a reunião, não dê conselho genérico, não "
        "sugira frase para ele falar.",
        f"Onde procurar (só leitura, seja rápido, no máximo ~5 leituras): a memória dele em {memoria} "
        "(comece pelo MEMORY.md, que é o índice); o Sinapse em "
        f"{projetos / 'sinapse'} (03-PROJETOS); os repositórios no diretório atual; atas anteriores em "
        f"{projetos / 'atas' / 'atas-salvas'} (<id>/ata.md).",
    ])


_RE_CAMINHO = re.compile(r"[\w./\\:~-]+\.(?:md|py|json|jsonl|js|ts|txt|toml|yaml|yml|html)\b", re.I)


def fonte_conferida(fonte, cfg):
    """True se algum arquivo citado na fonte existe (em ~/Projetos, na memória ou como caminho
    absoluto); False se cita arquivo e nenhum existe; None se a fonte não cita arquivo."""
    projetos, memoria = _dirs(cfg)
    achados = _RE_CAMINHO.findall(fonte or "")
    if not achados:
        return None
    for a in achados:
        a = a.replace("\\", "/").strip("./") if not re.match(r"^[a-zA-Z]:", a) else a
        p = pathlib.Path(a).expanduser()
        candidatos = [p] if p.is_absolute() else [projetos / p, memoria / p, memoria / p.name]
        if any(c.exists() for c in candidatos):
            return True
        if not p.is_absolute() and list(projetos.glob(f"*/{p.as_posix()}"))[:1]:
            return True
    return False


def chamar_claude(g, contexto, sessao_m, cfg, guardar_proc=None):
    """Roda o claude -p com Read/Grep/Glob e devolve {sabe, resposta, fonte, segundos, custo_usd,
    modelo}. Levanta com o motivo. `guardar_proc(p)` recebe o processo (para matar no fim da gravação)."""
    import config as _config
    c = config(cfg)
    exe = _config.claude_cli(cfg)
    if not exe:
        raise RuntimeError("claude.exe não encontrado")
    projetos, memoria = _dirs(cfg)
    cmd = [exe, "-p", prompt(g, contexto, sessao_m, cfg),
           "--output-format", "json",
           "--json-schema", json.dumps(ESQUEMA, ensure_ascii=False),
           "--tools", "Read,Grep,Glob",          # só leitura
           "--allowedTools", "Read,Grep,Glob",   # sem janela: sem isso o pedido de permissão trava
           "--no-session-persistence", "--strict-mcp-config", "--setting-sources", ""]
    if memoria.exists():
        cmd += ["--add-dir", str(memoria)]
    modelo = c.get("modelo") or cfg.get("claude_modelo")
    if modelo:
        cmd += ["--model", modelo]
    if c.get("esforco"):
        cmd += ["--effort", str(c["esforco"])]
    t0 = time.time()
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         cwd=str(projetos), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if guardar_proc:
        guardar_proc(p)
    try:
        out, err = p.communicate(timeout=float(c["timeout_s"]))
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise RuntimeError(f"sem resposta em {c['timeout_s']} s")
    saida = out.decode("utf-8", "replace")
    try:
        dado = json.loads(saida)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude saiu com código {p.returncode} sem JSON: "
                           f"{(saida or err.decode('utf-8', 'replace'))[-300:]}")
    so = dado.get("structured_output")
    if dado.get("is_error") or not isinstance(so, dict):
        raise RuntimeError(f"claude não respondeu: {str(dado.get('result'))[:300]}")
    usos = dado.get("modelUsage") or {}
    principal = max(usos, key=lambda k: usos[k].get("outputTokens", 0)) if usos else None
    return {"sabe": bool(so.get("sabe")), "resposta": str(so.get("resposta") or "").strip(),
            "fonte": str(so.get("fonte") or "").strip(), "segundos": round(time.time() - t0, 1),
            "custo_usd": dado.get("total_cost_usd"), "modelo": principal}


def limpar_resposta(r, cfg):
    """Regra 3 no código: "sabe" sem fonte vira "não sei"; resposta longa é cortada em 2 linhas/240
    caracteres; a fonte que cita arquivo é conferida no disco (`fonte_conferida`)."""
    r = dict(r)
    if r.get("sabe") and not r.get("fonte"):
        r["sabe"] = False
        r["motivo_nao_sei"] = "respondeu sem fonte"
    linhas = [x.strip() for x in (r.get("resposta") or "").splitlines() if x.strip()][:2]
    txt = " ".join(linhas)
    if len(txt) > 240:
        txt = txt[:239].rsplit(" ", 1)[0] + "…"
    r["resposta"] = txt if r.get("sabe") else (txt or "não sei")
    r["fonte_conferida"] = fonte_conferida(r.get("fonte"), cfg) if r.get("sabe") else None
    return r


def registrar(sessao, item):
    """Uma linha em `intervencoes.jsonl` (append, uma escrita por linha)."""
    with open(sessao.caminho(ARQUIVO), "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def ler_registro(sessao_ou_pasta):
    p = pathlib.Path(getattr(sessao_ou_pasta, "pasta", sessao_ou_pasta)) / ARQUIVO
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


# ── a thread ────────────────────────────────────────────────────────────────
class Intervencionista(threading.Thread):
    """Lê o `ao-vivo.md`, filtra, chama o Claude (uma vez por vez) e entrega pelo `entregar(item)`
    — a janela põe isso na fila do Tk, que mostra o cartão. `chamar` é injetável (testes)."""

    def __init__(self, sessao, cfg, entregar=None, chamar=None, relogio=time.monotonic, desde_t=0.0):
        super().__init__(daemon=True, name="intervencionista")
        from sessao import fora_da_medicao
        self.s = sessao
        self.cfg = cfg
        self.c = config(cfg)
        self.entregar = entregar or (lambda item: None)
        self.chamar = chamar or chamar_claude
        self.ctl = Controle(self.c, relogio)
        self.daily = fora_da_medicao(sessao)
        meu = cfg.get("meu_nome", "Pedro")
        self.nomes = [meu, *self.c.get("nomes", [])]
        import daily as _daily
        self.frentes = _daily.frentes_do_config(cfg)
        excluir = [meu, *self.c.get("nomes", []), *sessao.participantes_remotos()]
        self.projetos = [] if self.daily else nomes_de_projeto(cfg, excluir=excluir)
        self.desde_t = float(desde_t or 0.0)     # ligado no meio: o que foi dito antes não dispara
        self.falas = []
        self.offset = 0
        self.pendentes = []
        self._parar = threading.Event()
        self._proc = None
        self.erro = None
        self.respostas = 0                       # cartões mostrados
        self.teto_avisado = False

    @property
    def chamadas(self):
        return self.ctl.chamadas

    def parar(self):
        self._parar.set()
        p = self._proc
        if p is not None and p.poll() is None:
            try:
                p.kill()                         # a reunião acabou: a resposta já não serve
            except OSError:
                pass

    def _guardar(self, p):
        self._proc = p

    def passo(self):
        """Uma rodada: lê as falas novas, filtra, chama se puder. Devolve o item registrado ou None."""
        novas, self.offset = ler_novas(self.s.caminho("ao-vivo.md"), self.offset)
        ini = len(self.falas)
        self.falas += novas
        achados, ainda = reavaliar_pendentes(self.falas, self.pendentes, self.nomes)
        novos, pend = gatilhos(self.falas, ini, self.nomes, self.frentes, self.projetos, self.daily)
        self.pendentes = ainda + pend
        for g in achados + novos:
            if g["t"] >= self.desde_t:
                self.ctl.oferecer(g)
        if not self.falas:
            return None
        if self.ctl.teto() and self.ctl.fila is not None and not self.teto_avisado:
            self.teto_avisado = True
            registrar(self.s, {"evento": "teto", "em": _agora(), "chamadas": self.ctl.chamadas,
                               "t": _ata.fmt_t(self.ctl.fila["t"]), "trecho": self.ctl.fila["trecho"][:200]})
        g = self.ctl.proximo(self.falas[-1]["t"])
        if g is None:
            return None
        try:
            return self._intervir(g)
        finally:
            self.ctl.terminou()

    def _intervir(self, g):
        ctx = [f for f in self.falas[:g["i"] + 1] if g["t"] - f["t"] <= 120][-25:]
        item = {"evento": "intervencao", "em": _agora(), "t": _ata.fmt_t(g["t"]), "t_s": g["t"],
                "gatilho": g["tipo"], "motivo": g["motivo"], "rotulo": g["rotulo"], "trecho": g["trecho"],
                "chamada": self.ctl.chamadas, "versao_prompt": VERSAO_PROMPT}
        try:
            r = limpar_resposta(self.chamar(g, ctx, self.s.m, self.cfg, guardar_proc=self._guardar), self.cfg)
            item.update({"sabe": r["sabe"], "resposta": r["resposta"], "fonte": r.get("fonte") or "",
                         "fonte_conferida": r.get("fonte_conferida"), "segundos": r.get("segundos"),
                         "custo_usd": r.get("custo_usd"), "modelo": r.get("modelo")})
            if r.get("motivo_nao_sei"):
                item["motivo_nao_sei"] = r["motivo_nao_sei"]
            item["mostrado"] = bool(r["sabe"] or self.c.get("mostrar_nao_sei"))
        except Exception as e:
            item.update({"erro": f"{type(e).__name__}: {e}"[:300], "mostrado": False})
            self.erro = None if self._parar.is_set() else f"intervencionista: {item['erro']}"[:200]
        registrar(self.s, item)
        if item["mostrado"] and not self._parar.is_set():
            self.respostas += 1
            self.entregar(item)
        return item

    def run(self):
        while not self._parar.wait(float(self.c["leitura_s"])):
            try:
                self.passo()
            except Exception as e:
                self.erro = f"intervencionista: {type(e).__name__}: {e}"[:200]


def _agora():
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


# ── o cartão (Tk) ───────────────────────────────────────────────────────────
FUNDO, TEXTO, APAGADO = "#1C1C1C", "#F2F2F2", "#9A9A94"
_GWL_EXSTYLE, _WS_EX_NOACTIVATE, _WS_EX_TOOLWINDOW, _WS_EX_TOPMOST = -20, 0x08000000, 0x80, 0x8


def _area_de_trabalho():
    """(esquerda, topo, direita, baixo) da área útil do monitor principal (sem a barra de tarefas)."""
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
        return r.left, r.top, r.right, r.bottom
    return None


def _sem_foco(hwnd):
    """WS_EX_NOACTIVATE + TOOLWINDOW: o Windows não ativa a janela nem ao mostrar nem ao clicar, e ela
    não aparece na barra de tarefas. É o que garante que o cartão nunca tira o foco da chamada."""
    import ctypes
    u = ctypes.windll.user32
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    ex = u.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
    u.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, ex | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW)
    return u.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)


def hwnd_de(top):
    import ctypes
    u = ctypes.windll.user32
    u.GetParent.restype = ctypes.c_void_p
    return u.GetParent(top.winfo_id()) or top.winfo_id()


class Cartao:
    """Um cartão por vez, no canto inferior direito, sempre por cima, sem foco, sem som. Some sozinho
    em `segundos` ou com um clique em qualquer lugar dele."""

    def __init__(self, raiz, item, segundos=25, escala=1.0):
        import tkinter as tk
        p = lambda n: int(round(n * escala))           # noqa: E731
        self.top = top = tk.Toplevel(raiz)
        top.withdraw()
        top.overrideredirect(True)
        top.configure(bg=FUNDO, padx=p(16), pady=p(12))
        cab = f"{ROTULO_GATILHO.get(item.get('gatilho'), 'Ao vivo')} · {item.get('t', '')}"
        tk.Label(top, text=cab, bg=FUNDO, fg=APAGADO, font=("Segoe UI", 8), anchor="w").pack(anchor="w")
        tk.Label(top, text=item.get("resposta") or "", bg=FUNDO, fg=TEXTO, font=("Segoe UI", 10),
                 wraplength=p(340), justify="left", anchor="w").pack(anchor="w", pady=(p(4), p(4)))
        fonte = item.get("fonte") or ""
        if item.get("fonte_conferida") is False:
            fonte = f"{fonte} · fonte não conferida"
        if fonte:
            tk.Label(top, text=fonte, bg=FUNDO, fg=APAGADO, font=("Segoe UI", 8), wraplength=p(340),
                     justify="left", anchor="w").pack(anchor="w")
        top.update_idletasks()
        self.hwnd = hwnd_de(top)
        try:
            self.estilo = _sem_foco(self.hwnd)
        except Exception:
            self.estilo = None
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        area = _area_de_trabalho() or (0, 0, top.winfo_screenwidth(), top.winfo_screenheight())
        top.geometry(f"+{area[2] - w - p(20)}+{area[3] - h - p(20)}")
        top.deiconify()
        top.attributes("-topmost", True)
        for w_ in [top, *top.winfo_children()]:
            w_.bind("<Button-1>", lambda _e: self.fechar())
        self._timer = top.after(int(segundos * 1000), self.fechar)

    def fechar(self):
        try:
            self.top.after_cancel(self._timer)
        except Exception:
            pass
        try:
            self.top.destroy()
        except Exception:
            pass

    def vivo(self):
        try:
            return bool(self.top.winfo_exists())
        except Exception:
            return False
