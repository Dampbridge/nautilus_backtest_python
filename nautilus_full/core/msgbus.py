"""
MessageBus — lightweight pub/sub event bus.

Topics use dot-notation with optional wildcard ``*`` suffix:
  - ``data.bars.BTCUSDT.BINANCE-1m``   exact match
  - ``data.bars.*``                      prefix wildcard (matches any bar)
  - ``events.order.*``                   all order events
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Callable, Optional


class Subscription:
    """Handle for a single subscription, usable for unsubscribing."""
    __slots__ = ("topic", "handler", "sub_id")

    def __init__(self, topic: str, handler: Callable, sub_id: str) -> None:
        self.topic = topic
        self.handler = handler
        self.sub_id = sub_id

    def __repr__(self) -> str:
        return f"Subscription(topic='{self.topic}', id='{self.sub_id}')"


class MessageBus:
    """
    Central message bus for framework-wide event distribution.

    Supports exact-match topics and wildcard prefix matching (``topic.*``).
    """

    def __init__(self, trader_id: str = "TRADER-001") -> None:
        self.trader_id = trader_id
        # exact topic -> list of subscriptions
        self._exact: dict[str, list[Subscription]] = defaultdict(list)
        # prefix -> list of subscriptions  (stored without trailing ".*")
        self._prefix: dict[str, list[Subscription]] = defaultdict(list)
        self._sent_count: int = 0

    # ── Subscribe ──────────────────────────────────────────────────────────

    def subscribe(
        self,
        topic: str,
        handler: Callable,
        sub_id: Optional[str] = None,
    ) -> Subscription:
        """
        Subscribe ``handler`` to ``topic``.

        Parameters
        ----------
        topic : str
            Exact topic or prefix wildcard (ends with ``.*``).
        handler : Callable
            Called with the published message as the single argument.
        sub_id : str, optional
            Unique subscription id; auto-generated if not provided.
        """
        sid = sub_id or str(uuid.uuid4())
        sub = Subscription(topic=topic, handler=handler, sub_id=sid)

        if topic.endswith(".*"):
            prefix = topic[:-2]  # strip ".*"
            self._prefix[prefix].append(sub)
        else:
            self._exact[topic].append(sub)

        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscription by its handle."""
        topic = subscription.topic
        if topic.endswith(".*"):
            prefix = topic[:-2]
            subs = self._prefix.get(prefix, [])
            self._prefix[prefix] = [s for s in subs if s.sub_id != subscription.sub_id]
        else:
            subs = self._exact.get(topic, [])
            self._exact[topic] = [s for s in subs if s.sub_id != subscription.sub_id]

    def unsubscribe_topic(self, topic: str) -> None:
        """Remove all subscriptions for a topic."""
        if topic.endswith(".*"):
            self._prefix.pop(topic[:-2], None)
        else:
            self._exact.pop(topic, None)

    # ── Publish ────────────────────────────────────────────────────────────

    def publish(self, topic: str, message: Any) -> None:
        """
        Publish ``message`` to all handlers subscribed to ``topic``.

        Delivery order: exact-match handlers first, then prefix-wildcard
        handlers (longest prefix first).
        """
        self._sent_count += 1

        # Exact match
        for sub in list(self._exact.get(topic, [])):
            sub.handler(message)

        # Prefix wildcard: check every registered prefix
        for prefix, subs in self._prefix.items():
            if topic.startswith(prefix):
                for sub in list(subs):
                    sub.handler(message)

    # ── Utility ────────────────────────────────────────────────────────────

    def has_subscribers(self, topic: str) -> bool:
        if self._exact.get(topic):
            return True
        for prefix in self._prefix:
            if topic.startswith(prefix) and self._prefix[prefix]:
                return True
        return False

    @property
    def sent_count(self) -> int:
        return self._sent_count

    def reset(self) -> None:
        self._exact.clear()
        self._prefix.clear()
        self._sent_count = 0
