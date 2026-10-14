# -*- coding: utf-8 -*-
"""
Modo treino (14/10/2026, pedido do Pedro: "gosto do modo treino para reunião").

O Pedro grava de 2 a 5 minutos treinando SOZINHO e recebe o Raio-X da fala de monólogo e um
retorno curto do Claude. Dois tipos:

  reuniao  ensaiar uma fala de reunião de cliente (abertura, proposta/status, objeção, próximos
           passos). O Claude olha: ideia central nos primeiros ~20 s; problema → o que muda →
           próximo passo; promete resultado, não método; compromisso com dono e prazo; perguntas
           abertas (se for descoberta); certeza absoluta/promessa no reflexo.
  tema     explicar um assunto de estudo (nota do Sinapse em 02-ESTUDO ou texto livre). O Claude
           confere o conteúdo contra a nota com citação literal (a mesma auditoria da ata) e diz se
           passou por ideia → problema → mecanismo → exemplo.

Em ambos: "1 coisa para manter e 1 para mudar", tom de colega, e toda métrica com leitura.

O que mede (só o que faz sentido em monólogo; fatia de fala, turnos e interrupção ficam fora):
sílabas/s de elocução e de articulação, pausas ≥0,5 s (por minuto e % do tempo, dos tempos de cada
palavra do Whisper), palavras entre pausas, muleta pura e "aí" por mil palavras, entonação, duração
contra o alvo e o trecho mais corrido (janela de 10 s).

ISOLAMENTO (regra do Pedro): treino é ensaio, não reunião.
  - grava só o microfone, sem loopback; sem diarização, sem ata, sem upload;
  - fica em `atas-salvas/treinos/<id>/` (manifesto `treino.json`, nunca `sessao.json`: o
    `sessao.listar()` não enxerga treino e nada do pipeline de reunião roda nele);
  - o histórico é `fala-analise/treinos.jsonl`; o `historico.jsonl` das reuniões é só LIDO (a
    mediana das reuniões é a régua da transferência) — treino nunca entra na mediana, no painel,
    na nota `fala-raio-x.md` do Sinapse, na avaliação nem em entregável;
  - a nota de estudo do Sinapse é só lida.
O áudio é apagado depois de `audio_reter_dias` (30), como o das reuniões, salvo se o Pedro marcar
o treino para manter (`atas.py treinos --manter <id>`).
"""
import datetime as _dt
import json
import os
import pathlib
import shutil
import statistics

import analise_fala as af
import ata as _ata
import sessao as _sessao
from sessao import SR, Sessao, agora_iso, escrever_json, ler_json, slug

SCHEMA_TREINO = "atas/treino@1"
MANIFESTO = "treino.json"
HIST_NOME = "treinos.jsonl"

TIPOS_TREINO = {"reuniao": "Reunião", "tema": "Explicar um tema"}
# alvo de sílabas/s (pesquisa de 14/10, seção E): leitura ritmada 4,5 → roteiro de 3 tópicos 5,0 →
# explicação livre 4,8. A norma de João Pessoa é 4,2 ± 0,7; o Pedro fala ~5,9 nas reuniões.
ALVOS = {4.8: "padrão", 4.5: "leitura ritmada", 5.0: "roteiro de 3 tópicos"}
ALVO_PADRAO = 4.8
DURACOES_MIN = (2, 3, 4, 5)
DURACAO_PADRAO_S = 180
PAUSA_S = 0.5                   # pausa = silêncio de meio segundo ou mais entre duas palavras
PAUSAS_POR_MIN = (8, 15)        # referência prática (uma pausa por frase), sem norma publicada
ENTONACAO_ALVO = 3.0            # apresentação: 3 semitons ou mais (Arantes, Abralin)
JANELA_CORRIDO_S = 10.0
TOLERANCIA_ALVO = 0.3           # até 0,3 sílaba/s acima do alvo ainda conta como no alvo
PRINCIPAIS = ("silabas_por_s", "pausas_por_min", "muleta_pura_por_1000", "entonacao_st")   # os 4 da tela
VERSAO_PROMPT = "treino-1"


# ── onde fica cada coisa ─────────────────────────────────────────────────────
def raiz_treinos(raiz=None):
    """`atas-salvas/treinos/` (fora do git, como as reuniões). Lido na hora: os testes trocam o SALVAS."""
    return pathlib.Path(raiz) if raiz else _sessao.SALVAS / "treinos"


def hist_treinos_path(pasta=None):
    return (pathlib.Path(pasta) if pasta else af.FALA_DIR) / HIST_NOME


def vault():
    """O vault do Sinapse, pela mesma regra do Raio-X (env SINAPSE_VAULT ou ../../sinapse)."""
    base = os.environ.get("SINAPSE_VAULT")
    return pathlib.Path(base) if base else pathlib.Path(__file__).parents[2] / "sinapse"


def notas_de_estudo():
    """{nome: caminho} das notas de `02-ESTUDO` (com subpastas), para a janela oferecer."""
    pasta = vault() / "02-ESTUDO"
    if not pasta.exists():
        return {}
    return {p.stem: p for p in sorted(pasta.rglob("*.md")) if not p.stem.startswith("MOC")}


def achar_nota(ref):
    """Caminho de uma nota: caminho de arquivo, ou o nome (sem .md) de uma nota de 02-ESTUDO."""
    if not ref:
        return None
    p = pathlib.Path(ref)
    if p.exists():
        return p
    nome = p.stem if p.suffix == ".md" else str(ref)
    achada = notas_de_estudo().get(nome)
    if achada is None:
        raise FileNotFoundError(f"nota não encontrada: {ref} (caminho ou nome de uma nota de 02-ESTUDO)")
    return achada


# ── o treino no disco ────────────────────────────────────────────────────────
class Treino(Sessao):
    """Mesma pasta-de-sessão do gravador (mic.pcm, .batida, audio/), mas com manifesto próprio
    (`treino.json`): o `Gravador` grava nele como numa reunião, e nada que procura `sessao.json`
    (listar, retomar, retenção das reuniões, importador do celular) o enxerga."""

    def salvar(self):
        escrever_json(self.pasta / MANIFESTO, self.m)

    @classmethod
    def criar(cls, tipo, assunto="", nota=None, duracao_alvo_s=DURACAO_PADRAO_S, alvo=ALVO_PADRAO,
              raiz=None, quando=None, origem="gravacao"):
        if tipo not in TIPOS_TREINO:
            raise ValueError(f"tipo de treino inválido: {tipo!r} (use {', '.join(TIPOS_TREINO)})")
        raiz = raiz_treinos(raiz)
        raiz.mkdir(parents=True, exist_ok=True)
        quando = quando or _dt.datetime.now()
        base = f"{quando:%Y-%m-%d_%H%M}_treino-{tipo}" + (f"-{slug(assunto, 32)}" if assunto else "")
        tid, n = base, 2
        while (raiz / tid).exists():
            tid, n = f"{base}-{n}", n + 1
        pasta = raiz / tid
        pasta.mkdir()
        m = {"schema": SCHEMA_TREINO, "id": tid, "modo": "treino",
             "tipo": "treino",                  # nunca um tipo de reunião: publicar() recusa, por garantia
             "tipo_treino": tipo, "titulo": f"Treino · {TIPOS_TREINO[tipo]}" + (f" · {assunto}" if assunto else ""),
             "assunto": (assunto or "").strip(), "nota": str(nota) if nota else None,
             "duracao_alvo_s": int(duracao_alvo_s or DURACAO_PADRAO_S), "alvo_silabas_s": float(alvo or ALVO_PADRAO),
             "origem": origem, "criado": agora_iso(),
             "inicio": quando.astimezone().isoformat(timespec="seconds") if origem != "gravacao" else None,
             "fim": None, "estado": "preparando", "dispositivos": {}, "audio": {"sr": SR},
             "etapas": {}, "avisos": [], "manter": False}
        t = cls(pasta, m)
        t.salvar()
        return t

    @classmethod
    def abrir(cls, pasta_ou_id, raiz=None):
        p = pathlib.Path(pasta_ou_id)
        if not p.is_absolute() and not p.exists():
            p = raiz_treinos(raiz) / str(pasta_ou_id)
        m = ler_json(p / MANIFESTO)
        if m is None:
            raise FileNotFoundError(f"não é um treino do Atas: {p}")
        return cls(p, m)

    @property
    def tipo_treino(self):
        return self.m.get("tipo_treino") or "reuniao"


def listar(raiz=None):
    r = raiz_treinos(raiz)
    if not r.exists():
        return []
    out = []
    for p in sorted(r.iterdir()):
        if p.is_dir() and (p / MANIFESTO).exists():
            try:
                out.append(Treino.abrir(p))
            except Exception:
                continue
    out.sort(key=lambda t: t.m.get("inicio") or t.m.get("criado") or "")
    return out


def achar(ref, raiz=None):
    todos = listar(raiz)
    if ref in (None, "", "ultimo", "último", "ultima"):
        if not todos:
            raise FileNotFoundError("nenhum treino ainda")
        return todos[-1]
    exatos = [t for t in todos if t.id == ref]
    if exatos:
        return exatos[0]
    cands = [t for t in todos if t.id.startswith(ref)]
    if len(cands) != 1:
        raise FileNotFoundError(f"treino {ref!r}: {len(cands)} encontrados")
    return cands[0]


# ── transcrição com o tempo de cada palavra ─────────────────────────────────
def transcrever(x, cfg, log=print):
    """Áudio (float32, 16 kHz) → ([{w, start, end}], info). Uma passada só, no canal do microfone,
    com `word_timestamps` (as pausas saem daqui). Sem diarização: só o Pedro fala."""
    import transcribe
    modelo, info = transcribe.carregar_modelo(cfg.get("model", "auto"), cfg.get("dispositivo", "auto"), log)
    log(f"  Modelo {info['modelo']} em {info['dispositivo'].upper()}")
    kw = dict(language=cfg.get("idioma", "pt"), vad_filter=True, beam_size=5, word_timestamps=True)
    if cfg.get("vocabulario", True):
        hot = transcribe.vocabulario(None, None, None, cfg.get("meu_nome"))
        if hot:
            kw["hotwords"] = ", ".join(hot)
    segs, _ = modelo.transcribe(x, **kw)
    palavras = []
    for s in segs:
        for w in (s.words or []):
            if w.word.strip():
                palavras.append({"w": w.word.strip(), "start": round(float(w.start), 2),
                                 "end": round(float(w.end), 2)})
    return palavras, info


def segmentos(palavras, corte_s=PAUSA_S):
    """Palavras → trechos de "Você" (corte na pausa ≥ corte_s ou no fim de frase longa), no formato
    que o Raio-X das reuniões lê (muletas, "aí", voz)."""
    out, atual = [], []

    def fechar():
        if atual:
            out.append({"speaker": "Você", "start": atual[0]["start"], "end": atual[-1]["end"],
                        "text": " ".join(w["w"] for w in atual)})
    for w in sorted(palavras, key=lambda p: p["start"]):
        if atual and (w["start"] - atual[-1]["end"] >= corte_s or
                      (atual[-1]["w"][-1:] in ".?!" and w["start"] - atual[0]["start"] >= 2.0)):
            fechar()
            atual = []
        atual.append(w)
    fechar()
    return out


def frases(palavras, pausa_longa_s=2.0):
    """Palavras → frases (corte no ponto final do Whisper ou numa pausa de 2 s). É a "linha" que o
    Claude cita e que a auditoria confere: em monólogo, juntar por pausa daria uma fala só de 3 min."""
    out, atual = [], []

    def fechar():
        if atual:
            out.append({"speaker": "Você", "start": atual[0]["start"], "end": atual[-1]["end"],
                        "text": " ".join(w["w"] for w in atual)})
    for w in sorted(palavras, key=lambda p: p["start"]):
        if atual and (atual[-1]["w"][-1:] in ".?!…" or w["start"] - atual[-1]["end"] >= pausa_longa_s):
            fechar()
            atual = []
        atual.append(w)
    fechar()
    return out


def transcricao_texto(palavras):
    return "\n".join(f"[{_ata.fmt_t(f['start'])}] {f['text']}" for f in frases(palavras))


# ── métricas de monólogo ─────────────────────────────────────────────────────
def pausas_e_corridas(palavras, limiar=PAUSA_S):
    """Pausas ≥`limiar` entre palavras seguidas e quantas palavras cabem entre uma pausa e outra.
    Só conta o silêncio ENTRE palavras: o antes da primeira e o depois da última ficam fora (é o
    tempo de apertar o botão). Devolve {pausas: [(início, duração)], corridas: [n palavras],
    fala_s: da 1ª à última palavra, pausa_s: soma das pausas}."""
    ws = sorted(palavras, key=lambda p: p["start"])
    if not ws:
        return {"pausas": [], "corridas": [], "fala_s": 0.0, "pausa_s": 0.0}
    pausas, corridas, n = [], [], 0
    for a, b in zip(ws, ws[1:]):
        n += 1
        gap = b["start"] - a["end"]
        if gap >= limiar:
            pausas.append((round(a["end"], 2), round(gap, 2)))
            corridas.append(n)
            n = 0
    corridas.append(n + 1)
    return {"pausas": pausas, "corridas": corridas, "fala_s": round(ws[-1]["end"] - ws[0]["start"], 2),
            "pausa_s": round(sum(d for _, d in pausas), 2)}


def trecho_mais_corrido(palavras, janela_s=JANELA_CORRIDO_S, minimo_palavras=5):
    """A janela de ~`janela_s` com mais sílabas por segundo (contando as pausas de dentro): é o
    trecho para ouvir de novo. None se a fala for curta demais."""
    ws = sorted(palavras, key=lambda p: p["start"])
    sil = [af.silabas(w["w"]) for w in ws]
    melhor = None
    for i, w in enumerate(ws):
        j, s = i, 0
        while j < len(ws) and ws[j]["end"] - w["start"] <= janela_s:
            s += sil[j]
            j += 1
        if j - i < minimo_palavras:
            continue
        dur = ws[j - 1]["end"] - w["start"]
        if dur < 0.6 * janela_s:
            continue
        taxa = s / dur
        if melhor is None or taxa > melhor["silabas_s"]:
            melhor = {"ini": round(w["start"], 2), "fim": round(ws[j - 1]["end"], 2),
                      "silabas_s": round(taxa, 2), "texto": " ".join(x["w"] for x in ws[i:j])}
    return melhor


def medir(palavras, audio_voz=None, gravado_s=None, alvo=ALVO_PADRAO, duracao_alvo_s=DURACAO_PADRAO_S):
    """As métricas do treino. `audio_voz`: o áudio do microfone (para a entonação)."""
    segs = segmentos(palavras)
    texto = " ".join(w["w"] for w in palavras)
    an = af.analisar(segs)
    post = af.postura(segs)
    pc = pausas_e_corridas(palavras)
    fala_s = pc["fala_s"]
    sil = af.silabas(texto)
    fonacao = max(0.0, fala_s - pc["pausa_s"])
    n_pal = an["palavras_voce"] if palavras else 0
    v, voz_erro = None, None
    if audio_voz:
        try:
            v = af.voz(segs, audio_voz)
        except Exception as e:                  # voz é bônus: nunca derruba o treino
            voz_erro = f"{type(e).__name__}: {e}"
    corr = pc["corridas"]
    return {
        "versao": 1,
        "palavras": n_pal,
        "silabas": sil,
        "fala_s": fala_s,
        "gravado_s": round(gravado_s, 1) if gravado_s else fala_s,
        "duracao_alvo_s": int(duracao_alvo_s or DURACAO_PADRAO_S),
        "alvo_silabas_s": float(alvo or ALVO_PADRAO),
        "silabas_por_s": round(sil / fala_s, 2) if fala_s else 0,
        "articulacao_sil_s": round(sil / fonacao, 2) if fonacao else 0,
        "ppm": round(n_pal / (fala_s / 60), 1) if fala_s else 0,
        "pausas": len(pc["pausas"]),
        "pausas_por_min": round(len(pc["pausas"]) / (fala_s / 60), 1) if fala_s else 0,
        "pausa_pct": round(100 * pc["pausa_s"] / fala_s) if fala_s else 0,
        "pausa_media_s": round(pc["pausa_s"] / len(pc["pausas"]), 2) if pc["pausas"] else 0,
        "palavras_entre_pausas": round(statistics.median(corr), 1) if corr and n_pal else 0,
        "muleta_pura_por_1000": an["muleta_pura_por_1000"],
        "muletas_puras": an["muletas_puras"],
        "marcador_por_1000": an["marcador_por_1000"],
        "ai_por_1000": post["ai_por_1000"],
        "certeza_total": post["certeza_total"],
        "promessa_total": post["promessa_total"],
        "frases_revisar": post["frases_revisar"][:5],
        "entonacao_st": v["entonacao_st"] if v else None,
        "voz": {k: v[k] for k in ("entonacao_st", "volume_variacao_db", "volume_db", "tom_hz")} if v else None,
        "voz_erro": voz_erro,
        "trecho_corrido": trecho_mais_corrido(palavras),
    }


# ── comparação: último treino do mesmo tipo × mediana das reuniões reais ─────
def ler_treinos(pasta=None):
    p = hist_treinos_path(pasta)
    out = []
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
    out.sort(key=lambda r: str(r.get("data", "")))
    return out


def _mediana(vals):
    nums = [v for v in vals if isinstance(v, (int, float))]
    return {"mediana": round(statistics.median(nums), 2), "n": len(nums)} if nums else None


def comparar(tipo, tid, data, treinos=None, reunioes=None):
    """{ultimo: métricas do treino anterior do mesmo tipo, reunioes: {chave: {mediana, n}}}.
    As reuniões são as 5 últimas com ≥1.000 palavras (a mesma base do Raio-X). O histórico das
    reuniões é só LIDO aqui."""
    treinos = ler_treinos() if treinos is None else treinos
    reunioes = af.ler_historico() if reunioes is None else reunioes
    ant = [r for r in treinos if r.get("tipo") == tipo and r.get("id") != tid and str(r.get("data", "")) < str(data)]
    base = af.anteriores(reunioes, None, "9999", af.METAS_PADRAO["min_palavras"], 5)
    med = {}
    for chave in ("silabas_por_s", "articulacao_sil_s", "muleta_pura_por_1000", "ai_por_1000", "ppm"):
        b = af.base_de(base, chave)
        if b:
            med[chave] = {"mediana": b["mediana"], "n": b["n"]}
    ent = _mediana([((r.get("metrics") or {}).get("voz") or {}).get("entonacao_st") for r in base])
    if ent:
        med["entonacao_st"] = ent
    pe = _mediana([(r.get("metrics") or {}).get("palavras_entre_pausas") for r in ant])
    return {"ultimo": (ant[-1].get("metrics") or {}) if ant else None,
            "ultimo_data": ant[-1].get("data") if ant else None,
            "reunioes": med, "palavras_entre_pausas_treinos": pe}


# ── leitura: o que é · faixa · onde ficou · comparação · o que fazer ─────────
_br = af._br


def _mmss(s):
    s = int(round(s or 0))
    return f"{s // 60}:{s % 60:02d}"


def _comp_txt(chave, comp, fmt=lambda x: _br(x, 2), reunioes=True):
    partes = []
    u = (comp.get("ultimo") or {}).get(chave)
    if u is not None:
        partes.append(f"último treino {fmt(u)}")
    r = (comp.get("reunioes") or {}).get(chave) if reunioes else None
    if r:
        partes.append(f"suas reuniões {fmt(r['mediana'])}")
    return " · ".join(partes) or "primeiro treino deste tipo"


def ler(m, comp):
    """(principais, extras). Principais = os 4 números da tela (ritmo, pausas, muletas, entonação);
    extras = o resto, em "Mais detalhes". Cada item: {chave, nome, valor, valor_txt, o_que_e, faixa,
    fonte, status (ok|fora|info|sem), onde, comparacao, dica}."""
    comp = comp or {}
    alvo = m.get("alvo_silabas_s") or ALVO_PADRAO
    mu_, dp = af.NORMA_SILABAS_S
    curta = (m.get("palavras") or 0) < 150

    def item(chave, nome, valor, valor_txt, o_que_e, faixa, fonte, status, onde, comparacao, dica):
        if curta and status in ("ok", "fora") and chave in PRINCIPAIS:
            onde += f". Fala curta ({m.get('palavras', 0)} palavras): leia com cautela"
        return {"chave": chave, "nome": nome, "valor": valor, "valor_txt": valor_txt, "o_que_e": o_que_e,
                "faixa": faixa, "fonte": fonte, "status": status, "onde": onde, "comparacao": comparacao,
                "dica": dica}

    principais, extras = [], []
    # 1 · ritmo (elocução)
    v = m.get("silabas_por_s") or 0
    dif = v - alvo
    ok = 3.5 <= v <= alvo + TOLERANCIA_ALVO
    lado = ("no alvo" if ok else f"{_br(abs(dif), 1)} acima do alvo" if dif > 0 else "abaixo do ritmo de conversa")
    tc = m.get("trecho_corrido")
    reun = (comp.get("reunioes") or {}).get("silabas_por_s")
    if ok:
        dica = ("mantenha; o desafio é levar esse ritmo para a reunião"
                + (f" (lá a sua mediana é {_br(reun['mediana'], 1)})." if reun else "."))
    elif dif > 0:
        dica = ("pare um instante no fim de cada ideia e respire antes de número, preço e prazo"
                + (f"; ouça o trecho de {_mmss(tc['ini'])}, o mais corrido ({_br(tc['silabas_s'], 1)} sílabas/s)."
                   if tc else "."))
    else:
        dica = "suba um pouco o ritmo: frases mais diretas, menos voltas."
    principais.append(item(
        "silabas_por_s", "Ritmo", v, f"{_br(v, 1)} sílabas/s",
        "Velocidade da fala: sílabas por segundo do começo ao fim, contando as pausas. É o que quem ouve sente.",
        f"alvo {_br(alvo, 1)} sílabas/s ({ALVOS.get(alvo, 'escolhido')}); norma de João Pessoa "
        f"{_br(mu_)} ± {_br(dp)} ({_br(mu_ - dp)} a {_br(mu_ + dp)})",
        "RBCS/UFPB 2019 (adultos de João Pessoa, fala semi-espontânea); alvo da pesquisa de 14/10",
        "ok" if ok else "fora", f"Você ficou em {_br(v, 1)} sílabas/s, {lado}",
        _comp_txt("silabas_por_s", comp, lambda x: _br(x, 1)), dica))

    # 2 · pausas
    pm, pct = m.get("pausas_por_min") or 0, m.get("pausa_pct") or 0
    lo, hi = PAUSAS_POR_MIN
    ok = lo <= pm <= hi
    principais.append(item(
        "pausas_por_min", "Pausas", pm, f"{_br(pm, 1)} por minuto",
        "Silêncios de meio segundo ou mais entre palavras. É onde quem ouve processa a ideia; sem elas, "
        "a fala vira um bloco só.",
        f"{lo} a {hi} por minuto (uma pausa por frase)", "referência prática deste sistema, sem norma publicada",
        "ok" if ok else "fora",
        f"Você fez {_br(pm, 1)} pausas por minuto ({pct}% do tempo em silêncio) e falou em média "
        f"{_br(m.get('palavras_entre_pausas'), 1)} palavras entre uma pausa e outra (nas reuniões esta "
        "medida ainda não existe: o Raio-X delas não guarda o tempo de cada palavra)",
        _comp_txt("pausas_por_min", comp, lambda x: _br(x, 1), reunioes=False),
        "mantenha as pausas: são elas que deixam a velocidade aceitável." if ok else
        ("feche cada frase com um ponto de verdade: meio segundo de silêncio antes da próxima."
         if pm < lo else "pausas demais podem soar como hesitação: pense a próxima frase antes de começar a atual.")))

    # 3 · muletas (muleta pura; o "aí" vai junto na leitura)
    pura, ai = m.get("muleta_pura_por_1000") or 0, m.get("ai_por_1000") or 0
    b = (comp.get("reunioes") or {}).get("muleta_pura_por_1000")
    top = ", ".join(f"\"{k}\" {n}×" for k, n in list((m.get("muletas_puras") or {}).items())[:3]) or "nenhuma"
    if b:
        limite = round(b["mediana"] * (1 - af.METAS_PADRAO["muleta_pura_reducao"]), 1)
        faixa, status = (f"até {_br(limite)} a cada mil palavras (a mediana das suas reuniões, {_br(b['mediana'])}, "
                         "menos 20%: a mesma meta do Raio-X)"), ("ok" if pura <= limite else "fora")
    else:
        faixa, status = "sem meta: ainda não há reuniões com ≥1.000 palavras para tirar a base", "info"
    cada = round(1000 / m["palavras"], 1) if m.get("palavras") else None
    principais.append(item(
        "muleta_pura_por_1000", "Muletas", pura, f"{_br(pura)} a cada mil palavras",
        "Palavras que não carregam nada e saem sem mudar a frase: aí, tipo, cara, pô, enfim, basicamente…",
        faixa, "meta que sai dos seus dados (Raio-X calibrado, §17)", status,
        f"Você ficou em {_br(pura)} (\"aí\" sozinho: {_br(ai)}); as mais usadas: {top}"
        + (f". Num treino deste tamanho, cada muleta pesa {_br(cada)} por mil" if cada else ""),
        _comp_txt("muleta_pura_por_1000", comp, lambda x: _br(x, 1)),
        "mantenha." if status != "fora" else f"a campeã foi {top.split(',')[0]}: troque-a por uma pausa curta."))

    # 4 · entonação
    ent = m.get("entonacao_st")
    if ent is None:
        principais.append(item(
            "entonacao_st", "Entonação", None, "não medida",
            "Quanto o seu tom sobe e desce enquanto você fala (em semitons).", f"{_br(ENTONACAO_ALVO)} semitons ou mais",
            "Arantes (Abralin)", "sem", "Não deu para medir a voz neste áudio" + (f" ({m['voz_erro']})" if m.get("voz_erro") else ""),
            "—", "grave pelo menos 1 minuto de fala contínua no microfone do fone."))
    else:
        zona = af._zona("entonacao_st", ent)[0]
        ok = ent >= ENTONACAO_ALVO
        principais.append(item(
            "entonacao_st", "Entonação", ent, f"{_br(ent, 1)} semitons",
            "Quanto o seu tom sobe e desce enquanto você fala. Um semitom é a distância entre duas teclas "
            "vizinhas do piano. É o que faz a fala soar viva ou monótona.",
            f"{_br(ENTONACAO_ALVO)} semitons ou mais para apresentar; a fala masculina brasileira fica em ~2,9–3",
            "Arantes (Abralin)", "ok" if ok else "fora", f"Você ficou em {_br(ent, 1)} semitons ({zona})",
            _comp_txt("entonacao_st", comp, lambda x: _br(x, 1)),
            "mantenha." if ok else "escolha uma palavra por frase para enfatizar, subindo o tom nela; desça no ponto final."))

    # a leitura em meia linha, para a tela: onde ficou em relação à faixa
    lim_mul = round(b["mediana"] * (1 - af.METAS_PADRAO["muleta_pura_reducao"]), 1) if b else None
    curtos = {
        "silabas_por_s": {"ok": f"no alvo de {_br(alvo, 1)}",
                          "fora": f"acima do alvo de {_br(alvo, 1)}" if v > alvo else "abaixo do ritmo de conversa"},
        "pausas_por_min": {"ok": f"na faixa de {lo} a {hi}",
                           "fora": f"abaixo da faixa de {lo} a {hi}" if pm < lo else f"acima da faixa de {lo} a {hi}"},
        "muleta_pura_por_1000": {"ok": f"dentro da meta (até {_br(lim_mul)})", "fora": f"acima da meta (até {_br(lim_mul)})",
                                 "info": "sem meta ainda"},
        "entonacao_st": {"ok": f"viva ({_br(ENTONACAO_ALVO)} ou mais)", "fora": f"abaixo de {_br(ENTONACAO_ALVO)} semitons",
                         "sem": "sem áudio para medir"},
    }
    for it in principais:
        it["curto"] = curtos[it["chave"]].get(it["status"], "")

    # extras
    art = m.get("articulacao_sil_s") or 0
    extras.append(item(
        "articulacao_sil_s", "Articulação", art, f"{_br(art, 1)} sílabas/s",
        "Sílabas por segundo só enquanto você fala, sem as pausas: a velocidade da boca. A diferença para o "
        "ritmo é o quanto as pausas seguram a fala.",
        "sem norma da mesma fonte: leia junto com o ritmo", "medido aqui", "info",
        f"Você articulou a {_br(art, 1)} sílabas/s; as pausas baixam isso para {_br(v, 1)}",
        _comp_txt("articulacao_sil_s", comp, lambda x: _br(x, 1)),
        "se a articulação está alta e o ritmo no alvo, as pausas estão fazendo o trabalho: mantenha-as."))
    pe = m.get("palavras_entre_pausas") or 0
    rp = comp.get("palavras_entre_pausas_treinos")
    extras.append(item(
        "palavras_entre_pausas", "Palavras entre pausas", pe, f"{_br(pe, 1)} palavras",
        "Quantas palavras você fala, no meio, entre uma pausa e a seguinte. Número alto = frases longas sem respirar.",
        "a régua é a sua mediana nos treinos" + (f": {_br(rp['mediana'], 1)} (em {rp['n']})" if rp else " (ainda sem treinos anteriores)"),
        "medido aqui", "info", f"Você falou {_br(pe, 1)} palavras entre pausas",
        _comp_txt("palavras_entre_pausas", comp, lambda x: _br(x, 1), reunioes=False),
        "se subir em relação à sua mediana, encurte as frases: uma ideia por frase."))
    extras.append(item(
        "ai_por_1000", "\"Aí\"", ai, f"{_br(ai)} a cada mil palavras",
        "O \"aí\" de ligação (\"aí eu fiz, aí ele disse\").", "até 20 a cada mil (degrau 1 do Raio-X)",
        "meta em degraus do Raio-X (§17)", "ok" if ai <= 20 else "fora", f"Você ficou em {_br(ai)}",
        _comp_txt("ai_por_1000", comp, lambda x: _br(x, 1)),
        "mantenha." if ai <= 20 else "termine a frase com ponto e comece a próxima sem o \"aí\"."))
    da, dg = m.get("duracao_alvo_s") or DURACAO_PADRAO_S, m.get("fala_s") or 0
    ok = 0.8 * da <= dg <= 1.2 * da
    extras.append(item(
        "duracao", "Duração", dg, _mmss(dg),
        "Do começo ao fim da fala, contra o tempo que você se deu.", f"alvo {_mmss(da)} (±20%)", "escolha sua",
        "ok" if ok else "fora", f"Você falou {_mmss(dg)} de {_mmss(da)}", "—",
        "mantenha." if ok else ("corte: diga o essencial no tempo combinado." if dg > da
                                else "você terminou cedo: desenvolva o exemplo ou o próximo passo.")))
    if tc:
        extras.append(item(
            "trecho_corrido", "Trecho mais corrido", tc["silabas_s"], f"{_mmss(tc['ini'])}–{_mmss(tc['fim'])}",
            f"Os ~{int(JANELA_CORRIDO_S)} s em que você falou mais rápido.", "—", "medido aqui", "info",
            f"{_br(tc['silabas_s'], 1)} sílabas/s: \"{tc['texto'][:140]}\"", "—",
            "ouça esse trecho: é ali que a pausa no fim da ideia faz mais falta."))
    return principais, extras


# ── o retorno do Claude ──────────────────────────────────────────────────────
_S = {"type": "string"}
_SN = {"type": ["string", "null"]}
ASPECTOS = {
    "reuniao": {
        "ideia_central": "a ideia central foi dita nos primeiros ~20 s?",
        "clareza": "passou por problema → o que muda → próximo passo?",
        "resultado_nao_metodo": "prometeu o resultado (\"vai estar funcionando até sexta\") e não o método "
                                "(\"vou configurar X, vou usar Y\")?",
        "compromisso": "o próximo passo saiu com dono e prazo?",
        "perguntas_abertas": "se havia descoberta, fez perguntas abertas? (sem descoberta: nao_se_aplica)",
        "certeza_promessa": "certeza absoluta ou promessa no reflexo (\"com certeza\", \"já dá\", \"é rapidinho\")?",
    },
    "tema": {
        "ideia_central": "a ideia do tema foi dita em 1 frase logo no começo (~20 s)?",
        "estrutura": "passou por ideia → problema → mecanismo → exemplo?",
        "exemplo": "deu um exemplo concreto (de preferência do trabalho dele)?",
        "certeza_promessa": "afirmou com certeza absoluta algo que merecia ressalva?",
    },
}


def esquema(tipo):
    """JSON Schema fechado do retorno (vai no `--json-schema` do claude -p)."""
    cit = {"type": "object", "additionalProperties": False,
           "properties": {"texto": _S, "citacao": _SN, "t": _SN}, "required": ["texto", "citacao", "t"]}
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "manter": cit, "mudar": cit,
            "pontos": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"aspecto": {"type": "string", "enum": list(ASPECTOS[tipo])},
                               "situacao": {"type": "string", "enum": ["bom", "atencao", "nao_se_aplica"]},
                               "comentario": _S, "citacao": _SN, "t": _SN},
                "required": ["aspecto", "situacao", "comentario", "citacao", "t"]}},
            "conteudo": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"afirmacao": _S, "citacao": _S, "t": _S,
                               "situacao": {"type": "string", "enum": ["confere", "diverge", "fora_da_nota"]},
                               "trecho_nota": _SN, "comentario": _S},
                "required": ["afirmacao", "citacao", "t", "situacao", "trecho_nota", "comentario"]}},
        },
        "required": ["manter", "mudar", "pontos", "conteudo"],
    }


SEPARADOR_NOTA = "=== NOTA DE ESTUDO ==="


def prompt(tipo, assunto=None, com_nota=False, meu_nome="Pedro"):
    asp = "\n".join(f"- {k}: {v}" for k, v in ASPECTOS[tipo].items())
    if tipo == "reuniao":
        quem = (f"Você ouviu o {meu_nome} ENSAIAR SOZINHO uma fala de reunião com cliente"
                + (f" (assunto: {assunto})" if assunto else "") + ". É treino, não reunião.")
    else:
        quem = (f"Você ouviu o {meu_nome} EXPLICAR SOZINHO um tema de estudo"
                + (f" ({assunto})" if assunto else "") + ", em voz alta, para fixar.")
    linhas = [
        quem,
        "A transcrição chega no stdin, uma frase por linha: `[mm:ss] texto`.",
        "Dê um retorno curto, como um colega: português simples, frases curtas, sem jargão, sem elogio vazio.",
        "",
        "Olhe estes pontos (um item em `pontos` para cada um):",
        asp,
        "",
        "`manter` e `mudar`: UMA coisa cada, a mais importante, em uma ou duas frases.",
        "Regras: toda `citacao` é cópia LITERAL de um trecho de UMA linha da transcrição (5 a 25 palavras, "
        "sem reticências, sem corrigir) e `t` é o [mm:ss] dessa linha, sem colchetes; sem trecho, null nos "
        "dois. Nada que não esteja na transcrição. Não comente velocidade, pausas nem muletas: isso já é medido.",
    ]
    if com_nota:
        linhas += [
            "",
            f"Depois da transcrição, após a linha `{SEPARADOR_NOTA}`, vem a nota de estudo dele sobre o tema.",
            "`conteudo`: para cada afirmação importante que ele fez, diga se `confere` com a nota, `diverge` "
            "dela ou está `fora_da_nota`. `trecho_nota` é cópia LITERAL de um trecho da nota (5 a 30 palavras) "
            "que confirma ou contradiz; null quando `fora_da_nota`. Em `comentario`, se diverge, o que a nota diz.",
        ]
    else:
        linhas.append("`conteudo`: lista vazia.")
    return "\n".join(linhas)


def auditar_retorno(ret, palavras, nota_texto=None):
    """A mesma auditoria da ata: a citação tem de estar numa frase da transcrição (o `t` é corrigido
    para o dessa frase); o trecho da nota tem de estar na nota. Marca `verificado` em cada item;
    citação inventada perde a citação (o comentário fica, sem prova)."""
    fl = frases(palavras)
    for it in [ret.get("manter") or {}, ret.get("mudar") or {}] + list(ret.get("pontos") or []) \
            + list(ret.get("conteudo") or []):
        cit = it.get("citacao")
        if not cit:
            it["verificado"] = None
            continue
        i = _ata._achar(cit, fl, _ata.parse_t(it.get("t")))
        if i is None:
            it["verificado"] = False
            it["citacao_inventada"] = cit
            it["citacao"] = None
        else:
            it["verificado"] = True
            it["t"] = _ata.fmt_t(fl[i]["start"])
    for it in ret.get("conteudo") or []:
        tn = it.get("trecho_nota")
        it["nota_verificada"] = (bool(nota_texto) and _ata._contem(tn, nota_texto)) if tn else None
    return ret


def retorno_claude(palavras, tipo, cfg, assunto=None, nota_texto=None, log=print):
    """(retorno auditado, meta). Levanta se o Claude falhar (quem chama segue só com as métricas)."""
    import estruturar
    entrada = transcricao_texto(palavras)
    if nota_texto:
        entrada += f"\n\n{SEPARADOR_NOTA}\n{nota_texto[:30000]}"
    ret, meta = estruturar.chamar_claude(prompt(tipo, assunto, bool(nota_texto), cfg.get("meu_nome", "Pedro")),
                                         entrada, cfg, log, esquema=esquema(tipo))
    meta["versao_prompt"] = VERSAO_PROMPT
    return auditar_retorno(ret, palavras, nota_texto), meta


# ── o fluxo: áudio → palavras → métricas → comparação → Claude → resultado ───
def _registrar(t, m, comp_ok, pasta=None):
    """Upsert da linha deste treino em `treinos.jsonl` (nunca no historico.jsonl das reuniões)."""
    p = hist_treinos_path(pasta)
    p.parent.mkdir(parents=True, exist_ok=True)
    linhas = [r for r in ler_treinos(pasta) if r.get("id") != t.id]
    leve = {k: v for k, v in m.items() if k not in ("frases_revisar", "trecho_corrido", "voz_erro")}
    linhas.append({"id": t.id, "data": t.m.get("inicio") or t.m.get("criado"), "tipo": t.tipo_treino,
                   "assunto": t.m.get("assunto"), "metrics": leve, "retorno": comp_ok})
    linhas.sort(key=lambda r: str(r.get("data", "")))
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in linhas) + "\n", encoding="utf-8")


def analisar(t, cfg=None, log=print, claude=True):
    """Roda o treino gravado (ou importado): devolve o manifesto com `resultado`. Nada aqui escreve
    no historico.jsonl das reuniões nem no vault."""
    import audio
    import config as _config
    cfg = cfg or _config.carregar()
    fonte = audio.fonte_audio(t, "mic")
    if not fonte:
        t.m["estado"] = "falhou"
        t.m["resultado"] = {"erro": "não há áudio neste treino"}
        t.salvar()
        return t.m
    t.m["estado"] = "processando"
    t.salvar()
    x = audio.ler_audio(fonte)
    gravado = len(x) / SR
    log("  Transcrevendo o treino…")
    palavras, info = transcrever(x, cfg, log)
    escrever_json(t.caminho("transcricao.json"), {"palavras": palavras, "info": info})
    nota_txt, nota_p = None, None
    if t.m.get("nota"):
        try:
            nota_p = achar_nota(t.m["nota"])
            nota_txt = nota_p.read_text(encoding="utf-8")          # só leitura: o vault não é tocado
        except Exception as e:
            t.avisar(f"nota não lida: {e}")
    m = medir(palavras, fonte, gravado, t.m.get("alvo_silabas_s"), t.m.get("duracao_alvo_s"))
    data = t.m.get("inicio") or t.m.get("criado")
    comp = comparar(t.tipo_treino, t.id, data)
    principais, extras = ler(m, comp)
    res = {"metrics": m, "comparacao": comp, "principais": principais, "extras": extras,
           "retorno": None, "retorno_erro": None, "em": agora_iso()}
    if not palavras:
        res["retorno_erro"] = "nenhuma fala reconhecida no áudio: confira o microfone"
    elif not claude or not cfg.get("estruturar", True):
        res["retorno_erro"] = "retorno do Claude desligado: só as métricas"
    else:
        log("  Pedindo o retorno ao Claude…")
        try:
            ret, meta = retorno_claude(palavras, t.tipo_treino, cfg, t.m.get("assunto"), nota_txt, log)
            res["retorno"], res["retorno_meta"] = ret, meta
        except Exception as e:
            res["retorno_erro"] = f"o Claude não respondeu ({type(e).__name__}: {str(e)[:200]}): só as métricas"
    t.m["resultado"] = res
    t.m["processado_em"] = agora_iso()
    t.m["estado"] = "pronto"
    t.salvar()
    escrever_resultado(t)
    _registrar(t, m, res["retorno"] is not None)
    try:
        audio.aposentar_pcm(t)                     # mic.pcm → audio/mic.opus, conferido
    except Exception as e:
        t.avisar(f"áudio não compactado: {e}")
    limpar_audio(cfg.get("audio_reter_dias", 30), raiz=t.pasta.parent)
    return t.m


def importar(arquivo, tipo="reuniao", assunto="", nota=None, duracao_alvo_s=DURACAO_PADRAO_S, alvo=ALVO_PADRAO,
             raiz=None, quando=None):
    """Um áudio já gravado (ex.: do celular) vira um treino: decodifica para o mic.pcm do treino e segue
    o mesmo caminho da gravação. O arquivo de origem não é tocado."""
    import audio
    import numpy as np
    origem = pathlib.Path(arquivo)
    if not origem.exists():
        raise FileNotFoundError(f"arquivo não encontrado: {origem}")
    if quando is None:
        import celular
        quando = celular.data_do_nome(origem.name) or _dt.datetime.fromtimestamp(origem.stat().st_mtime)
    x = audio.ler_audio(origem)
    if len(x) < SR:
        raise ValueError("áudio vazio ou com menos de 1 s")
    t = Treino.criar(tipo, assunto, nota, duracao_alvo_s, alvo, raiz=raiz, quando=quando, origem="arquivo")
    (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tofile(str(t.mic_pcm))
    t.m["origem_arquivo"] = {"nome": origem.name, "bytes": origem.stat().st_size}
    t.m["audio"]["duracao_s"] = round(len(x) / SR, 1)
    t.m["estado"] = "gravado"
    t.salvar()
    return t


def limpar_audio(dias, raiz=None):
    """Apaga `audio/` dos treinos prontos mais velhos que `dias`, salvo os marcados para manter."""
    if not dias or dias <= 0:
        return []
    limite = _dt.datetime.now().astimezone() - _dt.timedelta(days=dias)
    limpos = []
    for t in listar(raiz):
        if t.m.get("manter") or t.m.get("estado") != "pronto" or not t.audio_dir.exists():
            continue
        try:
            quando = _dt.datetime.fromisoformat(t.m.get("processado_em") or t.m.get("criado"))
        except (TypeError, ValueError):
            continue
        if quando.tzinfo is None:
            quando = quando.astimezone()
        if quando < limite:
            shutil.rmtree(t.audio_dir, ignore_errors=True)
            t.m["audio_apagado_em"] = agora_iso()
            t.salvar()
            limpos.append(t.id)
    return limpos


def trecho_wav(t, ini, fim, margem_s=0.5):
    """Recorta [ini, fim] do áudio do treino num .wav dentro de `audio/` (apagado com ele) e devolve o
    caminho, para tocar. None se o áudio já foi apagado."""
    import audio
    fonte = audio.fonte_audio(t, "mic")
    if not fonte:
        return None
    x = audio.ler_audio(fonte)
    a, b = max(0, int((ini - margem_s) * SR)), min(len(x), int((fim + margem_s) * SR))
    if b <= a:
        return None
    t.audio_dir.mkdir(exist_ok=True)
    destino = t.audio_dir / "trecho-mais-corrido.wav"
    audio.escrever_wav(destino, x[a:b])
    return destino


# ── texto do resultado (CLI e resultado.md) ──────────────────────────────────
_MARCA = {"ok": "✓", "fora": "!", "info": "·", "sem": "·"}
_ROTULO_ASPECTO = {"ideia_central": "Ideia central", "clareza": "Clareza", "resultado_nao_metodo": "Resultado, não método",
                   "compromisso": "Compromisso", "perguntas_abertas": "Perguntas abertas",
                   "certeza_promessa": "Certeza e promessa", "estrutura": "Estrutura", "exemplo": "Exemplo"}
_SITUACAO = {"bom": "✓", "atencao": "!", "nao_se_aplica": "·"}


def _cit(it):
    return f" [{it['t']}] \"{it['citacao']}\"" if it.get("citacao") and it.get("verificado") else ""


def escrever_resultado(t):
    """`resultado.md` e `resultado.html` (tema RYZE escuro, o mesmo do Raio-X) na pasta do treino.
    A janela mostra o essencial e abre a página para o resto ("Ver tudo")."""
    import tema
    L = texto_resultado(t)
    t.caminho("resultado.md").write_text("\n".join(L), encoding="utf-8")
    quando = (t.m.get("inicio") or t.m.get("criado") or "")[:16].replace("T", " ")
    corpo = (tema.capa(t.m.get("titulo") or "Treino", "Treino de fala", quando)
             + "<section>" + tema.markdown_html("\n".join(L[2:])) + "</section>"
             + tema.rodape("treino · fica fora do Raio-X das reuniões"))
    t.caminho("resultado.html").write_text(tema.pagina(t.m.get("titulo") or "Treino", corpo), encoding="utf-8")
    return t.caminho("resultado.html")


def texto_resultado(t):
    r = t.m.get("resultado") or {}
    m = r.get("metrics") or {}
    L = [f"# {t.m.get('titulo')}", "",
         f"_{(t.m.get('inicio') or t.m.get('criado') or '')[:16].replace('T', ' ')} · {_mmss(m.get('fala_s'))} de fala · "
         f"{m.get('palavras', 0)} palavras · treino (fica fora do Raio-X das reuniões)_", ""]
    if r.get("erro"):
        return L + [r["erro"]]
    L.append("## Os números")
    for it in r.get("principais") or []:
        L += [f"- {_MARCA[it['status']]} **{it['nome']}: {it['valor_txt']}** — {it['onde']}.",
              f"    - Comparação: {it['comparacao']}.", f"    - Faixa: {it['faixa']} _(fonte: {it['fonte']})_.",
              f"    - O que é: {it['o_que_e']}"]
        if it["dica"]:
            L.append(f"    - O que fazer: {it['dica']}")
    ret = r.get("retorno")
    L += ["", "## O retorno"]
    if ret:
        L += [f"- **Manter:** {ret['manter']['texto']}{_cit(ret['manter'])}",
              f"- **Mudar:** {ret['mudar']['texto']}{_cit(ret['mudar'])}", ""]
        for p in ret.get("pontos") or []:
            L.append(f"- {_SITUACAO.get(p['situacao'], '·')} {_ROTULO_ASPECTO.get(p['aspecto'], p['aspecto'])}: "
                     f"{p['comentario']}{_cit(p)}")
        if ret.get("conteudo"):
            L += ["", "### Conteúdo contra a nota"]
            for c in ret["conteudo"]:
                marca = {"confere": "✓", "diverge": "✗", "fora_da_nota": "?"}[c["situacao"]]
                prova = "" if c.get("nota_verificada") or not c.get("trecho_nota") else " _(trecho da nota não localizado)_"
                L.append(f"- {marca} {c['afirmacao']} — {c['comentario']}{prova}")
    else:
        L.append(f"_Sem retorno do Claude: {r.get('retorno_erro') or 'não pedido'}._")
    L += ["", "## Mais detalhes"]
    for it in r.get("extras") or []:
        dica = it["dica"][:1].upper() + it["dica"][1:] if it["dica"] else ""
        L.append(f"- {_MARCA[it['status']]} {it['nome']}: {it['valor_txt']} — {it['onde']}. {dica}")
    for f in m.get("frases_revisar") or []:
        L.append(f"- [{_mmss(f['t'])}] {f['motivo']}: \"{f['texto']}\"")
    return L
