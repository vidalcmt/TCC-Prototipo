"""Critério de pronto da etapa 1: uma requisição real grava tokens, custo e latência.

Uso (com o .env preenchido e o banco migrado):
    python -m scripts.teste_requisicao
"""

from pydantic import BaseModel

from app.correcao.llm import chamar_modelo
from app.correcao.prompts import carregar_prompt
from app.database import SessionLocal


class Eco(BaseModel):
    eco: str


def main() -> None:
    prompt = carregar_prompt("teste", 1)
    with SessionLocal() as sessao:
        resultado = chamar_modelo(sessao, prompt, Eco, {"frase": "metricas funcionando"})
        m = resultado.metrica
        print(f"sucesso:          {m.sucesso}")
        print(f"modelo (API):     {m.modelo}")
        print(f"prompt:           {m.prompt_versao}")
        print(f"tokens entrada:   {m.tokens_entrada}")
        print(f"tokens saida:     {m.tokens_saida}")
        print(f"custo (US$):      {m.custo_usd}")
        print(f"latencia (ms):    {m.latencia_ms:.0f}")
        if resultado.saida:
            print(f"resposta:         {resultado.saida.eco}")
        else:
            print(f"motivo da falha:  {m.motivo_falha}")


if __name__ == "__main__":
    main()
