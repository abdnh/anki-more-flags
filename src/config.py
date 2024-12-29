from __future__ import annotations

import dataclasses

from ankiutils.config import Config as AddonConfig


@dataclasses.dataclass
class CustomFlag:
    label: str
    color_light: str
    color_dark: str
    shortcut: str | None = None


class Config(AddonConfig):
    @property
    def flags(self) -> list[CustomFlag]:
        return [CustomFlag(**flag) for flag in self["flags"]]

    @flags.setter
    def flags(self, flags: list[CustomFlag]) -> None:
        self["flags"] = [dataclasses.asdict(flag) for flag in flags]


config = Config(__name__)
