"""O som da chamada é gravado do fone que está no microfone, não da saída padrão do Windows.

Achado de 05/11/2026 (daily 05/11): o Windows tinha o alto-falante Realtek como saída padrão, o
Meet tocava no fone AB13X e a ata saiu só com a voz do Pedro, porque o loopback seguia o padrão.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local"))
import record  # noqa: E402


def _disp(nome, loop=False):
    return SimpleNamespace(name=nome, isloopback=loop)


class _SC:
    def __init__(self, padrao, loops):
        self._padrao, self._loops = padrao, loops

    def default_speaker(self):
        return _disp(self._padrao)

    def get_microphone(self, nome, include_loopback=True):
        for m in self._loops:
            if m.name == nome:
                return m
        raise RuntimeError("não achou")

    def all_microphones(self, include_loopback=True):
        return list(self._loops)


def _preparar(monkeypatch, padrao, loops, abrem=None):
    monkeypatch.setattr(record, "sc", _SC(padrao, loops))
    abrem = abrem if abrem is not None else {m.name for m in loops}
    monkeypatch.setattr(record, "_abre", lambda d: d.name in abrem)


def test_aparelho_pelo_nome():
    assert record._aparelho("Microphone (AB13X USB Audio)") == record._aparelho("Speakers (AB13X USB Audio)")
    assert record._aparelho("Speakers (Realtek(R) Audio)") == "realtek(r) audio"


def test_fone_no_microfone_grava_a_saida_do_fone_mesmo_com_realtek_padrao(monkeypatch):
    loops = [_disp("Speakers (Realtek(R) Audio)", True), _disp("Speakers (AB13X USB Audio)", True)]
    _preparar(monkeypatch, "Speakers (Realtek(R) Audio)", loops)
    loop, aviso = record._escolher_loop("Microphone (AB13X USB Audio)")
    assert loop.name == "Speakers (AB13X USB Audio)"
    assert aviso and "fone" in aviso


def test_microfone_interno_segue_a_saida_padrao(monkeypatch):
    loops = [_disp("Speakers (Realtek(R) Audio)", True), _disp("Speakers (AB13X USB Audio)", True)]
    _preparar(monkeypatch, "Speakers (Realtek(R) Audio)", loops)
    loop, aviso = record._escolher_loop("Microphone (Realtek(R) Audio)")
    assert loop.name == "Speakers (Realtek(R) Audio)" and aviso is None


def test_saida_do_fone_que_nao_abre_cai_para_a_padrao(monkeypatch):
    loops = [_disp("Speakers (Realtek(R) Audio)", True), _disp("Speakers (AB13X USB Audio)", True)]
    _preparar(monkeypatch, "Speakers (Realtek(R) Audio)", loops, abrem={"Speakers (Realtek(R) Audio)"})
    loop, _ = record._escolher_loop("Microphone (AB13X USB Audio)")
    assert loop.name == "Speakers (Realtek(R) Audio)"


def test_fone_ja_padrao_nao_gera_aviso(monkeypatch):
    loops = [_disp("Speakers (AB13X USB Audio)", True), _disp("Speakers (Realtek(R) Audio)", True)]
    _preparar(monkeypatch, "Speakers (AB13X USB Audio)", loops)
    loop, aviso = record._escolher_loop("Microphone (AB13X USB Audio)")
    assert loop.name == "Speakers (AB13X USB Audio)" and aviso is None
