"""Python access to Module:ltc-pron and Module:ltc-pron/predict."""

import re
from dataclasses import dataclass
from functools import cached_property

from .lua import Scribunto

_SUP = re.compile(r"<sup>(\d)</sup>")


@dataclass(frozen=True)
class Categories:
    initial: int
    final: int
    tone: int  # 1 平, 2 上, 3 去, 4 入


class LtcPron:
    def __init__(self, runtime: Scribunto | None = None):
        self.rt = runtime or Scribunto()

    @cached_property
    def pron(self):
        return self.rt.require("Module:ltc-pron")

    @cached_property
    def predict(self):
        return self.rt.require("Module:ltc-pron/predict")

    @cached_property
    def data(self):
        return self.rt.require("Module:ltc-pron/data")

    def categories(self, reading: str) -> Categories:
        """Categorise a Module:zh/data/ltc-pron/<char> reading string."""
        initial, final, _tone_label = self.pron.infer_categories(reading)
        tone_char = reading[5]
        return Categories(int(initial), int(final), int(self.data.tone_number[tone_char]))

    def cmn(self, c: Categories) -> str:
        """Expected Mandarin reflex, numbered pinyin (e.g. 'sheng1')."""
        return self.predict.predict_cmn(c.initial, c.final, c.tone)

    def yue(self, c: Categories) -> str:
        """Expected Cantonese reflex, Jyutping (e.g. 'sang1')."""
        return _SUP.sub(r"\1", self.predict.predict_yue(c.initial, c.final, c.tone))

