# -*- coding: utf-8 -*-
"""Formato da reunião de cliente (14/10/2026): a janela pergunta (opcional, só em cliente), o
sessao.json guarda, `atas.py formato` corrige depois e o Raio-X lê."""
import json

import pytest

import sessao
from sessao import Sessao


def test_criar_guarda_o_formato(raiz):
    s = Sessao.criar("Demo do sistema", "cliente", formato="demo", raiz=raiz)
    assert Sessao.abrir(s.pasta).m["formato"] == "demo"
    s2 = Sessao.criar("Sem formato", "cliente", raiz=raiz)
    assert Sessao.abrir(s2.pasta).m["formato"] is None


def test_formato_invalido(raiz):
    with pytest.raises(ValueError):
        Sessao.criar("x", "cliente", formato="palestra", raiz=raiz)


def test_formato_da_tela_so_vale_em_cliente():
    import app
    assert app.formato_da_tela("cliente", "descoberta") == "descoberta"
    assert app.formato_da_tela("cliente", app.FORMATO_NAO_SEI) is None     # "não sei" = vazio
    assert app.formato_da_tela("parresia", "demo") is None                 # escolha antiga não vaza


@pytest.fixture
def cli(raiz, monkeypatch, tmp_path):
    import analise_fala
    monkeypatch.setattr(sessao, "SALVAS", raiz)
    monkeypatch.setattr(analise_fala, "FALA_DIR", tmp_path / "fala")
    monkeypatch.setattr(analise_fala, "_atualizar_vault", lambda linhas: None)
    import atas
    return atas


def test_cli_formato_corrige_e_refaz_o_raio_x(cli, raiz, capsys):
    from conftest import segs_exemplo
    s = Sessao.criar("Alinhamento", "cliente", raiz=raiz)
    sessao.escrever_json(s.caminho("transcricao.json"), {"segments": segs_exemplo()})
    s.etapa("raio_x", "ok")
    cli.main(["formato", s.id, "descoberta"])
    s = Sessao.abrir(s.pasta)
    assert s.m["formato"] == "descoberta"
    import analise_fala
    linhas = [json.loads(x) for x in (analise_fala.FALA_DIR / "historico.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]
    assert linhas[-1]["formato"] == "descoberta"
    assert "Raio-X refeito" in capsys.readouterr().out
    cli.main(["formato", s.id, "nenhum"])
    assert Sessao.abrir(s.pasta).m["formato"] is None


def test_cli_formato_recusa_valor_errado(cli, raiz):
    s = Sessao.criar("x", "cliente", raiz=raiz)
    with pytest.raises(SystemExit):
        cli.main(["formato", s.id, "palestra"])


def test_raio_x_usa_o_formato_do_sessao_json():
    import analise_fala
    f = analise_fala.faixa_fatia("cliente", "descoberta")
    assert (f["lo"], f["hi"]) == (0.35, 0.50)
