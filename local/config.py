# -*- coding: utf-8 -*-
"""
Configuração: `local/config.json` (fora do git) por cima dos padrões abaixo.

Nenhuma chave é obrigatória para gravar: `worker_url` e `upload_token` só são
exigidos na hora de PUBLICAR uma reunião de cliente. Reunião interna não precisa
de nada remoto — e não deve precisar (decisão 1 de 30/09/2026).
"""
import glob
import json
import os
import pathlib
import shutil

BASE = pathlib.Path(__file__).parent
CONFIG = BASE / "config.json"

PADROES = {
    "meu_nome": "Pedro",
    "worker_url": "",
    "upload_token": "",
    # transcrição
    "model": "auto",              # auto = large-v3-turbo na GPU, small na CPU
    "dispositivo": "auto",        # auto | cuda | cpu
    "vocabulario": True,
    "idioma": "pt",
    # diarização
    "diarizar": True,
    "diar_threshold": 0.7,       # calibrado 30/09 (corpus sintético); recalibrar com áudio real: atas.py calibrar
    "diar_max_falantes": 6,
    "diar_python": None,
    "microfone": None,
    # ata estruturada pelo Claude
    "estruturar": True,
    "claude_cli": None,           # None = procura o claude.exe da extensão do VS Code
    "claude_modelo": None,        # None = o padrão da conta
    "claude_timeout_s": 1200,
    # retenção
    "audio_reter_dias": 30,
    "publicacao_reter_dias": 90,
    # ao vivo (R9)
    "ao_vivo": False,
    "ao_vivo_janela_s": 30,
}


def carregar(caminho=CONFIG):
    cfg = dict(PADROES)
    p = pathlib.Path(caminho)
    if p.exists():
        dado = json.loads(p.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in dado.items() if not k.startswith("_")})
    # compatibilidade: o config de antes da v2 tinha "model": "small" fixo, que
    # desperdiça a GPU. "small" continua valendo se for escolha explícita nova.
    return cfg


def pode_publicar(cfg):
    return bool(cfg.get("worker_url") and cfg.get("upload_token"))


def _versao(caminho):
    import re
    m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", caminho)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def claude_cli(cfg):
    """Caminho do claude.exe: config → PATH → extensão do VS Code mais nova."""
    if cfg.get("claude_cli") and pathlib.Path(cfg["claude_cli"]).exists():
        return cfg["claude_cli"]
    achado = shutil.which("claude")
    if achado:
        return achado
    padrao = os.path.join(os.path.expanduser("~"), ".vscode", "extensions",
                          "anthropic.claude-code-*", "resources", "native-binary", "claude.exe")
    candidatos = sorted(glob.glob(padrao), key=_versao)
    return candidatos[-1] if candidatos else None
