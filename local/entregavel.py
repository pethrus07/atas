# -*- coding: utf-8 -*-
"""
Gera o entregável OFFLINE da ata: baixa a página branded do Worker e salva
como .html e .pdf na pasta atas-salvas, para enviar direto ao cliente
(WhatsApp/email) sem precisar compartilhar o link.

A página não contém o endereço do Worker no corpo; e o PDF é impresso sem
cabeçalho/rodapé, então nenhuma URL aparece no arquivo final.

Puramente adicional: qualquer falha aqui é engolida e NÃO afeta a gravação.

Uso standalone (teste):
    python entregavel.py <url> <caminho_base_sem_extensao>
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.request

# Navegadores Chromium capazes de imprimir HTML -> PDF em modo headless.
# Chrome vem primeiro DE PROPÓSITO: o Edge, quando já está aberto (o caso desta
# máquina), faz a chamada headless dar "rendezvous" com a instância em uso e sai
# sem imprimir. O Chrome roda um processo headless isolado e é confiável.
_NAVEGADORES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _navegador():
    for p in _NAVEGADORES:
        if os.path.exists(p):
            return p
    return None


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _baixar_html(url, timeout=30):
    # UA de navegador: sem isso o Cloudflare (Bot Fight Mode) pode barrar (1010).
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _html_para_pdf(html_path, pdf_path):
    nav = _navegador()
    if not nav:
        return False
    uri = pathlib.Path(html_path).resolve().as_uri()
    with tempfile.TemporaryDirectory() as perfil:
        cmd = [
            nav,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",          # sem cabeçalho/rodapé => sem URL no PDF
            "--virtual-time-budget=12000",     # espera fontes do Google/layout antes de imprimir
            f"--user-data-dir={perfil}",       # perfil descartável (não briga com Edge aberto)
            f"--print-to-pdf={pdf_path}",
            uri,
        ]
        try:
            subprocess.run(
                cmd, timeout=90, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            return False
    return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0


def gerar(url, base_sem_ext):
    """
    Baixa a página da ata em <url> e salva .html (+ .pdf, se der) com o mesmo
    nome-base do backup .md. Retorna {"html": Path|None, "pdf": Path|None}.
    """
    resultado = {"html": None, "pdf": None}
    try:
        html = _baixar_html(url)
    except Exception:
        return resultado

    html_path = pathlib.Path(str(base_sem_ext) + ".html")
    try:
        html_path.write_text(html, encoding="utf-8")
        resultado["html"] = html_path
    except Exception:
        return resultado

    pdf_path = pathlib.Path(str(base_sem_ext) + ".pdf")
    try:
        if _html_para_pdf(html_path, pdf_path):
            resultado["pdf"] = pdf_path
    except Exception:
        pass
    return resultado


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("uso: python entregavel.py <url> <caminho_base_sem_extensao>")
        sys.exit(1)
    r = gerar(sys.argv[1], sys.argv[2])
    print("html:", r["html"])
    print("pdf :", r["pdf"])
