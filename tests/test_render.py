# -*- coding: utf-8 -*-
"""A marca segue o tipo, o entregável só leva o que foi verificado, e nada escapa sem escape."""
from conftest import segs_exemplo
from test_ata import _bruto, _sessao

import ata
import render


def _a(raiz, tipo="parresia"):
    s = _sessao(raiz)
    s.m["tipo"] = tipo
    return ata.montar(s, segs_exemplo(), _bruto(), {}, "Pedro")


def test_interna_nao_tem_marca_ryze(raiz):
    h = render.html(_a(raiz), segs_exemplo())
    assert "RYZE" not in h and "ryzecode" not in h
    assert "Parresia (interna)" in h
    assert "Migrar tudo para Kubernetes" in h and "origem não localizada" in h


def test_entregavel_de_cliente(raiz):
    a = _a(raiz, "cliente")
    h = render.html(a, segs_exemplo(), cliente=True)
    assert "RYZE" in h
    assert "Kubernetes" not in h, "item sem origem não vai ao cliente"
    assert "Lacunas a fechar" not in h


def test_nome_nao_confirmado_nao_vai_ao_cliente(raiz):
    a = _a(raiz, "cliente")
    for p in a["participantes"]:
        if p["rotulo"] == "Participante":
            p["confirmado"] = False
    h = render.html(a, segs_exemplo(), cliente=True)
    assert "Ricardo?" not in h
    assert ">Participante<" in h or "Participante</" in h
    assert "Ricardo?" in render.html(a, segs_exemplo())


def test_escape_de_html_na_transcricao(raiz):
    segs = segs_exemplo()
    segs[0]["text"] = "<script>alert(1)</script> vamos revisar o módulo de pagamentos"
    h = render.html(_a(raiz), segs)
    assert "<script>" not in h and "&lt;script&gt;" in h


def test_impressao_abre_tudo(raiz):
    a = _a(raiz)
    assert "<details class=\"transc\">" in render.html(a, segs_exemplo())
    assert "<details class=\"transc\" open>" in render.html(a, segs_exemplo(), impressao=True)


def test_markdown_tem_ids_e_transcricao(raiz):
    md = render.markdown(_a(raiz), segs_exemplo())
    assert "**D1**" in md and "| E1 |" in md and "## Transcrição" in md
    assert "**[00:05] Ricardo:**" in md


def test_pendente_avisa_para_rodar_ata(raiz):
    s = _sessao(raiz)
    a = ata.base(s, segs_exemplo(), "Pedro")
    assert "/ata" in render.html(a, segs_exemplo())


def test_dono_com_nome_nao_confirmado_nao_vaza(raiz):
    import copy
    segs = copy.deepcopy(segs_exemplo())
    for s in segs:
        if s["speaker"] == "Participante":
            s["speaker"] = "Participante 1"
    b = _bruto()
    b["falantes"] = [{"rotulo": "Participante 1", "nome": "Carlos Souza", "evidencia": "x"}]
    b["encaminhamentos"][1]["dono"] = "Carlos Souza"
    b["resumo"] = "Carlos Souza pediu a revisão."
    s = _sessao(raiz, remotos=("Carlos Souza", "Outro"))
    s.m["tipo"] = "cliente"
    a = ata.montar(s, segs, b, {}, "Pedro")
    h = render.html(a, segs, cliente=True)
    assert "Carlos Souza" not in h, "nome deduzido e não confirmado foi ao cliente"
    assert "Carlos Souza?" in render.html(a, segs)
    for p in a["participantes"]:
        p["confirmado"] = True
    assert "Carlos Souza" in render.html(a, segs, cliente=True)
