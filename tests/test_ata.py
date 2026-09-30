# -*- coding: utf-8 -*-
"""R3 — nada inventado: a auditoria confere cada item contra a transcrição."""
import copy

from conftest import segs_exemplo

import ata
from sessao import Sessao


def _bruto():
    return {
        "falantes": [{"rotulo": "Participante", "nome": "Ricardo", "evidencia": "[00:05] Bom dia Pedro"}],
        "contexto": "Revisão do módulo de pagamentos.",
        "resumo": "A release espera o gateway.",
        "temas": ["pagamentos"],
        "decisoes": [
            {"decisao": "A release espera a resposta do gateway", "quem": "Ricardo", "contexto": None,
             "revisar_em": None, "revisar_em_dito": None, "t": "00:05",
             "citacao": "Ficou decidido que a release espera a resposta do gateway"},
            {"decisao": "Migrar tudo para Kubernetes", "quem": "Ricardo", "contexto": None,
             "revisar_em": None, "revisar_em_dito": None, "t": "00:20",
             "citacao": "vamos migrar toda a infraestrutura para Kubernetes em outubro"},
        ],
        "encaminhamentos": [
            {"acao": "Mandar o resumo ao time", "dono": "Pedro", "prazo": "2026-10-02",
             "prazo_dito": "até sexta-feira", "t": "00:13",
             "citacao": "Eu mando o resumo para o time até sexta-feira à tarde"},
            {"acao": "Revisar eventos do onboarding", "dono": None, "prazo": "2026-10-10",
             "prazo_dito": "dia 10", "t": "00:20",
             "citacao": "alguém precisa revisar os eventos do onboarding antes da próxima sprint"},
            {"acao": "Falar com o Jurídico", "dono": "Marta", "prazo": None, "prazo_dito": None,
             "t": "00:00", "citacao": "vamos revisar o módulo de pagamentos do Mettria hoje"},
        ],
        "perguntas_abertas": [],
        "riscos": [],
    }


def _sessao(raiz, remotos=("Ricardo",)):
    s = Sessao.criar("Revisão", "parresia", "mettria", list(remotos), raiz=raiz)
    s.m["inicio"] = "2026-09-30T14:00:00-03:00"
    return s


def test_citacao_inventada_nao_e_verificada(raiz):
    a = ata.montar(_sessao(raiz), segs_exemplo(), _bruto(), {"por": "teste"}, "Pedro")
    d1, d2 = a["decisoes"]
    assert d1["verificado"] is True and d1["id"] == "D1"
    assert d2["verificado"] is False
    assert {"ref": "D2", "falta": "trecho de origem (não localizado)"} in a["lacunas"]


def test_prazo_sem_expressao_dita_vira_lacuna(raiz):
    a = ata.montar(_sessao(raiz), segs_exemplo(), _bruto(), {}, "Pedro")
    e1, e2, _ = a["encaminhamentos"]
    assert e1["prazo"] == "2026-10-02"                     # "até sexta-feira" foi dito
    assert e2["prazo"] is None                             # "dia 10" nunca foi dito
    assert any("removido" in p for p in e2["problemas"])
    assert {"ref": "E2", "falta": "prazo"} in a["lacunas"]
    assert {"ref": "E2", "falta": "dono"} in a["lacunas"]


def test_dono_desconhecido_e_anotado(raiz):
    a = ata.montar(_sessao(raiz), segs_exemplo(), _bruto(), {}, "Pedro")
    e3 = a["encaminhamentos"][2]
    assert any("Marta" in p for p in e3["problemas"])


def test_timestamp_errado_e_corrigido(raiz):
    b = _bruto()
    b["decisoes"][0]["t"] = "00:40"
    a = ata.montar(_sessao(raiz), segs_exemplo(), b, {}, "Pedro")
    assert a["decisoes"][0]["t"] == "00:05"


def test_campo_manual_nao_e_removido(raiz):
    s = _sessao(raiz)
    a = ata.montar(s, segs_exemplo(), _bruto(), {}, "Pedro")
    e2 = a["encaminhamentos"][1]
    e2["prazo"] = "2026-10-15"
    e2["manual"] = ["prazo"]
    ata.auditar(a, segs_exemplo())
    assert e2["prazo"] == "2026-10-15"


def test_participante_unico_informado_e_confirmado(raiz):
    a = ata.montar(_sessao(raiz), segs_exemplo(), _bruto(), {}, "Pedro")
    nomes = {p["rotulo"]: (p["nome"], p["confirmado"]) for p in a["participantes"]}
    assert nomes == {"Você": ("Pedro", True), "Participante": ("Ricardo", True)}


def test_nome_deduzido_fica_a_confirmar(raiz):
    segs = copy.deepcopy(segs_exemplo())
    for s in segs:
        if s["speaker"] == "Participante":
            s["speaker"] = "Participante 1"
    b = _bruto()
    b["falantes"] = [{"rotulo": "Participante 1", "nome": "Ricardo", "evidencia": "x"}]
    a = ata.montar(_sessao(raiz, remotos=("Ricardo", "Guilherme")), segs, b, {}, "Pedro")
    p1 = [p for p in a["participantes"] if p["rotulo"] == "Participante 1"][0]
    assert p1["nome"] == "Ricardo" and p1["confirmado"] is False
    assert {"ref": "Participante 1", "falta": "confirmar que é Ricardo"} in a["lacunas"]


def test_decisao_no_formato_do_log(raiz):
    a = ata.montar(_sessao(raiz), segs_exemplo(), _bruto(), {}, "Pedro")
    log = ata.decisao_para_log(a, a["decisoes"][0])
    # mesmas chaves de qa-parresia/rotinas/decisoes.jsonl, mais a origem
    assert {"data", "decisao", "contexto", "quem", "destrava", "revisar_em"} <= set(log)
    assert log["data"] == "2026-09-30" and log["origem"]["ata"] == a["id"]


def test_falas_juntam_trechos_do_mesmo_falante():
    segs = [{"speaker": "Você", "start": 0, "end": 2, "text": "a"},
            {"speaker": "Você", "start": 2.5, "end": 4, "text": "b"},
            {"speaker": "Participante", "start": 4.2, "end": 5, "text": "c"}]
    f = ata.falas(segs)
    assert [x["text"] for x in f] == ["a b", "c"]
    assert ata.transcricao_texto(segs).splitlines()[0] == "[00:00] Você: a b"


# ── achados da revisão adversarial de 30/09/2026 ──
def _um_item(raiz, **campos):
    b = _bruto()
    it = {"acao": "x", "dono": None, "prazo": None, "prazo_dito": None, "t": "00:13",
          "citacao": "Eu mando o resumo para o time até sexta-feira à tarde"}
    it.update(campos)
    b["encaminhamentos"] = [it]
    return ata.montar(_sessao(raiz), segs_exemplo(), b, {}, "Pedro")["encaminhamentos"][0]


def test_prazo_inventado_colado_por_reticencias(raiz):
    e = _um_item(raiz, citacao="Eu mando o resumo para o time ... até dia 20",
                 prazo="2026-10-20", prazo_dito="até dia 20")
    assert e["verificado"] is False and e["prazo"] is None


def test_expressao_sem_limite_de_palavra_nao_casa(raiz):
    e = _um_item(raiz, prazo="2026-10-01", prazo_dito="sexta")      # "sexta" existe; 01/10 é quinta
    assert e["prazo"] is None
    e = _um_item(raiz, dono="Mana")                                   # não casa em "semana"
    assert any("Mana" in p for p in e["problemas"])


def test_data_convertida_e_conferida(raiz):
    assert _um_item(raiz, prazo="2026-10-02", prazo_dito="até sexta-feira")["prazo"] == "2026-10-02"
    assert _um_item(raiz, prazo="2027-10-02", prazo_dito="até sexta-feira")["prazo"] is None


def test_citacao_pedaco_de_palavra_nao_casa(raiz):
    e = _um_item(raiz, citacao="ando o resumo para o time")         # pedaço de "mando"
    assert e["verificado"] is False
