"""Senhas guardadas como resumo criptográfico (scrypt), nunca em texto.

O scrypt é uma função de derivação de chave lenta de propósito, o que
encarece tentativas de adivinhar senhas a partir do banco. Faz parte da
biblioteca padrão do Python, então não exige dependência extra.

Parâmetros: os mínimos recomendados pela OWASP para scrypt (N=2^17, r=8,
p=1). Cada resumo usa cerca de 128 MB de memória e meio segundo, custo
pago só no login e na troca de senha. Como n, r e p ficam gravados junto
do resumo, mudar os valores no futuro não invalida senhas antigas.

Formato gravado: scrypt$n$r$p$sal_base64$resumo_base64
"""

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**17, 8, 1
TAMANHO_MINIMO = 8
_ALFABETO_PROVISORIA = "abcdefghjkmnpqrstuvwxyz23456789"  # sem letras e números parecidos


def _memoria(n: int, r: int) -> int:
    # O scrypt usa 128 * r * n bytes; a folga cobre o restante da conta.
    return 128 * r * n + 32 * 1024 * 1024


def gerar_resumo(senha: str) -> str:
    sal = secrets.token_bytes(16)
    resumo = hashlib.scrypt(senha.encode(), salt=sal, n=N, r=R, p=P, maxmem=_memoria(N, R), dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${N}${R}${P}${b64(sal)}${b64(resumo)}"


def conferir(senha: str, gravado: str) -> bool:
    try:
        nome, n, r, p, sal, resumo = gravado.split("$")
        if nome != "scrypt":
            return False
        calculado = hashlib.scrypt(
            senha.encode(), salt=base64.b64decode(sal), n=int(n), r=int(r), p=int(p),
            maxmem=_memoria(int(n), int(r)), dklen=32,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, base64.b64decode(resumo))


def senha_provisoria() -> str:
    """Senha aleatória fácil de ditar, no formato xxxx-xxxx-xxxx."""
    blocos = ["".join(secrets.choice(_ALFABETO_PROVISORIA) for _ in range(4)) for _ in range(3)]
    return "-".join(blocos)


def problema_na_senha_nova(senha: str, confirmacao: str) -> str | None:
    if len(senha) < TAMANHO_MINIMO:
        return f"A senha precisa ter pelo menos {TAMANHO_MINIMO} caracteres."
    if senha != confirmacao:
        return "A confirmação não é igual à senha."
    return None
