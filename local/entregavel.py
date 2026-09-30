# -*- coding: utf-8 -*-
"""
HTML → PDF com o Chrome headless, a partir de um arquivo LOCAL.

Até a v1 este módulo baixava a página publicada no Worker e só então imprimia —
então sem upload não havia PDF, e ata interna nunca teria PDF. Agora o HTML é
gerado na máquina (render.py) e o PDF sai dele, com ou sem internet.

O PDF é impresso sem cabeçalho nem rodapé do navegador: nenhuma URL ou caminho de
arquivo aparece no documento.

Uso standalone:  python entregavel.py <arquivo.html> [<saida.pdf>]
"""
import os
import pathlib
import subprocess
import sys
import tempfile

# Chrome vem primeiro DE PROPÓSITO: o Edge, quando já está aberto (o caso desta
# máquina), faz a chamada headless dar "rendezvous" com a instância em uso e sai
# sem imprimir. O Chrome roda um processo headless isolado e é confiável.
_NAVEGADORES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def navegador():
    for p in _NAVEGADORES:
        if os.path.exists(p):
            return p
    return None


def html_para_pdf(html_path, pdf_path, espera_ms=8000):
    """Imprime o HTML em PDF. Levanta RuntimeError com o motivo se não sair arquivo."""
    nav = navegador()
    if not nav:
        raise RuntimeError("nenhum Chrome/Edge encontrado para imprimir o PDF")
    pdf_path = pathlib.Path(pdf_path)
    tmp_pdf = pdf_path.with_suffix(".pdf.tmp")
    if tmp_pdf.exists():
        tmp_pdf.unlink()
    uri = pathlib.Path(html_path).resolve().as_uri()
    with tempfile.TemporaryDirectory() as perfil:
        cmd = [nav, "--headless", "--disable-gpu", "--no-pdf-header-footer",
               f"--virtual-time-budget={espera_ms}",   # espera fontes/layout
               f"--user-data-dir={perfil}",            # perfil descartável
               f"--print-to-pdf={tmp_pdf}", uri]
        subprocess.run(cmd, timeout=120, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not tmp_pdf.exists() or tmp_pdf.stat().st_size == 0:
        raise RuntimeError("o navegador não produziu o PDF")
    os.replace(tmp_pdf, pdf_path)
    return pdf_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python entregavel.py <arquivo.html> [<saida.pdf>]")
        sys.exit(1)
    h = pathlib.Path(sys.argv[1])
    print(html_para_pdf(h, sys.argv[2] if len(sys.argv) > 2 else h.with_suffix(".pdf")))
