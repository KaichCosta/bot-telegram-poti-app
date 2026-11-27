"""Utilitários para manipulação segura de valores monetários, formatação BRL e slugs."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Union

from src.exceptions import InvalidAmountError, InvalidMonthRefError

# Padrão regex para validação de mês de referência: YYYY-MM
MONTH_REF_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def to_decimal(
    value: Union[str, int, float, Decimal],
    allow_negative: bool = False,
    allow_zero: bool = True,
) -> Decimal:
    """Converte com segurança diferentes representações numéricas/strings para Decimal(10,2).
    
    Aceita formatos como:
      - '284,71'
      - '284.71'
      - 'R$ 1.800,00'
      - '1.250,50'
      - 284.71
      - Decimal('284.71')
    """
    if value is None:
        raise InvalidAmountError(value, "O valor não pode ser nulo.")

    if isinstance(value, (int, Decimal)):
        try:
            dec = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise InvalidAmountError(value, str(exc)) from exc
    elif isinstance(value, float):
        # Converte float via string para evitar artefatos de ponto flutuante binário
        try:
            dec = Decimal(f"{value:.2f}").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise InvalidAmountError(value, str(exc)) from exc
    elif isinstance(value, str):
        cleaned = value.strip().replace("R$", "").replace("r$", "").strip()
        if not cleaned:
            raise InvalidAmountError(value, "Valor informado em branco.")

        # Tratamento de sinal negativo
        is_negative = cleaned.startswith("-")
        if is_negative:
            cleaned = cleaned[1:].strip()

        # Detecção de padrão de separadores milhar/decimal
        if "." in cleaned and "," in cleaned:
            dot_pos = cleaned.find(".")
            comma_pos = cleaned.find(",")
            if dot_pos < comma_pos:
                # Padrão brasileiro: 1.234,56
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # Padrão americano: 1,234.56
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            # Apenas vírgula: 284,71
            cleaned = cleaned.replace(",", ".")
        # Se contiver apenas ponto, assume formato decimal comum: 284.71

        try:
            dec = Decimal(cleaned)
            if is_negative:
                dec = -dec
            dec = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise InvalidAmountError(value, f"Não foi possível converter para número: {cleaned}") from exc
    else:
        raise InvalidAmountError(value, f"Tipo de dado não suportado: {type(value).__name__}")

    if not allow_negative and dec < Decimal("0.00"):
        raise InvalidAmountError(value, "Valores negativos não são permitidos nesta operação.")

    if not allow_zero and dec == Decimal("0.00"):
        raise InvalidAmountError(value, "O valor precisa ser maior que zero.")

    return dec


def format_brl(value: Union[Decimal, float, int, str, None]) -> str:
    """Formata um valor numérico para padrão de moeda brasileira (BRL): R$ 1.234,56."""
    if value is None:
        return "R$ 0,00"

    dec = to_decimal(value, allow_negative=True, allow_zero=True)
    is_neg = dec < Decimal("0.00")
    abs_dec = abs(dec)

    # Formatação com vírgula como decimal e ponto como separador de milhar
    formatted = f"{abs_dec:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    prefix = "R$ -" if is_neg else "R$ "
    return f"{prefix}{formatted}"


def slugify(text: str) -> str:
    """Normaliza strings removendo acentos e pontuações para geração de slugs amigáveis.
    
    Exemplo:
        'Prestação Carro' -> 'prestacao-carro'
        'Faculdade' -> 'faculdade'
        'Água & Luz / Energia' -> 'agua-luz-energia'
    """
    if not text or not text.strip():
        raise ValueError("O texto para slug não pode ser vazio.")

    # Normalização Unicode decomposta (NFKD) para separar caracteres de seus acentos
    normalized = unicodedata.normalize("NFKD", text.strip())
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))

    # Converte para minúsculas e substitui caracteres não alfanuméricos por hífen
    lowered = without_accents.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")

    if not slug:
        raise ValueError(f"Não foi possível gerar um slug válido a partir de '{text}'.")

    return slug


def validate_month_ref(month_ref: Optional[str] = None) -> str:
    """Valida ou obtém a referência de mês no formato YYYY-MM (ex: '2026-11')."""
    if month_ref is None or not str(month_ref).strip():
        return datetime.now().strftime("%Y-%m")

    cleaned = str(month_ref).strip()
    if not MONTH_REF_PATTERN.match(cleaned):
        raise InvalidMonthRefError(cleaned)

    return cleaned
