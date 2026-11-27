"""Exceções de domínio e infraestrutura da aplicação."""


class ExpenseControlError(Exception):
    """Exceção base para erros de negócio do controle de gastos."""

    def __init__(self, message: str, code: str = "GENERIC_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class CategoryNotFoundError(ExpenseControlError):
    """Lançada quando uma categoria especificada não existe no banco de dados."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            message=f"Categoria com identificador '{slug}' não foi encontrada.",
            code="CATEGORY_NOT_FOUND",
        )
        self.slug = slug


class CategoryAlreadyExistsError(ExpenseControlError):
    """Lançada quando há tentativa de renomear para um slug que já existe."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            message=f"Já existe uma categoria cadastrada com o identificador '{slug}'.",
            code="CATEGORY_ALREADY_EXISTS",
        )
        self.slug = slug


class InvalidAmountError(ExpenseControlError):
    """Lançada quando um valor monetário informado é inválido ou incompatível."""

    def __init__(self, raw_value: object, detail: str = "Valor monetário inválido.") -> None:
        super().__init__(
            message=f"O valor '{raw_value}' não é válido: {detail}",
            code="INVALID_AMOUNT",
        )
        self.raw_value = raw_value


class InvalidMonthRefError(ExpenseControlError):
    """Lançada quando a referência de mês não está no formato YYYY-MM."""

    def __init__(self, month_ref: str) -> None:
        super().__init__(
            message=f"Referência de mês '{month_ref}' inválida. Use o formato YYYY-MM (ex: '2026-11').",
            code="INVALID_MONTH_REF",
        )
        self.month_ref = month_ref


class DatabaseConfigurationError(ExpenseControlError):
    """Lançada quando há falha de conexão ou parâmetros incompletos de banco de dados."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            message=f"Falha na conexão com o banco de dados MySQL: {detail}",
            code="DATABASE_CONFIG_ERROR",
        )
