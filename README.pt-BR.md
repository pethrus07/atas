# Ágora

[English](README.md) · Português

Gravador de reuniões que roda inteiro numa máquina Windows. Grava a chamada no disco enquanto ela
acontece, transcreve localmente na GPU, separa quem falou e monta uma ata estruturada (decisões,
encaminhamentos com dono e prazo, perguntas em aberto, riscos). Cada item da ata aponta o trecho da
conversa de onde saiu. O que não foi dito aparece como lacuna, nunca como dado.

O nome visível é Ágora desde 22/10/2026. O repositório, a pasta, o `atas.py` e a skill `/ata` mantêm o
nome antigo de propósito.

## Status

Em uso diário, só local (11/2026). A publicação de atas para o cliente (Cloudflare Worker + D1) existe no
código mas está desligada desde 22/10/2026: o Worker está vazio e nada sai da máquina.

## O problema

Reunião importante some da memória em dias. Anotar à mão durante a chamada tira a atenção da conversa, e
resumo feito depois mistura o que foi dito com o que se lembra. O Ágora grava, transcreve e só registra o
que tem citação.

## Stack

- Python 3.14: `tkinter` (janela), `soundcard` e `sounddevice` (captura do microfone e do áudio da chamada),
  `faster-whisper` large-v3-turbo na GPU (CUDA), `av`/ffmpeg (Opus), `numpy`.
- Python 3.12 num venv separado: `sherpa-onnx` para separar as vozes (diarização).
- Claude Code (`claude -p`) para estruturar a ata a partir da transcrição, com auditoria das citações.
- Chrome headless para o PDF.
- Cloudflare Worker + D1 (`worker/`), sem uso desde 22/10/2026.

## Como funciona

```
[máquina Windows, tudo local]
 app.py (janela) / atas.py (CLI)
   record.py       microfone + áudio da chamada -> .pcm no disco, bloco a bloco
   transcribe.py   Whisper large-v3-turbo (GPU) + vocabulário por tipo de reunião
   diarize.py      separa as vozes remotas (venv próprio), com teto
   estruturar.py   claude -p -> ata.json, auditada por ata.py
   render.py       ata.md · ata.html · PDF · entregavel.pdf
   analise_fala.py Raio-X da fala (interno)
   ao_vivo.py      transcrição ao vivo (ao-vivo.md) e modo intervencionista

[Cloudflare] worker/ (Worker + D1): vazio e sem uso desde 22/10/2026.
             upload.py e o código de publicação continuam no repositório, desligados.
```

Se o PC travar, a gravação perde no máximo os últimos ~5 s: o áudio vai para o disco em blocos.

## Rodar localmente

Só Windows, com GPU NVIDIA para a transcrição rápida (sem GPU funciona, mais devagar).

1. Venv principal (Python 3.14): `faster-whisper soundcard sounddevice numpy av pytest pillow` e, para a GPU,
   `nvidia-cublas-cu12` e `nvidia-cudnn-cu12==9.*`.
2. Venv da diarização (Python 3.12): `sherpa-onnx numpy`, com os modelos ONNX (~35 MB) em `local/models/diar/`.
3. Claude Code instalado.
4. Copie `local/config.example.json` para `local/config.json`. Nenhuma chave é obrigatória para gravar.
5. Rode `python local/app.py` (janela) ou `python local/atas.py --help` (linha de comando).

O manual do dia a dia (daily, marcar momento, intervencionista, reunião gravada no celular, modo treino) está
em [docs/USO.md](docs/USO.md).

## Testes

```
python -m pytest tests -q                  # 211 testes, ~1 min
python -m pytest tests -q -m "not lento"   # pula os que usam Whisper, Chrome ou dispositivo real
cd worker && npm test                      # 10 testes do Worker (Miniflare)
```

Os 2 testes de `tests/test_dispositivos_reais.py` precisam de microfone e saída de áudio de verdade. As
fixtures de áudio (`tests/fixtures/*.opus`) são vozes sintéticas (SAPI), não gravações de pessoas.

## Estrutura

```
local/       app, CLI e o pipeline (gravar, transcrever, separar vozes, estruturar, renderizar)
tests/       suíte pytest e fixtures sintéticas
worker/      Cloudflare Worker + D1 (publicação com senha, sem uso)
claude/      skill /ata do Claude Code
docs/        ARQUITETURA.md (fonte da verdade), USO.md (manual), MELHORIAS.md (backlog), arquitetura/ (diagramas)
assets/      ícone
```

Fora do git: `atas-salvas/` (uma pasta por reunião, com áudio e transcrição), `fala-analise/`, `local/config.json`,
`local/out/`, `local/models/`.

## Arquitetura

- [docs/ARQUITETURA.md](docs/ARQUITETURA.md): pipeline, dados e retenção, armadilhas, receitas.
- [docs/arquitetura/](docs/arquitetura/README.md): casos de uso (UML), processo (BPMN) e containers (C4).

## Decisões e limites conhecidos

- Reunião interna nunca sai da máquina. A publicação para cliente está desligada desde 22/10/2026.
- Nada é publicado sozinho: memória, notas e tarefas são propostas e só valem com o OK do dono.
- O áudio é apagado 30 dias depois que a ata fica garantida (estruturada e conferida).
- A separação de vozes erra em chamadas com muita gente. Só as falas rotuladas "Você" são atribuídas ao dono.
- Ainda não calibrados com uso real: o teto da daily (`docs/MELHORIAS.md` §21) e o modo intervencionista (§22).
- Feito para uma máquina e uma pessoa. Caminhos de venv estão na documentação, não num instalador.

## Licença

Todos os direitos reservados.
