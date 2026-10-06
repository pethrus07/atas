# -*- coding: utf-8 -*-
"""v2.2 (06/10/2026) — tema RYZE escuro em tudo e Raio-X com postura."""
from conftest import segs_exemplo
from test_ata import _bruto, _sessao

import analise_fala
import ata
import render


def test_postura_ignora_negacao_e_frase_curta():
    segs = [{"speaker": "Você", "start": 0, "end": 5, "text": "Não dá pra fazer isso pela assinatura de jeito nenhum."},
            {"speaker": "Você", "start": 6, "end": 9, "text": "Muito simples."},
            {"speaker": "Você", "start": 10, "end": 15, "text": "Isso aí já existe no sistema, é só importar o arquivo."},
            {"speaker": "Você", "start": 16, "end": 20, "text": "A gente faz e eu reviso, com certeza absoluta."}]
    p = analise_fala.postura(segs)
    assert "dá pra fazer" not in p["promessa"], "negação não é promessa"
    assert p["promessa"].get("já existe") == 1 and p["promessa"].get("é só importar") == 1
    textos = [f["texto"] for f in p["frases_revisar"]]
    assert "Muito simples." not in textos and any("já existe" in t for t in textos)
    assert p["eu"] == 1 and p["a_gente"] == 1 and p["sujeito_claro"] == 0.5


def test_pagina_da_reuniao_traz_postura_e_avaliacao(tmp_path):
    segs = [{"speaker": "Você", "start": float(i), "end": i + 4.0, "text": "aí a gente já tem isso, entendeu?"}
            for i in range(0, 600, 10)]
    md = "# Avaliação\n## 3. A negociação\n**Funcionou**\n- escopo fechado\n## 4. Postura\n**Pontos fortes**\n- calmo\n"
    r = analise_fala.processar(segs, "Reunião X", "2026-10-05T10:00", pasta=tmp_path, tipo="cliente",
                               sessao_id="x", vault=False, avaliacao_md=md)
    h = r["pagina"].read_text(encoding="utf-8")
    assert "#0D0D0D" in h and "RYZE" in h and "Uso interno" in h
    assert "Postura" in h and "Frases para revisar" in h and "Metas" in h
    assert "<li>escopo fechado</li>" in h, "a lista da avaliação vira lista (linha em branco inserida)"
    painel = r["dashboard"].read_text(encoding="utf-8")
    assert r["pagina"].name in painel, "o painel leva à página da reunião"


def test_entregavel_escuro_sem_selo_interno(raiz):
    s = _sessao(raiz)
    s.m["tipo"] = "cliente"
    a = ata.montar(s, segs_exemplo(), _bruto(), {}, "Pedro")
    cli = render.html(a, segs_exemplo(), cliente=True)
    assert "#0D0D0D" in cli and "RYZE" in cli and "Uso interno" not in cli
    assert "sem data de revisão" not in render.html(a, segs_exemplo())
