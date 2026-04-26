from porto2026.models import ParsedExpense, ExpenseCategory, Currency


def test_parsed_expense():
    item = ParsedExpense(
        description="Jantar no Porto",
        category=ExpenseCategory.ALIMENTACAO,
        currency=Currency.EUR,
        amount_original=80,
    )
    assert item.amount_original == 80
