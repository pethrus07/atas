# -*- coding: utf-8 -*-
"""Daily da Parresia (19/10/2026): fora de toda medição (garantido no código), formato por tipo,
ata atas/daily@1 (card conferido, menção não tratada, rodada) e a busca `atas.py daily`."""
import hashlib
import json
import pathlib

import pytest

import analise_fala
import ata
import avaliar
import daily
import entregavel
import estruturar
import pipeline
import render
import sessao
import transcribe
from sessao import ForaDaMedicao, Sessao

_AVALIAR = avaliar.avaliar          # o original (a fixture troca por um que falha se for chamado)
CFG = {"meu_nome": "Pedro", "estruturar": True, "audio_reter_dias": 30, "avaliar": True,
       "avaliar_acima_min": 0, "daily_equipe": ["Otávio", "Rogério", "Caio", "Augusto", "Pedro"],
       "frentes_rastreadas": [{"nome": "Frota WP", "palavras": ["frota", "MainWP"],
                               "cards": ["SUP-953", "SUP-955", "SUP-957", "SUP-959"]}]}


def segs_daily():
    return [
        {"speaker": "Participante 1", "start": 0.0, "end": 5.0,
         "text": "Bom dia pessoal, vamos começar a daily. Rogério, e você?"},
        {"speaker": "Participante 2", "start": 6.0, "end": 30.0,
         "text": "Ontem eu terminei a revisão dos plugins do SUP 953 na frota, e hoje sigo com o MainWP dos servidores."},
        {"speaker": "Participante 1", "start": 31.0, "end": 35.0, "text": "Show. Fala, Caio."},
        {"speaker": "Participante 3", "start": 37.0, "end": 60.0,
         "text": "Eu fechei o deploy do Lumen e estou travado esperando o acesso do Augusto ao servidor novo."},
        {"speaker": "Participante 1", "start": 62.0, "end": 66.0,
         "text": "Pedro, você consegue validar o card 955 hoje à tarde para a gente fechar?"},
        {"speaker": "Você", "start": 67.0, "end": 72.0, "text": "Consigo sim, valido hoje à tarde e te aviso no grupo."},
        {"speaker": "Participante 2", "start": 200.0, "end": 210.0,
         "text": "Ah, e sobre o 957 eu ainda não mexi em nada, fica para amanhã cedo."},
        {"speaker": "Participante 3", "start": 300.0, "end": 310.0,
         "text": "Lembrando que o deploy do Lumen precisa de revisão antes de sexta, pessoal."},
    ]


def bruto_daily():
    return {
        "falantes": [{"rotulo": "Participante 2", "nome": "Rogério", "evidencia": "[00:00] Rogério, e você?"},
                     {"rotulo": "Participante 3", "nome": "Caio", "evidencia": "[00:31] Fala, Caio."}],
        "contexto": "Daily da equipe.",
        "resumo": "Rogério revisou plugins da frota; Caio travado no acesso.",
        "pessoas": [
            {"nome": "Rogério", "rotulo": "Participante 2",
             "fez": [{"item": "Revisou os plugins do SUP-953", "card": "SUP-953", "t": "00:06",
                      "citacao": "eu terminei a revisão dos plugins do SUP 953 na frota"}],
             "vai_fazer": [{"item": "MainWP dos servidores", "card": "SUP-959", "t": "00:06",
                            "citacao": "hoje sigo com o MainWP dos servidores"}],
             "travado": []},
            {"nome": "Caio", "rotulo": "Participante 3", "fez": [
                {"item": "Fechou o deploy do Lumen", "card": None, "t": "00:37",
                 "citacao": "Eu fechei o deploy do Lumen e estou travado"}],
             "vai_fazer": [],
             "travado": [{"item": "Esperando acesso do Augusto", "card": "SUP-953", "t": "05:00",
                          "citacao": "o deploy do Lumen precisa de revisão antes de sexta"}]},
        ],
        "com_voce": [{"o_que": "Validar o card 955 hoje à tarde", "quem": "Participante 1", "card": "SUP-955",
                      "frente": "Frota WP", "tipo": "pedido", "t": "01:02",
                      "citacao": "Pedro, você consegue validar o card 955 hoje à tarde"}],
        "decisoes": [],
        "encaminhamentos": [{"acao": "Validar o card 955", "dono": "Pedro", "prazo": None, "prazo_dito": None,
                             "t": "01:07", "citacao": "valido hoje à tarde e te aviso no grupo"}],
    }


def _daily(raiz, remotos=("Mauro",), titulo="Daily"):
    s = Sessao.criar(titulo, "parresia", "", list(remotos), raiz=raiz, formato="daily")
    s.m["inicio"] = "2026-10-19T09:00:00-03:00"
    s.salvar()
    return s


def _foto(pasta):
    return {str(p.relative_to(pasta)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(pathlib.Path(pasta).rglob("*")) if p.is_file()}


# ── formato por tipo ─────────────────────────────────────────────────────────
def test_formato_vale_por_tipo(raiz):
    assert Sessao.criar("d", "parresia", formato="daily", raiz=raiz).m["formato"] == "daily"
    assert Sessao.criar("c", "cliente", formato="demo", raiz=raiz).m["formato"] == "demo"
    for tipo, f in (("cliente", "daily"), ("parresia", "demo"), ("carreira", "daily"), ("pessoal", "descoberta")):
        with pytest.raises(ValueError):
            Sessao.criar("x", tipo, formato=f, raiz=raiz)
    import app
    assert app.formato_da_tela("parresia", "daily") == "daily"
    assert app.formato_da_tela("parresia", app.FORMATO_REUNIAO) is None      # "reunião" = sem formato
    assert app.formato_da_tela("cliente", "daily") is None                   # escolha de outro tipo não vaza
    assert app.formato_da_tela("carreira", "daily") is None


def test_predicado_unico(raiz):
    s = _daily(raiz)
    assert sessao.fora_da_medicao(s) and sessao.fora_da_medicao(s.m)
    assert sessao.fora_da_medicao({"formato": "daily"}) and not sessao.fora_da_medicao({"formato": None})
    assert not sessao.fora_da_medicao(Sessao.criar("r", "parresia", raiz=raiz))


# ── fora de toda medição ─────────────────────────────────────────────────────
@pytest.fixture
def ambiente(monkeypatch, tmp_path, raiz):
    """Histórico e vault de verdade (não falsos): o teste confere o hash deles."""
    fala = tmp_path / "fala"
    fala.mkdir()
    hist = [{"id": f"r{i}", "data": f"2026-10-0{i}T10:00:00-03:00", "titulo": f"R{i}", "safe": f"R{i}",
             "tipo": "cliente", "formato": None,
             "metrics": {"versao": 3, "palavras_voce": 3000, "dur_min": 60, "share_fala": 0.4, "conf_por_min": 0.4,
                         "muletas": {}, "muleta_pura_por_1000": 30, "ritmo": {"ppm": 190}}} for i in range(1, 4)]
    (fala / "historico.jsonl").write_text("".join(json.dumps(r) + "\n" for r in hist), encoding="utf-8")
    vault = tmp_path / "vault"
    (vault / "08-CRESCIMENTO").mkdir(parents=True)
    (vault / "08-CRESCIMENTO" / "fala-raio-x.md").write_text("nota antiga\n", encoding="utf-8")
    monkeypatch.setattr(sessao, "SALVAS", raiz)
    monkeypatch.setattr(analise_fala, "FALA_DIR", fala)
    monkeypatch.setenv("SINAPSE_VAULT", str(vault))
    monkeypatch.setattr(transcribe, "transcrever_sessao", lambda s, cfg, log=print: (segs_daily(), {
        "modelo": "falso", "dispositivo": "cpu", "segundos_processamento": 0,
        "diarizacao": {"status": "ok", "modo": "teto", "falantes": 3}}))
    chamadas = []

    def claude(p, entrada, cfg, log=print, esquema=None):
        chamadas.append({"prompt": p, "esquema": esquema})
        return bruto_daily(), {"por": "falso", "custo_usd": 0.01}
    monkeypatch.setattr(estruturar, "chamar_claude", claude)
    monkeypatch.setattr(entregavel, "html_para_pdf", lambda h, p: p.write_bytes(b"%PDF-falso") or p)

    def nunca(*a, **k):
        raise AssertionError("a avaliação interna não pode rodar numa daily")
    monkeypatch.setattr(avaliar, "avaliar", nunca)
    return {"fala": fala, "vault": vault, "claude": chamadas}


def _gravada(s):
    s.mic_pcm.write_bytes(b"\x00\x00" * 16000 * 3)
    s.loop_pcm.write_bytes(b"\x00\x00" * 16000 * 3)
    s.estado("gravado")
    return s


def test_pipeline_daily_fica_fora_da_medicao(ambiente, raiz):
    antes_fala, antes_vault = _foto(ambiente["fala"]), _foto(ambiente["vault"])
    s = _gravada(_daily(raiz))
    et = pipeline.processar(s, dict(CFG), log=lambda *a: None)
    assert et["raio_x"]["status"] == "pulada" and et["raio_x"]["detalhe"] == "daily: fora da medição"
    assert et["avaliacao"]["status"] == "pulada" and et["avaliacao"]["detalhe"] == "daily: fora da medição"
    assert _foto(ambiente["fala"]) == antes_fala              # historico.jsonl byte a byte igual, nenhuma página
    assert _foto(ambiente["vault"]) == antes_vault            # nota do vault byte a byte igual
    assert et["publicacao"]["status"] == "pulada"             # interna: não sai da máquina
    a = json.loads(s.caminho("ata.json").read_text(encoding="utf-8"))
    assert a["schema"] == ata.SCHEMA_DAILY
    assert ambiente["claude"][0]["esquema"] == estruturar.ESQUEMA_DAILY
    assert not s.caminho("entregavel.html").exists()
    assert "pessoas" in et["estrutura"]["detalhe"]
    # reprocessar continua fora (forçando estrutura e avaliação)
    pipeline.processar(Sessao.abrir(s.pasta), dict(CFG), log=lambda *a: None, forcar=("estrutura", "avaliacao"))
    assert _foto(ambiente["fala"]) == antes_fala and _foto(ambiente["vault"]) == antes_vault


def test_travas_no_ponto_de_escrita(ambiente, raiz):
    reg = {"id": "d1", "data": "2026-10-19T09:00", "titulo": "Daily", "safe": "Daily", "tipo": "parresia",
           "formato": "daily", "metrics": {}}
    with pytest.raises(ForaDaMedicao):
        analise_fala._upsert_historico(reg, ambiente["fala"])
    with pytest.raises(ForaDaMedicao):
        analise_fala._atualizar_vault([reg])
    with pytest.raises(ForaDaMedicao):
        analise_fala.processar(segs_daily(), "Daily", "2026-10-19T09:00", pasta=ambiente["fala"],
                               tipo="parresia", formato="daily")
    s = _daily(raiz)
    assert avaliar.deve_avaliar(s, segs_daily(), {"avaliar": True, "avaliar_acima_min": 0}) is False
    with pytest.raises(ForaDaMedicao):
        _AVALIAR(s, segs_daily(), {}, None, {})
    # linha daily que já esteja no histórico nunca entra na mediana nem no painel
    with open(ambiente["fala"] / "historico.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(reg) + "\n")
    assert all(r.get("formato") != "daily" for r in analise_fala.ler_historico(ambiente["fala"]))


def test_app_nao_mostra_cartao_da_daily(ambiente, raiz):
    import app

    class Falso:
        empacotou = False
    s = _daily(raiz)
    # a linha do histórico tem o id da daily (ex.: 09/10 antes de virar daily): mesmo assim, nada de cartão
    with open(ambiente["fala"] / "historico.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": s.id, "data": "2026-10-19", "metrics": {"metas": [["x", 1, 2, False]]}}) + "\n")
    assert app.App._cartao_fala(Falso(), None, s) is None      # sai antes de tocar no Tk


def test_recalcular_pula_daily(ambiente, raiz, capsys):
    import atas
    s = _daily(raiz)
    sessao.escrever_json(s.caminho("transcricao.json"), {"segments": segs_daily()})
    antes = _foto(ambiente["fala"])
    atas.main(["fala", "--recalcular"])
    assert "daily: fora da medição (pulada)" in capsys.readouterr().out
    assert _foto(ambiente["fala"]) == antes
    atas.main(["fala", s.id, "--sem-abrir"])
    assert "fora da medição" in capsys.readouterr().out
    assert Sessao.abrir(s.pasta).status_etapa("raio_x") == "pulada"


def test_formato_daily_em_sessao_ja_medida(ambiente, raiz, capsys):
    """Em cópia: a reunião foi medida como Parresia normal; virar daily tira a linha (com backup), refaz
    a nota do vault sem ela, apaga a página dela e guarda a avaliação como *.antes-daily.*."""
    import atas
    from conftest import segs_exemplo
    s = Sessao.criar("Reunião método", "parresia", "", ["Mauro"], raiz=raiz)
    s.m["inicio"] = "2026-10-09T09:35:00-03:00"
    s.salvar()
    sessao.escrever_json(s.caminho("transcricao.json"), {"segments": segs_exemplo()})
    analise_fala.processar(segs_exemplo(), s.m["titulo"], s.m["inicio"], tipo="parresia", sessao_id=s.id)
    s.etapa("raio_x", "ok")
    s.etapa("avaliacao", "ok")
    s.caminho("avaliacao-interna.md").write_text("# avaliação\n", encoding="utf-8")
    s.caminho("avaliacao-interna.html").write_text("<p>avaliação</p>", encoding="utf-8")
    hist = ambiente["fala"] / "historico.jsonl"
    assert s.id in hist.read_text(encoding="utf-8")
    nota = ambiente["vault"] / "08-CRESCIMENTO" / "fala-raio-x.md"
    assert "| Parresia |" in nota.read_text(encoding="utf-8")
    paginas = list(ambiente["fala"].glob("*Reuni*"))
    assert paginas
    atas.main(["formato", s.id, "daily"])
    s = Sessao.abrir(s.pasta)
    assert s.m["formato"] == "daily"
    assert s.id not in hist.read_text(encoding="utf-8")
    assert list(ambiente["fala"].glob("historico.jsonl.bak-*"))
    assert "| Parresia |" not in nota.read_text(encoding="utf-8")            # nota refeita sem a linha
    assert not any(p.exists() for p in paginas)
    assert not s.caminho("avaliacao-interna.md").exists()
    assert s.caminho("avaliacao-interna.antes-daily.md").exists()
    assert s.caminho("avaliacao-interna.antes-daily.html").exists()
    assert s.status_etapa("raio_x") == "pulada" and s.status_etapa("avaliacao") == "pulada"
    assert avaliar.mais_recente(s) is None
    out = capsys.readouterr().out
    assert "backup" in out and "--forcar estrutura" in out


def test_formato_recusa_o_de_outro_tipo_e_tipo_limpa(ambiente, raiz, capsys):
    import atas
    c = Sessao.criar("cli", "cliente", raiz=raiz)
    with pytest.raises(SystemExit):
        atas.main(["formato", c.id, "daily"])
    d = _daily(raiz)
    atas.main(["tipo", d.id, "cliente"])
    assert Sessao.abrir(d.pasta).m["formato"] is None
    assert "não vale" in capsys.readouterr().out


# ── quem falou ──────────────────────────────────────────────────────────────
def test_atalho_de_um_remoto_desligado_na_daily(raiz):
    segs = [{"speaker": "Você", "start": 0, "end": 3, "text": "bom dia"},
            {"speaker": "Participante", "start": 4, "end": 60, "text": "bom dia a todos, vamos lá"}]
    normal = ata.participantes_iniciais(segs, "Pedro", ["Mauro"])
    assert next(p for p in normal if p["rotulo"] == "Participante")["confirmado"] is True
    d = ata.participantes_iniciais(segs, "Pedro", ["Mauro"], daily=True)
    p = next(p for p in d if p["rotulo"] == "Participante")
    assert p["nome"] is None and p["confirmado"] is False
    s = _daily(raiz)
    assert next(p for p in ata.base(s, segs, "Pedro")["participantes"] if p["rotulo"] == "Participante")["nome"] is None


def test_transcricao_da_daily_diariza_com_parametros_proprios(raiz, monkeypatch):
    import audio as _audio
    import numpy as np
    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: (None, {"modelo": "falso", "dispositivo": "cpu"}))
    monkeypatch.setattr(transcribe, "_passada", lambda m, a_, falante, hot=None, idioma="pt":
                        [{"speaker": falante, "start": 1.0, "end": 3.0, "text": "oi gente bom dia"}])
    monkeypatch.setattr(_audio, "ler_audio", lambda p: np.zeros(16000, dtype="float32"))
    chamadas = []

    def diar(arq, thr, n, mx, py=None, referencia=None, **teto):
        chamadas.append((n, mx, teto))
        return {"turnos": [{"start": 0, "end": 4, "speaker": 0}], "falantes": 1, "modo": "teto", "brutos": 9}
    monkeypatch.setattr(transcribe, "_diarizar", diar)
    d = _daily(raiz)
    d.mic_pcm.write_bytes(b"\x00\x00" * 16000)
    d.loop_pcm.write_bytes(b"\x00\x00" * 16000)
    cfg = {"diar_threshold": 0.7, "daily_diar": {"max_falantes": 12, "min_fatia": 0.015, "min_segundos": 15}}
    _segs, info = transcribe.transcrever_sessao(d, cfg, log=lambda *a: None)
    assert chamadas == [(-1, 12, {"fatia_min": 0.015, "min_seg": 15})]       # 1 remoto informado ≠ contagem
    assert info["diarizacao"]["parametros"]["calibrado"] is False
    normal = Sessao.criar("r", "parresia", "", ["Mauro"], raiz=raiz)
    normal.mic_pcm.write_bytes(b"\x00\x00" * 16000)
    normal.loop_pcm.write_bytes(b"\x00\x00" * 16000)
    _segs, info = transcribe.transcrever_sessao(normal, cfg, log=lambda *a: None)
    assert len(chamadas) == 1 and info["diarizacao"]["motivo"] == "1 participante remoto informado"
    tres = _daily(raiz, remotos=("A", "B", "C"))
    tres.mic_pcm.write_bytes(b"\x00\x00" * 16000)
    tres.loop_pcm.write_bytes(b"\x00\x00" * 16000)
    transcribe.transcrever_sessao(tres, cfg, log=lambda *a: None)
    assert chamadas[-1][0] == 3                                               # N informado é respeitado
    # a equipe entra no vocabulário (primeiro, para o limite de 40 não cortar)
    assert transcribe.vocabulario("parresia", equipe=["Rogério"])[0] == "Rogério"


def test_linha_de_comando_da_diarizacao_normal_nao_muda(monkeypatch, tmp_path):
    cmds = []

    class R:
        stdout = '{"turnos": [], "falantes": 0, "modo": "vazio", "brutos": 0}'
        stderr = ""
        returncode = 0
    monkeypatch.setattr(transcribe.subprocess, "run", lambda cmd, **k: cmds.append(cmd) or R())
    py = tmp_path / "python.exe"
    py.write_text("")
    transcribe._diarizar("a.wav", 0.7, -1, 6, py)
    transcribe._diarizar("a.wav", 0.7, -1, 12, py, fatia_min=0.015, min_seg=15)
    assert cmds[0][2:] == ["a.wav", "0.7", "-1", "6"]
    assert cmds[1][2:] == ["a.wav", "0.7", "-1", "12", "", "0.015", "15"]


def test_rodada_propoe_nome_com_evidencia():
    r = daily.rodada(segs_daily(), CFG["daily_equipe"], "Pedro")
    por = {x["rotulo"]: x for x in r}
    assert por["Participante 2"]["nome"] == "Rogério"
    assert "[00:00] Participante 1" in por["Participante 2"]["evidencias"][0]
    assert "[00:06] Participante 2 começa a falar" in por["Participante 2"]["evidencias"][0]
    assert por["Participante 3"]["nome"] == "Caio"
    assert "Você" not in por                                   # "Pedro, você consegue…" não propõe nada
    # pergunta SOBRE alguém não é vocativo
    assert daily.vocativos("Você falou com o Rogério?", ["Rogério"]) == []
    assert daily.vocativos("Rogério?", ["Rogério"]) == ["Rogério"]
    assert daily.vocativos("e aí, Téo, como tá?", ["Téo"]) == ["Téo"]


# ── a ata da daily ──────────────────────────────────────────────────────────
def _ata_daily(raiz):
    s = _daily(raiz)
    return daily.montar(s, segs_daily(), bruto_daily(), {"por": "teste"}, "Pedro", dict(CFG))


def test_card_conferido_a_60_segundos(raiz):
    a = _ata_daily(raiz)
    rod, luc = a["pessoas"]
    assert rod["fez"][0]["card"] == "SUP-953" and rod["fez"][0]["verificado"] is True
    assert rod["vai_fazer"][0]["card"] is None                              # SUP-959 nunca foi dito
    assert rod["vai_fazer"][0]["card_removido"] == "SUP-959"
    trav = luc["travado"][0]
    assert trav["verificado"] is True and trav["card"] is None              # 953 dito em 00:06, citação em 05:00
    assert any("60 s" in p for p in trav["problemas"])
    assert any(l["ref"] == trav["id"] and "SUP-953" in l["falta"] for l in a["lacunas"])
    assert a["com_voce"][0]["card"] == "SUP-955"                            # "card 955" dito na própria fala


def test_mencao_a_card_rastreado_nao_tratada_vira_lacuna(raiz):
    a = _ata_daily(raiz)
    fr = a["frentes"][0]
    assert fr["nome"] == "Frota WP"
    por_t = {m["t"]: m for m in fr["mencoes"]}
    assert por_t["00:06"]["cards"] == ["SUP-953"] and por_t["00:06"]["tratada"] is True
    assert por_t["03:20"]["cards"] == ["SUP-957"] and por_t["03:20"]["tratada"] is False
    assert any(l["ref"] == "[03:20]" and "menção não tratada: SUP-957" in l["falta"] for l in a["lacunas"])
    assert not any("SUP-955" in l["falta"] and "menção" in l["falta"] for l in a["lacunas"])
    # o prompt recebe a lista obrigatória e as pistas da rodada
    s = _daily(raiz)
    p = estruturar.prompt_daily(s, "Pedro", CFG["daily_equipe"], daily.frentes_do_config(CFG),
                                daily.mencoes(ata.falas(segs_daily()), daily.frentes_do_config(CFG)),
                                daily.rodada(segs_daily(), CFG["daily_equipe"]))
    assert "[03:20] Participante 2 (Frota WP; cards SUP-957)" in p
    assert "Participante 2 → Rogério" in p


def test_rerender_mantem_a_auditoria(raiz):
    a = _ata_daily(raiz)
    a2 = ata.auditar(json.loads(json.dumps(a)), segs_daily())             # o que `atas.py render` faz
    assert ata.contagem(a2) == ata.contagem(a)
    assert a2["rodada"][0]["nome"] in ("Rogério", "Caio")


def test_render_da_daily_com_voce_no_topo(raiz):
    a = _ata_daily(raiz)
    h = render.html(a, segs_daily())
    assert h.index("Com você") < h.index("Frota WP") < h.index("Por pessoa") < h.index("Encaminhamentos")
    assert "Participante 2 (Rogério?)" in h and "menção não tratada" in h
    md = render.markdown(a, segs_daily())
    assert md.index("## Com você") < md.index("## Por pessoa")
    with pytest.raises(ValueError):
        render.html(a, segs_daily(), cliente=True)                          # daily nunca é entregável


# ── duas dailies e busca ────────────────────────────────────────────────────
def test_titulo_da_proxima_daily(raiz):
    s1 = _daily(raiz, titulo="Daily Parresia")
    assert sessao.titulo_da_proxima_daily(s1, raiz) == "Daily Parresia (2)"
    s2 = _daily(raiz, titulo="Daily Parresia (2)")
    assert sessao.titulo_da_proxima_daily(s2, raiz) == "Daily Parresia (3)"


def test_busca_daily(raiz, monkeypatch, capsys):
    import atas
    monkeypatch.setattr(sessao, "SALVAS", raiz)
    a = _ata_daily(raiz)
    s = Sessao.abrir(raiz / a["id"])
    sessao.escrever_json(s.caminho("ata.json"), a)
    sessao.escrever_json(s.caminho("transcricao.json"), {"segments": segs_daily()})
    normal = Sessao.criar("Reunião", "parresia", raiz=raiz)                # fora da busca: não é daily
    sessao.escrever_json(normal.caminho("transcricao.json"), {"segments": segs_daily()})
    sessao.escrever_json(normal.caminho("ata.json"), ata.base(normal, segs_daily(), "Pedro"))
    atas.main(["daily", "SUP-953"])
    out = capsys.readouterr().out
    assert "Participante 2 (Rogério?) · SUP-953 · F1 fez: Revisou os plugins do SUP-953" in out
    assert normal.id not in out
    atas.main(["daily", "deploy", "--pessoa", "Caio"])
    assert "Fechou o deploy do Lumen" in capsys.readouterr().out
    atas.main(["daily", "957", "--frente", "Frota WP"])                     # sem item: cai na transcrição
    assert "transcrição" in capsys.readouterr().out
    atas.main(["daily", "SUP-953", "--desde", "2026-10-20"])
    assert "nada sobre" in capsys.readouterr().out


def test_gravar_a_proxima_daily_sem_tela_de_digitar(raiz):
    import app

    class Falso:
        l_proxima = None
        comecou = False

        def _preparar_gravacao(self):
            self.comecou = True
    s = _daily(raiz, titulo="Daily Parresia")
    f = Falso()
    app.App.proxima_daily(f, s)
    assert f.comecou
    assert f.ctx == {"titulo": "Daily Parresia (2)", "tipo": "parresia", "projeto": "", "formato": "daily",
                     "participantes": ["Mauro"]}


def test_rodada_que_discorda_do_nome_deduzido_vira_lacuna(raiz):
    b = bruto_daily()
    b["falantes"][0]["nome"] = "Augusto"                  # o texto diz Augusto, a rodada diz Rogério
    a = daily.montar(_daily(raiz), segs_daily(), b, {}, "Pedro", dict(CFG))
    assert any(l["ref"] == "Participante 2" and "a rodada aponta Rogério" in l["falta"] for l in a["lacunas"])
