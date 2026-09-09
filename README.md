# Atas — gravador + transcrição de reuniões (grátis, local)

Grava suas reuniões (Meet/Zoom/WhatsApp/ligação), transcreve **offline** no seu PC
com faster-whisper e publica uma **página com a sua marca e link próprio** contendo
**resumo + decisões + próximos passos + transcrição por falante**. O áudio **não** é guardado.

> **Para entender o código sozinho, comece por [docs/ARQUITETURA.md](docs/ARQUITETURA.md).**

```
[XPS / local]                                       [Cloudflare]
 gravar.bat → run.py                                 worker.js
   record.py       (mic + áudio do sistema)          ├─ Workers AI → resumo/ata
   transcribe.py   (faster-whisper, 2 passadas)      ├─ D1         → guarda o texto
   diarize.py      (separa os remotos, venv diar)    └─ /r/<id>    → página branded (seu link)
   upload.py       (envia o texto)            POST →        │
   entregavel.py   (baixa a página → PDF do cliente) ←──────┘
   analise_fala.py (raio-x da fala — interno, nunca sai daqui)
```

## Como usar (no dia a dia)
1. Deixe o áudio da chamada saindo pelo **alto-falante padrão** do Windows.
2. Dê 2 cliques em [local/gravar.bat](local/gravar.bat).
3. Aperte **ENTER** para parar quando a reunião acabar.
4. Digite um título (ex.: "Cliente X — proposta").
5. Ele transcreve, resume e imprime o **link** (já copiado para a área de transferência).
   Em `atas-salvas/` ficam o backup `.md` e o **PDF/HTML para mandar ao cliente**, que abre
   sozinho no fim junto com o raio-x da fala.

> **Consentimento (LGPD):** avise/peça autorização antes de gravar uma reunião com cliente.

## Quem falou o quê
- **Você** = seu microfone. **Participante** = áudio da chamada (loopback).
- Numa call em grupo o áudio dos remotos vem mixado num canal só, então uma **diarização
  acústica** (sherpa-onnx) tenta separá-los em "Participante 1", "Participante 2"…
- Ela é boa, mas exige calibragem: com o padrão `diar_threshold: 0.5` ela já fatiou **uma**
  pessoa em dezenas. Se isso acontecer, suba o limiar ou crave `diar_num_speakers` no
  `config.json` — receita em [docs/ARQUITETURA.md](docs/ARQUITETURA.md#11--receitas).

## Setup (uma vez)

### Local
- Depende do venv `C:\Users\olive\.venvs\faster-whisper` (Python 3.14, com faster-whisper + PyAV).
- Dependência extra instalada: `soundcard` (`pip install soundcard`).
- A diarização roda num **segundo** venv, `C:\Users\olive\.venvs\diar` (Python 3.12, `sherpa-onnx`),
  chamado por subprocess — os dois não convivem no mesmo ambiente. Os modelos ONNX (~35 MB) ficam
  fora do git, em `local/models/diar/`.
- Copie `local/config.example.json` para `local/config.json` e preencha `worker_url` e `upload_token`.

### Cloudflare (pasta `worker/`)
```powershell
cd worker
npx wrangler d1 create atas                 # copie o database_id para o wrangler.toml
npx wrangler d1 execute atas --remote --file schema.sql
npx wrangler secret put UPLOAD_TOKEN        # gere um token forte; use o MESMO no config.json
npx wrangler deploy
```
Link final: `https://atas.desbravando-utv.workers.dev/r/<id>`.

## Trocar coisas
- **Marca** da página: constantes `MARCA`, `SITE` e `LOGO_PATH` no topo de
  [worker/worker.js](worker/worker.js) (o CSS fica no fim do mesmo arquivo).
- **Modelo do resumo**: constante `MODELO` em `worker.js` — hoje
  `@cf/meta/llama-3.3-70b-instruct-fp8-fast`.
- **Modelo do Whisper**: campo `model` no `config.json` (ex.: `medium` para mais precisão — mais lento).
- **Diarização**: campos `diarizar`, `diar_threshold` e `diar_num_speakers` no `config.json`.
