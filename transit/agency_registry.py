"""
Agency registry — maps agency_id strings to TransitAgency subclasses.

To add a new agency:
  1. Create transit/agencies/<name>.py with a TransitAgency subclass
  2. Import it here and add to REGISTRY
"""

from typing import Dict, Type

from transit.agencies.base import TransitAgency
from transit.agencies.mta import MtaAgency
from transit.agencies.custom import CustomAgency

REGISTRY: Dict[str, Type[TransitAgency]] = {
    "mta": MtaAgency,
    "custom": CustomAgency,
    # "wmata": WmataAgency,   # DC Metro — future
    # "bart": BartAgency,     # BART — future
    # "cta": CtaAgency,       # Chicago L — future
}


def get_agency(agency_id: str, config: dict) -> TransitAgency:
    """
    Return an instantiated TransitAgency for the given agency_id.

    Raises:
        ValueError: if agency_id is not in the registry.
    """
    cls = REGISTRY.get(agency_id)
    if cls is None:
        raise ValueError(
            f"Unknown agency_id: '{agency_id}'. "
            f"Available: {sorted(REGISTRY)}"
        )
    return cls(config)
