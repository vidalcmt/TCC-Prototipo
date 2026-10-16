"""Carregamento de prompts versionados.

Cada prompt é um arquivo em prompts/<nome>/v<N>.md. A versão gravada nas
métricas é "<nome>_v<N>", o que permite dizer, na seção de Métodos, qual prompt
gerou cada resultado. Nunca edite uma versão já usada na coleta: crie a próxima
e registre a mudança em prompts/CHANGELOG.md.

Dentro do arquivo, a linha "---usuario---" separa a instrução de sistema do
modelo de mensagem do usuário. Campos entre chaves, como {enunciado}, são
preenchidos na hora da chamada.
"""

from dataclasses import dataclass

from app.config import RAIZ

PASTA_PROMPTS = RAIZ / "prompts"
SEPARADOR = "---usuario---"


@dataclass(frozen=True)
class Prompt:
    nome: str
    versao: int
    sistema: str
    usuario: str

    @property
    def identificador(self) -> str:
        return f"{self.nome}_v{self.versao}"

    def mensagens(self, **campos: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.sistema},
            {"role": "user", "content": self.usuario.format(**campos)},
        ]


def carregar_prompt(nome: str, versao: int) -> Prompt:
    caminho = PASTA_PROMPTS / nome / f"v{versao}.md"
    texto = caminho.read_text(encoding="utf-8")
    if SEPARADOR not in texto:
        raise ValueError(f"{caminho} não tem a linha {SEPARADOR}")
    sistema, usuario = texto.split(SEPARADOR, 1)
    return Prompt(nome=nome, versao=versao, sistema=sistema.strip(), usuario=usuario.strip())
