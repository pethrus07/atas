# -*- coding: utf-8 -*-
"""MELHORIAS 10 (22/10/2026): trechos "Palavra Por Palavra" do turbo. Medido na reunião de 05/10: o canal da
chamada entrou nesse modo aos ~38 min e não saiu mais; o mesmo trecho transcrito sozinho sai normal. O
Whisper passa a rodar sem condition_on_previous_text, e a região que ainda sair picada é refeita sozinha
(sem hotwords) ou marcada com baixa confiança."""
import numpy as np

import transcribe

PICADO = ["Ele Ter Um", "Site Já Que", "Descreve Ele Pede", "Para Baixar Fala", "O Que Faz"]
NORMAL = "ele ter um site já que descreve, ele pede para baixar, fala o que faz."


class _W:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class _S:
    def __init__(self, texto, t0, passo=0.3):
        ws = texto.split()
        self.words = [_W(" " + w, t0 + i * passo, t0 + i * passo + 0.25) for i, w in enumerate(ws)]
        self.text, self.start, self.end = texto, t0, t0 + len(ws) * passo


class _Modelo:
    """1ª chamada: o áudio inteiro, com uma região picada no meio; as seguintes: `refeito`."""

    def __init__(self, refeito):
        self.chamadas = []
        self.refeito = refeito

    def transcribe(self, audio, **kw):
        self.chamadas.append((len(audio), kw))
        if len(self.chamadas) == 1:
            segs = [_S("Bom dia, vamos começar pela loja.", 0.0)]
            t = 10.0
            for p in PICADO * 2:
                segs.append(_S(p, t))
                t += 1.2
            segs.append(_S("e depois a gente vê o preço com calma.", 40.0))
            return segs, None
        return [_S(x, 0.5 + 3 * i) for i, x in enumerate(self.refeito)], None


def test_regioes_picadas_acha_so_a_palavra_por_palavra():
    segs = [{"start": 0.0, "end": 2.0, "text": "Bom dia, vamos começar pela loja do Valter."},
            *[{"start": 10.0 + i, "end": 10.8 + i, "text": p} for i, p in enumerate(PICADO)],
            {"start": 60.0, "end": 63.0, "text": "e depois a gente vê o preço com calma, tá bom?"}]
    assert transcribe.regioes_picadas(segs) == [(10.0, 14.8)]
    # nome próprio e começo de frase não contam
    assert transcribe.regioes_picadas([{"start": 0, "end": 3, "text": "O Pedro e o Valter. Foram ao Instituto ontem."}]) == []


def test_modo_legenda_por_janela_de_5_min():
    # cada pedaço de 2–3 palavras com maiúscula (05/10, 1:46: "Para poder | Nem as máquinas | Que eu tenho"):
    # a fala juntada fica em ~40% (nenhuma passa de 70%), mas a janela de 5 min passa de 30%
    pedacos = ["Para poder", "Nem as máquinas", "Que eu tenho", "Eu consigo testar", "Você entendeu",
               "Porque eu tenho", "Que pegar", "Um CLP"]
    segs = [{"start": 300.0 + 1.5 * i, "end": 301.0 + 1.5 * i, "text": pedacos[i % 8]} for i in range(60)]
    assert transcribe.regioes_picadas(segs) == [(300.0, 389.5)]
    normal = [{"start": 300.0 + 6 * i, "end": 305.0 + 6 * i,
               "text": "então a gente pega o CLP da Inovance e testa na rotuladora do Valter."} for i in range(20)]
    assert transcribe.regioes_picadas(normal) == []


def test_passada_sem_condicionar_e_refaz_a_regiao_picada():
    m = _Modelo([NORMAL])
    rel = []
    out = transcribe._passada(m, np.zeros(16000 * 50, dtype=np.float32), "Participante", ["Valter"], "pt", relatorio=rel)
    _, kw1 = m.chamadas[0]
    assert kw1["condition_on_previous_text"] is False and kw1["hotwords"] == "Valter"
    n2, kw2 = m.chamadas[1]
    assert "hotwords" not in kw2 and kw2["condition_on_previous_text"] is False
    assert n2 < 16000 * 50                                         # só a região, não o áudio inteiro
    textos = " ".join(s["text"] for s in out)
    assert "Ele Ter Um" not in textos and "descreve, ele pede" in textos
    assert textos.startswith("Bom dia") and textos.endswith("com calma.")       # o resto fica igual
    assert [s["start"] for s in out] == sorted(s["start"] for s in out)
    assert rel and rel[0]["refeito"] is True and rel[0]["baixa_confianca"] is False
    assert not any(s.get("baixa_confianca") for s in out)


def test_regiao_que_continua_picada_fica_com_baixa_confianca():
    m = _Modelo(PICADO * 2)
    rel = []
    out = transcribe._passada(m, np.zeros(16000 * 50, dtype=np.float32), "Participante", None, "pt", relatorio=rel)
    assert rel[0]["baixa_confianca"] is True
    marcados = [s for s in out if s.get("baixa_confianca")]
    assert marcados and all("Bom dia" not in s["text"] for s in marcados)


def test_condicionar_volta_pelo_config():
    m = _Modelo([NORMAL])
    transcribe._passada(m, np.zeros(16000 * 50, dtype=np.float32), "Você", None, "pt", condicionar=True)
    assert m.chamadas[0][1]["condition_on_previous_text"] is True
