from .base import Adapter, Blocked, CollectResult, Disallowed, FetchError, Offer
from .floraccess import FlorAccessAdapter
from .jtl import JtlAdapter
from .shopify import ShopifyAdapter

REGISTRY: dict[str, type[Adapter]] = {
    a.key: a for a in (ShopifyAdapter, JtlAdapter, FlorAccessAdapter)
}

__all__ = ["REGISTRY", "Adapter", "Blocked", "CollectResult", "Disallowed", "FetchError", "Offer"]
