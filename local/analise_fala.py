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

# v3 (14/10/2026): muleta PURA (não carrega nada: dá para tirar sem mudar a frase) separada de
# MARCADOR de discurso (organiza a fala: "então", "tá", "assim"; não é defeito em si). Antes tudo era
# "muleta", inclusive o "tá" verbo ("tá funcionando") — 13/10 deu 77,2/1k, com boa parte disso marcador.
# O Whisper apaga as pausas preenchidas ("éé", "hum"), então o número mede palavras, não hesitação.
MULETAS_PURAS = ["aí", "tipo", "cara", "pô", "mano", "enfim", "basicamente", "literalmente",
                 "simplesmente", "digamos"]          # "tipo assim" conta uma vez, pelo "tipo"
MARCADORES = ["então", "tá", "assim", "exatamente", "né", "beleza", "olha", "sabe", "realmente",
              "praticamente", "óbvio", "tá ligado"]
MULETAS = MULETAS_PURAS + MARCADORES                 # compatibilidade: a soma das duas listas
FRASES = ["por exemplo", "e aí", "tipo assim", "no caso", "quer dizer",
          "na verdade", "meio que", "ou seja", "é o seguinte", "de certa forma",
          "cada vez mais", "mais ou menos", "e tal", "muito simples"]   # "muito simples": abertura de explicação (14× em 05/10)
# "a gente" saiu dos bordões em 14/10/2026: é o pronome padrão de 1ª pessoa do plural no pt-BR falado
# (Omena 2003). Continua aparecendo, sem tom de defeito, na postura ("eu" × "a gente").
TAGS = ["entendeu", "certo", "né", "tá", "não é", "sabe", "correto", "beleza", "saca", "tá ligado"]
VERSAO = 3                     # 3 = Raio-X calibrado (14/10/2026); linhas sem o campo são da v2

_LETRA = "a-zàáâãéêíóôõúûüç"
_TOK_SEP = re.compile(rf"([{_LETRA}]+)([^{_LETRA}]*)")
_PONTUACAO = re.compile(r"[?.,!;:…—–]")
# antes do "tá": quem faz dele um verbo ("isso tá", "não tá", "a gente tá")
_SUJEITO_OU_ADV = set("""eu você voce ele ela eles elas vocês gente isso isto aquilo não já ainda que
    tudo nada quem onde aqui lá ali só também sempre nunca agora hoje ninguém algo""".split())
# depois do "tá": palavras que mostram que ele foi só marcador ("tá, então…", "tá e aí")
_DEPOIS_DO_TA_MARCADOR = set("tá então e mas aí né tipo cara pô mano enfim assim olha entendi vamos deixa porque".split())
# antes de "tipo"/"cara": determinante = substantivo ("esse tipo", "o cara"), não muleta
_DETERMINANTES = set("""o a os as um uma uns umas esse essa este esta aquele aquela que qual quais cada todo
    toda outro outra mesmo mesma meu minha seu sua teu tua nosso nossa do da no na dum duma num numa desse
    dessa nesse nessa deste desta algum alguma nenhum nenhuma qualquer tal novo""".split())


def _toks(texto):
    return _WORD.findall(texto.lower())


def classificar_palavras(texto):
    """Conta muletas puras e marcadores num texto, separando os usos que não são muleta:
    - "tá" VERBO não conta: depois de sujeito/negação/advérbio ("isso tá", "não tá") ou seguido de
      palavra na mesma oração ("tá funcionando", "tá pronto", "tá bom"). "tá bom", "tá certo", "tá ok"
      contam como concordância (verbo), não como muleta.
    - "tá?" / "né?" / "sabe?" com interrogação são CONFIRMAÇÃO (contadas à parte), não marcador.
    - "tipo"/"cara" depois de determinante ("esse tipo", "o cara") ou antes de "de" são substantivo.
    Limite: a vírgula do Whisper decide o que é "mesma oração"; sem pontuação, "tá" + palavra vira verbo.
    Devolve (puras Counter, marcadores Counter, {"ta_verbo", "substantivo", "tags"})."""
    puras, marc = Counter(), Counter()
    outros = Counter()
    toks = _TOK_SEP.findall(str(texto or "").lower())
    pular = set()
    for i, (w, sep) in enumerate(toks):
        if i in pular:
            continue
        ant, sep_ant = (toks[i - 1] if i else ("", "."))
        prox = toks[i + 1][0] if i + 1 < len(toks) else ""
        colado_ant = bool(ant) and not _PONTUACAO.search(sep_ant)
        colado_prox = bool(prox) and not _PONTUACAO.search(sep)
        if w in TAGS and "?" in sep:
            outros["tags"] += 1
            continue
        if w == "tá" and colado_prox and prox == "ligado":   # "tá ligado" = "sabe": marcador; com "?", confirmação
            pular.add(i + 1)
            if "?" in toks[i + 1][1]:
                outros["tags"] += 1
            else:
                marc["tá ligado"] += 1
        elif w == "tá":
            if (colado_ant and ant in _SUJEITO_OU_ADV) or (colado_prox and prox not in _DEPOIS_DO_TA_MARCADOR):
                outros["ta_verbo"] += 1
            else:
                marc["tá"] += 1
        elif w == "sabe":
            if (colado_ant and ant in _SUJEITO_OU_ADV) or colado_prox:
                continue                                      # "você sabe", "sabe fazer": verbo
            marc["sabe"] += 1
        elif w in ("tipo", "cara"):
            if (colado_ant and ant in _DETERMINANTES) or (colado_prox and prox in ("de", "do", "da", "dos", "das")):
                outros["substantivo"] += 1
            else:
                puras[w] += 1
                if w == "tipo" and colado_prox and prox == "assim":
                    pular.add(i + 1)                          # "tipo assim" = uma muleta só
        elif w in MULETAS_PURAS:
            puras[w] += 1
        elif w in MARCADORES:
            marc[w] += 1
    return puras, marc, dict(outros)


def _por_mil(n, total):
    return round(1000 * n / total, 1) if total else 0.0


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

    # confirmação = a tag COM interrogação ("entendeu?", "tá?"); "tá," e "né." são concordância/marcador
    confirm = {t: len(re.findall(r"(?<!\w)" + re.escape(t) + r"\s*\?", blob)) for t in TAGS}
    confirm = {k: v for k, v in confirm.items() if v > 0}
    conf_total = sum(confirm.values())
    puras, marc, outros = Counter(), Counter(), Counter()
    for s in voce:                         # por fala: a pontuação de uma não vaza para a outra
        p_, m_, o_ = classificar_palavras(s.get("text", ""))
        puras.update(p_)
        marc.update(m_)
        outros.update(o_)
    ordena = lambda c: {k: v for k, v in sorted(c.items(), key=lambda x: -x[1]) if v > 0}
    muletas = ordena(puras + marc)
    bordoes = {f: len(re.findall(r"(?<!\w)" + re.escape(f) + r"(?!\w)", blob)) for f in FRASES}
    bordoes = {k: v for k, v in sorted(bordoes.items(), key=lambda x: -x[1]) if v > 0}
    hedge = len(re.findall(r"\bacho que\b", blob))

    return {
        "versao": VERSAO,
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
        "muleta_pura_por_1000": _por_mil(sum(puras.values()), total),
        "marcador_por_1000": _por_mil(sum(marc.values()), total),
        "muletas_puras": ordena(puras),
        "marcadores": ordena(marc),
        "ta_verbo": outros.get("ta_verbo", 0),
        "muletas_por_1000": _por_mil(sum(muletas.values()), total),     # puras + marcadores
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
    "share_fala": [0.35, 0.55],       # fatia de fala em cliente sem formato informado (ver faixa_fatia)
    "conf_por_min": 0.5,              # "entendeu?/certo?" por minuto (era 3,11 em jul; ~0 em ago)
    "ppm": [130, 180],                # palavras por minuto nos seus turnos: conversa clara sem arrastar
    "maior_monologo_s": 120,          # explicar demais: acima de 2 min sem deixar o outro entrar (Gong: até 150 s)
    # v3 (14/10/2026) — o "aí" desce em degraus pelos DADOS: ≤20; quando a mediana das últimas 5
    # reuniões (≥1.000 palavras) ficar ≤20, a meta vira ≤15. A meta antiga (≤8) era inalcançável (29,8).
    "ai_por_1000": [20, 15],
    "muleta_pura_reducao": 0.20,      # meta da muleta pura = mediana das últimas 5 −20%
    "resposta_s": [0.6, 1.0],         # paciência (Gong): esperar 0,6–1 s antes de responder
    "tomou_vez_por_10min": 1,         # heurística inicial: tomar a vez ≤1 a cada 10 min
    "perguntas_abertas": [11, 16],    # descoberta (Gong 2025: 15–16 nas ganhas; 11–14, fonte secundária)
    "min_palavras": 1000,             # abaixo disso, nenhuma meta é julgada: amostra pequena
}
# Norma de João Pessoa (RBCS/UFPB 2019, adultos 18–27 anos, fala semi-espontânea): 4,2 ± 0,7 sílabas/s
# e 125–134 palavras/min. https://periodicos.ufpb.br/ojs2/index.php/rbcs/article/download/48420/28324
NORMA_SILABAS_S = (4.2, 0.7)
NORMA_PPM = (125, 134)
_FORTES = set("aeoáéíóúâêôãõà")
_VOGAIS = re.compile(r"[aeiouáéíóúâêôãõàü]+")


def silabas(texto):
    """Sílabas por núcleo vocálico, em pt-BR, com ajuste simples de ditongo: num grupo de vogais,
    cada vogal forte (a, e, o, acentuadas) é um núcleo; i/u sem acento junto de forte é semivogal
    ("muito", "coisa", "quero"); depois de ã/õ, o "o"/"e" é semivogal ("pão", "mãe"); grupo só de
    i/u conta 1 ("fui"). Limite: hiato com i/u átono ("dia", "rua") conta 1 — na fala rápida
    costuma mesmo virar uma sílaba —, e número escrito em algarismo não conta."""
    n = 0
    for w in _toks(texto):
        for grupo in _VOGAIS.findall(w):
            k, nasal = 0, False
            for ch in grupo:
                if ch in _FORTES and not (nasal and ch in "eo"):
                    k += 1
                nasal = ch in "ãõ"
            n += max(1, k)
    return n


# perguntas abertas: pedem explicação, não sim/não
_ABERTA = re.compile(r"(?<!\w)(como|por que|porquê|o que|o quê|qual|quais|quant[oa]s?|quando|onde|aonde|"
                     r"quem|me conta|me explica|me fala|me diz|me descreve|de que forma|pra que|para que)(?!\w)")


def pergunta_aberta(texto):
    """A pergunta (a última frase com "?") pede explicação? Limite: "você viu o que eu mandei?"
    tem "o que" e é fechada; "e o preço?" não tem marcador e é aberta."""
    frases = [f for f in re.split(r"(?<=[.!?…])\s+", str(texto or "").strip()) if f.strip()]
    alvo = next((f for f in reversed(frases) if f.rstrip().endswith("?")), frases[-1] if frases else "")
    return bool(_ABERTA.search(alvo.lower()))


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
    # sobreposição = começar a falar com o outro ainda falando (sobreposição real > 0,5 s)
    def sobrepoe(t, lista):
        return any(o["start"] < t["start"] - 0.5 and o["end"] > t["start"] + 0.5 for o in lista)
    def falando_em(instante, lista):
        return any(o["start"] <= instante < o["end"] for o in lista)
    # v3: a sobreposição se divide em "tomou a vez" (o outro para em até 2 s depois que você começa e
    # você fala ≥2 s) e "apoio" (≤1 s ou ≤2 palavras: "isso", "uhum", "sim"). O resto (falaram juntos e
    # ninguém cedeu) fica só no total `interrompeu`, que guarda o sentido antigo.
    tomou = apoio = interrompeu = 0
    for t in meus:
        if not sobrepoe(t, outro):
            continue
        interrompeu += 1
        dur = t["end"] - t["start"]
        if dur <= 1.0 or t["palavras"] <= 2:
            apoio += 1
        elif dur >= 2.0 and not falando_em(t["start"] + 2.0, outro):
            tomou += 1
    interrompido = sum(1 for t in turnos if t["quem"] == "outro" and sobrepoe(t, voce))
    # tempo de resposta: do fim da fala do outro até o começo da sua (só quando é você respondendo)
    resp = []
    for a, b in zip(turnos, turnos[1:]):
        if a["quem"] == "outro" and b["quem"] == "Você" and 0 <= b["start"] - a["end"] <= 8:
            resp.append(b["start"] - a["end"])
    perg = [s for s in voce if s.get("text", "").strip().endswith("?")
            and not _TAGS_RE.search(s.get("text", "").lower().strip())]
    abertas = [s for s in perg if pergunta_aberta(s.get("text", ""))]
    fechadas = [s for s in perg if not pergunta_aberta(s.get("text", ""))]
    # sílabas: elocução = pelo tempo do turno (com as pausas curtas); articulação = só o tempo dentro
    # das falas transcritas (desconta as lacunas entre trechos do mesmo turno)
    sil = sum(silabas(s.get("text", "")) for s in voce)
    trechos_s = sum(max(0.0, s["end"] - s["start"]) for s in voce)
    reuniao_s = (max((s["end"] for s in segments), default=0) - min((s["start"] for s in segments), default=0))
    return {
        "ppm": round(pals / (fala_s / 60), 1) if fala_s else 0,
        "fala_min": round(fala_s / 60, 1),
        "silabas": sil,
        "silabas_por_s": round(sil / fala_s, 2) if fala_s else 0,
        "articulacao_sil_s": round(sil / trechos_s, 2) if trechos_s else 0,
        "turnos": len(meus),
        "turno_medio_s": round(sum(t["end"] - t["start"] for t in meus) / len(meus), 1) if meus else 0,
        "maior_monologo_s": round(maior["end"] - maior["start"]) if maior else 0,
        "maior_monologo_em": round(maior["start"]) if maior else None,
        "interrompeu": interrompeu,
        "tomou_vez": tomou,
        "apoio": apoio,
        "tomou_vez_por_10min": round(10 * tomou / (reuniao_s / 60), 2) if reuniao_s > 0 else 0,
        "foi_interrompido": interrompido,
        "resposta_media_s": round(sum(resp) / len(resp), 2) if resp else None,
        "respostas": len(resp),
        "atropelo_pct": round(100 * sum(1 for x in resp if x < 0.3) / len(resp)) if resp else None,
        "perguntas_reais": len(perg),
        "perguntas_abertas": len(abertas),
        "perguntas_fechadas": len(fechadas),
        "exemplos_fechadas": [{"t": round(s.get("start", 0)), "texto": s.get("text", "").strip()}
                              for s in fechadas[:5]],
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
                        "muletas_por_1000": m["muletas_por_1000"],
                        "muleta_pura_por_1000": m["muleta_pura_por_1000"], "ppm": r["ppm"],
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
                   "duas teclas vizinhas do piano. É o que faz a fala soar expressiva ou monótona.",
        "fonte": "homens brasileiros falam com ~2,9–3 semitons (Arantes, Abralin); para apresentar, mire 3 ou mais",
        "zonas": [(0, 1.5, "monótona", "a fala soa chapada e cansa quem ouve"),
                  (1.5, 2.2, "pouco variada", "dá para a fala soar mais expressiva"),
                  (2.2, 4.5, "típica", "na média da fala masculina brasileira; em apresentação, 3 ou mais"),
                  (4.5, 7, "agitada", "a fala pode soar ansiosa ou exaltada")],
        "dica": {"monótona": "suba o tom ao abrir uma ideia nova e desça no ponto final; leia um texto em voz alta marcando as ênfases.",
                 "pouco variada": "escolha uma palavra por frase para enfatizar, subindo o tom nela.",
                 "típica": "mantenha; ao apresentar, fique em 3 semitons ou mais e cuide para não cair no fim das reuniões longas.",
                 "agitada": "faça pausas curtas antes das frases importantes e baixe o tom no final delas."}},
    "volume_variacao_db": {
        "nome": "Variação de volume", "unidade": "dB", "escala": (0, 12),
        "fonte": "referência prática de fala em reunião, não norma publicada",
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
        "fonte": "referência prática de gravação de fala, não norma publicada",
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
        "fonte": "sem faixa boa ou ruim: o que se lê é a evolução",
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
                      "o_que_e": f["o_que_e"] + extra, "zona": zona, "efeito": efeito, "fonte": f.get("fonte", ""),
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


# ── compromisso com dono e prazo (v3, 14/10/2026) ───────────────────────────────────────────
# Troca a antiga meta de "a gente": o problema nunca foi o pronome, e sim o compromisso que sai sem
# quem faz e sem quando ("a gente vai ver isso"). Prazo: a mesma detecção da auditoria da ata.
# Duas formas: (1) a ação já no presente, na 1ª pessoa ("eu te mando", "eu faço", "fica pronto");
# (2) futuro + VERBO DE ENTREGA ("vou mandar", "a gente vai revisar", "você vai me passar"). Sem o verbo
# de entrega, "vou ser bem-sucedido", "você vai querer", "vamos pegar um exemplo" não são compromisso.
_DIRETO = re.compile(
    r"(?<!\w)(?:(?P<eu>(?:eu|já) (?:te |lhe )?(?:faço|mando|envio|passo|entrego|resolvo|retorno|preparo|monto|"
    r"ajusto|corrijo|termino|confiro|reviso|devolvo|organizo|levanto)|te (?:mando|envio|passo|entrego|retorno|"
    r"devolvo)|deixo pront[oa])"
    r"|(?P<gente>fica pront[oa]|vai ficar pront[oa]|vai estar pront[oa]))(?!\w)")
_FUTURO = re.compile(r"(?<!\w)(?:(?P<eu>eu vou|vou)|(?P<voce>você vai|vocês vão)|(?P<gente>a gente vai|vamos))(?!\w)")
_ACAO = set("""mandar enviar passar entregar fazer preparar montar ajustar corrigir resolver terminar finalizar
    revisar conferir organizar publicar subir criar gravar escrever retornar ligar marcar agendar levantar orçar
    cotar verificar testar configurar instalar desenvolver implementar documentar atualizar pagar cobrar assinar
    providenciar analisar avaliar fechar formalizar definir alinhar apresentar encaminhar devolver deixar
    conversar refazer cadastrar estudar pesquisar validar aprovar contratar emitir""".split())
# entre o futuro e o verbo: pronome e advérbio curto ("vou te mandar", "vou já fazer", "vou estar mandando")
_ENCOSTO = set("te lhe me só agora aqui já então também ainda estar".split())


def _verbo_de_entrega(palavras):
    """A primeira palavra depois dos encostos é verbo de entrega? Aceita o gerúndio ("mandando")."""
    for i, w in enumerate(palavras):
        if w in _ENCOSTO:
            continue
        inf = w[:-3] + "r" if w.endswith("ndo") else w
        prox = palavras[i + 1] if i + 1 < len(palavras) else ""
        if inf == "fazer" and prox in ("assim", "da", "o", "a", "uma", "um") and \
                (prox in ("assim", "da") or palavras[i + 2:i + 3] in (["seguinte"], ["matemática"], ["conta"], ["exemplo"])):
            return False                                   # "vamos fazer assim", "fazer a conta": raciocínio
        return inf in _ACAO or (inf == "falar" and "com" in palavras)
    return False


def compromissos(segments, nomes=None, janela_s=20, max_frases=15):
    """Frases de compromisso nas falas de "Você": quantas com dono (eu/você/nome; "vou" conta como
    você mesmo, na 1ª pessoa) e quantas com prazo dito na mesma frase ou nas suas falas dos `janela_s`
    seguintes (prazo = ata.expressao_de_prazo, a mesma detecção da auditoria da ata). Limites: só acha
    o que segue os padrões (futuro + verbo de entrega, ou a ação na 1ª pessoa); "vamos cadastrar uma
    máquina" numa demo passa como compromisso; frase cortada ("Ou você vai...") fica de fora."""
    import ata as _ata
    voce = sorted((s for s in segments if s.get("speaker") == "Você"), key=lambda s: s.get("start", 0))
    nomes = [n.strip().lower() for n in (nomes or []) if n and n.strip()]
    re_nome = (re.compile(r"(?<!\w)(?:o |a )?(" + "|".join(re.escape(n) for n in nomes)
                          + r") (?:vai|fica de|ficou de|me manda|te manda|manda|envia|passa|entrega|resolve)(?!\w)")
               if nomes else None)
    achados = []
    for i, s in enumerate(voce):
        texto = s.get("text", "")
        for f in (f for f in re.split(r"(?<=[.!?…])\s+", texto.strip()) if f.strip()):
            if f.rstrip().endswith(("?", "...", "…")):
                continue                                   # pergunta ou frase cortada
            fl = f.lower()
            achou, dono = False, None
            for rx in (_DIRETO, _FUTURO):
                for mt_ in rx.finditer(fl):
                    if fl[:mt_.start()].rstrip().endswith(("não", "nem", "nunca")):
                        continue
                    if rx is _FUTURO and not _verbo_de_entrega(_toks(fl[mt_.end():])[:4]):
                        continue
                    achou = True
                    dono = "eu" if mt_.group("eu") else "você" if mt_.groupdict().get("voce") else None
                    break
                if achou:
                    break
            if not achou and re_nome:
                mn = re_nome.search(fl)
                if mn and (not mn.group(0).endswith("vai") or _verbo_de_entrega(_toks(fl[mn.end():])[:4])):
                    achou, dono = True, mn.group(1)
            if not achou:
                continue
            perto = " ".join([texto] + [o.get("text", "") for o in voce[i + 1:]
                                        if o.get("start", 0) - s.get("start", 0) <= janela_s])
            prazo = _ata.expressao_de_prazo(f) or _ata.expressao_de_prazo(perto)
            achados.append({"t": round(s.get("start", 0)), "texto": f.strip(), "dono": dono, "prazo": prazo})
    n = len(achados)
    completos = sum(1 for a in achados if a["dono"] and a["prazo"])
    revisar = [{"t": a["t"], "texto": a["texto"],
                "falta": [x for x, v in (("dono", a["dono"]), ("prazo", a["prazo"])) if not v]}
               for a in achados if not (a["dono"] and a["prazo"])]
    return {"total": n, "com_dono": sum(1 for a in achados if a["dono"]),
            "com_prazo": sum(1 for a in achados if a["prazo"]), "completos": completos,
            "pct_completos": round(100 * completos / n) if n else None,
            "revisar": revisar[:max_frases]}


# ── fatia de fala por tipo de reunião (v3) ──────────────────────────────────────────────────
FORMATOS = ("descoberta", "demo", "alinhamento")


def numero_de_falantes(segments, participantes=None):
    """Você + os participantes informados na partida; sem eles, os rótulos remotos com ≥10% das
    palavras do outro lado (a diarização fatia uma pessoa em vários rótulos pequenos)."""
    if participantes:
        return 1 + len([p for p in participantes if p and str(p).strip()])
    por = Counter()
    for s in segments:
        if s.get("speaker") != "Você":
            por[s.get("speaker")] += len(_toks(s.get("text", "")))
    tot = sum(por.values())
    return 1 + max(1 if tot else 0, sum(1 for v in por.values() if tot and v / tot >= 0.10))


def faixa_fatia(tipo=None, formato=None, n_falantes=2, padrao=(0.35, 0.55)):
    """{lo, hi, rotulo, por_que}; lo/hi None = sem meta, só informa. Referência: Gong 2016 (43% de
    fala do vendedor nas melhores), Gong 2025 (326 mil ligações: ganhas 57%, perdidas 62%)."""
    if tipo not in (None, "cliente"):
        ref = f"; com {n_falantes} pessoas, a parte igual seria {round(100 / n_falantes)}%" if n_falantes >= 3 else ""
        return {"lo": None, "hi": None, "rotulo": "sem meta",
                "por_que": f"reunião {tipo}: interna ou técnica de terceiro, a fatia só informa{ref}"}
    if formato == "descoberta":
        return {"lo": 0.35, "hi": 0.50, "rotulo": "descoberta",
                "por_que": "descoberta: o cliente fala mais do que você"}
    if formato in ("demo", "alinhamento"):
        return {"lo": 0.45, "hi": 0.60, "rotulo": formato,
                "por_que": f"{formato}: você conduz, mas sem passar de 60% (acima de 65% piora)"}
    if n_falantes >= 3:
        parte = 1 / n_falantes
        return {"lo": round(0.75 * parte, 2), "hi": round(1.5 * parte, 2), "rotulo": f"{n_falantes} pessoas",
                "por_que": f"{n_falantes} pessoas: a parte igual é {round(100 * parte)}%; faixa de 0,75× a 1,5× "
                           "dela (heurística)"}
    lo, hi = padrao
    return {"lo": lo, "hi": hi, "rotulo": "cliente",
            "por_que": "cliente sem formato informado (descoberta, demo ou alinhamento): faixa geral; "
                       "com `formato` no sessao.json a faixa fica mais justa"}


# ── histórico: mediana das últimas 5 e a meta que sai dos dados (v3) ──────────────────────────
def ler_historico(pasta=None):
    pasta = pathlib.Path(pasta) if pasta else FALA_DIR
    hist = pasta / "historico.jsonl"
    out = []
    if hist.exists():
        for ln in hist.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
    out.sort(key=lambda r: str(r.get("data", "")))
    return out


def anteriores(hist, reg_id, data, minimo=1000, n=5):
    """As `n` reuniões ANTES desta (por data) com ≥`minimo` palavras suas: a base de comparação."""
    ok = [r for r in hist if r.get("id") != reg_id and str(r.get("data", "")) < str(data)
          and ((r.get("metrics") or {}).get("palavras_voce") or 0) >= minimo]
    return ok[-n:]


def valor_de(m, chave):
    """(valor, aproximado?) de uma métrica numa linha do histórico, lendo as linhas antigas também.
    Linha antiga (sem `versao` 3): a muleta pura sai da contagem por palavra (aproximada: contava
    "esse tipo"/"o cara"); confirmação contava "tá,"/"né." e não é comparável — fica de fora."""
    m = m.get("metrics", m) if isinstance(m, dict) else {}
    r, p = m.get("ritmo") or {}, m.get("postura") or {}
    v3 = (m.get("versao") or 0) >= VERSAO
    pal = m.get("palavras_voce") or 0
    if chave == "muleta_pura_por_1000" and not v3:
        mu = m.get("muletas")
        return (_por_mil(sum(mu.get(k, 0) for k in MULETAS_PURAS), pal), True) if pal and mu is not None else (None, False)
    if chave == "ai_por_1000":
        if "ai_por_1000" in p:
            return p["ai_por_1000"], False
        mu = m.get("muletas")
        return (_por_mil(mu.get("aí", 0), pal), False) if pal and mu is not None else (None, False)
    if chave == "conf_por_min" and not v3:
        return None, False
    if chave == "compromisso_pct":
        return (m.get("compromissos") or {}).get("pct_completos"), False
    if chave in m:
        return m[chave], False
    return r.get(chave), False


def base_de(ant, chave):
    """{mediana, n, aprox} da métrica nas reuniões de `ant` (as que têm o número)."""
    import statistics
    vals = [valor_de(r, chave) for r in ant]
    nums = [v for v, _ in vals if isinstance(v, (int, float))]
    if not nums:
        return None
    return {"mediana": round(statistics.median(nums), 2), "n": len(nums),
            "aprox": sum(1 for v, a in vals if a and isinstance(v, (int, float)))}


def _br(x, casas=1):
    if x is None:
        return "—"
    if isinstance(x, float) and not x.is_integer():
        return f"{x:.{casas}f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(int(x)) if isinstance(x, float) else str(x)


_UNID_MEDIANA = {"share_fala": lambda x: f"{x * 100:.0f}%", "compromisso_pct": lambda x: f"{_br(x)}%",
                 "atropelo_pct": lambda x: f"{_br(x)}%", "resposta_media_s": lambda x: f"{_br(x, 2)} s",
                 "maior_monologo_s": lambda x: f"{_br(x)} s", "ppm": lambda x: f"{_br(x)} palavras/min",
                 "silabas_por_s": lambda x: f"{_br(x, 2)} sílabas/s", "articulacao_sil_s": lambda x: f"{_br(x, 2)} sílabas/s"}


def ler_metricas(m, metas=None, ant=None, ctx=None):
    """Cada medida com a LEITURA (pedido do Pedro, 06/10 e 14/10/2026): o que é, a faixa e de onde ela
    vem, onde você ficou, a mediana das suas últimas 5 reuniões e o que fazer. Uma meta só é julgada
    com ≥`min_palavras` palavras suas; abaixo disso o número aparece como informativo.
    Devolve [{chave, nome, valor, valor_txt, o_que_e, faixa, fonte, meta, status, onde, mediana, dica}],
    status = ok | fora | info | pequena."""
    mt = {**METAS_PADRAO, **(metas or {})}
    ctx, ant = ctx or {}, ant or []
    r = m.get("ritmo") or {}
    pal = m.get("palavras_voce") or 0
    pequena = pal < mt["min_palavras"]
    tipo, formato, nf = ctx.get("tipo"), ctx.get("formato"), ctx.get("n_falantes") or 2
    itens = []

    def add(chave, nome, valor, valor_txt, o_que_e, faixa, fonte, ok, onde, dica_ok, dica_fora, meta=True):
        b = base_de(ant, chave)
        if not meta or ok is None:
            status = "info"
        elif pequena:
            status = "pequena"
        else:
            status = "ok" if ok else "fora"
        if b:
            mv = _UNID_MEDIANA.get(chave, lambda x: _br(x, 2))(b["mediana"])
            med = (f"mediana das suas últimas {b['n']} reuniões (≥1.000 palavras): {mv}" if b["n"] > 1
                   else f"na sua última reunião com ≥1.000 palavras: {mv}")
            if b["n"] < 5:
                med += f" (só há {b['n']} com amostra suficiente e esta medida)"
        else:
            med = "sem reuniões anteriores comparáveis ainda"
        if status == "pequena":
            onde += f". Amostra pequena ({pal} palavras suas, menos de {mt['min_palavras']}): só informativo"
        dica = dica_fora if status == "fora" else dica_ok
        itens.append({"chave": chave, "nome": nome, "valor": valor, "valor_txt": valor_txt, "o_que_e": o_que_e,
                      "faixa": faixa, "fonte": fonte, "meta": bool(meta and ok is not None), "status": status,
                      "onde": onde, "mediana": b["mediana"] if b else None, "mediana_txt": med, "dica": dica})

    # 1 · fatia de fala
    f = faixa_fatia(tipo, formato, nf, tuple(mt["share_fala"]))
    sf = m.get("share_fala", 0)
    if f["lo"] is None:
        add("share_fala", "Fatia de fala", sf, f"{sf * 100:.0f}%", "Quanto da conversa, em palavras, foi sua.",
            f"sem meta: {f['por_que']}", "Gong 2016 e 2025", None, f"Você falou {sf * 100:.0f}% das palavras",
            "só informa; compare com as suas outras reuniões do mesmo tipo.", "")
    else:
        ok = f["lo"] <= sf <= f["hi"]
        lado = "dentro da faixa" if ok else ("acima da faixa" if sf > f["hi"] else "abaixo da faixa")
        add("share_fala", "Fatia de fala", sf, f"{sf * 100:.0f}%", "Quanto da conversa, em palavras, foi sua.",
            f"{f['lo'] * 100:.0f}% a {f['hi'] * 100:.0f}% ({f['por_que']})",
            "Gong 2016 (43% nas melhores) e 2025 (326 mil ligações: ganhas 57%, perdidas 62%; acima de 65% piora)",
            ok, f"Você falou {_br(round(sf * 100, 1))}% das palavras, {lado}", "mantenha.",
            "deixe o outro falar mais: feche suas falas com uma pergunta aberta e espere a resposta inteira."
            if sf > (f["hi"] or 1) else "puxe o assunto que precisa ser decidido; você sumiu da conversa.")

    # 2 · ritmo e sílabas
    if r.get("ppm"):
        a, b_ = mt["ppm"]
        ok = a <= r["ppm"] <= b_
        add("ppm", "Ritmo", r["ppm"], f"{_br(r['ppm'])} palavras/min",
            "Palavras por minuto nos seus turnos, contando as pausas curtas: é o que quem ouve sente.",
            f"{a} a {b_} (meta prática de conversa clara)",
            f"norma de João Pessoa: {NORMA_PPM[0]}–{NORMA_PPM[1]} palavras/min, desvio ~25 (RBCS/UFPB 2019)", ok,
            f"Você falou a {_br(r['ppm'])} palavras/min, {'dentro' if ok else 'fora'} da meta; a norma é "
            f"{NORMA_PPM[0]}–{NORMA_PPM[1]}", "mantenha.",
            "faça uma pausa de um segundo no fim de cada ideia e encurte as frases." if r["ppm"] > b_
            else "suba um pouco o ritmo: frases mais diretas, menos voltas.")
    if r.get("silabas"):
        v = r["silabas_por_s"]
        mu_, dp = NORMA_SILABAS_S
        z = (v - mu_) / dp
        zona = ("dentro da norma" if abs(z) <= 1 else "mais rápida que a norma" if z > 0 else "mais lenta que a norma")
        add("silabas_por_s", "Sílabas por segundo", v, f"{_br(v, 2)} sílabas/s",
            "Velocidade de fala (taxa de elocução): sílabas por segundo no tempo dos seus turnos, com as pausas "
            "curtas. Mede velocidade melhor que palavras/min, porque palavra longa e curta pesam diferente.",
            f"norma {_br(mu_)} ± {_br(dp)} sílabas/s ({_br(mu_ - dp)} a {_br(mu_ + dp)})",
            "adultos de João Pessoa, fala semi-espontânea (RBCS/UFPB 2019)", None,
            f"Você ficou em {_br(v, 2)} sílabas/s, {zona} ({_br(abs(z), 1)} desvio{'s' if abs(z) >= 2 else ''} "
            f"{'acima' if z > 0 else 'abaixo'} da média)",
            "acima da norma: pausa no fim de cada ideia e respiração antes de número, preço e prazo."
            if z > 1 else "mantenha.", "", meta=False)
        art = r.get("articulacao_sil_s") or 0
        pausa = round(100 * (1 - v / art)) if art else 0
        add("articulacao_sil_s", "Articulação", art, f"{_br(art, 2)} sílabas/s",
            "Sílabas por segundo só dentro das falas transcritas, sem as lacunas entre trechos: a velocidade da "
            "boca. A diferença para a elocução é o quanto você pausa.",
            "sem norma da mesma fonte: leia junto com a elocução", "medido aqui", None,
            f"Você articulou a {_br(art, 2)} sílabas/s; as pausas tiram {pausa}% disso",
            "se as duas estão altas, é velocidade; se a articulação está alta e a elocução normal, as suas "
            "pausas estão fazendo o trabalho — mantenha as pausas.", "", meta=False)

    # 3 · muletas e marcadores
    pura = m.get("muleta_pura_por_1000")
    if pura is not None:
        b = base_de(ant, "muleta_pura_por_1000")
        top = ", ".join(f"\"{k}\" {v}×" for k, v in list((m.get("muletas_puras") or {}).items())[:3]) or "nenhuma"
        if b:
            limite = round(b["mediana"] * (1 - mt["muleta_pura_reducao"]), 1)
            faixa = (f"até {_br(limite)} (mediana das últimas {b['n']}, {_br(b['mediana'])}, menos "
                     f"{round(100 * mt['muleta_pura_reducao'])}%)")
            if b["n"] < 5:
                faixa += f"; só há {b['n']} reuniões com ≥1.000 palavras, a meta usa essas"
            if b["aprox"]:
                faixa += (f"; {b['aprox']} delas são do histórico antigo, que contava \"esse tipo\"/\"o cara\" "
                          "como muleta (a base pode estar um pouco alta)")
            ok = pura <= limite
        else:
            faixa, ok = "sem meta ainda: precisa de reuniões anteriores com ≥1.000 palavras", None
        add("muleta_pura_por_1000", "Muleta pura", pura, f"{_br(pura)} a cada mil palavras",
            "Palavras que não carregam nada e saem sem mudar a frase: aí, tipo, cara, pô, mano, enfim, "
            "basicamente, literalmente… (\"esse tipo de\" e \"o cara\" não contam).",
            faixa, "meta que sai dos seus dados; fluentes do pt-BR têm ~6,9% de descontinuidade por sílaba "
            "(Castro 2014, CoDAS), mas o Whisper apaga \"éé\"/\"hum\", então aqui só entram palavras",
            ok, f"Você ficou em {_br(pura)}; as mais usadas: {top}", "mantenha.",
            f"a campeã foi {top.split(',')[0]}: troque-a por uma pausa curta.")
        marc = m.get("marcador_por_1000", 0)
        topm = ", ".join(f"\"{k}\" {v}×" for k, v in list((m.get("marcadores") or {}).items())[:3]) or "nenhum"
        add("marcador_por_1000", "Marcadores de discurso", marc, f"{_br(marc)} a cada mil palavras",
            "Palavras que organizam a fala: então, tá, assim, exatamente, né (sem pergunta). Não são defeito em "
            "si; em excesso viram ruído. O \"tá\" verbo (\"tá funcionando\", \"tá bom\") não entra.",
            "sem meta: só informa", "classificação deste sistema (14/10/2026)", None,
            f"Você ficou em {_br(marc)}; os mais usados: {topm}; {m.get('ta_verbo', 0)} \"tá\" verbo ficaram de fora",
            "se um marcador abre quase toda frase (\"então…\"), comece direto pelo assunto.", "", meta=False)

    p = m.get("postura") or {}
    if p:
        b = base_de(ant, "ai_por_1000")
        degraus = mt["ai_por_1000"] if isinstance(mt["ai_por_1000"], (list, tuple)) else [mt["ai_por_1000"]]
        limite = degraus[0]
        if len(degraus) > 1 and b and b["mediana"] <= degraus[0]:
            limite = degraus[1]
            como = f"degrau 2: a mediana das últimas {b['n']} já está em {_br(b['mediana'])}, ≤{degraus[0]}"
        elif len(degraus) > 1:
            como = (f"degrau 1; quando a mediana das últimas 5 ficar ≤{degraus[0]}, a meta vira ≤{degraus[1]}"
                    + (f" (hoje {_br(b['mediana'])})" if b else ""))
        else:
            como = "meta fixa do config"
        ok = p["ai_por_1000"] <= limite
        add("ai_por_1000", "\"Aí\"", p["ai_por_1000"], f"{_br(p['ai_por_1000'])} a cada mil palavras",
            "O \"aí\" de ligação (\"aí eu fiz, aí ele disse\"): a muleta pura mais frequente na sua fala.",
            f"até {limite} ({como})", "meta em degraus pelos seus dados (14/10/2026)", ok,
            f"Você ficou em {_br(p['ai_por_1000'])}", "mantenha; o próximo degrau vem pelos dados.",
            "termine a frase com ponto e comece a próxima sem o \"aí\"; um silêncio curto faz o mesmo papel.")

    # 4 · confirmações e monólogo
    c = m.get("conf_por_min", 0)
    ok = c <= mt["conf_por_min"]
    add("conf_por_min", "Confirmações", c, f"{_br(c, 2)} por minuto",
        "Pedidos de confirmação COM interrogação (\"entendeu?\", \"certo?\", \"tá?\", \"né?\"). \"Tá,\" e \"né.\" "
        "sem pergunta são concordância e não entram.",
        f"até {_br(mt['conf_por_min'])} por minuto", "meta própria (julho: 3,11/min)", ok,
        f"Você ficou em {_br(c, 2)}/min ({m.get('conf_total', 0)} no total)", "mantenha.",
        "troque o \"entendeu?\" do fim de cada frase por uma pergunta aberta no fim do bloco: "
        "\"o que ficou faltando?\".")
    if r.get("maior_monologo_s") is not None:
        ok = r["maior_monologo_s"] <= mt["maior_monologo_s"]
        add("maior_monologo_s", "Maior monólogo", r["maior_monologo_s"], f"{r['maior_monologo_s']} s",
            "O turno mais longo em que você falou sem o outro entrar.",
            f"até {mt['maior_monologo_s']} s", "Gong: monólogos de até ~150 s nas ligações ganhas", ok,
            f"O maior foi de {r['maior_monologo_s']} s, em {_mmss(r.get('maior_monologo_em'))}", "mantenha.",
            "em explicação longa, pare a cada 1–2 minutos com uma pergunta.")

    # 5 · tomar a vez × apoio
    if "tomou_vez" in r:
        julga = tipo in (None, "cliente") and formato not in ("demo", "alinhamento")
        v = r["tomou_vez_por_10min"]
        add("tomou_vez_por_10min", "Tomou a vez", v, f"{_br(v, 2)} a cada 10 min",
            "Vezes em que você começou a falar com o outro falando e ele parou em até 2 s, ficando você com a "
            "palavra (e falando ≥2 s). \"Isso\", \"uhum\", \"sim\" curtos são apoio e não contam.",
            f"até {mt['tomou_vez_por_10min']} a cada 10 min" + ("" if julga else " (só informa neste tipo de reunião)"),
            "heurística inicial, pensada para descoberta; sem norma publicada", (v <= mt["tomou_vez_por_10min"]) if julga else None,
            f"Você tomou a vez {r['tomou_vez']} vez(es); além disso deu {r.get('apoio', 0)} apoio(s), que são bons",
            "mantenha.", "quando perceber que entrou por cima, devolva: \"desculpa, pode terminar\".")

    # 6 · paciência
    if r.get("resposta_media_s") is not None:
        a, b_ = mt["resposta_s"]
        v = r["resposta_media_s"]
        ok = a <= v <= b_
        add("resposta_media_s", "Paciência", v, f"{_br(v, 2)} s",
            "Quanto você espera, em média, depois que o outro termina, para começar a falar.",
            f"{_br(a)} a {_br(b_)} s", "Gong (\"paciência\" dos melhores vendedores)", ok,
            f"Você esperou {_br(v, 2)} s em média, {'dentro' if ok else 'fora'} da faixa", "mantenha.",
            "conte um segundo antes de responder, principalmente depois de objeção ou de preço."
            if v < a else "acima de 1 s pode soar hesitante; confira se não é o atraso da chamada.")
        at = r.get("atropelo_pct")
        if at is not None:
            add("atropelo_pct", "Atropelo", at, f"{at}% das respostas",
                "Respostas suas que começaram menos de 0,3 s depois de o outro terminar: emendou sem ouvir até o fim.",
                "sem faixa publicada: compare com a sua mediana; quanto menor, melhor", "medido aqui", None,
                f"{at}% de {r.get('respostas', 0)} respostas", "se passar da sua mediana, respire antes de responder.",
                "", meta=False)

    # 7 · perguntas
    if "perguntas_abertas" in r:
        ab, fe = r["perguntas_abertas"], r["perguntas_fechadas"]
        a, b_ = mt["perguntas_abertas"]
        julga = formato == "descoberta"
        tot = ab + fe
        add("perguntas_abertas", "Perguntas abertas", ab, f"{ab} abertas · {fe} de sim/não",
            "Perguntas que pedem explicação (como, por que, o que, qual, quanto, quando, me conta, me explica…) "
            "contra as de sim/não. Não conta \"entendeu?\".",
            f"{a} a {b_} abertas em reunião de descoberta" + ("" if julga else " (só informa: formato não é descoberta)"),
            "Gong 2025: 15–16 perguntas nas ligações ganhas; 11–14 em descoberta (fonte secundária)",
            (a <= ab <= b_) if julga else None,
            f"Você fez {ab} abertas e {fe} de sim/não" + (f" ({round(100 * ab / tot)}% abertas)" if tot else ""),
            "transforme as de sim/não em abertas: \"isso funciona pra você?\" → \"como isso funcionaria aí?\".",
            "faça mais perguntas abertas: \"como vocês fazem isso hoje?\", \"o que acontece quando…?\".")

    # 8 · compromisso com dono e prazo
    cp = m.get("compromissos")
    if cp and cp.get("total"):
        add("compromisso_pct", "Compromisso com dono e prazo", cp["pct_completos"],
            f"{cp['completos']} de {cp['total']} ({cp['pct_completos']}%)",
            "Das frases de compromisso (\"vou\", \"te mando\", \"a gente vai\", \"vamos\", \"fica pronto\"), quantas "
            "saíram com dono (eu, você ou um nome; \"vou\" conta como você) e com prazo (\"até sexta\", \"amanhã\", "
            "\"em 15 dias\").",
            "sem faixa publicada: o alvo é todo compromisso com cliente sair com dono e prazo",
            "troca a antiga meta de \"a gente\" (14/10/2026)", None,
            f"{cp['com_dono']} com dono, {cp['com_prazo']} com prazo, {cp['completos']} com os dois",
            "\"a gente vai ver isso\" não tem dono nem data: diga quem faz e até quando. As frases sem um dos dois "
            "estão listadas para você conferir se viraram encaminhamento na ata.", "", meta=False)
    return itens


def avaliar_metas(m, metas=None, ant=None, ctx=None):
    """[(métrica, valor, meta em texto, ok?)] para o relatório, o painel, a janela e a avaliação.
    ok = None quando a amostra é pequena (< 1.000 palavras suas): número informativo, sem julgamento."""
    itens = m.get("leitura") if ant is None and ctx is None and m.get("leitura") else ler_metricas(m, metas, ant, ctx)
    return metas_de(itens)


def metas_de(itens):
    out = []
    for it in itens:
        if not it["meta"]:
            continue
        ok = None if it["status"] == "pequena" else it["status"] == "ok"
        faixa = it["faixa"].split(" (")[0].split(";")[0]         # a faixa curta; a leitura completa fica no item
        faixa += " · amostra pequena, só informativo" if it["status"] == "pequena" else ""
        out.append((it["nome"], it["valor_txt"], faixa, ok))
    return out


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
         f"- Pedidos de confirmação (com \"?\"): **{m['conf_total']}** (~{m['conf_por_min']}/min)",
         (f"- Muleta pura: {m['muleta_pura_por_1000']} a cada 1000 palavras · marcadores de discurso: "
          f"{m['marcador_por_1000']} ({m.get('ta_verbo', 0)} \"tá\" verbo fora da conta)"
          if "muleta_pura_por_1000" in m else f"- Muletas: {m['muletas_por_1000']} a cada 1000 palavras"),
         f"- Hedge ('acho que'): {m['hedge']}", ""]
    if m.get("leitura"):
        L.append("## Leitura de cada medida")
        rot = {"ok": "✅ dentro da meta", "fora": "⚠️ fora da meta", "info": "ℹ️ só informa",
               "pequena": "ℹ️ amostra pequena, só informativo"}
        for it in m["leitura"]:
            L += ["", f"### {it['nome']}: {it['valor_txt']} → {rot[it['status']]}",
                  f"- O que é: {it['o_que_e']}",
                  f"- Faixa: {it['faixa']} _(fonte: {it['fonte']})_",
                  f"- Você: {it['onde']}.",
                  f"- Comparação: {it['mediana_txt']}."]
            if it["dica"]:
                L.append(f"- O que fazer: {it['dica']}")
        L.append("")
    L.append("## Perguntas-muleta (confirmação)")
    for k, v in m["confirmacoes"].items():
        L.append(f"- {k}? — {v}")
    if "muletas_puras" in m:
        L += ["", "## Muletas puras"] + [f"- {k} — {v}" for k, v in m["muletas_puras"].items()]
        L += ["", "## Marcadores de discurso"] + [f"- {k} — {v}" for k, v in m["marcadores"].items()]
    else:
        L += ["", "## Muletas (palavra solta)"] + [f"- {k} — {v}" for k, v in m["muletas"].items()]
    cp = m.get("compromissos") or {}
    if cp.get("revisar"):
        L += ["", "## Compromissos sem dono ou sem prazo"]
        L += [f"- [{_mmss(c['t'])}] {c['texto']} _(falta: {', '.join(c['falta'])})_" for c in cp["revisar"]]
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
              (f"- Sobreposições: você entrou com o outro falando **{r['interrompeu']}** vezes — tomou a vez "
               f"**{r['tomou_vez']}**, apoio {r['apoio']}; foi interrompido {r['foi_interrompido']}"
               if "tomou_vez" in r else
               f"- Interrupções: você interrompeu **{r['interrompeu']}** vezes; foi interrompido {r['foi_interrompido']}"),
              f"- Tempo médio para responder: {r['resposta_media_s']} s" if r.get("resposta_media_s") is not None
              else "- Tempo médio para responder: —",
              f"- Perguntas de verdade (sem contar \"entendeu?\"): {r['perguntas_reais']}"]
    if m.get("blocos"):
        L += ["", "## Ao longo da reunião (cansaço)", "",
              "| Trecho | Fala | Ritmo | Conf/min | Muleta pura/1k | Mul+marc/1k |", "|---|---|---|---|---|---|"]
        for b in m["blocos"]:
            L.append(f"| {b['de_min']}–{b['ate_min']} min | {b['share_fala']*100:.0f}% | {b['ppm']} | "
                     f"{b['conf_por_min']} | {b.get('muleta_pura_por_1000', '—')} | {b['muletas_por_1000']} |")
    v = m.get("voz")
    if v:
        itens, evolucao = leitura_voz(v)
        L += ["", "## Voz (áudio do microfone)",
              f"_Amostra: {v['amostra_min']} min das suas falas, espalhados pela reunião. Entonação comparada "
              "com a fala masculina brasileira (Arantes, Abralin); volume e nível são referência prática, "
              "não diagnóstico._"]
        for it in itens:
            faixas = " · ".join(f"{n} {a}–{b}" for a, b, n, _ in it["zonas"])
            L += ["", f"### {it['nome']}: {it['valor']} {it['unidade']} → **{it['zona']}**",
                  f"- O que é: {it['o_que_e']}",
                  f"- Faixas: {faixas}" + (f" _(fonte: {it['fonte']})_" if it.get("fonte") else "")]
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
            L.append(f"| {nome} | {val} | {meta} | {'ℹ️' if ok is None else '✅' if ok else '⚠️'} |")
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
        top = ", ".join(list(m.get("muletas_puras") or m["muletas"])[:3]) or "—"
        tipo = _TIPO_ROTULO.get(r.get("tipo"), "—")
        ppm = (m.get("ritmo") or {}).get("ppm") or "—"
        pura, aprox = valor_de(m, "muleta_pura_por_1000")
        conf = m["conf_por_min"] if (m.get("versao") or 0) >= VERSAO else f"{m['conf_por_min']}*"
        return (f"| {str(r['data'])[:16]} | {tipo} | {m['dur_min']} | {m['share_fala']*100:.0f}% "
                f"| {conf} | {_br(pura)}{'*' if aprox else ''} | {ppm} | {top} |")
    def _leitura(chave):
        it = next((x for x in ult.get("leitura") or [] if x["chave"] == chave), None)
        if not it:
            return "—"
        st = {"ok": "dentro da meta", "fora": "fora da meta", "info": "só informa",
              "pequena": "amostra pequena, só informativo"}[it["status"]]
        return f"**{it['valor_txt']}** ({st}; faixa {it['faixa'].split(' (')[0]})"
    tab = "\n".join(_row(r) for r in linhas[-8:])
    return "\n".join([
        "---", "tipo: nota", "area: crescimento",
        "tags: [comunicacao, fala, raio-x, auto-gerado]", "status: em-progresso",
        f"atualizado: {linhas[-1]['data'] if linhas else ''}", "---", "",
        "# 📈 Raio-X da Fala (auto)", "",
        "> ⚙️ **Nota auto-gerada** pelo sistema [[atas]] a cada reunião — não editar à mão. "
        "A narrativa e as metas ficam em [[fala-e-apresentacao]]. Dado pessoal, nunca vai ao cliente.", "",
        "## Agora",
        "_Raio-X calibrado em 14/10/2026: cada número com a faixa e a fonte; com menos de 1.000 palavras "
        "suas, nenhuma meta é julgada. A leitura completa (o que é, onde você está, o que fazer) fica na "
        "página da reunião, em `fala-analise/`._",
        f"- Fatia de fala: {_leitura('share_fala')}",
        f"- Confirmações (só com \"?\"): {_leitura('conf_por_min')}",
        f"- Muleta pura: {_leitura('muleta_pura_por_1000')} · marcadores: {_leitura('marcador_por_1000')}",
        f"- \"Aí\": {_leitura('ai_por_1000')}",
        f"- Ritmo: {_leitura('ppm')} · sílabas/s: {_leitura('silabas_por_s')} · maior monólogo: "
        f"{_leitura('maior_monologo_s')}",
        f"- Tomou a vez: {_leitura('tomou_vez_por_10min')} · paciência: {_leitura('resposta_media_s')}",
        f"- Perguntas: {_leitura('perguntas_abertas')} · compromisso com dono e prazo: {_leitura('compromisso_pct')}",
        ("- Voz: " + " · ".join(f"{it['nome'].lower()} **{it['valor']} {it['unidade']}** ({it['zona']})"
                                for it in leitura_voz(ult["voz"])[0])
         if ult.get("voz") else "- Voz: sem áudio do microfone nesta reunião"),
        (f"- Postura: \"eu\" {ult['postura']['eu']} × \"a gente\" {ult['postura']['a_gente']} (informação, "
         f"não meta) · promessa no reflexo **{ult['postura']['promessa_total']}** · certeza absoluta "
         f"**{ult['postura']['certeza_total']}**" if ult.get("postura") else "- Postura: —"),
        f"- Reuniões monitoradas: **{len(linhas)}**", "",
        "## Reunião a reunião (últimas)",
        "_\\* = linha anterior à calibração: confirmação contava \"tá,\"/\"né.\" e a muleta pura é aproximada._", "",
        "| Data | Tipo | Min | Fala | Conf/min | Muleta pura/1k | Ritmo | Top muletas |",
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


def calcular(segments, quando, reg_id, pasta=None, tipo=None, audio_mic=None, metas=None,
             participantes=None, formato=None, voz_pronta=None, hist=None):
    """Só as métricas (sem gravar nada). `hist` = linhas do histórico (padrão: o da `pasta`);
    `voz_pronta` reaproveita a voz já medida (o recálculo não decodifica o áudio de novo)."""
    mt = {**METAS_PADRAO, **(metas or {})}
    metrics = analisar(segments)
    metrics["ritmo"] = ritmo_e_turnos(segments)
    metrics["postura"] = postura(segments)
    metrics["compromissos"] = compromissos(segments, participantes)
    metrics["blocos"] = por_bloco(segments) if metrics["dur_min"] >= 45 else []
    if voz_pronta is not None:                   # {} = "não medir a voz" (recálculo sem voz antiga)
        metrics["voz"] = voz_pronta or None
    else:
        try:
            metrics["voz"] = voz(segments, audio_mic) if audio_mic else None
        except Exception as e:                   # voz é bônus: nunca derruba o Raio-X
            metrics["voz"] = None
            metrics["voz_erro"] = f"{type(e).__name__}: {e}"
    formato = formato if formato in FORMATOS else None
    ctx = {"tipo": tipo, "formato": formato, "n_falantes": numero_de_falantes(segments, participantes)}
    hist = ler_historico(pasta) if hist is None else hist
    ant = anteriores(hist, reg_id, quando, mt["min_palavras"])
    metrics["contexto"] = ctx
    metrics["base_ids"] = [r.get("id") for r in ant]
    metrics["leitura"] = ler_metricas(metrics, metas, ant, ctx)
    metrics["metas"] = metas_de(metrics["leitura"])
    return metrics


def processar(segments, titulo, quando, pasta=None, tipo=None, sessao_id=None, vault=True,
              audio_mic=None, metas=None, avaliacao_md=None, participantes=None, formato=None,
              voz_pronta=None):
    """Analisa, salva relatório .md, atualiza histórico, regenera o painel e
    alimenta o Sinapse. Retorna os caminhos gerados (vault=None se não gravou).
    v2.1: ritmo/turnos/interrupções, blocos de 30 min, voz (se `audio_mic` existir) e metas.
    v3 (14/10/2026): leitura de cada medida contra a mediana das últimas 5 reuniões; fatia de fala
    pelo tipo/`formato`/nº de pessoas; compromissos com dono e prazo."""
    pasta = pathlib.Path(pasta) if pasta else FALA_DIR
    pasta.mkdir(parents=True, exist_ok=True)
    reg_id = sessao_id or f"{quando}|{titulo}"
    metrics = calcular(segments, quando, reg_id, pasta, tipo, audio_mic, metas, participantes, formato,
                       voz_pronta)
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in titulo).strip() or "reuniao"
    reg = {"id": reg_id, "data": quando, "titulo": titulo,
           "safe": safe, "tipo": tipo, "formato": metrics["contexto"]["formato"], "metrics": metrics}
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
