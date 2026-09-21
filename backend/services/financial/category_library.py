"""Explicitly shared categories. Case-derived labels remain private to their case."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from postgres.models.financial_category import FinancialCategory
from services.financial.payment_inference import MERCHANTS

DEFAULT_COLOR = '#8060a9'
DEFAULT_NAMES = sorted({kind for _, _, kind in MERCHANTS} | {
    'Income', 'Transfers', 'Travel', 'Meals', 'Shopping', 'Cash withdrawals',
    'Fees and interest', 'Bank fees', 'Interest income', 'Interest charges',
    'Card payments', 'Card rewards', 'Merchant credits', 'Taxes', 'Rent and leases',
    'Payroll', 'Returned transfers', 'Deposits', 'Payments', 'Parking and tolls',
    'Health and pharmacy', 'Personal care', 'Storage', 'Transport', 'Entertainment',
    'Government payments', 'Vehicle care', 'Insurance', 'Groceries',
    'Subscriptions', 'Uncategorized',
})


def clean_name(value):
    if any(ord(c) < 32 for c in value):
        raise ValueError('Category names must be a single line.')
    value = ' '.join(value.split())
    if not value:
        raise ValueError('Enter a category name.')
    return value


class CreatePaymentCategoryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    color: str = Field(default=DEFAULT_COLOR, pattern=r'^#[0-9a-fA-F]{6}$')

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, value):
        return clean_name(value)


def category_view(row):
    return dict(name=row.name, color=row.color, scope='shared')


def category_library(session):
    values = {name.casefold(): dict(name=name, color=DEFAULT_COLOR, scope='built-in') for name in DEFAULT_NAMES}
    for row in session.scalars(select(FinancialCategory).order_by(FinancialCategory.name)):
        values[row.normalized_name] = category_view(row)
    return sorted(values.values(), key=lambda item: item['name'].casefold())


def ensure_category(session, *, name, color=DEFAULT_COLOR, actor):
    """Part of the caller's transaction; idempotent even for concurrent creation."""
    name = clean_name(name)
    key = name.casefold()
    default = next((value for value in DEFAULT_NAMES if value.casefold() == key), None)
    if default:
        return dict(name=default, color=DEFAULT_COLOR, scope='built-in')
    row = session.get(FinancialCategory, key)
    if row is None:
        try:
            with session.begin_nested():
                row = FinancialCategory(normalized_name=key, name=name, color=color, created_by=actor.email)
                session.add(row)
                session.flush()
        except IntegrityError:
            row = session.get(FinancialCategory, key)
            if row is None:
                raise
    return category_view(row)
