# -*- coding: utf-8 -*-
"""
Raio-X da Fala — análise PESSOAL/INTERNA do Pedro a partir da transcrição.

Roda localmente depois de transcrever. Analisa só as falas do "Você",
salva um relatório por reunião e acumula um histórico para acompanhar a
evolução. NUNCA sobe para o Worker nem entra no entregável do cliente.

Saída em Projetos/atas/fala-analise/ (fora do git, só nesta máquina):
  - historico.jsonl        (uma linha por reunião — fonte de verdade)
  - <stamp>_<titulo>.md    (relatório detalhado da reunião)
  - raio-x.html            (painel com todas as reuniões + tendência)

e a nota `sinapse/08-CRESCIMENTO/fala-raio-x.md`, que **não leva o título da reunião**:
título costuma ter nome de cliente ou assunto da Parresia, e o vault é outro
repositório. Na nota cada reunião aparece por data + tipo (v2, 30/09/2026).
"""
import json
import pathlib
import re
from collections import Counter

FALA_DIR = pathlib.Path(__file__).parent.parent / "fala-analise"
_WORD = re.compile(r"[a-zàáâãéêíóôõúûüç]+")

MULETAS = ["aí", "tá", "assim", "cara", "tipo", "então", "pô", "enfim", "sabe",
           "beleza", "basicamente", "literalmente", "exatamente", "praticamente",
           "realmente", "óbvio", "digamos", "mano", "simplesmente", "olha"]
FRASES = ["a gente", "por exemplo", "e aí", "tipo assim", "no caso", "quer dizer",
          "na verdade", "meio que", "ou seja", "é o seguinte", "de certa forma",
          "cada vez mais", "mais ou menos", "e tal", "muito simples"]   # "muito simples": abertura de explicação (14× em 05/10)
TAGS = ["entendeu", "certo", "né", "tá", "não é", "sabe", "correto", "beleza", "saca"]


def _toks(texto):
    return _WORD.findall(texto.lower())


def analisar(segments):
    """Calcula as métricas de fala a partir dos segmentos (speaker/start/text)."""
    voce = [s for s in segments if s.get("speaker") == "Você"]
    outro = [s for s in segments if s.get("speaker") != "Você"]
    blob = " ".join(s.get("text", "") for s in voce).lower()
    pals = _toks(blob)
    total = len(pals) or 1
    pals_outro = sum(len(_toks(s.get("text", ""))) for s in outro)
    dur_min = round(max((s.get("start", 0) for s in segments), default=0) / 60)

    stop = set("""a o e que de do da em um uma os as dos das no na nos nas por para com se eu
    você ele ela nós eles isso isto é são foi ser tem ter vai vou tá está já mais muito bem
    então aí né tipo assim cara certo entendeu sabe pô lá pra pro dele dela como mas ou também
    só até sem sobre entre quando qual quem porque a gente vamos esse essa este esta não sim
    ah eh me te se meu seu sua minha nesse dessa isso aqui ali""".split())
    conteudo = Counter(p for p in pals if p not in stop and len(p) > 2)

    confirm = {t: len(re.findall(r"\b" + re.escape(t) + r"\s*[?.,]", blob)) for t in TAGS}
    confirm = {k: v for k, v in confirm.items() if v > 0}
    conf_total = sum(confirm.values())
    muletas = {m: pals.count(m) for m in MULETAS}
    muletas = {k: v for k, v in sorted(muletas.items(), key=lambda x: -x[1]) if v > 0}
    bordoes = {f: len(re.findall(r"\b" + re.escape(f) + r"\b", blob)) for f in FRASES}
    bordoes = {k: v for k, v in sorted(bordoes.items(), key=lambda x: -x[1]) if v > 0}
    hedge = len(re.findall(r"\bacho que\b", blob))

    return {
        "dur_min": dur_min,
        "turnos_voce": len(voce),
        "turnos_outro": len(outro),
        "palavras_voce": len(pals),
        "palavras_outro": pals_outro,
        "vocab_unico": len(set(pals)),
        "share_fala": round(total / (total + pals_outro), 3) if (total + pals_outro) else 0,
        "conf_total": conf_total,
        "conf_por_min": round(conf_total / dur_min, 2) if dur_min else 0,
        "confirmacoes": dict(sorted(confirm.items(), key=lambda x: -x[1])),
        "muletas_por_1000": round(1000 * sum(muletas.values()) / total, 1),
        "muletas": muletas,
        "bordoes": bordoes,
        "hedge": hedge,
        "top_conteudo": conteudo.most_common(20),
    }


# ── v2.1 (06/10/2026): ritmo, turnos, interrupções, cansaço, voz e metas ─────
# O Pedro pediu "a análise da minha voz, da minha fala" de volta e mais completa. Tudo sai do que
# já existe: os tempos de cada fala (transcrição) e o áudio do microfone (só o canal dele).
_TAGS_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in TAGS) + r")\s*\?\s*$")

METAS_PADRAO = {
    "share_fala": [0.35, 0.55],       # fatia de fala: nem sumir nem dominar
    "conf_por_min": 0.5,              # "entendeu?/certo?" por minuto (era 3,11 em jul; ~0 em ago)
    "muletas_por_1000": 30,           # meta de [[fala-e-apresentacao]]: abaixo de 30, rumo a 20
    "ppm": [130, 180],                # palavras por minuto nos seus turnos: conversa clara sem arrastar
    "maior_monologo_s": 120,          # explicar demais: acima de 2 min sem deixar o outro entrar
    "ai_por_1000": 8,                 # meta 1 da nota fala-e-apresentacao: derrubar o "aí"
    "a_gente_por_1000": 8,            # meta 2: trocar "a gente" por sujeito claro
}


def _turnos(segments, junta_s=1.5):
    """Funde falas seguidas da mesma pessoa (pausa < junta_s e ninguém no meio) em turnos."""
    out = []
    for s in sorted(segments, key=lambda x: x.get("start", 0)):
        quem = "Você" if s.get("speaker") == "Você" else "outro"
        if out and out[-1]["quem"] == quem and s["start"] - out[-1]["end"] < junta_s:
            out[-1]["end"] = max(out[-1]["end"], s["end"])
            out[-1]["palavras"] += len(_toks(s.get("text", "")))
        else:
            out.append({"quem": quem, "start": s["start"], "end": s["end"],
                        "palavras": len(_toks(s.get("text", "")))})
    return out


def ritmo_e_turnos(segments):
    voce = [s for s in segments if s.get("speaker") == "Você"]
    outro = [s for s in segments if s.get("speaker") != "Você"]
    turnos = _turnos(segments)
    meus = [t for t in turnos if t["quem"] == "Você"]
    # ritmo pelo TURNO (inclui as pausas curtas): é o que o ouvinte sente. Pela soma dos trechos
    # transcritos dava 225 pal/min na reunião de 05/10 — os trechos não contam as pausas.
    fala_s = sum(t["end"] - t["start"] for t in meus)
    pals = sum(t["palavras"] for t in meus)
    maior = max(meus, key=lambda t: t["end"] - t["start"], default=None)
    # interrupção = começar a falar com o outro ainda falando (sobreposição real > 0,5 s)
    def sobrepoe(t, lista):
        return any(o["start"] < t["start"] - 0.5 and o["end"] > t["start"] + 0.5 for o in lista)
    interrompeu = sum(1 for t in meus if sobrepoe(t, outro))
    interrompido = sum(1 for t in turnos if t["quem"] == "outro" and sobrepoe(t, voce))
    # tempo de resposta: do fim da fala do outro até o começo da sua (só quando é você respondendo)
    resp = []
    for a, b in zip(turnos, turnos[1:]):
        if a["quem"] == "outro" and b["quem"] == "Você" and 0 <= b["start"] - a["end"] <= 8:
            resp.append(b["start"] - a["end"])
    perguntas = sum(1 for s in voce if s.get("text", "").strip().endswith("?")
                    and not _TAGS_RE.search(s.get("text", "").lower().strip()))
    return {
        "ppm": round(pals / (fala_s / 60), 1) if fala_s else 0,
        "fala_min": round(fala_s / 60, 1),
        "turnos": len(meus),
        "turno_medio_s": round(sum(t["end"] - t["start"] for t in meus) / len(meus), 1) if meus else 0,
        "maior_monologo_s": round(maior["end"] - maior["start"]) if maior else 0,
        "maior_monologo_em": round(maior["start"]) if maior else None,
        "interrompeu": interrompeu,
        "foi_interrompido": interrompido,
        "resposta_media_s": round(sum(resp) / len(resp), 2) if resp else None,
        "perguntas_reais": perguntas,
    }


def por_bloco(segments, bloco_min=30):
    """As métricas de palavra por bloco de tempo: mostra o cansaço (a reunião de 05/10 foi das 23 h às 2 h)."""
    if not segments:
        return []
    fim = max(s.get("end", 0) for s in segments)
    out, ini = [], 0.0
    while ini < fim:
        bs = [s for s in segments if ini <= s.get("start", 0) < ini + bloco_min * 60]
        voce = [s for s in bs if s.get("speaker") == "Você"]
        if voce:
            m = analisar(bs)
            m["dur_min"] = bloco_min
            m["conf_por_min"] = round(m["conf_total"] / bloco_min, 2)
            r = ritmo_e_turnos(bs)
            out.append({"de_min": round(ini / 60), "ate_min": round(min(ini / 60 + bloco_min, fim / 60)),
                        "palavras": m["palavras_voce"], "conf_por_min": m["conf_por_min"],
                        "muletas_por_1000": m["muletas_por_1000"], "ppm": r["ppm"],
                        "share_fala": m["share_fala"]})
        ini += bloco_min * 60
    return out


def _pcm_do_audio(caminho):
    """int16 mono 16 kHz do canal do microfone: o .pcm da gravação (memória mapeada) ou, depois de
    aposentado, o .opus decodificado pelo ffmpeg. None se não houver como ler."""
    import numpy as np
    import shutil
    import subprocess
    p = pathlib.Path(caminho) if caminho else None
    if not p or not p.exists():
        return None
    if p.suffix == ".pcm":
        return np.memmap(p, dtype=np.int16, mode="r")
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    r = subprocess.run([ff, "-v", "error", "-i", str(p), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.int16) if r.returncode == 0 and r.stdout else None


def _voz_de(frames_db, frames_f0):
    """Os números de voz de um conjunto de quadros (a reunião inteira ou um bloco)."""
    import numpy as np
    if len(frames_db) < 50 or len(frames_f0) < 50:
        return None
    db, f0 = np.array(frames_db), np.array(frames_f0)
    med = float(np.median(f0))
    st = 12 * np.log2(f0 / med)
    st = st[np.abs(st) < 12]                                  # erro de oitava fora
    return {"volume_db": round(float(np.median(db)), 1),
            "volume_variacao_db": round(float(np.std(db)), 1),
            "tom_hz": round(med),
            "tom_p10_hz": round(float(np.percentile(f0, 10))),
            "tom_p90_hz": round(float(np.percentile(f0, 90))),
            "entonacao_st": round(float(np.std(st)), 2)}


def voz(segments, caminho_mic, sr=16000, max_min=20, bloco_min=30):
    """Volume e entonação da SUA voz, medidos no áudio do microfone, só nos trechos em que você fala.
    Amostra até `max_min` minutos espalhados pela reunião (3 h de áudio inteiro é desperdício) e
    guarda a evolução por bloco de `bloco_min` min: tom que sobe = tensão; entonação que cai = cansaço.
    Entonação = variação do tom em semitons (1 semitom = duas teclas vizinhas do piano)."""
    import numpy as np
    x = _pcm_do_audio(caminho_mic)
    if x is None or len(x) < sr:
        return None
    voce = [s for s in segments if s.get("speaker") == "Você" and s["end"] - s["start"] >= 1.0]
    if not voce:
        return None
    total = sum(s["end"] - s["start"] for s in voce)
    passo = max(1, int(total / (max_min * 60)))
    amostra = voce[::passo]
    janela, salto = int(0.04 * sr), int(0.02 * sr)
    db, f0, por_bloco = [], [], {}
    lag_min, lag_max = sr // 400, sr // 75                    # tom de voz entre 75 e 400 Hz
    for s in amostra:
        seg = np.asarray(x[int(s["start"] * sr):int(s["end"] * sr)], dtype=np.float32) / 32768.0
        if len(seg) < janela:
            continue
        n = 1 + (len(seg) - janela) // salto
        idx = np.arange(janela)[None, :] + salto * np.arange(n)[:, None]
        q = seg[idx] * np.hanning(janela)
        rms = np.sqrt((q ** 2).mean(axis=1)) + 1e-9
        d = 20 * np.log10(rms)
        voz_on = d > (np.percentile(d, 60) if len(d) > 4 else d.min())   # só os quadros com voz
        espec = np.fft.rfft(q[voz_on], n=2 * janela)
        ac = np.fft.irfft(np.abs(espec) ** 2)[:, :janela]
        ac = ac / (ac[:, :1] + 1e-12)
        faixa = ac[:, lag_min:lag_max]
        lag = faixa.argmax(axis=1) + lag_min
        sonoro = faixa.max(axis=1) > 0.45                     # periodicidade clara = vogal
        d_on, f_on = d[voz_on].tolist(), (sr / lag[sonoro]).tolist()
        db.extend(d_on)
        f0.extend(f_on)
        b = por_bloco.setdefault(int(s["start"] // (bloco_min * 60)), ([], []))
        b[0].extend(d_on)
        b[1].extend(f_on)
    geral = _voz_de(db, f0)
    if not geral:
        return None
    geral["amostra_min"] = round(sum(s["end"] - s["start"] for s in amostra) / 60, 1)
    blocos = []
    for k in sorted(por_bloco):
        v = _voz_de(*por_bloco[k])
        if v:
            blocos.append({"de_min": k * bloco_min, **v})
    geral["blocos"] = blocos if len(blocos) >= 2 else []
    return geral


# ── leitura da voz: número sozinho não diz nada (pedido do Pedro, 06/10/2026) ─────────────
# Cada medida vira: o que é · a faixa · onde você está · o que fazer. As faixas são referências
# práticas de fala em reunião, não diagnóstico.
_FAIXAS_VOZ = {
    "entonacao_st": {
        "nome": "Entonação", "unidade": "semitons", "escala": (0, 7),
        "o_que_e": "Quanto o seu tom sobe e desce enquanto você fala. Um semitom é a distância entre "
                   "duas teclas vizinhas do piano. É o que faz a fala soar viva ou monótona.",
        "zonas": [(0, 1.5, "monótona", "a fala soa chapada e cansa quem ouve"),
                  (1.5, 2.2, "pouco variada", "dá para a fala soar mais expressiva"),
                  (2.2, 4.5, "viva", "faixa boa para conversa e apresentação"),
                  (4.5, 7, "agitada", "a fala pode soar ansiosa ou exaltada")],
        "dica": {"monótona": "suba o tom ao abrir uma ideia nova e desça no ponto final; leia um texto em voz alta marcando as ênfases.",
                 "pouco variada": "escolha uma palavra por frase para enfatizar, subindo o tom nela.",
                 "viva": "mantenha; cuide para não perder isso no fim das reuniões longas.",
                 "agitada": "faça pausas curtas antes das frases importantes e baixe o tom no final delas."}},
    "volume_variacao_db": {
        "nome": "Variação de volume", "unidade": "dB", "escala": (0, 12),
        "o_que_e": "Quanto o seu volume muda dentro das falas. É a ênfase: falar mais forte o que importa "
                   "e mais baixo o que é detalhe.",
        "zonas": [(0, 3, "chapada", "tudo no mesmo volume, sem ênfase"),
                  (3, 8, "com ênfase", "o volume acompanha o que importa"),
                  (8, 12, "oscilando", "pode ser o fone se afastando e se aproximando da boca")],
        "dica": {"chapada": "fale um pouco mais forte a palavra-chave de cada frase.",
                 "com ênfase": "mantenha.",
                 "oscilando": "mantenha o fone na mesma posição; se não for isso, controle o volume nas falas longas."}},
    "volume_db": {
        "nome": "Nível da gravação", "unidade": "dBFS", "escala": (-50, -10),
        "o_que_e": "O quanto a sua voz chega forte no microfone, em decibéis abaixo do máximo (0). "
                   "Depende do fone e da distância da boca, não de quanto você fala alto para o outro: "
                   "o aplicativo da chamada ajusta o volume. Serve para comparar reuniões com o mesmo fone.",
        "zonas": [(-50, -40, "muito baixo", "a transcrição pode perder palavras"),
                  (-40, -30, "baixo", "funciona, mas aproximar o microfone ajuda a transcrição"),
                  (-30, -18, "bom", "faixa ideal para gravação de fala"),
                  (-18, -10, "alto", "risco de distorcer nos picos")],
        "dica": {"muito baixo": "aproxime o microfone da boca ou suba o ganho dele no Windows.",
                 "baixo": "aproxime um pouco o microfone (uns dois dedos da boca, de lado).",
                 "bom": "mantenha.",
                 "alto": "afaste um pouco o microfone."}},
    "tom_hz": {
        "nome": "Tom da voz", "unidade": "Hz", "escala": (75, 300),
        "o_que_e": "A altura média da sua voz (grave ou aguda). Sozinha não é boa nem ruim: é a sua "
                   "voz. O que importa é se ela sobe ao longo da reunião (tensão, pressa) e quanto "
                   "varia (a entonação).",
        "zonas": [(75, 140, "grave", "é a sua voz natural, não há o que corrigir; olhe a evolução abaixo"),
                  (140, 200, "média", "é a sua voz natural, não há o que corrigir; olhe a evolução abaixo"),
                  (200, 300, "aguda", "é a sua voz natural, não há o que corrigir; olhe a evolução abaixo")],
        "dica": {}},
}


def _zona(chave, valor):
    zonas = _FAIXAS_VOZ[chave]["zonas"]
    for a, b, nome, efeito in zonas:
        if a <= valor < b:
            return nome, efeito
    return (zonas[0][2], zonas[0][3]) if valor < zonas[0][0] else (zonas[-1][2], zonas[-1][3])


def leitura_voz(v):
    """([{chave, nome, valor, unidade, o_que_e, zona, efeito, dica, escala, zonas}], [evolução em texto])."""
    import math
    if not v:
        return [], []
    itens = []
    for chave in ("entonacao_st", "volume_variacao_db", "volume_db", "tom_hz"):
        f = _FAIXAS_VOZ[chave]
        zona, efeito = _zona(chave, v[chave])
        extra = ""
        if chave == "tom_hz" and v.get("tom_p10_hz"):
            extra = f" Você usa de {v['tom_p10_hz']} a {v['tom_p90_hz']} Hz na maior parte das falas."
        itens.append({"chave": chave, "nome": f["nome"], "valor": v[chave], "unidade": f["unidade"],
                      "o_que_e": f["o_que_e"] + extra, "zona": zona, "efeito": efeito,
                      "dica": f["dica"].get(zona, ""), "escala": f["escala"], "zonas": f["zonas"]})
    evolucao = []
    bl = v.get("blocos") or []
    if len(bl) >= 2:
        ini, fim = bl[0], bl[-1]
        subida = 12 * math.log2(fim["tom_hz"] / ini["tom_hz"]) if ini["tom_hz"] else 0
        if subida >= 1.5:
            evolucao.append(f"O tom subiu {subida:.1f} semitons do começo ao fim ({ini['tom_hz']} → {fim['tom_hz']} Hz). "
                            "Costuma ser sinal de tensão ou pressa: respire antes de responder no fim da reunião.")
        elif subida <= -1.5:
            evolucao.append(f"O tom caiu {abs(subida):.1f} semitons do começo ao fim ({ini['tom_hz']} → {fim['tom_hz']} Hz): "
                            "a voz foi ficando mais baixa, o que costuma acompanhar o cansaço.")
        else:
            evolucao.append(f"O tom ficou estável do começo ao fim ({ini['tom_hz']} → {fim['tom_hz']} Hz): "
                            "sem sinal de tensão na voz.")
        de = fim["entonacao_st"] - ini["entonacao_st"]
        if de <= -0.5:
            evolucao.append(f"A entonação caiu de {ini['entonacao_st']} para {fim['entonacao_st']} semitons: a fala foi "
                            "ficando mais monótona. Em reunião longa, faça uma pausa ou encurte.")
        elif de >= 0.5:
            evolucao.append(f"A entonação subiu de {ini['entonacao_st']} para {fim['entonacao_st']} semitons: a fala ficou "
                            "mais expressiva (ou mais exaltada) no fim.")
        else:
            evolucao.append(f"A entonação se manteve ({ini['entonacao_st']} → {fim['entonacao_st']} semitons): "
                            "a voz não perdeu a vida com o cansaço.")
    return itens, evolucao


# ── postura (v2.2): o que a avaliação manual de 05/10 apontou, agora medido em toda reunião ──
CERTEZA = ["com certeza", "absolutamente", "obviamente", "óbvio", "claro que", "sem dúvida",
           "certeza absoluta", "100%", "com toda certeza"]
PROMESSA = ["já dá", "já existe", "já tem", "já faz", "isso faz", "dá pra fazer", "dá para fazer",
            "tranquilamente", "é muito fácil", "é só colocar", "é só importar",
            "em cinco minutos", "rapidinho"]
CONCESSAO = ["sem problema", "sem problemas", "tranquilo", "pode ser", "pode deixar", "fechado",
             "combinado", "pode sim"]


def _conta(frases, blob, sem_negacao=False):
    neg = r"(?<!não )(?<!nao )(?<!nem )" if sem_negacao else ""
    return {f: len(re.findall(neg + r"(?<!\w)" + re.escape(f) + r"(?!\w)", blob)) for f in frases}


def postura(segments, max_frases=15):
    """Sujeito, certeza, promessa no reflexo, concessão e corte. Só as falas de "Você".
    "Frases para revisar" = onde houve promessa ou certeza absoluta: é ali que nasce afirmação
    errada para o cliente (na reunião de 05/10, seis das erradas vieram de um "já dá")."""
    voce = [s for s in segments if s.get("speaker") == "Você"]
    blob = " ".join(s.get("text", "") for s in voce).lower()
    total = len(_toks(blob)) or 1
    eu = len(re.findall(r"(?<!\w)eu(?!\w)", blob))
    a_gente = len(re.findall(r"(?<!\w)a gente(?!\w)", blob))
    ai = len(re.findall(r"(?<!\w)aí(?!\w)", blob))
    cert = {k: v for k, v in _conta(CERTEZA, blob).items() if v}
    prom = {k: v for k, v in _conta(PROMESSA, blob, sem_negacao=True).items() if v}
    conc = {k: v for k, v in _conta(CONCESSAO, blob).items() if v}
    cortes = sum(1 for s in voce if re.match(r"\s*não[.,!]?\s+não\b", s.get("text", "").lower()))
    frases = []
    # "não dá pra fazer" não é promessa: a palavra logo antes não pode ser uma negação
    _neg = r"(?<!não )(?<!nao )(?<!nem )"
    for s in voce:
        t = s.get("text", "").lower()
        motivo = ("promessa" if any(re.search(_neg + r"(?<!\w)" + re.escape(p) + r"(?!\w)", t) for p in PROMESSA)
                  else "certeza" if any(re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", t) for c in CERTEZA)
                  else None)
        if motivo and len(_toks(t)) >= 5:          # "Muito simples." sozinho não diz nada
            frases.append({"t": round(s.get("start", 0)), "texto": s.get("text", "").strip(), "motivo": motivo})
    frases.sort(key=lambda f: (f["motivo"] != "promessa", f["t"]))
    return {
        "eu": eu, "a_gente": a_gente,
        "sujeito_claro": round(eu / (eu + a_gente), 2) if (eu + a_gente) else None,
        "a_gente_por_1000": round(1000 * a_gente / total, 1),
        "ai_por_1000": round(1000 * ai / total, 1),
        "certeza": cert, "certeza_total": sum(cert.values()),
        "promessa": prom, "promessa_total": sum(prom.values()),
        "concessao": conc, "concessao_total": sum(conc.values()),
        "cortes": cortes,
        "frases_revisar": sorted(frases[:max_frases], key=lambda f: f["t"]),
    }


def avaliar_metas(m, metas=None):
    """[(métrica, valor, meta em texto, ok?)] para o relatório, o painel e a janela."""
    mt = {**METAS_PADRAO, **(metas or {})}
    r = m.get("ritmo") or {}
    linhas = []
    lo, hi = mt["share_fala"]
    linhas.append(("Fatia de fala", f"{m['share_fala']*100:.0f}%", f"{lo*100:.0f}% a {hi*100:.0f}%",
                   lo <= m["share_fala"] <= hi))
    linhas.append(("Confirmações por minuto", m["conf_por_min"], f"até {mt['conf_por_min']}",
                   m["conf_por_min"] <= mt["conf_por_min"]))
    linhas.append(("Muletas a cada 1000 palavras", m["muletas_por_1000"], f"até {mt['muletas_por_1000']}",
                   m["muletas_por_1000"] <= mt["muletas_por_1000"]))
    if r.get("ppm"):
        a, b = mt["ppm"]
        linhas.append(("Ritmo (palavras por minuto)", r["ppm"], f"{a} a {b}", a <= r["ppm"] <= b))
    if r.get("maior_monologo_s") is not None:
        linhas.append(("Maior monólogo", f"{r['maior_monologo_s']} s", f"até {mt['maior_monologo_s']} s",
                       r["maior_monologo_s"] <= mt["maior_monologo_s"]))
    p = m.get("postura") or {}
    if p:
        # metas da nota [[fala-e-apresentacao]]: derrubar o "aí" e trocar "a gente" por sujeito claro
        linhas.append(('"Aí" a cada 1000 palavras', p["ai_por_1000"], f"até {mt['ai_por_1000']}",
                       p["ai_por_1000"] <= mt["ai_por_1000"]))
        linhas.append(('"A gente" a cada 1000 palavras', p["a_gente_por_1000"], f"até {mt['a_gente_por_1000']}",
                       p["a_gente_por_1000"] <= mt["a_gente_por_1000"]))
    return linhas


def _mmss(s):
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def _stamp(quando):
    return re.sub(r"[^0-9]", "", quando)[:12] or "000000000000"


def _upsert_historico(reg, pasta):
    hist_path = pasta / "historico.jsonl"
    linhas = []
    if hist_path.exists():
        for ln in hist_path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                linhas.append(json.loads(ln))
            except Exception:
                pass
    # Upsert pela chave data|título: reprocessar a mesma reunião corrige a linha
    # em vez de duplicá-la, senão a tendência do painel ficaria torta.
    linhas = [r for r in linhas if r.get("id") != reg["id"]]
    linhas.append(reg)
    linhas.sort(key=lambda r: r.get("data", ""))
    hist_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in linhas) + "\n",
        encoding="utf-8",
    )
    return linhas


def _relatorio_md(reg, pasta):
    m = reg["metrics"]
    L = [f"# Raio-X da Fala — {reg['titulo']}", "",
         f"_{reg['data']} · {m['dur_min']} min · USO INTERNO (não enviar ao cliente)_", "",
         "## Panorama",
         f"- Suas falas: **{m['turnos_voce']}** turnos / **{m['palavras_voce']}** palavras "
         f"(**{m['share_fala']*100:.0f}%** da reunião)",
         f"- Vocabulário único: {m['vocab_unico']}",
         f"- Pedidos de confirmação: **{m['conf_total']}** (~{m['conf_por_min']}/min)",
         f"- Muletas: {m['muletas_por_1000']} a cada 1000 palavras",
         f"- Hedge ('acho que'): {m['hedge']}", "",
         "## Perguntas-muleta (confirmação)"]
    for k, v in m["confirmacoes"].items():
        L.append(f"- {k}? — {v}")
    L += ["", "## Muletas (palavra solta)"]
    for k, v in m["muletas"].items():
        L.append(f"- {k} — {v}")
    L += ["", "## Bordões (frase)"]
    for k, v in m["bordoes"].items():
        L.append(f"- {k} — {v}")
    L += ["", "## Palavras de conteúdo mais repetidas"]
    for k, v in m["top_conteudo"]:
        L.append(f"- {k} — {v}")
    r = m.get("ritmo")
    if r:
        L += ["", "## Ritmo e turnos",
              f"- Ritmo: **{r['ppm']}** palavras por minuto de fala ({r['fala_min']} min falando)",
              f"- Turnos: {r['turnos']} · turno médio {r['turno_medio_s']} s · maior monólogo "
              f"**{r['maior_monologo_s']} s** (em {_mmss(r['maior_monologo_em'])})",
              f"- Interrupções: você interrompeu **{r['interrompeu']}** vezes; foi interrompido {r['foi_interrompido']}",
              f"- Tempo médio para responder: {r['resposta_media_s']} s" if r.get("resposta_media_s") is not None
              else "- Tempo médio para responder: —",
              f"- Perguntas de verdade (sem contar \"entendeu?\"): {r['perguntas_reais']}"]
    if m.get("blocos"):
        L += ["", "## Ao longo da reunião (cansaço)", "", "| Trecho | Fala | Ritmo | Conf/min | Mul/1k |",
              "|---|---|---|---|---|"]
        for b in m["blocos"]:
            L.append(f"| {b['de_min']}–{b['ate_min']} min | {b['share_fala']*100:.0f}% | {b['ppm']} | "
                     f"{b['conf_por_min']} | {b['muletas_por_1000']} |")
    v = m.get("voz")
    if v:
        itens, evolucao = leitura_voz(v)
        L += ["", "## Voz (áudio do microfone)",
              f"_Amostra: {v['amostra_min']} min das suas falas, espalhados pela reunião. As faixas são "
              "referências práticas de fala em reunião, não diagnóstico._"]
        for it in itens:
            faixas = " · ".join(f"{n} {a}–{b}" for a, b, n, _ in it["zonas"])
            L += ["", f"### {it['nome']}: {it['valor']} {it['unidade']} → **{it['zona']}**",
                  f"- O que é: {it['o_que_e']}",
                  f"- Faixas: {faixas}"]
            if it["efeito"]:
                L.append(f"- Você: {it['efeito']}.")
            if it["dica"]:
                L.append(f"- O que fazer: {it['dica']}")
        if evolucao:
            L += ["", "### A voz ao longo da reunião"] + [f"- {t}" for t in evolucao]
            L += ["", "| Bloco | Tom (Hz) | Entonação (st) | Variação de volume (dB) |", "|---|---|---|---|"]
            L += [f"| {b['de_min']} min | {b['tom_hz']} | {b['entonacao_st']} | {b['volume_variacao_db']} |"
                  for b in v["blocos"]]
    if m.get("metas"):
        L += ["", "## Metas", "", "| | Agora | Meta | |", "|---|---|---|---|"]
        for nome, val, meta, ok in m["metas"]:
            L.append(f"| {nome} | {val} | {meta} | {'✅' if ok else '⚠️'} |")
    p = pasta / f"{_stamp(reg['data'])}_{reg['safe']}.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ─────────────────────────────────────────────────────────────────────────────
# Alimenta o segundo cérebro (Sinapse): escreve uma nota AUTO-gerada de Fala no
# vault a cada reunião → aba Crescimento Pessoal. A narrativa/metas ficam na nota
# escrita à mão (fala-e-apresentacao); esta é só o retrato de dados, sobrescrevível.
_TIPO_ROTULO = {"cliente": "cliente", "parresia": "Parresia", "carreira": "carreira",
                "pessoal": "pessoal/estudo"}


def _nota_vault_md(linhas):
    ult = linhas[-1]["metrics"] if linhas else {}
    def _row(r):
        m = r["metrics"]
        top = ", ".join(list(m["muletas"])[:3]) or "—"
        tipo = _TIPO_ROTULO.get(r.get("tipo"), "—")
        ppm = (m.get("ritmo") or {}).get("ppm") or "—"
        return (f"| {str(r['data'])[:16]} | {tipo} | {m['dur_min']} | {m['share_fala']*100:.0f}% "
                f"| {m['conf_por_min']} | {m['muletas_por_1000']} | {ppm} | {top} |")
    tab = "\n".join(_row(r) for r in linhas[-8:])
    return "\n".join([
        "---", "tipo: nota", "area: crescimento",
        "tags: [comunicacao, fala, raio-x, auto-gerado]", "status: em-progresso",
        f"atualizado: {linhas[-1]['data'] if linhas else ''}", "---", "",
        "# 📈 Raio-X da Fala (auto)", "",
        "> ⚙️ **Nota auto-gerada** pelo sistema [[atas]] a cada reunião — não editar à mão. "
        "A narrativa e as metas ficam em [[fala-e-apresentacao]]. Dado pessoal, nunca vai ao cliente.", "",
        "## Agora",
        f"- Fatia de fala: **{ult.get('share_fala', 0)*100:.0f}%** (meta ~50%)",
        f"- Confirmações/min: **{ult.get('conf_por_min', 0)}** (menor = melhor)",
        f"- Muletas / 1000 palavras: **{ult.get('muletas_por_1000', 0)}**",
        f"- Ritmo: **{(ult.get('ritmo') or {}).get('ppm', '—')}** palavras/min · maior monólogo "
        f"**{(ult.get('ritmo') or {}).get('maior_monologo_s', '—')} s** · interrompeu "
        f"**{(ult.get('ritmo') or {}).get('interrompeu', '—')}** vezes",
        ("- Voz: " + " · ".join(f"{it['nome'].lower()} **{it['valor']} {it['unidade']}** ({it['zona']})"
                                for it in leitura_voz(ult["voz"])[0])
         if ult.get("voz") else "- Voz: sem áudio do microfone nesta reunião"),
        (f"- Postura: \"aí\" **{ult['postura']['ai_por_1000']}**/1k · \"a gente\" "
         f"**{ult['postura']['a_gente_por_1000']}**/1k (metas 1 e 2 de [[fala-e-apresentacao]]) · "
         f"promessa no reflexo **{ult['postura']['promessa_total']}** · certeza absoluta "
         f"**{ult['postura']['certeza_total']}**" if ult.get("postura") else "- Postura: —"),
        f"- Reuniões monitoradas: **{len(linhas)}**", "",
        "## Reunião a reunião (últimas)",
        "| Data | Tipo | Min | Fala | Conf/min | Mul/1k | Ritmo | Top muletas |",
        "|---|---|---|---|---|---|---|---|", tab, "",
        "## Conexões",
        "- Narrativa e metas: [[fala-e-apresentacao]]",
        "- Ferramenta: [[atas]]", "- Aba: [[MOC-crescimento]]", "",
    ])


def _atualizar_vault(linhas):
    """Grava a nota de Fala no vault do Sinapse, se ele existir.
    Vault = env SINAPSE_VAULT, senão ../../sinapse (irmão de atas). Devolve o caminho,
    None se o vault não existe nesta máquina; um erro de escrita LEVANTA (a etapa
    raio_x do pipeline registra) — na v1 era engolido em silêncio."""
    import os
    base = os.environ.get("SINAPSE_VAULT")
    vault = pathlib.Path(base) if base else pathlib.Path(__file__).parents[2] / "sinapse"
    destino = vault / "08-CRESCIMENTO"
    if not destino.exists():
        return None  # vault ausente nesta máquina
    p = destino / "fala-raio-x.md"
    p.write_text(_nota_vault_md(linhas), encoding="utf-8")
    return p


def processar(segments, titulo, quando, pasta=None, tipo=None, sessao_id=None, vault=True,
              audio_mic=None, metas=None, avaliacao_md=None):
    """Analisa, salva relatório .md, atualiza histórico, regenera o painel e
    alimenta o Sinapse. Retorna os caminhos gerados (vault=None se não gravou).
    v2.1: ritmo/turnos/interrupções, blocos de 30 min, voz (se `audio_mic` existir) e metas."""
    pasta = pathlib.Path(pasta) if pasta else FALA_DIR
    pasta.mkdir(exist_ok=True)
    metrics = analisar(segments)
    metrics["ritmo"] = ritmo_e_turnos(segments)
    metrics["postura"] = postura(segments)
    metrics["blocos"] = por_bloco(segments) if metrics["dur_min"] >= 45 else []
    try:
        metrics["voz"] = voz(segments, audio_mic) if audio_mic else None
    except Exception as e:                       # voz é bônus: nunca derruba o Raio-X
        metrics["voz"] = None
        metrics["voz_erro"] = f"{type(e).__name__}: {e}"
    metrics["metas"] = avaliar_metas(metrics, metas)
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in titulo).strip() or "reuniao"
    reg = {"id": sessao_id or f"{quando}|{titulo}", "data": quando, "titulo": titulo,
           "safe": safe, "tipo": tipo, "metrics": metrics}
    linhas = _upsert_historico(reg, pasta)
    md = _relatorio_md(reg, pasta)
    pagina = _escrever_pagina(reg, pasta, avaliacao_md)
    dash = _escrever_painel(linhas, pasta)
    nota = _atualizar_vault(linhas) if vault else None
    return {"md": md, "pagina": pagina, "dashboard": dash, "metrics": metrics, "vault": nota}


def _arquivo_pagina(reg):
    return f"{_stamp(reg['data'])}_{reg['safe']}.html"


def _escrever_pagina(reg, pasta, avaliacao_md=None):
    import raio_x_html
    destino = pasta / _arquivo_pagina(reg)
    destino.write_text(raio_x_html.pagina_reuniao(reg, avaliacao_md), encoding="utf-8")
    return destino


def _escrever_painel(linhas, pasta):
    import raio_x_html
    dash = pasta / "raio-x.html"
    dash.write_text(raio_x_html.painel(linhas, lambda r: _arquivo_pagina(r) if (pasta / _arquivo_pagina(r)).exists()
                                       else None), encoding="utf-8")
    return dash


def pagina_da_reuniao(sessao_id, avaliacao_md=None, pasta=None):
    """Regrava a página de uma reunião já analisada (ex.: quando a avaliação interna fica pronta,
    a página ganha a negociação e a postura). Devolve o caminho, ou None se não houver Raio-X."""
    pasta = pathlib.Path(pasta) if pasta else FALA_DIR
    hist = pasta / "historico.jsonl"
    if not hist.exists():
        return None
    linhas = [json.loads(ln) for ln in hist.read_text(encoding="utf-8").splitlines() if ln.strip()]
    reg = next((r for r in linhas if r.get("id") == sessao_id), None)
    if not reg or "safe" not in reg:
        return None
    destino = _escrever_pagina(reg, pasta, avaliacao_md)
    _escrever_painel(linhas, pasta)
    return destino


def reescrever_nota(pasta=None, tipos=None):
    """Regrava a nota do vault a partir do histórico, completando o `tipo` das
    linhas antigas com `tipos` ({id_do_historico: tipo}). Usado na migração v2."""
    pasta = pathlib.Path(pasta) if pasta else FALA_DIR
    hist = pasta / "historico.jsonl"
    if not hist.exists():
        return None
    linhas = [json.loads(ln) for ln in hist.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for r in linhas:
        if tipos and not r.get("tipo") and r.get("id") in tipos:
            r["tipo"] = tipos[r["id"]]
    hist.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in linhas) + "\n",
                    encoding="utf-8")
    return _atualizar_vault(linhas)
