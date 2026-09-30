# -*- coding: utf-8 -*-
"""
Traz as atas de antes da v2 (arquivos soltos em atas-salvas/) para o formato de sessão.

Antes: atas-salvas/2026-09-24_1142_alinhamento valter 24_09.md (+ .html + .pdf)
Depois: atas-salvas/2026-09-24_1142_alinhamento-valter-24-09/
            sessao.json (legado: true) · transcricao.json · legado.md/.html/.pdf

Não há áudio dessas reuniões — o `finally` do run.py antigo apagava sempre. O que
se recupera é a transcrição, parseada do backup .md (`**[MM:SS] Falante:** texto`;
MM passa de 59 em reunião longa). Tipo e projeto vêm de `legado-classificacao.json`
(em atas-salvas/, fora do git porque tem nome de cliente); sem ele, ficam "pessoal"
e em branco, marcados como não classificados.
"""
import datetime as _dt
import json
import pathlib
import re
import shutil

from sessao import SALVAS, SCHEMA_SESSAO, Sessao, escrever_json, slug

_LINHA = re.compile(r"^\*\*\[(\d+):(\d{2})\] ([^:*]+):\*\*\s?(.*)$")
_NOME = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_(.+)\.md$")


def parse_md(texto):
    titulo, link, segs = None, None, []
    for ln in texto.splitlines():
        if titulo is None and ln.startswith("# "):
            titulo = ln[2:].strip()
        elif ln.startswith("Link: "):
            link = ln[6:].strip()
        else:
            m = _LINHA.match(ln)
            if m:
                ini = int(m.group(1)) * 60 + int(m.group(2))
                segs.append({"speaker": m.group(3).strip(), "start": float(ini),
                             "end": float(ini), "text": m.group(4).strip()})
    # o .md antigo não guardava o fim do trecho: usa o início do próximo
    for a, b in zip(segs, segs[1:]):
        a["end"] = max(a["start"] + 0.5, min(b["start"], a["start"] + 30))
    if segs:
        segs[-1]["end"] = segs[-1]["start"] + 5
    return titulo, link, segs


def importar(raiz=None, classificacao=None, log=print):
    raiz = pathlib.Path(raiz) if raiz else SALVAS
    cls_path = raiz / "legado-classificacao.json"
    if classificacao is None and cls_path.exists():
        classificacao = json.loads(cls_path.read_text(encoding="utf-8"))
    classificacao = classificacao or {}
    feitos = []
    for md in sorted(raiz.glob("*.md")):
        m = _NOME.match(md.name)
        if not m:
            continue
        titulo, link, segs = parse_md(md.read_text(encoding="utf-8"))
        titulo = titulo or m.group(3)
        quando = _dt.datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H%M").astimezone()
        sid = f"{m.group(1)}_{m.group(2)}_{slug(titulo)}"
        pasta = raiz / sid
        if (pasta / "sessao.json").exists():
            continue
        pasta.mkdir(exist_ok=True)
        c = classificacao.get(md.stem, {})
        manifest = {
            "schema": SCHEMA_SESSAO, "id": sid, "titulo": titulo,
            "tipo": c.get("tipo", "pessoal"), "projeto": c.get("projeto", ""),
            "participantes": c.get("participantes", []),
            "criado": quando.isoformat(timespec="seconds"),
            "inicio": quando.isoformat(timespec="seconds"), "fim": None,
            "estado": "pronto", "legado": True,
            "classificacao": "inferida" if c else "nenhuma",
            "dispositivos": {}, "audio": {"sr": 16000, "duracao_s": segs[-1]["end"] if segs else 0},
            "etapas": {"captura": {"status": "ok", "detalhe": "gravação anterior à v2"},
                       "transcricao": {"status": "ok", "detalhe": "importada do backup .md"}},
            "avisos": ["reunião anterior à v2: sem áudio, fim dos trechos aproximado"],
        }
        if link:
            manifest["publicacao"] = {"url": link, "legado": True}
        escrever_json(pasta / "transcricao.json", {"segments": segs, "info": {"legado": True}})
        escrever_json(pasta / "sessao.json", manifest)
        for ext in (".md", ".html", ".pdf"):
            origem = md.with_suffix(ext)
            if origem.exists():
                shutil.move(str(origem), str(pasta / f"legado{ext}"))
        feitos.append(sid)
        log(f"  importada: {sid} ({len(segs)} trechos)")
    return feitos


def sessao_legada(sid, raiz=None):
    return Sessao.abrir(sid, raiz)
