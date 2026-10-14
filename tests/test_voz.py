# -*- coding: utf-8 -*-
"""Leitura da voz (06/10/2026): número sozinho não diz nada — cada medida vem com o que é,
a faixa, onde você caiu e o que fazer."""
import analise_fala
import raio_x_html

VOZ = {"volume_db": -32.6, "volume_variacao_db": 5.1, "tom_hz": 138, "tom_p10_hz": 104,
       "tom_p90_hz": 190, "entonacao_st": 3.23, "amostra_min": 20.0,
       "blocos": [{"de_min": 0, "volume_db": -32.0, "volume_variacao_db": 5.0, "tom_hz": 130, "tom_p10_hz": 100,
                   "tom_p90_hz": 180, "entonacao_st": 3.6},
                  {"de_min": 150, "volume_db": -33.0, "volume_variacao_db": 5.2, "tom_hz": 150, "tom_p10_hz": 110,
                   "tom_p90_hz": 200, "entonacao_st": 2.9}]}


def test_zonas_e_bordas():
    assert analise_fala._zona("entonacao_st", 1.0)[0] == "monótona"
    assert analise_fala._zona("entonacao_st", 2.2)[0] == "típica"         # borda entra na zona de cima
    assert analise_fala._zona("entonacao_st", 9.0)[0] == "agitada"        # fora da escala = última zona
    assert analise_fala._zona("volume_db", -60)[0] == "muito baixo"       # abaixo da escala = primeira
    assert analise_fala._zona("volume_db", -32.6)[0] == "baixo"


def test_leitura_explica_cada_medida():
    itens, evolucao = analise_fala.leitura_voz(VOZ)
    por = {it["chave"]: it for it in itens}
    assert set(por) == {"entonacao_st", "volume_variacao_db", "volume_db", "tom_hz"}
    assert por["entonacao_st"]["zona"] == "típica" and por["entonacao_st"]["dica"]
    assert por["volume_variacao_db"]["zona"] == "com ênfase"
    assert "não de quanto você fala alto" in por["volume_db"]["o_que_e"], "nível é do microfone, não da voz"
    assert "104 a 190 Hz" in por["tom_hz"]["o_que_e"]
    for it in itens:
        assert it["o_que_e"] and it["unidade"] and it["zonas"]
    # 130 → 150 Hz = 2,5 semitons: subiu; entonação 3,6 → 2,9: caiu
    assert any("subiu 2.5 semitons" in t for t in evolucao)
    assert any("entonação caiu" in t.lower() for t in evolucao)


def test_evolucao_estavel_e_sem_blocos():
    v = dict(VOZ, blocos=[dict(VOZ["blocos"][0]), dict(VOZ["blocos"][0], de_min=30)])
    _, ev = analise_fala.leitura_voz(v)
    assert any("estável" in t for t in ev) and any("se manteve" in t for t in ev)
    assert analise_fala.leitura_voz(dict(VOZ, blocos=[]))[1] == []
    assert analise_fala.leitura_voz(None) == ([], [])


def test_pagina_mostra_regua_e_dica():
    h = raio_x_html._secao_voz(VOZ)
    assert h.count('class="regua"') == 4 and h.count('class="marca"') == 4
    assert "O que fazer:" in h and "Você:</b> típica" in h
    assert "Tom (Hz) por bloco" in h and "Entonação (semitons) por bloco" in h
    assert "st</div>" not in h, "nada de número solto sem leitura"
