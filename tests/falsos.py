"""Substitutos da API da OpenAI para os testes, sem rede e sem custo."""

from types import SimpleNamespace


def resposta_falsa(saida, status="completed", entrada=1500, saida_tokens=900):
    uso = SimpleNamespace(
        input_tokens=entrada,
        input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
        output_tokens=saida_tokens,
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )
    return SimpleNamespace(
        model="gpt-6.1-sol", usage=uso, output_parsed=saida, status=status,
        incomplete_details=None if status == "completed" else {"reason": "max_output_tokens"},
    )


class ClienteFalso:
    def __init__(self, resposta=None, erro=None):
        self.responses = SimpleNamespace(parse=self._parse)
        self._resposta, self._erro = resposta, erro
        self.chamadas = []

    def _parse(self, **kwargs):
        self.chamadas.append(kwargs)
        if self._erro:
            raise self._erro
        return self._resposta
