# -*- coding: utf-8 -*-
"""Rodar da raiz do repo, SEMPRE com o venv do faster-whisper:

    C:\\Users\\olive\\.venvs\\faster-whisper\\Scripts\\python.exe -m pytest tests -q
    ... -m "not lento"      pula o teste de fumaça (Whisper e Chrome de verdade, ~1 min)
"""
import pathlib
import sys

import pytest

LOCAL = pathlib.Path(__file__).resolve().parent.parent / "local"
sys.path.insert(0, str(LOCAL))


def pytest_configure(config):
    config.addinivalue_line("markers", "lento: roda o Whisper/Chrome de verdade")


@pytest.fixture
def raiz(tmp_path):
    return tmp_path / "atas-salvas"


def segs_exemplo():
    return [
        {"speaker": "Você", "start": 0.0, "end": 4.0,
         "text": "Bom dia Ricardo, vamos revisar o módulo de pagamentos do Mettria hoje."},
        {"speaker": "Participante", "start": 5.0, "end": 12.0,
         "text": "Bom dia Pedro. Ficou decidido que a release espera a resposta do gateway."},
        {"speaker": "Você", "start": 13.0, "end": 19.0,
         "text": "Combinado. Eu mando o resumo para o time até sexta-feira à tarde."},
        {"speaker": "Participante", "start": 20.0, "end": 27.0,
         "text": "E alguém precisa revisar os eventos do onboarding antes da próxima sprint."},
    ]
