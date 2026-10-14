# -*- coding: utf-8 -*-
"""Marcar momento (14/10/2026): o Pedro aperta um atalho na hora em que algo importa; a marca vai
para o sessao.json, o Claude trata o trecho (45 s antes, 15 s depois) como prioridade e a ata
interna abre com a seção "Momentos marcados" — auditada como o resto, nunca no entregável."""
import ctypes
import json
import time

import pytest
from conftest import segs_exemplo
from test_ata import _bruto

import ata
import atalho
import estruturar
import marcas
import pipeline
import render
import sessao
from sessao import Sessao


def _sessao(raiz, tipo="cliente"):
    s = Sessao.criar("Alinhamento", tipo, "projeto-x", ["Mauro"], raiz=raiz)
    s.m["inicio"] = "2026-09-30T14:00:00-03:00"
    s.salvar()
    return s


# ── gravação da marca ────────────────────────────────────────────────────────
def test_marca_vai_para_o_sessao_json_em_ordem_e_com_repique(raiz):
    s = _sessao(raiz)
    assert marcas.adicionar(s, 750.24, "atalho")["t"] == 750.2
    assert marcas.adicionar(s, 120, "botao") is not None
    assert marcas.adicionar(s, 751.5, "atalho") is None          # 2º toque em < 2 s = a mesma marca
    disco = json.loads(s.caminho("sessao.json").read_text(encoding="utf-8"))
    assert [m["t"] for m in disco["marcas"]] == [120.0, 750.2]   # gravado (fsync) e em ordem
    assert [m["origem"] for m in disco["marcas"]] == ["botao", "atalho"]
    assert all(m["criado"] for m in disco["marcas"])
    assert [i for i, _ in marcas.identificadas(disco["marcas"])] == ["M1", "M2"]


def test_ler_horarios():
    assert marcas.ler_horarios(["12:30", "1:02:03"]) == [750.0, 3723.0]
    assert marcas.ler_horarios(["12:30,40:10"]) == [750.0, 2410.0]
    for ruim in ("750", "12:75", "ab:cd", "12:"):
        with pytest.raises(ValueError):
            marcas.ler_horarios([ruim])


def test_janela_45_antes_15_depois():
    assert marcas.janela(750) == (705, 765)
    assert marcas.janela(10) == (0, 25)                          # não passa de zero
    assert marcas.dentro(706, 750) and marcas.dentro(764, 750)
    assert not marcas.dentro(690, 750) and not marcas.dentro(775, 750)


# ── prompt e esquema ─────────────────────────────────────────────────────────
def test_prompt_traz_as_marcas_com_o_trecho(raiz):
    s = _sessao(raiz)
    p0 = estruturar.prompt(s, "Pedro")
    assert "MOMENTOS MARCADOS" not in p0
    assert "momentos" not in estruturar.esquema(False)["required"]
    marcas.adicionar(s, 750, "atalho")
    p = estruturar.prompt(s, "Pedro")
    assert "MOMENTOS MARCADOS" in p
    assert "M1 em [12:30] → trecho de [11:45] a [12:45]" in p
    assert "Nunca invente" in p
    assert "momentos" in estruturar.esquema(True)["required"]
    assert "momentos" not in ata.ESQUEMA_CLAUDE["required"]      # o esquema-base não muda


# ── auditoria dos momentos ───────────────────────────────────────────────────
def _montar_com(raiz, momentos, ts=(6.0, 25.0, 300.0)):
    s = _sessao(raiz, "parresia")
    for t in ts:
        marcas.adicionar(s, t, "atalho")
    b = _bruto()
    b["momentos"] = momentos
    return ata.montar(s, segs_exemplo(), b, {}, "Pedro")


def test_momento_com_citacao_no_trecho_e_verificado_e_ligado_aos_itens(raiz):
    a = _montar_com(raiz, [
        {"marca": "M1", "o_que": "Release espera o gateway", "tipo": "decisao", "t": "00:05",
         "citacao": "Ficou decidido que a release espera a resposta do gateway"}])
    m1, m2, m3 = a["momentos"]
    assert m1["verificado"] is True and m1["t"] == "00:05" and m1["hora"] == "00:06"
    assert "D1" in m1["itens"]                                   # a decisão do trecho, já na ata
    assert "D2" not in m1["itens"]                               # item inventado não conta
    # M2 e M3: o Claude não devolveu nada → "sem decisão clara", nada inventado
    assert m2["o_que"] is None and m2["tipo"] == "nada" and m2["citacao"] is None
    assert m3["o_que"] is None and m3["itens"] == []


def test_momento_sem_citacao_achada_e_descartado(raiz):
    a = _montar_com(raiz, [
        {"marca": "M1", "o_que": "Vão migrar para Kubernetes", "tipo": "decisao", "t": "00:05",
         "citacao": "vamos migrar toda a infraestrutura para Kubernetes em outubro"},
        # citação real, mas de uma fala FORA do trecho da marca M3 (300 s → 255–315)
        {"marca": "M3", "o_que": "Resumo até sexta", "tipo": "compromisso", "t": "00:13",
         "citacao": "Eu mando o resumo para o time até sexta-feira à tarde"}])
    m1, _m2, m3 = a["momentos"]
    for m in (m1, m3):
        assert m["o_que"] is None and m["citacao"] is None and m["tipo"] == "nada"
        assert m["verificado"] is False and m["citacao_descartada"]
        assert any("descartada" in p for p in m["problemas"])
    assert "não localizada" in m1["problemas"][0]
    assert "fora do trecho" in m3["problemas"][0]
    assert render.texto_momento(m1) == (None, "marcado — sem decisão clara no trecho")


def test_reauditar_mantem_o_momento_e_marca_nova_fica_pendente(raiz, monkeypatch):
    monkeypatch.setattr(pipeline, "_pdfs", lambda *a: None)       # sem Chrome no teste rápido
    s = _sessao(raiz, "parresia")
    marcas.adicionar(s, 6, "atalho")
    b = _bruto()
    b["momentos"] = [{"marca": "M1", "o_que": "Release espera o gateway", "tipo": "decisao", "t": "00:05",
                      "citacao": "Ficou decidido que a release espera a resposta do gateway"}]
    a = ata.montar(s, segs_exemplo(), b, {}, "Pedro")
    sessao.escrever_json(s.caminho("transcricao.json"), {"segments": segs_exemplo()})
    sessao.escrever_json(s.caminho("ata.json"), a)
    marcas.adicionar(s, 2, "depois")                             # lembrou depois: vira M1, a antiga M2
    a2 = pipeline.reaplicar(Sessao.abrir(s.pasta), {}, log=lambda *x: None, publicar_=False)
    novo, antigo = a2["momentos"]
    assert (novo["id"], novo["pendente"]) == ("M1", True)
    assert "refaça a estrutura" in novo["problemas"][0]
    assert (antigo["id"], antigo["verificado"], antigo["o_que"]) == ("M2", True, "Release espera o gateway")


def test_ata_pendente_ja_mostra_as_marcas(raiz):
    s = _sessao(raiz)
    marcas.adicionar(s, 13, "atalho")
    a = ata.base(s, segs_exemplo(), "Pedro")
    assert a["momentos"][0]["pendente"] is True and a["momentos"][0]["hora"] == "00:13"


# ── render ───────────────────────────────────────────────────────────────────
def test_render_interna_abre_com_momentos_e_o_entregavel_nao_tem(raiz):
    a = _montar_com(raiz, [
        {"marca": "M1", "o_que": "Release espera o gateway", "tipo": "decisao", "t": "00:05",
         "citacao": "Ficou decidido que a release espera a resposta do gateway"}])
    segs = segs_exemplo()
    h = render.html(a, segs)
    assert "Momentos marcados" in h and h.index("Momentos marcados") < h.index("<h2>Decisões")
    assert 'href="#f-0"' in h and 'id="f-0"' in h                # horário leva ao trecho
    assert "marcado — sem decisão clara no trecho" in h
    assert "Release espera o gateway" in h
    a["participantes"] = [dict(p, confirmado=True, nome=p.get("nome") or "X") for p in a["participantes"]]
    cli = render.html(a, segs, cliente=True)
    assert "Momentos marcados" not in cli and "marcado —" not in cli and 'id="f-' not in cli
    md = render.markdown(a, segs)
    assert md.index("## Momentos marcados") < md.index("## Decisões")
    assert '- **M1** [00:06] Release espera o gateway — "Ficou decidido' in md
    assert "- **M2** [00:25] _marcado — sem decisão clara no trecho_" in md


# ── reunião longa: cada bloco recebe as marcas dele ─────────────────────────
def _segs_longos(minutos=100):
    out = []
    for i in range(minutos):
        quem = "Você" if i % 2 else "Participante"
        out.append({"speaker": quem, "start": i * 60.0, "end": i * 60.0 + 20,
                    "text": f"fala numero {i} sobre o andamento do projeto alfa e os proximos passos"})
    out.append({"speaker": "Participante", "start": 2980.0, "end": 2990.0,
                "text": "Ficou fechado que a mensalidade vai ser de quinhentos reais por mes a partir de novembro"})
    return sorted(out, key=lambda s: s["start"])


def test_blocos_levam_as_marcas_do_bloco_certo(raiz, monkeypatch):
    s = _sessao(raiz)
    for t in (300, 3000, 5900):                                  # bloco 1, bloco 2, bloco 3
        marcas.adicionar(s, t, "atalho")
    chamadas = []

    def falso(texto_prompt, transcricao, cfg, log=print, esquema=None):
        chamadas.append((texto_prompt, transcricao, esquema))
        if "temas_escopo" in (esquema or {}).get("properties", {}):
            return {"contexto": "c", "resumo": "r", "temas": [], "por_tema": [], "temas_escopo": []}, {}
        vazio = {k: [] for k, _ in ata.LISTAS} | {"falantes": [], "contexto": "", "resumo": "", "temas": [],
                                                   "por_tema": []}
        if "M2 em [50:00]" in texto_prompt:
            vazio["momentos"] = [{"marca": "M2", "o_que": "Mensalidade de R$ 350 a partir de novembro",
                                  "tipo": "valor", "t": "49:40",
                                  "citacao": "a mensalidade vai ser de quinhentos reais por mes"}]
            vazio["valores"] = [{"descricao": "Mensalidade", "valor": "quinhentos reais por mês",
                                 "condicao": "a partir de novembro", "natureza": "combinado", "t": "49:40",
                                 "citacao": "a mensalidade vai ser de quinhentos reais por mes"}]
        return vazio, {"segundos": 1, "custo_usd": 0}
    monkeypatch.setattr(estruturar, "chamar_claude", falso)
    a, motivo = estruturar.estruturar(s, _segs_longos(), {"meu_nome": "Pedro"}, log=lambda *x: None)
    assert motivo is None
    assert len(chamadas) == 4                                    # 3 blocos + a consolidação
    p1, p2, p3 = [c[0] for c in chamadas[:3]]
    assert "M1 em [05:00]" in p1 and "M2 em" not in p1 and "M3 em" not in p1
    assert "M2 em [50:00]" in p2 and "M1 em" not in p2 and "M3 em" not in p2
    assert "M3 em [1:38:20]" in p3 and "M2 em" not in p3
    assert all("momentos" in c[2]["required"] for c in chamadas[:3])
    m1, m2, m3 = a["momentos"]
    assert m2["verificado"] is True and m2["o_que"].startswith("Mensalidade") and m2["itens"] == ["V1"]
    assert m1["tipo"] == "nada" and m3["tipo"] == "nada"


# ── CLI ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(raiz, monkeypatch):
    monkeypatch.setattr(sessao, "SALVAS", raiz)
    import atas
    return atas


def test_cli_marcar_e_marcas(cli, raiz, capsys):
    s = _sessao(raiz)
    s.m["audio"]["duracao_s"] = 3000
    s.salvar()
    cli.main(["marcar", s.id, "12:30", "40:10,5:00"])
    assert [m["t"] for m in Sessao.abrir(s.pasta).m["marcas"]] == [300.0, 750.0, 2410.0]
    assert all(m["origem"] == "depois" for m in Sessao.abrir(s.pasta).m["marcas"])
    cli.main(["marcas", s.id])
    out = capsys.readouterr().out
    assert "3 momento(s) marcado(s)" in out and "M3     40:10  (depois)" in out
    cli.main(["marcar", s.id, "12:31", "--remover"])
    assert [m["t"] for m in Sessao.abrir(s.pasta).m["marcas"]] == [300.0, 2410.0]
    with pytest.raises(SystemExit):
        cli.main(["marcar", s.id, "55:00"])                     # depois do fim (50 min)
    with pytest.raises(SystemExit):
        cli.main(["marcar", s.id, "1230"])


def test_cli_marcar_recusa_gravacao_em_curso(cli, raiz):
    s = _sessao(raiz)
    s.m["estado"] = "gravando"
    s.salvar()
    s.bater()
    with pytest.raises(SystemExit):
        cli.main(["marcar", s.id, "1:00"])


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg fora do PATH")
def test_importar_do_celular_com_marcas(raiz, tmp_path):
    import celular
    from test_celular import _tom
    arq = _tom(tmp_path / "2026-10-14_1030.wav", 90)
    s = celular.importar(arq, raiz=raiz, processar=False, log=lambda *a: None, marcas=[30.0, 75.0])
    assert [(m["t"], m["origem"]) for m in Sessao.abrir(s.pasta).m["marcas"]] == [(30.0, "celular"),
                                                                                  (75.0, "celular")]
    with pytest.raises(ValueError):
        celular.importar(_tom(tmp_path / "b.wav", 10, 330), raiz=raiz, processar=False,
                         log=lambda *a: None, marcas=[60.0])


# ── atalho global ────────────────────────────────────────────────────────────
def test_ler_atalho():
    assert atalho.ler("ctrl+alt+m") == (atalho.MOD_CONTROL | atalho.MOD_ALT, ord("M"))
    assert atalho.ler("Ctrl+Shift+F9") == (atalho.MOD_CONTROL | atalho.MOD_SHIFT, 0x78)
    assert atalho.legivel("ctrl+alt+m") == "Ctrl+Alt+M"
    for ruim in ("m", "hyper+m", "ctrl+alt+enter"):
        with pytest.raises(ValueError):
            atalho.ler(ruim)


def test_atalho_registra_libera_e_acusa_conflito():
    # combinação que ninguém usa, para não brigar com nada da máquina
    combo = "ctrl+alt+shift+f23"
    a = atalho.iniciar(lambda: None, combo)
    try:
        assert a.erro is None and a.registrado
        b = atalho.iniciar(lambda: None, combo)              # o mesmo atalho de novo: o Windows recusa
        assert b.erro and "em uso" in b.erro and not b.is_alive()
    finally:
        assert a.parar()
    assert not a.registrado
    c = atalho.iniciar(lambda: None, combo)                  # liberado de verdade: registra de novo
    try:
        assert c.erro is None
    finally:
        c.parar()


# SendInput de verdade: aperta Ctrl+Alt+M no Windows e confere a marca no sessao.json
class _KI(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _IN(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KI), ("pad", ctypes.c_byte * 32)]
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _teclas(vks):
    seq = [(vk, 0) for vk in vks] + [(vk, 2) for vk in reversed(vks)]      # 2 = KEYEVENTF_KEYUP
    arr = (_IN * len(seq))(*[_IN(1, _IN._U(ki=_KI(vk, 0, fl, 0, 0))) for vk, fl in seq])
    return ctypes.windll.user32.SendInput(len(seq), arr, ctypes.sizeof(_IN))


@pytest.mark.lento
def test_atalho_de_verdade_grava_a_marca(raiz):
    s = _sessao(raiz)
    t0 = time.monotonic()
    a = atalho.iniciar(lambda: marcas.adicionar(s, time.monotonic() - t0, "atalho"), "ctrl+alt+m")
    if a.erro:
        pytest.skip(a.erro)
    try:
        time.sleep(0.3)
        assert _teclas([0x11, 0x12, ord("M")]) == 6                # Ctrl, Alt, M
        fim = time.time() + 3
        while not Sessao.abrir(s.pasta).m.get("marcas") and time.time() < fim:
            time.sleep(0.05)
    finally:
        a.parar()
    mk = Sessao.abrir(s.pasta).m.get("marcas")
    assert mk and mk[0]["origem"] == "atalho" and 0 < mk[0]["t"] < 5 and a.disparos == 1
