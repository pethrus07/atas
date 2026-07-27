# -*- coding: utf-8 -*-
"""
Envia a transcrição para o Worker Cloudflare, que resume (Workers AI),
guarda no D1 e devolve o link da página branded.

Usa só a stdlib (urllib) — sem dependências extras.
"""
import json
import urllib.request
import urllib.error


def enviar(segments, titulo, worker_url, token, timeout=180):
    """
    POST {titulo, segments} em <worker_url>/api/upload com Bearer token.
    Devolve a URL da ata em caso de sucesso, ou levanta exceção.
    """
    url = worker_url.rstrip("/") + "/api/upload"
    body = json.dumps({"titulo": titulo, "segments": segments}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            # Sem User-Agent, o Cloudflare (Bot Fight Mode) barra o urllib com
            # HTTP 403 "error code: 1010" antes de chegar no Worker. Um UA de
            # navegador passa pela verificação de assinatura.
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code} do Worker: {detalhe}") from e
    if not resp.get("url"):
        raise RuntimeError(f"Resposta inesperada do Worker: {resp}")
    return resp["url"]
