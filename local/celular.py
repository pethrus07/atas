# -*- coding: utf-8 -*-
"""
Reunião presencial gravada no celular (14/10/2026): um arquivo de áudio → uma sessão do Atas.

O gravador normal tem dois canais físicos — o microfone é o Pedro ("Você"), o loopback é a
chamada —, e é isso que garante a regra "só as falas de Você são dele". Numa reunião
presencial o celular grava **todo mundo num canal só**. Então:

    arquivo (m4a/mp3/wav/ogg/opus/aac/amr/3gp)
      → ffmpeg → atas-salvas/<id>/audio/celular.opus (mono 16 kHz, conferido)
      → transcrição de um canal só, rótulo "Falante"
      → diarização com N = participantes informados + o Pedro (sem eles: limiar + teto, §6)
      → qual grupo é o Pedro? (escolher_voce, abaixo) → "Você"; os outros → "Participante N"
      → tudo "a confirmar" até o /ata (`atas.py falantes` / `confirmar`)

**Quem é o Pedro.** Duas pistas, nesta ordem:
  1. **Amostra de referência** (`local/models/voz-referencia.wav`, fora do git): ~60 s da voz
     dele tirados do canal do MICROFONE de uma reunião gravada pelo Atas (lá só tem ele). O
     `diarize.py` compara o vetor de voz (CAM++, o mesmo da diarização) de cada grupo com o da
     amostra. Vale se o mais parecido passar de SIM_MIN e ganhar do segundo por MARGEM_MIN.
  2. **Tom da voz**: a mediana do tom do Pedro no histórico do Raio-X (~138 Hz). Vale só se
     exatamente um grupo ficar a até TOM_MAX_ST semitons dela — separa o Pedro de uma voz
     feminina, não de outro homem de voz parecida.
  Se nenhuma vale, ninguém vira "Você": todos ficam "Participante N" e o /ata pergunta.
  Os limiares foram escolhidos com vozes sintéticas, não calibrados em reunião real.

**Enquanto "Você" não é confirmado**: o Raio-X e a avaliação interna ficam `pendente` (medir a
voz de outra pessoa como se fosse a dele estragaria o histórico), e na ata "Você" aparece como
"a confirmar".

**Tipo.** Sem `--tipo`, a sessão fica `pendente` (regra de 30/09: o tipo é escolha do Pedro):
não gera entregável, não publica, não é avaliada, até `atas.py tipo <id> <tipo>`.

**LGPD.** As mesmas regras da gravação normal: o áudio fica 30 dias nesta máquina, interno não
sai dela. O arquivo de origem não é apagado (a não ser com `apagar_origem`); se ele veio pela
nuvem (OneDrive), a cópia de lá é responsabilidade de quem configurou a sincronização.
"""
import datetime as _dt
import hashlib
import json
import math
import pathlib
import re
import shutil
import subprocess
import time

import sessao as _sessao
from sessao import TIPO_PENDENTE, TIPOS, Sessao, agora_iso

EXTENSOES = {".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac", ".amr", ".3gp"}
REFERENCIA = pathlib.Path(__file__).parent / "models" / "voz-referencia.wav"
REFERENCIA_S = 60.0          # segundos de voz na amostra
SIM_MIN = 0.45               # cosseno mínimo para o grupo ser o Pedro pela amostra
MARGEM_MIN = 0.10            # e a distância mínima para o segundo mais parecido
TOM_MAX_ST = 2.0             # pelo tom: a até 2 semitons da mediana do Pedro, e só um grupo
IDADE_MIN_S = 60             # vigiar: arquivo mexido há menos que isso ainda está sincronizando

# AAAA-MM-DD_HHMM (MacroDroid), 20261014_103000, "Gravação 2026-10-14 10-30-00"…
_DATA_NO_NOME = re.compile(r"(20\d\d)[-_.]?([01]\d)[-_.]?([0-3]\d)[ _T.-]*([0-2]\d)[-_.h:]?([0-5]\d)")


# ── arquivo ───────────────────────────────────────────────────────────────────
def hash_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def data_do_nome(nome):
    """datetime do nome do arquivo (ex.: '2026-10-14_1030.m4a'), ou None."""
    m = _DATA_NO_NOME.search(pathlib.Path(nome).stem)
    if not m:
        return None
    try:
        return _dt.datetime(*(int(x) for x in m.groups()))
    except ValueError:
        return None


def titulo_do_nome(nome, quando=None):
    """Título a partir do nome do arquivo; nome que é só data vira 'Reunião presencial dd/mm HH:MM'."""
    stem = pathlib.Path(nome).stem
    resto = re.sub(r"[_\-.]+", " ", _DATA_NO_NOME.sub(" ", stem)).strip()
    if resto and not resto.isdigit():
        return resto
    return f"Reunião presencial {quando:%d/%m %H:%M}" if quando else "Reunião presencial"


def _ffmpeg():
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado no PATH (winget install Gyan.FFmpeg)")
    return ff


def duracao_origem(caminho):
    """Duração do arquivo de origem pelo ffprobe, ou None se não houver como saber."""
    fp = shutil.which("ffprobe")
    if not fp:
        return None
    r = subprocess.run([fp, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                        str(caminho)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def converter(origem, destino):
    """Qualquer áudio que o ffmpeg leia → Ogg/Opus mono 16 kHz 24 kbps (o mesmo do gravador).
    Escreve num temporário e confere a duração antes de trocar. Devolve os segundos."""
    import audio
    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp.opus")
    r = subprocess.run([_ffmpeg(), "-nostdin", "-v", "error", "-y", "-i", str(origem), "-vn",
                        "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "24k",
                        "-application", "voip", str(tmp)], capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg não converteu {pathlib.Path(origem).name}: {(r.stderr or '').strip()[-300:]}")
    dur = audio.duracao_opus(tmp)
    ref = duracao_origem(origem)
    if dur < 1.0 or (ref and abs(dur - ref) > max(2.0, 0.01 * ref)):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"conversão incompleta: {dur:.1f}s de {ref or '?'}s")
    tmp.replace(destino)
    return dur


def ja_importados(raiz=None):
    """{sha256: id da sessão} de tudo o que já veio de arquivo."""
    out = {}
    for s in _sessao.listar(raiz):
        h = (s.m.get("origem_arquivo") or {}).get("sha256")
        if h:
            out[h] = s.id
    return out


# ── importar ──────────────────────────────────────────────────────────────────
def importar(arquivo, titulo=None, tipo=None, projeto="", participantes=None, formato=None,
             quando=None, raiz=None, processar=True, cfg=None, log=print, forcar=False,
             apagar_origem=False):
    """Cria a sessão a partir de um arquivo de áudio e (por padrão) roda o pipeline.
    Devolve a Sessao. Levanta ValueError se o arquivo já foi importado (sem `forcar`)."""
    arquivo = pathlib.Path(arquivo)
    if not arquivo.is_file():
        raise FileNotFoundError(f"arquivo não encontrado: {arquivo}")
    if arquivo.suffix.lower() not in EXTENSOES:
        raise ValueError(f"extensão {arquivo.suffix} não aceita ({', '.join(sorted(EXTENSOES))})")
    tipo = tipo or TIPO_PENDENTE
    if tipo != TIPO_PENDENTE and tipo not in TIPOS:
        raise ValueError(f"tipo inválido: {tipo!r} (use {', '.join(TIPOS)}, ou deixe vazio = pendente)")
    sha = hash_arquivo(arquivo)
    feito = ja_importados(raiz).get(sha)
    if feito and not forcar:
        raise ValueError(f"este arquivo já foi importado: {feito}")

    if quando:
        inicio_por = "informado"
    elif data_do_nome(arquivo.name):
        quando, inicio_por = data_do_nome(arquivo.name), "nome do arquivo"
    else:
        quando, inicio_por = None, "data do arquivo"          # acertado depois da duração
    st = arquivo.stat()
    provisoria = quando or _dt.datetime.fromtimestamp(st.st_mtime)
    s = Sessao.criar(titulo or titulo_do_nome(arquivo.name, provisoria), tipo, projeto,
                     participantes, raiz=raiz, formato=formato, quando=provisoria, pendente_ok=True)
    try:
        dur = converter(arquivo, s.audio_dir / "celular.opus")
    except Exception:
        shutil.rmtree(s.pasta, ignore_errors=True)            # sessão sem áudio não serve para nada
        raise
    if not quando:                                             # mtime ≈ fim da gravação
        quando = _dt.datetime.fromtimestamp(st.st_mtime) - _dt.timedelta(seconds=dur)
    ini = quando.astimezone()
    s.m.update({
        "origem": "celular", "canais": 1,
        "origem_arquivo": {"nome": arquivo.name, "sha256": sha, "bytes": st.st_size,
                           "importado_em": agora_iso()},
        "inicio": ini.isoformat(timespec="seconds"), "inicio_por": inicio_por,
        "fim": (ini + _dt.timedelta(seconds=dur)).isoformat(timespec="seconds"),
        "dispositivos": {"celular": arquivo.name},
        "celular": {"voce_confirmado": False},
    })
    s.m["audio"]["duracao_s"] = round(dur, 1)
    if tipo == TIPO_PENDENTE:
        s.m["classificacao"] = "pendente"
    s.salvar()
    s.etapa("captura", "ok", f"importada do celular: {arquivo.name} · {dur / 60:.0f} min · "
            f"início pela {inicio_por}")
    s.estado("gravado")
    log(f"importada: {s.id} ({dur / 60:.0f} min, tipo {tipo})")
    if processar:
        import pipeline
        pipeline.processar(s, cfg, log=log)
        s = Sessao.abrir(s.pasta)
    if apagar_origem and audio_conferido(s):
        arquivo.unlink(missing_ok=True)
        log(f"  origem apagada: {arquivo}")
    return s


def audio_conferido(s):
    import audio
    op = s.audio_dir / "celular.opus"
    try:
        return op.exists() and audio.duracao_opus(op) >= 1.0
    except Exception:
        return False


def vigiar(pasta, raiz=None, tipo=None, projeto="", processar=True, cfg=None, log=print,
           idade_min_s=IDADE_MIN_S, apagar_origem=False, agora=None):
    """Importa os áudios novos de `pasta` (uma passada). Não duplica: compara o sha256 com o de
    tudo o que já foi importado. Pula o que foi mexido há menos de `idade_min_s` (o OneDrive ainda
    está baixando). Sem `tipo`, cada reunião fica pendente. Devolve [(arquivo, id ou motivo)]."""
    pasta = pathlib.Path(pasta)
    if not pasta.is_dir():
        raise FileNotFoundError(f"pasta não encontrada: {pasta}")
    agora = agora or time.time()
    vistos = ja_importados(raiz)
    out = []
    for arq in sorted(pasta.iterdir(), key=lambda p: p.name):
        if not arq.is_file() or arq.suffix.lower() not in EXTENSOES:
            continue
        if agora - arq.stat().st_mtime < idade_min_s:
            out.append((arq, "ainda sincronizando"))
            continue
        sha = hash_arquivo(arq)
        if sha in vistos:
            continue                                           # já importado: silêncio
        try:
            s = importar(arq, tipo=tipo, projeto=projeto, raiz=raiz, processar=processar, cfg=cfg,
                         log=log, apagar_origem=apagar_origem)
            vistos[sha] = s.id
            out.append((arq, s.id))
        except Exception as e:
            log(f"  ✗ {arq.name}: {e}")
            out.append((arq, f"falhou: {e}"))
    return out


# ── quem é o Pedro ────────────────────────────────────────────────────────────
def referencia(cfg=None):
    p = pathlib.Path((cfg or {}).get("voz_referencia") or REFERENCIA)
    return p if p.exists() and p.stat().st_size > 16000 * 2 * 5 else None


def criar_referencia(s=None, raiz=None, destino=None, log=print):
    """Amostra da voz do Pedro: até REFERENCIA_S segundos das falas "Você" (≥ 2 s cada, espalhadas
    pela reunião) do canal do MICROFONE de uma reunião gravada pelo Atas — o canal que só tem ele.
    Sem `s`, usa a mais recente com microfone e transcrição. Devolve o caminho."""
    import numpy as np
    import audio
    destino = pathlib.Path(destino or REFERENCIA)
    cands = [s] if s else [x for x in reversed(_sessao.listar(raiz))
                           if not x.celular and x.caminho("transcricao.json").exists()]
    for x in cands:
        fonte = audio.fonte_audio(x, "mic")
        segs = (_sessao.ler_json(x.caminho("transcricao.json"), {}) or {}).get("segments", [])
        voce = [g for g in segs if g.get("speaker") == "Você" and g["end"] - g["start"] >= 2.0]
        if not fonte or sum(g["end"] - g["start"] for g in voce) < 20:
            continue
        x_audio = audio.ler_audio(fonte)
        total = sum(g["end"] - g["start"] for g in voce)
        passo = max(1, int(total / REFERENCIA_S))
        pedacos, tot = [], 0.0
        for g in voce[::passo]:
            pedacos.append(x_audio[int(g["start"] * 16000):int(g["end"] * 16000)])
            tot += g["end"] - g["start"]
            if tot >= REFERENCIA_S:
                break
        destino.parent.mkdir(parents=True, exist_ok=True)
        audio.escrever_wav(destino, np.concatenate(pedacos))
        destino.with_suffix(".json").write_text(json.dumps(
            {"sessao": x.id, "segundos": round(tot, 1), "criado": agora_iso(),
             "o_que_e": "amostra da voz do Pedro (canal do microfone) para achar 'Você' no áudio do celular"},
            ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  amostra de voz de referência: {tot:.0f} s de {x.id}")
        return destino
    raise RuntimeError("nenhuma reunião com áudio do microfone e ≥ 20 s de fala sua para tirar a amostra")


def tom_de_referencia(pasta=None):
    """Mediana do tom do Pedro (Hz) nas reuniões do histórico do Raio-X, ou None."""
    import statistics
    import analise_fala
    tons = [((r.get("metrics") or {}).get("voz") or {}).get("tom_hz")
            for r in analise_fala.ler_historico(pasta)]
    tons = [t for t in tons if isinstance(t, (int, float)) and t > 0]
    return round(statistics.median(tons)) if tons else None


def _br(x):
    return f"{x:.2f}".replace(".", ",")


def escolher_voce(similaridades=None, tons=None, tom_ref=None):
    """Qual rótulo é o Pedro. {rotulo|None, metodo, evidencia}. Puro: os números vêm de fora.
    similaridades: {rotulo: cosseno com a amostra}; tons: {rotulo: Hz}; tom_ref: Hz do Pedro."""
    sims = sorted((similaridades or {}).items(), key=lambda kv: kv[1], reverse=True)
    if sims:
        (r1, v1), v2 = sims[0], (sims[1][1] if len(sims) > 1 else 0.0)
        if v1 >= SIM_MIN and v1 - v2 >= MARGEM_MIN:
            seg = f"; o segundo mais parecido ficou em {_br(v2)}" if len(sims) > 1 else ""
            return {"rotulo": r1, "metodo": "referencia",
                    "evidencia": f"voz parecida com a sua amostra de referência ({_br(v1)}{seg}) — a confirmar"}
    if tons and tom_ref:
        dist = {r: abs(12 * math.log2(hz / tom_ref)) for r, hz in tons.items() if hz}
        perto = [r for r, d in dist.items() if d <= TOM_MAX_ST]
        if len(perto) == 1:
            r = perto[0]
            return {"rotulo": r, "metodo": "tom",
                    "evidencia": f"tom da voz ({round(tons[r])} Hz) perto do seu ({tom_ref} Hz) e o único "
                                 f"grupo a até {TOM_MAX_ST:g} semitons — pista fraca, a confirmar"}
    motivo = ("nenhum grupo parecido o bastante com a sua amostra" if sims else
              "sem amostra de referência" if not tons else "o tom não separou os grupos")
    return {"rotulo": None, "metodo": "nenhum", "evidencia": f"não deu para saber qual é você ({motivo})"}


def aplicar_rotulos(segs, rotulo_voce):
    """"Falante N" → "Você" (o escolhido) e "Participante"/"Participante N" (os outros, na ordem em
    que aparecem; um só = "Participante", como na chamada com 1 remoto). Devolve {antigo: novo}."""
    ordem = []
    for s in sorted(segs, key=lambda x: x["start"]):
        if s["speaker"] != rotulo_voce and s["speaker"] not in ordem:
            ordem.append(s["speaker"])
    mapa = {r: ("Participante" if len(ordem) == 1 else f"Participante {i + 1}") for i, r in enumerate(ordem)}
    if rotulo_voce:
        mapa[rotulo_voce] = "Você"
    for s in segs:
        s["speaker"] = mapa.get(s["speaker"], s["speaker"])
    return mapa


def trocar_voce(segs, novo):
    """O Pedro disse que `novo` é ele: `novo` vira "Você" e o "Você" de antes (se havia) fica com o
    rótulo de `novo`. Devolve True se algo mudou."""
    if novo == "Você":
        return False
    rotulos = {s["speaker"] for s in segs}
    if novo not in rotulos:
        raise ValueError(f"rótulo {novo!r} não existe ({', '.join(sorted(rotulos))})")
    for s in segs:
        if s["speaker"] == novo:
            s["speaker"] = "Você"
        elif s["speaker"] == "Você":
            s["speaker"] = novo
    return True


def confirmar_voce(s, novo=None, meu_nome="Pedro"):
    """Grava a confirmação do /ata: troca os rótulos na transcrição e na ata, se preciso, e marca
    `celular.voce_confirmado`. Devolve True se a atribuição mudou (a ata deveria ser refeita)."""
    import ata as _ata
    t = _sessao.ler_json(s.caminho("transcricao.json"), {}) or {}
    segs = t.get("segments", [])
    mudou = bool(novo) and trocar_voce(segs, novo)
    if mudou:
        _sessao.escrever_json(s.caminho("transcricao.json"), t)
    cel = s.m.setdefault("celular", {})
    cel.update({"voce_confirmado": True, "confirmado_em": agora_iso(),
                "rotulo_confirmado": novo or cel.get("rotulo")})
    if mudou:
        cel["trocado_de"] = novo
    s.salvar()
    a = _sessao.ler_json(s.caminho("ata.json"))
    if a:
        antigos = {p["rotulo"]: p for p in a.get("participantes", [])}
        novos = _ata.participantes_iniciais(segs, meu_nome, s.participantes_remotos())
        for p in novos:
            v = antigos.get(p["rotulo"])
            if v and not mudou and not p["confirmado"] and v.get("nome"):
                p.update({k: v.get(k) for k in ("nome", "origem", "confirmado", "evidencia")})
        a["participantes"] = novos
        _sessao.escrever_json(s.caminho("ata.json"), a)
    return mudou
