# -*- coding: utf-8 -*-
"""Raio-X calibrado (14/10/2026): cada regra nova com um caso que a regra antiga errava.
Fontes das faixas: RBCS/UFPB 2019 (ritmo de João Pessoa), Gong 2016/2025 (fatia, paciência,
perguntas, monólogo), Arantes/Abralin (entonação), Castro 2014/CoDAS (disfluência), Omena 2003 ("a gente")."""
import json

import analise_fala
import ata
import raio_x_html


def _voce(texto, start=0.0, end=5.0):
    return {"speaker": "Você", "start": start, "end": end, "text": texto}


def _outro(texto, start, end):
    return {"speaker": "Participante", "start": start, "end": end, "text": texto}


# ── 1 · "tá" verbo × marcador × confirmação ─────────────────────────────────────────────────
def test_ta_verbo_nao_e_muleta():
    p, m, o = analise_fala.classificar_palavras(
        "Tá funcionando. O sistema tá pronto. Isso tá. Tá bom. Não tá rodando ainda.")
    assert m.get("tá", 0) == 0, "verbo e concordância não contam como marcador"
    assert o["ta_verbo"] == 5


def test_ta_marcador_e_confirmacao():
    p, m, o = analise_fala.classificar_palavras("Tá, então vamos lá. Tá. Beleza? Tá? Tá ligado, é assim.")
    assert m["tá"] == 2, '"Tá," e "Tá." soltos são marcador'
    assert o["tags"] == 2, '"tá?" e "beleza?" são confirmação, não marcador'
    assert m["tá ligado"] == 1


def test_muleta_pura_separada_de_marcador_e_substantivo():
    p, m, o = analise_fala.classificar_palavras(
        "Aí, tipo assim, o cara falou: esse tipo de coisa, cara, pô, então é exatamente isso, né.")
    assert p == {"aí": 1, "tipo": 1, "cara": 1, "pô": 1}, '"tipo assim" conta uma vez; "o cara"/"esse tipo de" não'
    assert m == {"então": 1, "exatamente": 1, "né": 1}, '"assim" de "tipo assim" não conta de novo'
    assert o["substantivo"] == 2


def test_analisar_mostra_as_duas_taxas_e_a_gente_nao_e_bordao():
    segs = [_voce("aí a gente tá fazendo, tá, então beleza tipo", 0, 5)]
    m = analise_fala.analisar(segs)
    # 9 palavras: puras "aí" e "tipo"; marcadores "tá" (o 2º; o 1º é verbo), "então", "beleza"
    assert m["muleta_pura_por_1000"] == 222.2 and m["marcador_por_1000"] == 333.3
    assert m["ta_verbo"] == 1
    assert "a gente" not in m["bordoes"]
    assert m["versao"] == analise_fala.VERSAO


# ── 4 · confirmação só com "?" ──────────────────────────────────────────────────────────────
def test_confirmacao_so_com_interrogacao():
    segs = [_voce("Entendeu? Tá, beleza. Né. Certo? Tá? Não é?", 0, 60)]
    m = analise_fala.analisar(segs)
    assert m["confirmacoes"] == {"entendeu": 1, "certo": 1, "tá": 1, "não é": 1}
    assert m["conf_total"] == 4


# ── 5 · tomou a vez × apoio ─────────────────────────────────────────────────────────────────
def test_tomou_a_vez_e_apoio():
    segs = [
        _outro("então a gente estava pensando em fazer o seguinte com o estoque", 0.0, 10.0),
        _voce("uhum", 4.0, 4.6),                                         # apoio: curto, o outro segue
        _voce("não, espera, deixa eu te explicar como funciona o estoque aqui", 9.0, 15.0),  # tomou a vez
        _outro("certo, pode falar", 16.5, 18.0),
        _outro("o problema é que a nota fiscal demora muito para sair aqui", 30.0, 40.0),
        _voce("é, mas a nota sai sozinha pelo sistema", 33.0, 36.0),     # sobreposição: o outro não parou
    ]
    r = analise_fala.ritmo_e_turnos(segs)
    assert r["apoio"] == 1 and r["tomou_vez"] == 1
    assert r["interrompeu"] == 3, "o total antigo continua contando todas as sobreposições"
    assert r["tomou_vez_por_10min"] == round(10 * 1 / (40 / 60), 2)


# ── 7c · perguntas abertas × sim/não ────────────────────────────────────────────────────────
def test_perguntas_abertas_e_fechadas():
    assert analise_fala.pergunta_aberta("Como vocês fazem isso hoje?")
    assert analise_fala.pergunta_aberta("Entendi. E por que trocaram de sistema?")
    assert analise_fala.pergunta_aberta("Me conta como é o fechamento do mês?")
    assert not analise_fala.pergunta_aberta("Isso funciona pra você?")
    assert not analise_fala.pergunta_aberta("Vocês usam planilha?")
    segs = [_voce("Quanto custa hoje o frete?", 0, 3), _voce("Vocês usam planilha?", 4, 6),
            _voce("Faz sentido, entendeu?", 7, 9)]
    r = analise_fala.ritmo_e_turnos(segs)
    assert (r["perguntas_abertas"], r["perguntas_fechadas"], r["perguntas_reais"]) == (1, 1, 2)
    assert r["exemplos_fechadas"][0]["texto"] == "Vocês usam planilha?"


# ── 7a · sílabas por segundo com frase conhecida ────────────────────────────────────────────
def test_silabas_frase_conhecida():
    # O / Bra-sil / é / um / pa-ís / mui-to / gran-de = 11 sílabas
    assert analise_fala.silabas("O Brasil é um país muito grande") == 11
    assert analise_fala.silabas("pão mãe coisa queijo") == 1 + 1 + 2 + 2, "ditongo e nasal contam 1"
    assert analise_fala.silabas("saúde poeta") == 3 + 3, "hiato com acento ou entre fortes conta 2"


def test_silabas_por_segundo_e_articulacao():
    # duas falas do mesmo turno com 1 s de lacuna: elocução conta a lacuna, articulação não
    segs = [_voce("O Brasil é um país muito grande", 0.0, 2.0),
            _voce("O Brasil é um país muito grande", 3.0, 5.0)]
    r = analise_fala.ritmo_e_turnos(segs)
    assert r["silabas"] == 22
    assert r["silabas_por_s"] == round(22 / 5.0, 2)
    assert r["articulacao_sil_s"] == round(22 / 4.0, 2)


# ── 7b · paciência e atropelo ───────────────────────────────────────────────────────────────
def test_atropelo():
    segs = [_outro("pergunta um", 0, 2), _voce("resposta", 2.1, 3),       # 0,1 s: atropelo
            _outro("pergunta dois", 5, 7), _voce("resposta", 7.8, 9)]     # 0,8 s: paciente
    r = analise_fala.ritmo_e_turnos(segs)
    assert r["atropelo_pct"] == 50 and r["resposta_media_s"] == 0.45


# ── 7d · compromisso com dono e prazo ───────────────────────────────────────────────────────
def test_compromisso_com_dono_e_prazo():
    segs = [_voce("Eu te mando a proposta até sexta.", 0, 3),
            _voce("A gente vai revisar isso.", 10, 12),
            _voce("Vou te mostrar a tela agora.", 20, 22),                 # narração: não é compromisso
            _voce("Vou ser bem sincero com você.", 30, 32),                # sem verbo de entrega
            _voce("Você vai me passar os acessos amanhã.", 40, 42),
            _voce("Não vou cobrar essa parte.", 50, 52),                   # negação
            _voce("Fica pronto.", 60, 61),
            _voce("O Valter vai mandar o logo.", 70, 72)]
    c = analise_fala.compromissos(segs, ["Valter"])
    assert c["total"] == 5
    assert c["completos"] == 2, "eu + até sexta; você + amanhã"
    faltas = {x["texto"]: x["falta"] for x in c["revisar"]}
    assert faltas["A gente vai revisar isso."] == ["dono", "prazo"]
    assert faltas["Fica pronto."] == ["dono", "prazo"]
    assert faltas["O Valter vai mandar o logo."] == ["prazo"]
    assert all(isinstance(x["t"], int) for x in c["revisar"])


def test_prazo_dito_na_fala_seguinte():
    segs = [_voce("Eu vou te mandar o orçamento.", 0, 3), _voce("Até quinta-feira.", 5, 6)]
    assert analise_fala.compromissos(segs)["completos"] == 1


def test_expressao_de_prazo_reaproveita_a_auditoria():
    assert ata.expressao_de_prazo("te mando até sexta") == "ate sexta"
    assert ata.expressao_de_prazo("entrego em 15 dias") == "em 15 dias"
    assert ata.expressao_de_prazo("sai até 15/10") == "15/10"
    assert ata.expressao_de_prazo("só vou entregar daqui dois dias") == "daqui dois dias"
    assert ata.expressao_de_prazo("na segunda versão") is None, "ordinal não é dia da semana"
    assert ata.expressao_de_prazo("vou fazer isso") is None
    # a auditoria continua com o mesmo prazo relativo
    assert ata._data_coerente("2026-10-20", "Limite máximo de 15 dias", "2026-10-05")


# ── 6 · fatia de fala por tipo ──────────────────────────────────────────────────────────────
def test_faixa_de_fatia_por_tipo_e_formato():
    assert analise_fala.faixa_fatia("cliente", "descoberta")["hi"] == 0.50
    assert analise_fala.faixa_fatia("cliente", "demo")["lo"] == 0.45
    assert analise_fala.faixa_fatia("cliente", None, 2)["hi"] == 0.55
    f = analise_fala.faixa_fatia("cliente", None, 4)
    assert (f["lo"], f["hi"]) == (0.19, 0.38), "4 pessoas: 1/4 de 0,75× a 1,5×"
    assert analise_fala.faixa_fatia("parresia", None, 2)["lo"] is None, "interna: só informa"
    assert analise_fala.numero_de_falantes([], ["Valter", "Tadeu"]) == 3


# ── 8 · limiar de 1.000 palavras ────────────────────────────────────────────────────────────
def _reuniao(n_falas, texto="aí a gente vai ver isso com calma, tá, então beleza agora"):
    segs = []
    for i in range(n_falas):
        segs.append(_voce(texto, i * 20.0, i * 20.0 + 5))
        segs.append(_outro("certo, faz sentido, pode seguir com isso aí então", i * 20.0 + 6, i * 20.0 + 19.2))
    return segs


def test_amostra_pequena_nao_julga_meta(tmp_path):
    m = analise_fala.calcular(_reuniao(20), "2026-10-14T10:00", "x", pasta=tmp_path, tipo="cliente")
    assert m["palavras_voce"] < 1000
    assert m["metas"] and all(ok is None for *_, ok in m["metas"]), "nenhuma meta julgada"
    assert all("amostra pequena" in meta for _, _, meta, _ in m["metas"])
    it = next(x for x in m["leitura"] if x["chave"] == "conf_por_min")
    assert it["status"] == "pequena" and "Amostra pequena" in it["onde"]
    m2 = analise_fala.calcular(_reuniao(120), "2026-10-14T10:00", "x", pasta=tmp_path, tipo="cliente")
    assert m2["palavras_voce"] >= 1000 and all(ok is not None for *_, ok in m2["metas"])


def test_toda_medida_vem_com_leitura(tmp_path):
    m = analise_fala.calcular(_reuniao(120), "2026-10-14T10:00", "x", pasta=tmp_path, tipo="cliente")
    for it in m["leitura"]:
        assert it["o_que_e"] and it["faixa"] and it["fonte"] and it["onde"] and it["mediana_txt"], it["chave"]
    chaves = {it["chave"] for it in m["leitura"]}
    assert {"muleta_pura_por_1000", "marcador_por_1000", "ai_por_1000", "silabas_por_s", "articulacao_sil_s",
            "tomou_vez_por_10min", "resposta_media_s", "perguntas_abertas"} <= chaves
    assert "a_gente_por_1000" not in chaves, '"a gente" não é mais meta'


# ── 1 + 2 · meta da muleta pura e degrau do "aí" pelos dados ─────────────────────────────────
def _hist(pasta, ais, puras=None, palavras=2000):
    linhas = []
    for i, ai in enumerate(ais):
        m = {"palavras_voce": palavras, "share_fala": 0.4, "conf_por_min": 1, "dur_min": 60,
             "muletas_por_1000": 50, "muletas": {"aí": round(ai * palavras / 1000)},
             "postura": {"ai_por_1000": ai}}
        if puras:
            m.update({"versao": 3, "muleta_pura_por_1000": puras[i]})
        linhas.append({"id": f"r{i}", "data": f"2026-09-{10 + i:02d}T10:00", "titulo": "x", "metrics": m})
    (pasta / "historico.jsonl").write_text("\n".join(json.dumps(r) for r in linhas), encoding="utf-8")


def test_degrau_do_ai_por_dados(tmp_path):
    def limite():
        m = analise_fala.calcular(_reuniao(120), "2026-10-14T10:00", "nova", pasta=tmp_path, tipo="cliente")
        return next(x for x in m["leitura"] if x["chave"] == "ai_por_1000")["faixa"]
    _hist(tmp_path, [30, 28, 25, 24, 22])
    assert limite().startswith("até 20 (degrau 1")
    _hist(tmp_path, [30, 19, 18, 20, 17, 16])        # as últimas 5: mediana 18 ≤ 20
    assert limite().startswith("até 15 (degrau 2")


def test_meta_da_muleta_pura_e_mediana_das_ultimas_5(tmp_path):
    _hist(tmp_path, [20] * 6, puras=[90, 40, 30, 50, 20, 10])       # últimas 5: 40 30 50 20 10 → mediana 30
    m = analise_fala.calcular(_reuniao(120), "2026-10-14T10:00", "nova", pasta=tmp_path, tipo="cliente")
    it = next(x for x in m["leitura"] if x["chave"] == "muleta_pura_por_1000")
    assert it["faixa"].startswith("até 24 (mediana das últimas 5, 30, menos 20%)")
    assert it["mediana"] == 30
    _hist(tmp_path, [20] * 2, puras=[40, 20])
    m = analise_fala.calcular(_reuniao(120), "2026-10-14T10:00", "nova", pasta=tmp_path, tipo="cliente")
    it = next(x for x in m["leitura"] if x["chave"] == "muleta_pura_por_1000")
    assert "só há 2 reuniões" in it["faixa"], "com menos de 5, usa as que há e diz isso"


def test_historico_antigo_continua_legivel(tmp_path):
    # linha da v2 (sem versao, sem muleta pura, sem ritmo novo) entra na base, aproximada
    _hist(tmp_path, [20] * 3)
    m = analise_fala.calcular(_reuniao(120), "2026-10-14T10:00", "nova", pasta=tmp_path, tipo="cliente")
    it = next(x for x in m["leitura"] if x["chave"] == "muleta_pura_por_1000")
    assert "histórico antigo" in it["faixa"]
    assert analise_fala.valor_de({"conf_por_min": 2.0}, "conf_por_min") == (None, False), \
        "confirmação antiga contava 'tá,' e não entra na mediana"
    linhas = analise_fala.ler_historico(tmp_path)
    h = raio_x_html.painel(linhas)                      # o painel lê linha antiga sem quebrar
    assert "Muleta pura" in h


def test_pagina_mostra_leitura_e_compromissos(tmp_path):
    segs = _reuniao(120) + [_voce("A gente vai revisar o contrato.", 5000, 5003)]
    r = analise_fala.processar(segs, "Reunião Y", "2026-10-14T10:00", pasta=tmp_path, tipo="cliente",
                               sessao_id="y", vault=False)
    h = r["pagina"].read_text(encoding="utf-8")
    assert "Leitura de cada medida" in h and "Fonte:" in h and "Comparação:" in h
    assert "Compromissos sem dono ou sem prazo" in h and "revisar o contrato" in h
    assert "Muletas puras" in h and "Marcadores de discurso" in h
