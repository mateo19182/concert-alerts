from dataclasses import dataclass, field

from .library import name_key


@dataclass(frozen=True)
class Area:
    """A preferred area: an event matches on city, state/province name, state code or postcode prefix."""
    label: str
    cities: frozenset = frozenset()
    states: frozenset = frozenset()
    state_codes: frozenset = frozenset()
    postcodes: tuple = ()

    @classmethod
    def from_config(cls, data):
        if not isinstance(data, dict) or not isinstance(data.get("label"), str) or not data["label"]:
            raise ValueError("Each preferred area needs a non-empty label")
        return cls(data["label"],
                   frozenset(name_key(v) for v in data.get("cities", [])),
                   frozenset(name_key(v) for v in data.get("states", [])),
                   frozenset(str(v).upper() for v in data.get("state_codes", [])),
                   tuple(str(v) for v in data.get("postcodes", [])))


@dataclass(frozen=True)
class Region:
    country: str = "ES"
    timezone: str = "Europe/Madrid"
    areas: tuple = field(default_factory=tuple)

    @classmethod
    def from_config(cls, config):
        country = str(config.get("country", "ES")).upper()
        if len(country) != 2 or not country.isalpha():
            raise ValueError("country must be an ISO 3166-1 alpha-2 code")
        return cls(country, config.get("timezone", "Europe/Madrid"),
                   tuple(Area.from_config(a) for a in config.get("preferred_areas", [])))

    def highlight(self, city="", state="", state_code="", postcode=""):
        """Label of the first preferred area the place falls in, or ""."""
        city, state = name_key(city or ""), name_key(state or "")
        state_code = (state_code or "").upper().removeprefix(self.country + "-")
        for area in self.areas:
            if (city in area.cities or state in area.states or state_code in area.state_codes
                    or (postcode and postcode.startswith(area.postcodes))):
                return area.label
        return ""
