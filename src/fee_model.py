from dataclasses import dataclass


@dataclass(frozen=True)
class AvanzaCourtageClass:
    percentage: float
    minimum_fee: float


AVANZA_COURTAGE_CLASSES = {
    "start": AvanzaCourtageClass(percentage=0.0, minimum_fee=0.0),
    "mini": AvanzaCourtageClass(percentage=0.0025, minimum_fee=1.0),
    "small": AvanzaCourtageClass(percentage=0.0015, minimum_fee=39.0),
    "medium": AvanzaCourtageClass(percentage=0.00069, minimum_fee=69.0),
}


def calculate_avanza_courtage(transaction_value: float, courtage_class: str = "mini") -> float:
    """Return the Avanza commission suggestion for a SEK trade value."""
    if transaction_value <= 0:
        return 0.0

    fee_class = AVANZA_COURTAGE_CLASSES.get(courtage_class.lower())
    if fee_class is None:
        raise ValueError(f"Unsupported Avanza courtage class: {courtage_class}")

    return max(transaction_value * fee_class.percentage, fee_class.minimum_fee)


def convert_foreign_trade_to_sek(
    native_price: float, fx_rate: float, fx_spread_percent: float, is_buy: bool
) -> float:
    """Convert a foreign share price to SEK using Avanza's directional FX spread."""
    if native_price < 0 or fx_rate <= 0 or fx_spread_percent < 0:
        raise ValueError("Price, FX rate, and FX spread must be non-negative")

    spread = fx_spread_percent / 100
    adjusted_rate = fx_rate * (1 + spread if is_buy else 1 - spread)
    return native_price * adjusted_rate


def calculate_fx_fee(transaction_value: float, fx_spread_percent: float) -> float:
    """Return the SEK cost of Avanza's FX spread for one foreign trade."""
    if transaction_value < 0 or fx_spread_percent < 0:
        raise ValueError("Transaction value and FX spread must be non-negative")

    return transaction_value * fx_spread_percent / 100


def estimate_avanza_exit_cost(
    transaction_value: float, courtage_class: str, fx_spread_percent: float,
    is_foreign_currency: bool,
) -> float:
    """Estimate brokerage and FX costs to sell one complete position."""
    brokerage = calculate_avanza_courtage(transaction_value, courtage_class)
    fx_fee = calculate_fx_fee(transaction_value, fx_spread_percent) if is_foreign_currency else 0.0
    return brokerage + fx_fee