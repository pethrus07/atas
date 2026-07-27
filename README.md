# Atas — gravador + transcrição de reuniões (grátis, local)

Grava suas reuniões (Meet/Zoom/WhatsApp/ligação), transcreve **offline** no seu PC
com faster-whisper e publica uma **página com a sua marca e link próprio** contendo
**resumo + decisões + próximos passos + transcrição por falante**. O áudio **não** é guardado.

```
[XPS / local]                                  [Cloudflare]
 gravar.bat → run.py                            worker.js
   record.py   (mic + áudio do sistema)   POST   ├─ Workers AI  → resumo/ata
   transcribe.py (faster-whisper, 2 passadas) →   ├─ D1          → guarda o texto
   upload.py   (envia o texto)                    └─ /r/<id>     → página branded (seu link)
```

## Como usar (no dia a dia)
1. Deixe o áudio da chamada saindo pelo **alto-falante padrão** do Windows.
2. Dê 2 cliques em [local/gravar.bat](local/gravar.bat).
3. Aperte **ENTER** para parar quando a reunião acabar.
4. Digite um título (ex.: "Cliente X — proposta").
5. Ele transcreve, resume e imprime o **link** (já copiado para a área de transferência).
   Um backup `.md` fica em `atas-salvas/`.

> **Consentimento (LGPD):** avise/peça autorização antes de gravar uma reunião com cliente.

## Quem falou o quê
- **Você** = seu microfone. **Participante** = áudio da chamada (loopback).
- Numa call em grupo, todos os remotos aparecem como "Participante" (áudio vem mixado).
  Distinguir cada pessoa remota exigiria diarização acústica (não incluído na v1).

## Setup (uma vez)

### Local
- Depende do venv `C:\Users\olive\.venvs\faster-whisper` (faster-whisper + PyAV já instalados).
- Dependência extra instalada: `soundcard` (`pip install soundcard`).
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
- **Marca** da página: constante `MARCA` no topo de [worker/worker.js](worker/worker.js).
- **Qualidade do resumo**: trocar `MODELO` para `@cf/meta/llama-3.3-70b-instruct-fp8-fast`.
- **Modelo do Whisper**: campo `model` no `config.json` (ex.: `medium` para mais precisão — mais lento).
