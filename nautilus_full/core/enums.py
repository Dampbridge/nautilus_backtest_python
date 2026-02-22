"""All enumerations used throughout the framework."""
from enum import Enum, auto


# ── Order side ────────────────────────────────────────────────────────────────

class OrderSide(Enum):
    BUY = auto()
    SELL = auto()
    NO_ORDER_SIDE = auto()


# ── Order type ────────────────────────────────────────────────────────────────

class OrderType(Enum):
    MARKET = auto()
    LIMIT = auto()
    STOP_MARKET = auto()
    STOP_LIMIT = auto()
    MARKET_IF_TOUCHED = auto()      # MIT — triggers on touch, fills as market
    LIMIT_IF_TOUCHED = auto()       # LIT — triggers on touch, fills as limit
    TRAILING_STOP_MARKET = auto()   # Trailing offset, fills as market
    TRAILING_STOP_LIMIT = auto()    # Trailing offset, fills as limit


# ── Time in force ─────────────────────────────────────────────────────────────

class TimeInForce(Enum):
    GTC = auto()   # Good Till Cancelled
    IOC = auto()   # Immediate Or Cancel — fill what you can, cancel rest
    FOK = auto()   # Fill Or Kill — fully fill or entirely cancel
    GTD = auto()   # Good Till Date
    DAY = auto()   # Expires end of session
    AT_THE_OPEN = auto()
    AT_THE_CLOSE = auto()


# ── Order status ──────────────────────────────────────────────────────────────

class OrderStatus(Enum):
    INITIALIZED = auto()
    DENIED = auto()
    SUBMITTED = auto()
    ACCEPTED = auto()
    REJECTED = auto()
    CANCELED = auto()
    EXPIRED = auto()
    TRIGGERED = auto()        # Stop/MIT order trigger fired
    PENDING_UPDATE = auto()
    PENDING_CANCEL = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()


# Valid FSM transitions: from_status -> set of valid to_statuses
ORDER_STATUS_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.INITIALIZED: {
        OrderStatus.DENIED, OrderStatus.SUBMITTED,
    },
    OrderStatus.SUBMITTED: {
        OrderStatus.ACCEPTED, OrderStatus.REJECTED, OrderStatus.CANCELED,
    },
    OrderStatus.ACCEPTED: {
        OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.TRIGGERED,
        OrderStatus.PENDING_UPDATE, OrderStatus.PENDING_CANCEL,
        OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
    },
    OrderStatus.TRIGGERED: {
        OrderStatus.CANCELED, OrderStatus.EXPIRED,
        OrderStatus.PENDING_UPDATE, OrderStatus.PENDING_CANCEL,
        OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
    },
    OrderStatus.PENDING_UPDATE: {
        OrderStatus.ACCEPTED, OrderStatus.CANCELED, OrderStatus.EXPIRED,
        OrderStatus.TRIGGERED, OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
    },
    OrderStatus.PENDING_CANCEL: {
        OrderStatus.CANCELED, OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.CANCELED, OrderStatus.EXPIRED,
        OrderStatus.PENDING_UPDATE, OrderStatus.PENDING_CANCEL,
        OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
    },
}


# ── Contingency type ──────────────────────────────────────────────────────────

class ContingencyType(Enum):
    NO_CONTINGENCY = auto()
    OCO = auto()    # One Cancels Other — sibling canceled when one fills
    OTO = auto()    # One Triggers Other — child submitted when parent fills
    OUO = auto()    # One Updates Other — updates linked order quantity


# ── Trailing offset type ──────────────────────────────────────────────────────

class TrailingOffsetType(Enum):
    PRICE = auto()           # Absolute price offset
    BASIS_POINTS = auto()    # Basis points (1 bp = 0.01%)
    TICKS = auto()           # Multiples of instrument tick size
    PIPS = auto()            # FX pips


# ── Trigger type ──────────────────────────────────────────────────────────────

class TriggerType(Enum):
    DEFAULT = auto()
    BID_ASK = auto()      # Trigger on bid/ask
    LAST_TRADE = auto()   # Trigger on last trade price
    MARK_PRICE = auto()
    INDEX_PRICE = auto()


# ── Position side ─────────────────────────────────────────────────────────────

class PositionSide(Enum):
    FLAT = auto()
    LONG = auto()
    SHORT = auto()


# ── Account type ──────────────────────────────────────────────────────────────

class AccountType(Enum):
    CASH = auto()
    MARGIN = auto()
    BETTING = auto()


# ── OMS type (Order Management System) ───────────────────────────────────────

class OmsType(Enum):
    UNSPECIFIED = auto()
    NETTING = auto()    # Single position per instrument
    HEDGING = auto()    # Multiple positions per instrument


# ── Asset class ───────────────────────────────────────────────────────────────

class AssetClass(Enum):
    FX = auto()
    EQUITY = auto()
    COMMODITY = auto()
    CRYPTO = auto()
    BOND = auto()
    INDEX = auto()
    METAL = auto()
    ENERGY = auto()
    RATE = auto()
    PREDICTION = auto()


# ── Instrument class ──────────────────────────────────────────────────────────

class InstrumentClass(Enum):
    SPOT = auto()
    SWAP = auto()
    FUTURE = auto()
    FORWARD = auto()
    CFD = auto()
    BOND = auto()
    OPTION = auto()
    WARRANT = auto()
    SPORTS_BETTING = auto()
    BINARY_OPTION = auto()


# ── Option kind ───────────────────────────────────────────────────────────────

class OptionKind(Enum):
    CALL = auto()
    PUT = auto()


# ── Currency type ─────────────────────────────────────────────────────────────

class CurrencyType(Enum):
    FIAT = auto()
    CRYPTO = auto()
    COMMODITY = auto()


# ── Liquidity side ────────────────────────────────────────────────────────────

class LiquiditySide(Enum):
    NO_LIQUIDITY_SIDE = auto()
    MAKER = auto()
    TAKER = auto()


# ── Bar aggregation ───────────────────────────────────────────────────────────

class BarAggregation(Enum):
    TICK = auto()
    TICK_IMBALANCE = auto()
    TICK_RUNS = auto()
    VOLUME = auto()
    VOLUME_IMBALANCE = auto()
    VOLUME_RUNS = auto()
    VALUE = auto()
    VALUE_IMBALANCE = auto()
    VALUE_RUNS = auto()
    MILLISECOND = auto()
    SECOND = auto()
    MINUTE = auto()
    HOUR = auto()
    DAY = auto()
    WEEK = auto()
    MONTH = auto()


# ── Price type ────────────────────────────────────────────────────────────────

class PriceType(Enum):
    BID = auto()
    ASK = auto()
    MID = auto()
    LAST = auto()


# ── Book action ───────────────────────────────────────────────────────────────

class BookAction(Enum):
    ADD = auto()
    UPDATE = auto()
    DELETE = auto()
    CLEAR = auto()


# ── Book type ─────────────────────────────────────────────────────────────────

class BookType(Enum):
    L1_MBP = auto()   # Level 1 (best bid/ask)
    L2_MBP = auto()   # Level 2 (market-by-price)
    L3_MBO = auto()   # Level 3 (market-by-order)


# ── Aggressor side ────────────────────────────────────────────────────────────

class AggressorSide(Enum):
    NO_AGGRESSOR = auto()
    BUYER = auto()
    SELLER = auto()


# ── Trading state ─────────────────────────────────────────────────────────────

class TradingState(Enum):
    ACTIVE = auto()
    REDUCING = auto()
    HALTED = auto()


# ── Instrument status ─────────────────────────────────────────────────────────

class MarketStatus(Enum):
    PRE_OPEN = auto()
    OPEN = auto()
    PAUSE = auto()
    HALT = auto()
    CLOSE = auto()


# ── Log level ─────────────────────────────────────────────────────────────────

class LogLevel(Enum):
    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()
