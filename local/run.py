# -*- coding: utf-8 -*-
"""
Atas — fluxo completo de uma reunião, no seu XPS.

  gravar  ->  transcrever  ->  resumir/publicar (Worker)  ->  link

O áudio NÃO é guardado: os .wav são apagados no final (bloco finally).
Sempre salva um backup .md local, mesmo que o upload falhe.

Uso:  python run.py     (ou dê 2 cliques em gravar.bat)
"""
import json
import os
import pathlib
import subprocess
import sys
import time

import record
import transcribe
import upload
import entregavel
import analise_fala

BASE = pathlib.Path(__file__).parent
CONFIG = BASE / "config.json"
OUT = BASE / "out"
SALVAS = BASE.parent / "atas-salvas"


def carregar_config():
    if not CONFIG.exists():
        print(f"ERRO: falta o arquivo de configuração: {CONFIG}")
        print("Copie config.example.json para config.json e preencha worker_url + upload_token.")
        sys.exit(1)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    faltando = [k for k in ("worker_url", "upload_token") if not cfg.get(k)]
    if faltando:
        print(f"ERRO: config.json sem: {', '.join(faltando)}")
        sys.exit(1)
    return cfg


def copiar_clipboard(texto):
    try:
        subprocess.run("clip", input=texto, text=True, shell=True, check=False)
        return True
    except Exception:
        return False


def abrir(caminho):
    """Abre um arquivo no app padrão do Windows (best-effort, nunca levanta)."""
    try:
        if caminho and hasattr(os, "startfile"):
            os.startfile(str(caminho))
    except Exception:
        pass


def salvar_md(titulo, segments, url=None):
    SALVAS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    nome_seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in titulo).strip()
    caminho = SALVAS / f"{stamp}_{nome_seguro or 'reuniao'}.md"
    linhas = [f"# {titulo}", "", f"_Gravado em {time.strftime('%d/%m/%Y %H:%M')}_", ""]
    if url:
        linhas += [f"Link: {url}", ""]
    linhas += ["## Transcrição", ""]
    for s in segments:
        mm = int(s["start"] // 60)
        ss = int(s["start"] % 60)
        linhas.append(f"**[{mm:02d}:{ss:02d}] {s['speaker']}:** {s['text']}")
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    return caminho


def main():
    cfg = carregar_config()
    OUT.mkdir(exist_ok=True)
    mic_wav = OUT / "mic.wav"
    loop_wav = OUT / "loopback.wav"

    print("=" * 56)
    print("  ATAS — gravador de reunião")
    print("=" * 56)
    print("\n  Lembrete: avise/peça consentimento para gravar. (LGPD)\n")

    try:
        diag = record.capturar(mic_wav, loop_wav, cfg.get("microfone"))
        if diag["dur_mic"] < 1 and diag["dur_loop"] < 1:
            print("\n  Gravação vazia. Nada a fazer.")
            return

        titulo = input("\n  Título da reunião (ex.: Cliente X — proposta): ").strip()
        if not titulo:
            titulo = f"Reunião {time.strftime('%d/%m/%Y %H:%M')}"

        print("\n  Transcrevendo (offline, pode levar alguns minutos)...")
        diar = {
            "enabled": cfg.get("diarizar", True),
            "threshold": cfg.get("diar_threshold", 0.5),
            "num_speakers": cfg.get("diar_num_speakers", -1),
            "python": cfg.get("diar_python"),
        }
        segments = transcribe.transcrever(mic_wav, loop_wav, cfg.get("model", "small"), diar)
        if not segments:
            print("  Nenhuma fala reconhecida. Backup salvo mesmo assim.")

        url = None
        try:
            print("\n  Publicando (resumo por IA + página)...")
            url = upload.enviar(segments, titulo, cfg["worker_url"], cfg["upload_token"])
        except Exception as e:
            print(f"  ⚠  Falha ao publicar: {e}")
            print("     Sem problema — o backup local foi salvo.")

        md = salvar_md(titulo, segments, url)

        # Entregável offline (PDF/HTML com a marca) — para enviar ao cliente sem
        # compartilhar o link. Puramente adicional: falhar aqui não quebra nada.
        # Depende do `url`: a página é BAIXADA do Worker, não montada aqui. Sem
        # upload não há PDF — o entregável é offline para o cliente, não para nós.
        entregas = {"html": None, "pdf": None}
        if url:
            try:
                print("\n  Gerando entregável (PDF/HTML) para mandar ao cliente...")
                entregas = entregavel.gerar(url, md.with_suffix(""))
            except Exception as e:
                print(f"  (entregável não gerado, sem problema: {e})")

        print("\n" + "=" * 56)
        print("  PRONTO!")
        if entregas.get("pdf"):
            print("  → Mande ESTE arquivo ao cliente (PDF):")
            print(f"    {entregas['pdf']}")
        elif entregas.get("html"):
            print("  → Mande ESTE arquivo ao cliente (HTML):")
            print(f"    {entregas['html']}")
        print(f"\n  Backup (.md): {md}")
        if url:
            copiar_clipboard(url)
            print(f"  Link ao vivo (opcional; a URL contém 'desbravando'): {url}")
        else:
            print("  (Sem link: o upload falhou; use o backup .md acima.)")

        # Raio-X da fala — análise pessoal INTERNA (nunca vai ao cliente).
        rx = None
        try:
            rx = analise_fala.processar(segments, titulo, time.strftime("%Y-%m-%dT%H:%M"))
            print(f"\n  Raio-x da fala (interno): {rx['dashboard']}")
        except Exception as e:
            print(f"  (raio-x da fala não gerado, sem problema: {e})")

        # Abre automaticamente o entregável do cliente (PDF/HTML) e o raio-x da fala.
        entregavel_path = entregas.get("pdf") or entregas.get("html")
        rx_path = rx.get("dashboard") if isinstance(rx, dict) else None
        if entregavel_path or rx_path:
            print("\n  Abrindo o PDF e o raio-x da fala...")
            abrir(entregavel_path)
            abrir(rx_path)
        print("=" * 56)
    finally:
        # Áudio nunca fica guardado.
        for f in (mic_wav, loop_wav):
            try:
                if f.exists():
                    os.remove(f)
            except Exception:
                pass


if __name__ == "__main__":
    main()
    try:
        input("\n  (ENTER para fechar)")
    except Exception:
        pass
