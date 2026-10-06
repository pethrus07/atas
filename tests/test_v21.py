# -*- coding: utf-8 -*-
"""v2.1 (06/10/2026) — o que a primeira reunião longa real (3h09 com o Valdir) mostrou:
editar a ata publicava sozinho, o PDF do cliente levava a conversa inteira, prazo "em N dias"
virava lacuna, valores e escopo não tinham lugar, e 3 horas numa passada só ficavam rasas."""
import argparse

from conftest import segs_exemplo
from test_ata import _bruto, _sessao
from test_pipeline import CFG, _gravada, _silencio, falsos  # noqa: F401 (fixture)

import ata
import atas
import estruturar
import pipeline
import render
from sessao import Sessao


# ── segurança ────────────────────────────────────────────────────────────────
def test_editar_ata_nao_publica_sozinho(raiz, falsos):
    s = _gravada(raiz, "cliente")
    pipeline.processar(s, dict(CFG), log=_silencio)
    assert falsos["publicar"] == []
    # render / falantes / confirmar passam por _reaplicar: sem página no ar, nada sobe
    atas._reaplicar(Sessao.abrir(s.pasta), argparse.Namespace(sem_publicar=False))
    assert falsos["publicar"] == [], "editar a ata não pode publicar pela primeira vez"
    assert Sessao.abrir(s.pasta).m["etapas"]["publicacao"]["status"] == "pendente"


def test_entregavel_leva_so_trechos_citados(raiz):
    segs = segs_exemplo() + [{"speaker": "Você", "start": 40.0, "end": 45.0,
                              "text": "Isto aqui é conversa pessoal, totalmente fora de pauta."}]
    s = _sessao(raiz)
    s.m["tipo"] = "cliente"
    a = ata.montar(s, segs, _bruto(), {}, "Pedro")
    cli = render.html(a, segs, cliente=True)
    assert "fora de pauta" not in cli, "fala que nenhum item cita não vai ao cliente"
    assert "Trechos citados" in cli and "release espera a resposta do gateway" in cli
    assert "fora de pauta" in render.html(a, segs), "a ata interna continua com a transcrição inteira"


# ── auditoria ────────────────────────────────────────────────────────────────
def test_prazo_relativo_em_dias_e_semanas():
    r = "2026-10-05"
    assert ata._data_coerente("2026-10-20", "Limite máximo de 15 dias", r)
    assert not ata._data_coerente("2026-10-28", "Limite máximo de 15 dias", r)
    assert ata._data_coerente("2026-10-10", "Eu vou levar uns 4 5 dias", r), "faixa vale o maior"
    assert ata._data_coerente("2026-10-19", "em duas semanas", r)
    assert ata._data_coerente("2026-10-15", "até 15/10", r), "data cheia continua valendo"
    assert not ata._data_coerente("2026-10-16", "até 15/10", r)


def test_decisao_sem_revisao_nao_vira_lacuna(raiz):
    a = ata.montar(_sessao(raiz), segs_exemplo(), _bruto(), {}, "Pedro")
    assert not [l for l in a["lacunas"] if l["falta"] == "data de revisão"]


def test_valores_e_escopo_sao_auditados(raiz):
    b = _bruto()
    b["valores"] = [
        {"descricao": "Resumo ao time", "valor": "R$ 300", "condicao": None, "t": "00:13",
         "citacao": "Eu mando o resumo para o time até sexta-feira à tarde"},
        {"descricao": "Inventado", "valor": "R$ 9.999", "condicao": None, "t": "00:20",
         "citacao": "o cliente aceitou pagar nove mil reais"}]
    b["escopo"] = [{"item": "Revisar os eventos do onboarding", "tema": "Mettria", "t": "00:20",
                    "citacao": "alguém precisa revisar os eventos do onboarding antes da próxima sprint"}]
    b["por_tema"] = [{"tema": "Pagamentos", "resumo": "A release espera o gateway."}]
    a = ata.montar(_sessao(raiz), segs_exemplo(), b, {}, "Pedro")
    assert [v["id"] for v in a["valores"]] == ["V1", "V2"] and a["escopo"][0]["id"] == "S1"
    assert a["valores"][0]["verificado"] is True and a["valores"][1]["verificado"] is False
    h = render.html(a, segs_exemplo())
    assert "Valores" in h and "Escopo e entregas" in h and "Por assunto" in h
    assert "R$ 9.999" not in render.html(a, segs_exemplo(), cliente=True)


# ── reunião longa ────────────────────────────────────────────────────────────
def test_blocos_com_sobreposicao():
    segs = [{"speaker": "Você", "start": float(t), "end": t + 5.0, "text": f"fala {t}"}
            for t in range(0, 6000, 60)]                     # 100 min
    bl = estruturar.blocos(segs, bloco_s=2400, sobra_s=120)
    assert [round(i) for i, _ in bl] == [0, 2400, 4800]
    assert any(s["start"] < 2400 for s in bl[1][1]), "o bloco 2 começa um pouco antes (sobra)"


def test_juntar_blocos_sem_repetir_item():
    d = {"decisao": "Fica R$ 500 por mês", "quem": "Pedro", "contexto": None, "revisar_em": None,
         "revisar_em_dito": None, "t": "40:10", "citacao": "fica 500 por mês e não acumula"}
    d2 = dict(d, t="40:12")                                   # o mesmo item, visto da sobra
    d3 = dict(d, decisao="App gratuito agora", t="1:10:00", citacao="o app não vai ser cobrado agora")
    j = estruturar.juntar([{"decisoes": [d], "falantes": [{"rotulo": "Participante", "nome": None}]},
                           {"decisoes": [d2, d3], "falantes": [{"rotulo": "Participante", "nome": "Valdir"}]}])
    assert len(j["decisoes"]) == 2
    assert j["falantes"][0]["nome"] == "Valdir", "o nome achado num bloco ganha do vazio"


# ── avaliação interna ────────────────────────────────────────────────────────
def test_avaliacao_so_em_reuniao_de_cliente_ou_parresia_longa(raiz):
    import avaliar
    longa = [{"speaker": "Você", "start": 0.0, "end": 1200.0, "text": "x"}]     # 20 min
    curta = [{"speaker": "Você", "start": 0.0, "end": 600.0, "text": "x"}]      # 10 min
    s = _sessao(raiz)
    for tipo, segs, esperado in (("cliente", longa, True), ("parresia", longa, True),
                                 ("pessoal", longa, False), ("carreira", longa, False),
                                 ("cliente", curta, False)):
        s.m["tipo"] = tipo
        assert avaliar.deve_avaliar(s, segs, {}) is esperado, (tipo, len(segs))
    s.m["tipo"] = "cliente"
    assert not avaliar.deve_avaliar(s, longa, {"avaliar": False})


def test_pipeline_gera_avaliacao_com_o_raio_x(raiz, falsos, monkeypatch):
    import avaliar
    recebido = {}

    def falsa(sessao, segs, ata, metricas, cfg, log=print):
        recebido["metricas"] = metricas
        p = sessao.caminho(avaliar.ARQUIVO)
        p.write_text("# Avaliação interna\n", encoding="utf-8")
        return p, {"segundos": 1.0, "custo_usd": 0.0}
    monkeypatch.setattr(avaliar, "avaliar", falsa)
    s = _gravada(raiz, "cliente")
    et = pipeline.processar(s, dict(CFG, avaliar_acima_min=0), log=_silencio)
    assert et["avaliacao"]["status"] == "ok"
    assert recebido["metricas"] and "metas" in recebido["metricas"], "a avaliação usa o Raio-X"
    assert "Avaliação interna" not in s.caminho("entregavel.html").read_text(encoding="utf-8")


def test_temas_do_escopo_alinhados_ao_resumo():
    junto = {"por_tema": [{"tema": "IoT", "resumo": "x"}, {"tema": "Conteúdo", "resumo": "y"}],
             "escopo": [{"item": "Siemens", "tema": "Sistema IoT"}, {"item": "Roteador", "tema": "Hardware IoT"},
                        {"item": "5 vídeos", "tema": "Pacote mensal"}, {"item": "Nome", "tema": "Marca"}]}
    estruturar.alinhar_temas(junto, [{"de": "Sistema IoT", "para": "IoT"}, {"de": "Hardware IoT", "para": "IoT"},
                                     {"de": "Pacote mensal", "para": "Conteúdo"},
                                     {"de": "Marca", "para": "Tema que não existe"}])
    assert [s["tema"] for s in junto["escopo"]] == ["IoT", "IoT", "Conteúdo", "Marca"]


def test_valor_citado_nao_vai_ao_cliente(raiz):
    b = _bruto()
    b["valores"] = [
        {"descricao": "Resumo ao time", "valor": "R$ 300", "condicao": None, "natureza": "combinado",
         "t": "00:13", "citacao": "Eu mando o resumo para o time até sexta-feira à tarde"},
        {"descricao": "Preço visto no Mercado Livre", "valor": "R$ 1.998", "condicao": None, "natureza": "citado",
         "t": "00:20", "citacao": "alguém precisa revisar os eventos do onboarding antes da próxima sprint"}]
    s = _sessao(raiz)
    s.m["tipo"] = "cliente"
    a = ata.montar(s, segs_exemplo(), b, {}, "Pedro")
    assert "R$ 1.998" not in render.html(a, segs_exemplo(), cliente=True)
    interna = render.html(a, segs_exemplo())
    assert "R$ 1.998" in interna and "referência, não acordo" in interna
