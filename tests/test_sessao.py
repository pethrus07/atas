# -*- coding: utf-8 -*-
import os
import time

import pytest

import sessao
from sessao import Batedor, Sessao


def test_criar_e_reabrir(raiz):
    s = Sessao.criar("Alinhamento PO — Ricardo", "parresia", "po", ["Ricardo", " "], raiz=raiz)
    assert s.id.endswith("_alinhamento-po-ricardo")
    assert s.m["participantes"] == ["Ricardo"]
    s2 = Sessao.abrir(s.id, raiz=raiz)
    assert s2.m["tipo"] == "parresia" and s2.m["estado"] == "preparando"


def test_tipo_invalido(raiz):
    with pytest.raises(ValueError):
        Sessao.criar("x", "empresa", raiz=raiz)


def test_mesmo_minuto_nao_colide(raiz):
    a = Sessao.criar("Reunião", "pessoal", raiz=raiz)
    b = Sessao.criar("Reunião", "pessoal", raiz=raiz)
    assert a.id != b.id and b.id.endswith("-2")


def test_json_atomico_nao_deixa_tmp(raiz):
    s = Sessao.criar("x", "pessoal", raiz=raiz)
    s.etapa("transcricao", "ok", "detalhe")
    assert not list(s.pasta.glob("*.tmp"))
    assert Sessao.abrir(s.pasta).status_etapa("transcricao") == "ok"


def test_orfa_pela_batida(raiz):
    s = Sessao.criar("x", "pessoal", raiz=raiz)
    s.estado("gravando")
    s.bater()
    assert not s.orfa()                          # batida recente = vivo
    velho = time.time() - sessao.ORFA_APOS_S - 5
    os.utime(s.pasta / ".batida", (velho, velho))
    assert s.orfa()                              # batida parada = gravador morreu
    assert [o.id for o in sessao.orfas(raiz)] == [s.id]


def test_batedor_mantem_viva(raiz, monkeypatch):
    monkeypatch.setattr(sessao, "BATIDA_S", 0.05)
    s = Sessao.criar("x", "pessoal", raiz=raiz)
    s.estado("processando")
    with Batedor(s):
        time.sleep(0.2)
        assert s.segundos_desde_batida() < 1
    assert not s.orfa()


def test_pronta_nunca_e_orfa(raiz):
    s = Sessao.criar("x", "pessoal", raiz=raiz)
    s.estado("pronto")
    assert not s.orfa()
