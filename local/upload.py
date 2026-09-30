# -*- coding: utf-8 -*-
"""
Publicação no Worker — SÓ para reunião de cliente (sessao.TIPOS_PUBLICAVEIS).

O Worker v2 não resume nem renderiza: recebe o HTML já pronto (o entregável,
gerado aqui), guarda no D1 com senha e prazo de expiração, e serve em /r/<id>
atrás de um formulário de senha.

  POST   /api/atas        {chave, titulo, html, senha, expira_dias} → {id, url}
  DELETE /api/atas/<id>   apaga
  GET    /api/atas        lista (id, título, data, expiração)

`chave` é o id da sessão: publicar de novo a mesma reunião ATUALIZA a página em vez
de criar outra — por isso aqui pode haver retry, o que a v1 não podia.

Só stdlib. O token é lido do config dentro do processo e nunca é impresso.
"""
import json
import secrets
import time
import urllib.error
import urllib.request

# Sem User-Agent de navegador, o Cloudflare (Bot Fight Mode) barra o urllib com
# HTTP 403 "error code: 1010" antes de o pedido chegar ao Worker.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

_ALFABETO = "abcdefghjkmnpqrstuvwxyz23456789"   # sem 0/o/1/l/i: senha ditada ao telefone


def gerar_senha():
    bruto = "".join(secrets.choice(_ALFABETO) for _ in range(8))
    return f"{bruto[:4]}-{bruto[4:]}"


def _pedido(metodo, url, token, corpo=None, timeout=60):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {token}",
        "User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {e.code} do Worker: {detalhe}") from e


def publicar(worker_url, token, chave, titulo, html, senha, expira_dias, tentativas=3):
    url = worker_url.rstrip("/") + "/api/atas"
    corpo = {"chave": chave, "titulo": titulo, "html": html, "senha": senha,
             "expira_dias": int(expira_dias or 0)}
    ultimo = None
    for n in range(tentativas):
        try:
            r = _pedido("POST", url, token, corpo, timeout=90)
            if not r.get("url"):
                raise RuntimeError(f"resposta inesperada do Worker: {r}")
            return r
        except RuntimeError as e:
            ultimo = e
            if "HTTP 4" in str(e):            # erro nosso (token, corpo): repetir não ajuda
                break
            time.sleep(2 * (n + 1))
        except (urllib.error.URLError, TimeoutError) as e:
            ultimo = e
            time.sleep(2 * (n + 1))
    raise RuntimeError(f"publicação falhou: {ultimo}")


def apagar(worker_url, token, ata_id):
    return _pedido("DELETE", worker_url.rstrip("/") + f"/api/atas/{ata_id}", token)


def listar(worker_url, token):
    return _pedido("GET", worker_url.rstrip("/") + "/api/atas", token)
