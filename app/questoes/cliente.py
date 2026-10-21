from openai import OpenAI


def obter_cliente_llm() -> OpenAI | None:
    """Cliente do modelo para as rotas. None significa o cliente padrão; os testes trocam por um falso."""
    return None
