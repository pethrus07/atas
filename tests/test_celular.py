# -*- coding: utf-8 -*-
"""Reunião presencial gravada no celular (14/10/2026): um arquivo → uma sessão, um canal só,
"Você" achado pela voz e A CONFIRMAR, tipo pendente sem entregável nem publicação.
O áudio dos testes rápidos é sintético (tom do ffmpeg); o Whisper e a diarização são
substituídos. O teste lento roda as peças de verdade com as vozes SAPI das fixtures."""
import datetime as dt
import os
import pathlib
import shutil
import subprocess
import time

import pytest
from conftest import segs_exemplo
from test_ata import _bruto

import analise_fala
import celular
import entregavel
import estruturar
import pipeline
import sessao
import transcribe
from sessao import Sessao

FX = pathlib.Path(__file__).parent / "fixtures"
CFG = {"meu_nome": "Pedro", "estruturar": True, "audio_reter_dias": 30, "diarizar": True,
       "worker_url": "https://w.test", "upload_token": "t"}

precisa_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fora do PATH")


def _tom(destino, segundos=30, freq=220):
    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:duration={segundos}", str(destino)], check=True)
    return destino


def _velho(p, segundos=600):
    t = time.time() - segundos
    os.utime(p, (t, t))
    return p


# ── peças puras ──────────────────────────────────────────────────────────────
def test_data_e_titulo_pelo_nome_do_arquivo():
    assert celular.data_do_nome("2026-10-14_1030.m4a") == dt.datetime(2026, 10, 14, 10, 30)
    assert celular.data_do_nome("Gravação 2026-10-14 10-30-00.m4a") == dt.datetime(2026, 10, 14, 10, 30)
    assert celular.data_do_nome("20261014_103000.amr") == dt.datetime(2026, 10, 14, 10, 30)
    assert celular.data_do_nome("Voice 001.m4a") is None
    q = dt.datetime(2026, 10, 14, 10, 30)
    assert celular.titulo_do_nome("2026-10-14_1030.m4a", q) == "Reunião presencial 14/10 10:30"
    assert celular.titulo_do_nome("2026-10-14_1030_oficina-jonas.m4a", q) == "oficina jonas"


def test_escolher_voce_pela_amostra_pelo_tom_ou_ninguem():
    e = celular.escolher_voce({"Falante 1": 0.18, "Falante 2": 0.71})
    assert e["rotulo"] == "Falante 2" and e["metodo"] == "referencia" and "a confirmar" in e["evidencia"]
    # perto demais um do outro: a amostra não decide; o tom decide se só um grupo bate
    e = celular.escolher_voce({"Falante 1": 0.50, "Falante 2": 0.47},
                              tons={"Falante 1": 210, "Falante 2": 140}, tom_ref=138)
    assert e["rotulo"] == "Falante 2" and e["metodo"] == "tom"
    # dois homens de voz parecida: o tom não separa → ninguém vira "Você"
    e = celular.escolher_voce({}, tons={"Falante 1": 135, "Falante 2": 142}, tom_ref=138)
    assert e["rotulo"] is None and e["metodo"] == "nenhum"
    assert celular.escolher_voce()["rotulo"] is None


def test_aplicar_rotulos_e_trocar():
    segs = [{"speaker": "Falante 1", "start": 0, "end": 1, "text": "a"},
            {"speaker": "Falante 2", "start": 2, "end": 3, "text": "b"},
            {"speaker": "Falante 3", "start": 4, "end": 5, "text": "c"}]
    mapa = celular.aplicar_rotulos(segs, "Falante 2")
    assert [s["speaker"] for s in segs] == ["Participante 1", "Você", "Participante 2"]
    assert mapa == {"Falante 1": "Participante 1", "Falante 3": "Participante 2", "Falante 2": "Você"}
    assert celular.trocar_voce(segs, "Participante 2")
    assert [s["speaker"] for s in segs] == ["Participante 1", "Participante 2", "Você"]
    with pytest.raises(ValueError):
        celular.trocar_voce(segs, "Participante 9")
    dois = [{"speaker": "Falante 1", "start": 0, "end": 1, "text": "a"},
            {"speaker": "Falante 2", "start": 2, "end": 3, "text": "b"}]
    celular.aplicar_rotulos(dois, "Falante 1")
    assert [s["speaker"] for s in dois] == ["Você", "Participante"]      # como a chamada com 1 remoto


# ── importar e vigiar ─────────────────────────────────────────────────────────
@precisa_ffmpeg
def test_importar_cria_sessao_de_um_canal_pendente(raiz, tmp_path):
    arq = _tom(tmp_path / "celular" / "2026-10-14_1030.m4a")
    s = celular.importar(arq, raiz=raiz, processar=False, log=lambda *a: None)
    s = Sessao.abrir(s.pasta)
    assert s.celular and s.m["canais"] == 1 and s.m["tipo"] == sessao.TIPO_PENDENTE
    assert s.m["inicio"].startswith("2026-10-14T10:30") and s.m["inicio_por"] == "nome do arquivo"
    assert s.id.startswith("2026-10-14_1030_")
    assert 29 <= s.m["audio"]["duracao_s"] <= 31
    assert (s.audio_dir / "celular.opus").exists() and arq.exists()       # a origem não é apagada
    assert s.m["origem_arquivo"]["sha256"] == celular.hash_arquivo(arq)
    assert s.m["estado"] == "gravado" and s.status_etapa("captura") == "ok"
    with pytest.raises(ValueError, match="já foi importado"):
        celular.importar(arq, raiz=raiz, processar=False, log=lambda *a: None)


@precisa_ffmpeg
def test_importar_com_tipo_formato_e_data(raiz, tmp_path):
    arq = _tom(tmp_path / "Voice 001.wav", 5)
    s = celular.importar(arq, titulo="Oficina", tipo="cliente", projeto="retifica",
                         participantes=["Jonas"], formato="demo",
                         quando=dt.datetime(2026, 10, 13, 9, 0), raiz=raiz, processar=False,
                         log=lambda *a: None)
    assert (s.m["tipo"], s.m["formato"], s.m["participantes"]) == ("cliente", "demo", ["Jonas"])
    assert s.m["inicio"].startswith("2026-10-13T09:00") and s.m["inicio_por"] == "informado"


def test_importar_recusa_extensao_e_tipo_errados(raiz, tmp_path):
    txt = tmp_path / "notas.txt"
    txt.write_text("x")
    with pytest.raises(ValueError):
        celular.importar(txt, raiz=raiz, processar=False)
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"0" * 100)
    with pytest.raises(ValueError):
        celular.importar(wav, tipo="empresa", raiz=raiz, processar=False)


@precisa_ffmpeg
def test_vigiar_importa_so_o_novo_e_nao_duplica(raiz, tmp_path):
    pasta = tmp_path / "Atas-celular"
    a = _velho(_tom(pasta / "2026-10-14_0900.m4a", 3))
    _tom(pasta / "2026-10-14_1100.m4a", 3, freq=330)                      # recém-chegado: ainda sincronizando
    (pasta / "leia-me.txt").write_text("não é áudio")
    r = celular.vigiar(pasta, raiz=raiz, processar=False, log=lambda *x: None)
    ids = [x for _, x in r if x.startswith("2026")]
    assert len(ids) == 1 and dict((p.name, x) for p, x in r)["2026-10-14_1100.m4a"] == "ainda sincronizando"
    assert Sessao.abrir(ids[0], raiz=raiz).m["tipo"] == sessao.TIPO_PENDENTE
    # a cópia com outro nome (o OneDrive renomeia em conflito) não vira reunião nova
    shutil.copy2(a, pasta / "2026-10-14_0900 (1).m4a")
    r2 = celular.vigiar(pasta, raiz=raiz, processar=False, log=lambda *x: None)
    assert [x for _, x in r2 if x.startswith("2026")] == []
    assert len(sessao.listar(raiz)) == 1


# ── pipeline com o Whisper e a diarização substituídos ─────────────────────────
@pytest.fixture
def falsos(monkeypatch, tmp_path):
    def passada(modelo, audio_, falante, hot=None, idioma="pt"):
        return [dict(x, speaker=falante) for x in segs_exemplo()]
    monkeypatch.setattr(transcribe, "carregar_modelo",
                        lambda *a, **k: (None, {"modelo": "falso", "dispositivo": "cpu"}))
    monkeypatch.setattr(transcribe, "_passada", passada)
    monkeypatch.setattr("audio.ler_audio", lambda p: __import__("numpy").zeros(16000, dtype="float32"))
    # o Pedro fala em 0–4 s e 13–19 s: grupo 1 do diarizador, que aparece primeiro → "Falante 1"
    turnos = [{"start": 0, "end": 4, "speaker": 1}, {"start": 5, "end": 12, "speaker": 0},
              {"start": 13, "end": 19, "speaker": 1}, {"start": 20, "end": 27, "speaker": 0}]
    chamadas = {}

    def diarizar(arq, thr, n, mx, py=None, referencia=None):
        chamadas.update(n=n, referencia=referencia)
        return {"turnos": turnos, "falantes": 2, "modo": "informado", "brutos": 2,
                "similaridade": {"1": 0.68, "0": 0.21}}
    monkeypatch.setattr(transcribe, "_diarizar", diarizar)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"\x00" * 400000)
    monkeypatch.setattr(celular, "REFERENCIA", ref)
    monkeypatch.setattr(estruturar, "chamar_claude", lambda *a, **k: (_bruto(), {"por": "falso"}))
    monkeypatch.setattr(entregavel, "html_para_pdf", lambda h, p: p.write_bytes(b"%PDF-falso") or p)
    monkeypatch.setattr(analise_fala, "FALA_DIR", tmp_path / "fala")
    monkeypatch.setattr(analise_fala, "_atualizar_vault", lambda linhas: None)
    return chamadas


@precisa_ffmpeg
def test_pipeline_do_celular_acha_voce_a_confirmar(raiz, tmp_path, falsos):
    arq = _tom(tmp_path / "2026-10-14_1030.m4a")
    s = celular.importar(arq, participantes=["Mauro"], raiz=raiz, cfg=dict(CFG),
                         log=lambda *a: None)
    assert falsos["n"] == 2 and falsos["referencia"]                    # Mauro + o Pedro, com a amostra
    segs, a = pipeline.carregar(s)
    assert [x["speaker"] for x in segs] == ["Você", "Participante", "Você", "Participante"]
    cel = s.m["celular"]
    assert cel["metodo"] == "referencia" and cel["voce_confirmado"] is False
    assert cel["similaridades"] == {"Você": 0.68, "Participante": 0.21}
    voce = next(p for p in a["participantes"] if p["rotulo"] == "Você")
    assert voce["confirmado"] is False and "a confirmar" in voce["evidencia"]
    mauro = next(p for p in a["participantes"] if p["rotulo"] == "Participante")
    assert mauro["nome"] == "Mauro" and mauro["confirmado"] is False
    et = s.m["etapas"]
    assert et["raio_x"]["status"] == "pendente"                       # não mede a voz de outra pessoa
    assert et["publicacao"]["status"] == "pulada"                     # tipo pendente não sai da máquina
    assert not s.caminho("entregavel.html").exists()
    assert "PRESENCIAL" in estruturar.prompt(s, "Pedro")
    assert "você = Falante 1" in et["falantes"]["detalhe"]
    with pytest.raises(RuntimeError):
        pipeline.publicar(s, dict(CFG))


@pytest.fixture
def cli(raiz, monkeypatch):
    monkeypatch.setattr(sessao, "SALVAS", raiz)
    import atas
    monkeypatch.setattr(atas._config, "carregar", lambda: dict(CFG))
    monkeypatch.setattr(pipeline._config, "carregar", lambda: dict(CFG))
    return atas


@precisa_ffmpeg
def test_falantes_troca_voce_e_libera_o_raio_x(raiz, tmp_path, falsos, cli, capsys):
    arq = _tom(tmp_path / "2026-10-14_1030.m4a")
    s = celular.importar(arq, participantes=["Mauro"], raiz=raiz, cfg=dict(CFG), log=lambda *a: None)
    # o palpite estava errado: o Pedro é o outro rótulo
    cli.main(["falantes", s.id, "Participante=Você", "--sem-publicar"])
    s = Sessao.abrir(s.pasta)
    segs, a = pipeline.carregar(s)
    assert segs[0]["speaker"] == "Participante" and segs[1]["speaker"] == "Você"
    assert s.m["celular"]["voce_confirmado"] and s.m["celular"]["trocado_de"] == "Participante"
    voce = next(p for p in a["participantes"] if p["rotulo"] == "Você")
    assert voce["confirmado"] and voce["nome"] == "Pedro"
    assert s.status_etapa("raio_x") == "ok"
    assert "--forcar estrutura" in capsys.readouterr().out


@precisa_ffmpeg
def test_confirmar_aceita_o_palpite_e_tipo_tira_do_pendente(raiz, tmp_path, falsos, cli):
    arq = _tom(tmp_path / "2026-10-14_1030.m4a")
    s = celular.importar(arq, participantes=["Mauro"], raiz=raiz, cfg=dict(CFG), log=lambda *a: None)
    cli.main(["confirmar", s.id, "--sem-publicar"])
    s = Sessao.abrir(s.pasta)
    _, a = pipeline.carregar(s)
    assert s.m["celular"]["voce_confirmado"] and "trocado_de" not in s.m["celular"]
    assert all(p["confirmado"] for p in a["participantes"])
    assert s.status_etapa("raio_x") == "ok"
    cli.main(["tipo", s.id, "cliente"])
    s = Sessao.abrir(s.pasta)
    assert s.tipo == "cliente" and s.caminho("entregavel.html").exists()
    assert s.status_etapa("publicacao") == "pendente"                 # publicar segue sendo decisão dele


# ── peças de verdade (Whisper, diarização com amostra de referência) ──────────
@pytest.mark.lento
@precisa_ffmpeg
def test_celular_ponta_a_ponta_com_amostra(raiz, tmp_path, monkeypatch):
    """As duas vozes SAPI das fixtures misturadas num arquivo só, como um celular na mesa; a
    amostra de referência sai do mic.opus (a voz de "Você")."""
    import numpy as np
    import audio
    monkeypatch.setattr(analise_fala, "FALA_DIR", tmp_path / "fala")
    monkeypatch.setattr(analise_fala, "_atualizar_vault", lambda linhas: None)
    mic = audio.ler_audio(FX / "mic.opus")
    ref = tmp_path / "ref.wav"
    audio.escrever_wav(ref, mic[: 16000 * 20])
    mix = tmp_path / "2026-10-14_1030.m4a"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(FX / "mic.opus"), "-i",
                    str(FX / "loop.opus"), "-filter_complex", "amix=inputs=2:normalize=0", str(mix)],
                   check=True)
    cfg = {"meu_nome": "Pedro", "idioma": "en", "model": "auto", "dispositivo": "auto",
           "estruturar": False, "diarizar": True, "audio_reter_dias": 30, "voz_referencia": str(ref)}
    s = celular.importar(mix, participantes=["Richard"], raiz=raiz, cfg=cfg, log=print)
    segs, _ = pipeline.carregar(s)
    cel = s.m["celular"]
    print(cel)
    assert cel["metodo"] == "referencia", cel
    # quanto de cada rótulo é, de fato, a voz do mic.opus (o "Pedro" do teste)
    falas_mic = transcribe._passada(transcribe.carregar_modelo("auto", "auto")[0], mic, "Você", idioma="en")

    def do_mic(x):
        return any(min(x["end"], m["end"]) - max(x["start"], m["start"]) > 0.5 for m in falas_mic)

    def pureza(rot):
        g = [x for x in segs if (x["speaker"] == "Você") == rot]
        return np.mean([do_mic(x) for x in g]) if g else 0.0
    # A diarização erra trechos nestas vozes sintéticas (medido em 14/10: 5 de 8 falas no rótulo
    # certo — ARQUITETURA §6 já registrava ~0,58), então o que se exige aqui é a IDENTIFICAÇÃO: o
    # grupo escolhido como "Você" é o que tem mais voz do Pedro.
    assert pureza(True) > pureza(False), (pureza(True), pureza(False), segs)
    assert s.status_etapa("raio_x") == "pendente"
