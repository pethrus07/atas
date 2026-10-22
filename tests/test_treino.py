# -*- coding: utf-8 -*-
"""Modo treino (14/10/2026): o Pedro grava sozinho e recebe o Raio-X de monólogo + o retorno do Claude.

O que se garante aqui:
  - as métricas novas (pausas, palavras entre pausas, trecho mais corrido) com tempos sintéticos;
  - a leitura (4 números com faixa, onde ficou, comparação e o que fazer);
  - o ISOLAMENTO: treino não altera o historico.jsonl das reuniões, não escreve no vault (que é
    só lido para a nota de estudo), não aparece em `sessao.listar()`;
  - o retorno do Claude com schema fechado e a mesma auditoria de citação da ata (Claude mockado);
  - Claude que falha → o resultado sai só com as métricas e diz isso.
O teste lento roda o Whisper de verdade num áudio sintético (voz SAPI das fixtures)."""
import hashlib
import json
import pathlib

import numpy as np
import pytest

import analise_fala
import atas
import audio
import estruturar
import sessao
import treino

FX = pathlib.Path(__file__).parent / "fixtures"


def _palavras(roteiro, t0=0.5):
    """roteiro: lista de frases; cada frase é (texto, duração_por_palavra, pausa_depois)."""
    out, t = [], t0
    for texto, dur, pausa in roteiro:
        ws = texto.split()
        for i, w in enumerate(ws):
            out.append({"w": w, "start": round(t, 2), "end": round(t + dur, 2)})
            t += dur + (0.08 if i < len(ws) - 1 else 0)
        t += pausa
    return out


ROTEIRO = [
    ("A proposta resolve o atraso no fechamento do mês.", 0.30, 0.7),
    ("Hoje o financeiro perde dois dias conferindo planilha.", 0.30, 0.6),
    ("Aí a gente automatiza a conferência e tipo o relatório sai sozinho.", 0.22, 0.2),
    ("O próximo passo é eu te mandar o cronograma até sexta.", 0.30, 0.8),
]


# ── métricas ─────────────────────────────────────────────────────────────────
def test_pausas_e_corridas_com_tempos_sinteticos():
    ws = _palavras(ROTEIRO)
    pc = treino.pausas_e_corridas(ws)
    # pausas ≥0,5 s: depois da 1ª e da 2ª frase; a de 0,2 s (3ª) não conta; a da 4ª é depois da última palavra
    assert len(pc["pausas"]) == 2
    assert [round(d, 1) for _, d in pc["pausas"]] == [0.7, 0.6]
    # palavras entre pausas: 9 | 8 | 12 + 11 (a pausa de 0,2 s não corta)
    assert pc["corridas"] == [9, 8, 23]
    assert pc["fala_s"] == pytest.approx(ws[-1]["end"] - ws[0]["start"], abs=0.01)
    assert pc["pausa_s"] == pytest.approx(1.3, abs=0.01)
    assert treino.pausas_e_corridas([]) == {"pausas": [], "corridas": [], "fala_s": 0.0, "pausa_s": 0.0}


def test_trecho_mais_corrido_acha_a_janela_rapida():
    lento = [("um dois tres quatro cinco seis sete oito nove dez onze doze", 0.45, 0.6)] * 3
    rapido = [("depois disso eu explico tudo muito rapidamente sem respirar nenhuma vez entre as frases", 0.16, 0.0)] * 3
    ws = _palavras(lento + rapido + lento)
    tc = treino.trecho_mais_corrido(ws)
    ini_rapido = ws[36]["start"]                          # 3 frases lentas de 12 palavras
    assert ini_rapido - 1 <= tc["ini"] <= ini_rapido + 6
    assert tc["silabas_s"] > 5
    assert treino.trecho_mais_corrido(ws[:3]) is None     # fala curta demais


def test_medir_e_ler_dao_os_quatro_numeros_com_leitura():
    ws = _palavras(ROTEIRO * 6)
    m = treino.medir(ws, audio_voz=None, gravado_s=60, alvo=4.8, duracao_alvo_s=60)
    assert m["palavras"] == len(ws)
    assert m["pausas"] >= 12 and m["pausas_por_min"] > 0
    assert 0 < m["pausa_pct"] < 50
    assert m["articulacao_sil_s"] > m["silabas_por_s"] > 0       # articulação desconta as pausas
    assert m["muletas_puras"].get("aí") == 6 and m["muletas_puras"].get("tipo") == 6
    assert m["entonacao_st"] is None                             # sem áudio, sem voz
    principais, extras = treino.ler(m, {})
    assert [i["chave"] for i in principais] == ["silabas_por_s", "pausas_por_min", "muleta_pura_por_1000",
                                                "entonacao_st"]
    for it in principais + extras:                               # regra 4: nunca só o número
        assert it["o_que_e"] and it["faixa"] and it["onde"] and it["comparacao"]
        assert it["status"] in ("ok", "fora", "info", "sem")
    assert principais[3]["status"] == "sem"                      # entonação não medida, e diz
    assert principais[2]["status"] == "info"                     # sem reuniões: muleta sem meta
    assert {"articulacao_sil_s", "palavras_entre_pausas", "ai_por_1000", "duracao"} <= {i["chave"] for i in extras}


def test_ritmo_no_alvo_ou_acima():
    def ritmo(v, alvo=4.8):
        return treino.ler({"silabas_por_s": v, "alvo_silabas_s": alvo, "palavras": 400}, {})[0][0]
    assert ritmo(4.9)["status"] == "ok"                          # tolerância de 0,3
    assert ritmo(5.9)["status"] == "fora" and "acima do alvo" in ritmo(5.9)["onde"]
    assert ritmo(4.7, alvo=4.5)["status"] == "ok"
    assert ritmo(4.9, alvo=4.5)["status"] == "fora"


def test_comparar_ultimo_treino_do_mesmo_tipo_e_mediana_das_reunioes():
    treinos_ = [{"id": "a", "data": "2026-10-10T10:00", "tipo": "reuniao", "metrics": {"silabas_por_s": 5.5, "palavras_entre_pausas": 10}},
                {"id": "b", "data": "2026-10-11T10:00", "tipo": "tema", "metrics": {"silabas_por_s": 4.4}},
                {"id": "c", "data": "2026-10-12T10:00", "tipo": "reuniao", "metrics": {"silabas_por_s": 5.1, "palavras_entre_pausas": 14}},
                {"id": "d", "data": "2026-10-20T10:00", "tipo": "reuniao", "metrics": {"silabas_por_s": 4.0}}]
    reunioes = [{"id": f"r{i}", "data": f"2026-10-0{i}", "metrics": {
        "versao": 3, "palavras_voce": 2000, "ritmo": {"silabas_por_s": 5.8 + i / 10, "ppm": 200},
        "muleta_pura_por_1000": 30.0, "postura": {"ai_por_1000": 18.0}, "voz": {"entonacao_st": 3.1}}}
        for i in range(1, 4)] + [{"id": "curta", "data": "2026-10-05", "metrics": {"palavras_voce": 300}}]
    c = treino.comparar("reuniao", "novo", "2026-10-14T09:00", treinos_, reunioes)
    assert c["ultimo"]["silabas_por_s"] == 5.1                   # o anterior do mesmo tipo, não o de "tema" nem o futuro
    assert c["reunioes"]["silabas_por_s"] == {"mediana": 6.0, "n": 3}   # a curta (<1.000 palavras) fica fora
    assert c["reunioes"]["entonacao_st"]["mediana"] == 3.1
    assert c["reunioes"]["muleta_pura_por_1000"]["mediana"] == 30.0
    assert c["palavras_entre_pausas_treinos"]["mediana"] == 12
    it = treino.ler({"silabas_por_s": 5.2, "alvo_silabas_s": 4.8, "palavras": 400,
                     "muleta_pura_por_1000": 30.0}, c)[0]
    assert "último treino 5,1" in it[0]["comparacao"] and "suas reuniões 6" in it[0]["comparacao"]
    assert it[2]["status"] == "fora"                             # 30 > 30 − 20% = 24


# ── o retorno do Claude ──────────────────────────────────────────────────────
def _fechado(sch):
    if sch.get("type") == "object":
        assert sch.get("additionalProperties") is False, sch
        assert set(sch["required"]) == set(sch["properties"]), sch
        for v in sch["properties"].values():
            _fechado(v)
    if sch.get("type") == "array":
        _fechado(sch["items"])


def test_esquema_fechado_e_aspectos_por_tipo():
    for tipo in treino.ASPECTOS:                       # a leitura não tem retorno do Claude
        sch = treino.esquema(tipo)
        _fechado(sch)
        enum = sch["properties"]["pontos"]["items"]["properties"]["aspecto"]["enum"]
        assert enum == list(treino.ASPECTOS[tipo])
    assert "resultado_nao_metodo" in treino.ASPECTOS["reuniao"]
    assert "estrutura" in treino.ASPECTOS["tema"]
    assert "manter" in treino.prompt("reuniao") and treino.SEPARADOR_NOTA in treino.prompt("tema", com_nota=True)


def _retorno(cit_ok="o próximo passo é eu te mandar o cronograma até sexta"):
    return {
        "manter": {"texto": "Abriu com o problema do cliente.", "citacao": "A proposta resolve o atraso no fechamento", "t": "00:00"},
        "mudar": {"texto": "Prometeu método.", "citacao": "vou configurar o servidor Kubernetes amanhã", "t": "00:10"},
        "pontos": [{"aspecto": "compromisso", "situacao": "bom", "comentario": "Dono e prazo.", "citacao": cit_ok, "t": "00:20"},
                   {"aspecto": "ideia_central", "situacao": "bom", "comentario": "Logo no começo.", "citacao": None, "t": None}],
        "conteudo": [{"afirmacao": "o fechamento atrasa", "citacao": "o financeiro perde dois dias conferindo planilha",
                      "t": "00:03", "situacao": "confere", "trecho_nota": "o financeiro perde dois dias", "comentario": "ok"},
                     {"afirmacao": "x", "citacao": "o financeiro perde dois dias conferindo planilha", "t": "00:03",
                      "situacao": "diverge", "trecho_nota": "frase que não está na nota de jeito nenhum", "comentario": "y"}],
    }


def test_auditoria_do_retorno_igual_a_da_ata():
    ws = _palavras(ROTEIRO)
    r = treino.auditar_retorno(_retorno(), ws, nota_texto="Nota: o financeiro perde dois dias por mês.")
    assert r["manter"]["verificado"] is True and r["manter"]["t"] == "00:00"
    assert r["mudar"]["verificado"] is False and r["mudar"]["citacao"] is None      # inventada: perde a citação
    assert r["mudar"]["citacao_inventada"].startswith("vou configurar")
    assert r["pontos"][0]["verificado"] is True
    assert r["pontos"][0]["t"] != "00:20"                                           # corrigido para o da frase
    assert r["pontos"][1]["verificado"] is None
    assert r["conteudo"][0]["nota_verificada"] is True
    assert r["conteudo"][1]["nota_verificada"] is False


# ── isolamento e fluxo completo (Whisper e Claude substituídos) ──────────────
@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """SALVAS, FALA_DIR e o vault em pastas temporárias, com um histórico de reuniões real-like."""
    raiz = tmp_path / "atas-salvas"
    fala = tmp_path / "fala"
    fala.mkdir()
    hist = [{"id": f"r{i}", "data": f"2026-10-0{i}T10:00", "titulo": "Reunião X", "tipo": "cliente",
             "metrics": {"versao": 3, "palavras_voce": 3000, "ritmo": {"silabas_por_s": 5.9, "ppm": 200},
                         "muleta_pura_por_1000": 31.4, "postura": {"ai_por_1000": 17.9}}} for i in range(1, 6)]
    (fala / "historico.jsonl").write_text("\n".join(json.dumps(r) for r in hist) + "\n", encoding="utf-8")
    vault = tmp_path / "vault"
    (vault / "02-ESTUDO").mkdir(parents=True)
    (vault / "08-CRESCIMENTO").mkdir()
    (vault / "02-ESTUDO" / "fechamento.md").write_text("# Fechamento\n\nO financeiro perde dois dias por mês.\n",
                                                       encoding="utf-8")
    monkeypatch.setattr(sessao, "SALVAS", raiz)
    monkeypatch.setattr(analise_fala, "FALA_DIR", fala)
    monkeypatch.setenv("SINAPSE_VAULT", str(vault))
    monkeypatch.setattr(treino, "transcrever", lambda x, cfg, log=print: (_palavras(ROTEIRO * 3), {"modelo": "falso"}))
    return {"raiz": raiz, "fala": fala, "vault": vault}


def _foto(pasta):
    return {str(p.relative_to(pasta)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(pathlib.Path(pasta).rglob("*")) if p.is_file()}


def _treino_com_audio(segundos=20, **kw):
    t = treino.Treino.criar(kw.pop("tipo", "reuniao"), **kw)
    x = 0.2 * np.sin(2 * np.pi * 140 * np.arange(segundos * 16000) / 16000)
    (x * 32767).astype("<i2").tofile(str(t.mic_pcm))
    t.m["inicio"] = "2026-10-14T09:00:00-03:00"
    t.m["estado"] = "gravado"
    t.salvar()
    return t


def test_treino_nao_toca_no_historico_das_reunioes_nem_no_vault(ambiente, monkeypatch):
    chamadas = []

    def claude_falso(p, entrada, cfg, log=print, esquema=None):
        chamadas.append((p, entrada, esquema))
        return _retorno(), {"custo_usd": 0.01}
    monkeypatch.setattr(estruturar, "chamar_claude", claude_falso)
    antes_hist = _foto(ambiente["fala"])
    antes_vault = _foto(ambiente["vault"])
    t = _treino_com_audio(tipo="tema", assunto="fechamento", nota=str(treino.achar_nota("fechamento")))
    treino.analisar(t, {"estruturar": True, "audio_reter_dias": 30, "meu_nome": "Pedro"}, log=lambda *_: None)

    assert _foto(ambiente["vault"]) == antes_vault                       # vault só lido
    depois = _foto(ambiente["fala"])
    assert depois.pop("treinos.jsonl")                                    # só o histórico de treinos nasceu
    assert depois == antes_hist                                           # historico.jsonl intacto, nenhuma página
    assert sessao.listar(ambiente["raiz"]) == []                         # treino não é reunião
    assert t.pasta.parent == ambiente["raiz"] / "treinos"
    assert not (t.pasta / "sessao.json").exists() and (t.pasta / "treino.json").exists()
    assert (t.audio_dir / "mic.opus").exists() and not t.mic_pcm.exists()  # áudio compactado e conferido
    linhas = treino.ler_treinos()
    assert [r["id"] for r in linhas] == [t.id] and linhas[0]["tipo"] == "tema"
    # o Claude recebeu a nota e o schema do tipo
    p, entrada, esq = chamadas[0]
    assert treino.SEPARADOR_NOTA in entrada and "dois dias por mês" in entrada
    assert esq == treino.esquema("tema")
    res = treino.Treino.abrir(t.id).m["resultado"]
    assert res["retorno"]["mudar"]["verificado"] is False                # citação inventada marcada
    assert res["comparacao"]["reunioes"]["silabas_por_s"]["mediana"] == 5.9
    assert (t.pasta / "resultado.md").read_text(encoding="utf-8").count("Manter") == 1


def test_claude_que_falha_deixa_so_as_metricas_e_diz(ambiente, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("claude.exe não encontrado")
    monkeypatch.setattr(estruturar, "chamar_claude", quebra)
    t = _treino_com_audio()
    treino.analisar(t, {"estruturar": True, "audio_reter_dias": 30}, log=lambda *_: None)
    res = treino.Treino.abrir(t.id).m["resultado"]
    assert res["retorno"] is None and "não respondeu" in res["retorno_erro"]
    assert len(res["principais"]) == 4
    assert "Sem retorno do Claude" in (t.pasta / "resultado.md").read_text(encoding="utf-8")
    assert treino.ler_treinos()[0]["retorno"] is False


def test_retencao_apaga_audio_velho_e_respeita_manter(ambiente, monkeypatch):
    monkeypatch.setattr(estruturar, "chamar_claude", lambda *a, **k: (_retorno(), {}))
    velho, guardado = _treino_com_audio(), _treino_com_audio(assunto="guardar")
    for t in (velho, guardado):
        treino.analisar(t, {"estruturar": False, "audio_reter_dias": 30}, log=lambda *_: None)
    for t in (velho, guardado):                       # envelhece depois: o analisar também roda a retenção
        t.m["processado_em"] = "2026-08-01T10:00:00-03:00"
        t.salvar()
    guardado.m["manter"] = True
    guardado.salvar()
    assert treino.limpar_audio(30) == [velho.id]
    assert not velho.audio_dir.exists() and guardado.audio_dir.exists()


def test_trecho_wav_recorta_o_audio(ambiente):
    t = _treino_com_audio(segundos=10)
    wav = treino.trecho_wav(t, 2.0, 4.0)
    assert wav.exists() and len(audio.ler_audio(wav)) == pytest.approx(3 * 16000, abs=200)


def test_cli_treino_de_arquivo_e_lista(ambiente, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(estruturar, "chamar_claude", lambda *a, **k: (_retorno(), {}))
    monkeypatch.setattr(atas._config, "carregar", lambda: {"estruturar": True, "audio_reter_dias": 30})
    wav = tmp_path / "2026-10-14_0900.wav"
    audio.escrever_wav(wav, (0.2 * np.sin(np.arange(16000 * 15) / 10)).astype("float32"))
    atas.main(["treino", str(wav), "--assunto", "proposta"])
    out = capsys.readouterr().out
    assert "Ritmo" in out and "Manter" in out
    t = treino.achar("ultimo")
    assert t.m["inicio"].startswith("2026-10-14T09:00") and t.m["origem"] == "arquivo"
    assert wav.exists()                                                   # a origem não é tocada
    atas.main(["treinos"])
    assert "reuniao" in capsys.readouterr().out
    atas.main(["treinos", "--manter", t.id])
    assert treino.Treino.abrir(t.id).m["manter"] is True
    with pytest.raises(SystemExit):
        atas.main(["treino", str(wav), "--tipo", "palestra"])


# ── ponta a ponta com o Whisper de verdade ──────────────────────────────────
@pytest.mark.lento
def test_treino_ponta_a_ponta_com_audio_sintetico(tmp_path, monkeypatch):
    """A voz SAPI do mic.opus das fixtures (inglês, 41 s) como se fosse um treino importado."""
    monkeypatch.setattr(sessao, "SALVAS", tmp_path / "atas-salvas")
    monkeypatch.setattr(analise_fala, "FALA_DIR", tmp_path / "fala")
    monkeypatch.setenv("SINAPSE_VAULT", str(tmp_path / "vault-vazio"))
    t = treino.importar(FX / "mic.opus", "reuniao", "teste", duracao_alvo_s=60)
    treino.analisar(t, {"idioma": "en", "model": "auto", "dispositivo": "auto", "estruturar": False,
                        "vocabulario": False, "audio_reter_dias": 30}, log=print)
    m = treino.Treino.abrir(t.id).m["resultado"]["metrics"]
    print({k: m[k] for k in ("palavras", "silabas_por_s", "articulacao_sil_s", "pausas_por_min", "pausa_pct",
                             "palavras_entre_pausas", "entonacao_st")})
    assert m["palavras"] > 30
    assert m["fala_s"] > 20 and m["silabas_por_s"] > 1
    assert m["pausas"] >= 1 and m["articulacao_sil_s"] >= m["silabas_por_s"]
    assert m["trecho_corrido"] is not None
    assert not (tmp_path / "vault-vazio").exists()
    assert (t.audio_dir / "mic.opus").exists()


# ── leitura ritmada (22/10/2026) ────────────────────────────────────────────
def test_barras_a_cada_5_a_8_palavras_sem_juntar_por_cima_do_ponto():
    for e in treino.TEXTOS_LEITURA:
        tr = treino.com_barras(e["texto"])
        assert " ".join(tr) == " ".join(e["texto"].split())          # nada se perde nem se repete
        tamanhos = [len(x.split()) for x in tr]
        assert max(tamanhos) <= treino.BARRA_MAX
        assert sum(4 <= n <= 8 for n in tamanhos) >= 0.8 * len(tamanhos)
        assert not any(". " in x for x in tr)                          # ponto final é sempre barra
    assert treino.com_barras("Uma frase de onze palavras sem nenhuma vírgula no meio dela.") == \
        ["Uma frase de onze palavras sem", "nenhuma vírgula no meio dela."]


def test_texto_da_nota_tira_o_que_nao_e_prosa(tmp_path):
    p = tmp_path / "cap.md"
    p.write_text("---\ntipo: estudo\n---\n# CAP\n\n- item de lista que não entra\n\n"
                 "O teorema [[cap-e-consistencia|CAP]] diz que, numa partição de rede, o sistema escolhe entre "
                 "consistência e disponibilidade. Não dá para ter as duas ao mesmo tempo quando a rede se divide. "
                 "Por isso, bancos como o **Cassandra** preferem responder sempre, e acertam depois. Já um banco "
                 "relacional com réplica síncrona prefere recusar a escrita a responder errado.\n\n```\ncodigo()\n```\n",
                 encoding="utf-8")
    txt = treino.texto_da_nota(p)
    assert txt.startswith("O teorema CAP diz") and "**" not in txt and "item de lista" not in txt and "codigo" not in txt
    (tmp_path / "curta.md").write_text("# X\n\nSó isso aqui.\n", encoding="utf-8")
    assert treino.texto_da_nota(tmp_path / "curta.md") is None


def test_pausas_nas_barras_alinha_a_leitura_ao_texto():
    trechos = ["Quem ouve não tem o texto na mão.", "Cada frase precisa de um instante,", "e esse instante é a pausa."]
    # pausou na 1ª barra (0,6 s), não na 2ª (0,1 s); uma pausa de 0,7 s no meio do 2º trecho
    roteiro = [("Quem ouve não tem o texto na mão.", 0.25, 0.6), ("Cada frase precisa", 0.25, 0.7),
               ("de um instante,", 0.25, 0.1), ("e esse instante é a pausa.", 0.25, 0)]
    b = treino.pausas_nas_barras(_palavras(roteiro), trechos)
    assert b == {"barras": 2, "medidas": 2, "pausou": 1, "pct": 0.5, "lidas_pct": 1.0, "fora": 1}
    # palavra lida errada perto da barra: aquela barra não é medida
    roteiro[1] = ("Toda frase precisa", 0.25, 0.7)
    assert treino.pausas_nas_barras(_palavras(roteiro), trechos)["medidas"] == 1


def test_leitura_no_lugar_das_muletas_e_sem_claude(ambiente, monkeypatch):
    def nao_chame(*a, **k):
        raise AssertionError("leitura não chama o Claude")
    monkeypatch.setattr(estruturar, "chamar_claude", nao_chame)
    t = _treino_com_audio(tipo="leitura")
    lt = t.m["leitura"]
    assert t.m["alvo_silabas_s"] == treino.ALVO_LEITURA and lt["fonte"] == "embutido"
    assert t.m["duracao_alvo_s"] == round(analise_fala.silabas(lt["texto"]) / treino.ALVO_LEITURA)
    # a leitura "perfeita" do texto, com pausa de 0,6 s em cada barra
    monkeypatch.setattr(treino, "transcrever", lambda x, cfg, log=print: (
        _palavras([(tr, 0.22, 0.6) for tr in lt["trechos"]]), {"modelo": "falso"}))
    treino.analisar(t, {"estruturar": True, "audio_reter_dias": 30}, log=lambda *_: None)
    res = treino.Treino.abrir(t.id).m["resultado"]
    chaves = [it["chave"] for it in res["principais"]]
    assert chaves == ["silabas_por_s", "pausas_por_min", "barras", "entonacao_st"]
    barra = res["principais"][2]
    assert barra["status"] == "ok" and barra["valor"] == 1.0 and barra["curto"]
    assert res["extras"][0]["chave"] == "muleta_pura_por_1000"
    assert res["retorno"] is None and res["retorno_erro"] is None
    md = (t.pasta / "resultado.md").read_text(encoding="utf-8")
    assert "## O texto (embutido)" in md and treino.BARRA.join(lt["trechos"]) in md and "Sem retorno" not in md
    # a próxima leitura pega o texto seguinte do rodízio; com nota, o texto vem dela
    assert treino.Treino.criar("leitura").m["leitura"]["titulo"] != lt["titulo"]
    (ambiente["vault"] / "02-ESTUDO" / "pausa.md").write_text(
        "# Pausa\n\n" + " ".join(["A pausa organiza a fala e dá tempo para quem ouve guardar a ideia."] * 4) + "\n",
        encoding="utf-8")
    assert treino.Treino.criar("leitura", nota="pausa").m["leitura"]["fonte"] == "nota pausa"


# ── ritmo ao vivo na tela "Treinando" (22/10/2026) ─────────────────────────
def test_ritmo_da_janela():
    import ao_vivo
    ws = _palavras([("A proposta resolve o atraso no fechamento do mês.", 0.30, 0.7)] * 3)
    r = ao_vivo.ritmo_da_janela(ws)
    span = ws[-1]["end"] - ws[0]["start"]
    assert r == round(analise_fala.silabas(" ".join(w["w"] for w in ws)) / span, 2)
    assert ao_vivo.ritmo_da_janela(ws[:5]) is None                     # pouca fala: não diz nada


def test_ritmo_ao_vivo_le_os_ultimos_20_s_e_entrega(ambiente):
    import ao_vivo

    class W:
        def __init__(self, w, a, b):
            self.word, self.start, self.end = w, a, b

    class S:
        def __init__(self, ws):
            self.words = ws

    vistos = []

    class Modelo:
        def transcribe(self, x, **kw):
            vistos.append((len(x), kw))
            ws = _palavras([("A proposta resolve o atraso no fechamento do mês.", 0.30, 0.7)] * 3)
            return [S([W(w["w"], w["start"], w["end"]) for w in ws])], None
    t = _treino_com_audio(segundos=45)
    entregues = []
    rv = ao_vivo.RitmoAoVivo(t, {}, entregues.append, modelo=Modelo())
    r = rv.passo()
    assert entregues == [r] and r["silabas_s"] > 0 and r["palavras"] == 27
    n, kw = vistos[0]
    assert n == int(ao_vivo.RITMO_JANELA_S * 16000)                     # só a janela final, não o treino todo
    assert kw["word_timestamps"] and kw["beam_size"] == 1


def test_ritmo_na_tela_vermelho_so_acima_do_alvo():
    import app

    class Rot:
        def configure(self, **kw):
            self.kw = kw

    class Falso:
        gt, tctx, l_tritmo = object(), {"alvo": 4.8}, Rot()
    f = Falso()
    app.App._mostrar_ritmo(f, {"silabas_s": 5.3, "palavras": 30})
    assert f.l_tritmo.kw["style"] == "Alerta.TLabel" and "acima do alvo de 4,8" in f.l_tritmo.kw["text"]
    app.App._mostrar_ritmo(f, {"silabas_s": 4.9, "palavras": 30})
    assert f.l_tritmo.kw == {"text": "ritmo agora 4,9 sílabas/s", "style": "Sub.TLabel"}
