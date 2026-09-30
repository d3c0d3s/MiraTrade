"""FinBERT over text that was published, scored as evidence rather than as a prediction.

FinBERT (``ProsusAI/finbert``) is a BERT **classifier**, not a language model: it reads a passage
and returns three numbers — positive, negative, neutral — and nothing else. It does not generate,
it cannot be prompted, and it will not run in Ollama, which serves generative models.

What it reads here is the **body of an 8-K**, and that choice is the whole point. A news API gives
you today's version of an article, often rewritten after the fact; an EDGAR filing cannot be
back-dated, carries an acceptance timestamp to the second, and is public domain. The one property
that makes a news backtest possible is the one property news feeds do not offer.

## What this is allowed to claim

Nothing. It is **off by default**, and that is the honest setting rather than a cautious one. No
news signal in this project has survived an out-of-sample test: the 8-K study found that almost
every kind of corporate news looks elevated before an insider buy until you control for the
trading window, and then it does not. So the score is shown beside an event, labelled as what was
published, and no screen says it predicts anything.

If it is ever promoted to a measured condition, the study's lesson applies first: compare against
placebo days **matched on the quarter**, or it will rediscover the trading window wearing a
sentiment score.

## Why ONNX

``transformers`` plus ``torch`` is about 2.5 GB installed for a 110 M-parameter model that runs on
a CPU in milliseconds. ONNX Runtime is about 250 MB and gives the same three numbers. The model is
the same either way; only the machinery around it differs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from miratrade.config import Config, SentimentParams

LABELS = ("positive", "negative", "neutral")
MAX_TOKENS = 512                  # BERT's hard limit; longer text is scored in pieces


@dataclass(frozen=True)
class Score:
    """One passage, judged. ``unclear`` is a real answer and the commonest honest one."""
    label: str                    # positive | negative | neutral | unclear
    score: float                  # −1 … +1, positive minus negative
    confidence: float             # the winning probability
    passages: int = 1

    @property
    def unclear(self) -> bool:
        return self.label == "unclear"

    def say(self, translate=None) -> str:
        from miratrade.messages import sayer

        say = sayer(translate)
        if self.unclear:
            return say("The wording does not lean either way clearly enough to call it.")
        word = {"positive": say("positive"), "negative": say("negative"),
                "neutral": say("neutral")}[self.label]
        return say("Wording reads {label} ({confidence} % sure). This says what was published, "
                   "not what will happen.", label=word, confidence=f"{self.confidence * 100:.0f}")


UNCLEAR = Score("unclear", 0.0, 0.0, 0)


class Unavailable(RuntimeError):
    """The model is not installed. A state to report, not a crash to swallow."""


# --------------------------------------------------------------------------- reading a filing

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
# The boilerplate every 8-K carries. Scoring it would measure the SEC's form, not the company.
_BOILERPLATE = re.compile(
    r"(UNITED STATES SECURITIES AND EXCHANGE COMMISSION|Washington,?\s*D\.?C\.?\s*20549|"
    r"Pursuant to Section 1[35] of the Securities Exchange Act|"
    r"Check the appropriate box below|Securities registered pursuant to|"
    r"Emerging growth company|Pursuant to the requirements of the Securities Exchange Act)",
    re.I)


def readable(html: str | bytes, min_words: int = 12) -> list[str]:
    """The sentences of a filing worth scoring, with the form's own words taken out.

    Every 8-K opens with the same three hundred words of SEC furniture. Feeding that to a
    classifier measures the form rather than the company, and it does it identically for every
    filing — which looks like a signal precisely because it is the same every time.
    """
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    text = _SPACE.sub(" ", _TAGS.sub(" ", html))
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if len(sentence.split()) < min_words or _BOILERPLATE.search(sentence):
            continue
        out.append(sentence)
    return out


# --------------------------------------------------------------------------- the backends

def onnx_backend(model: str) -> Callable[[Sequence[str]], list[tuple[str, float]]]:
    """FinBERT through ONNX Runtime: the same three numbers for a tenth of the install."""
    try:
        from optimum.onnxruntime import ORTModelForSequenceClassification
        from transformers import AutoTokenizer
    except ImportError as e:                    # a missing extra is a state, not a crash
        raise Unavailable(f"the `news` extra is not installed: {e}") from e

    tokenizer = AutoTokenizer.from_pretrained(model)
    net = ORTModelForSequenceClassification.from_pretrained(model, export=True)
    return _scorer(tokenizer, net)


def transformers_backend(model: str) -> Callable[[Sequence[str]], list[tuple[str, float]]]:
    """The same model through torch. Heavier, identical answer; kept for when ONNX will not build."""
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as e:
        raise Unavailable(f"the `news` extra is not installed: {e}") from e

    tokenizer = AutoTokenizer.from_pretrained(model)
    net = AutoModelForSequenceClassification.from_pretrained(model)
    net.eval()
    return _scorer(tokenizer, net)


def _scorer(tokenizer, net):
    def run(passages: Sequence[str]) -> list[tuple[str, float]]:
        import numpy as np

        if not passages:
            return []
        batch = tokenizer(list(passages), padding=True, truncation=True,
                          max_length=MAX_TOKENS, return_tensors="np")
        logits = np.asarray(net(**{k: v for k, v in batch.items()}).logits)
        exp = np.exp(logits - logits.max(axis=-1, keepdims=True))
        probs = exp / exp.sum(axis=-1, keepdims=True)
        # FinBERT's own order, from its config rather than assumed
        order = [net.config.id2label[i].lower() for i in range(probs.shape[-1])]
        out = []
        for row in probs:
            best = int(row.argmax())
            out.append((order[best], float(row[best])))
        return out
    return run


BACKENDS = {"onnx": onnx_backend, "transformers": transformers_backend}


# --------------------------------------------------------------------------- the engine

class Sentiment:
    """Scores passages, loading the model the first time it is actually asked for one.

    Never at import: the app has to start on a machine where the model was never downloaded, and
    an interface that will not open because a 440 MB file is missing is a worse failure than a
    missing score.
    """

    def __init__(self, params: SentimentParams | None = None, backend=None):
        self.params = params or Config().sentiment
        self._make = backend
        self._run = None

    @property
    def enabled(self) -> bool:
        return bool(self.params.enabled)

    def _ready(self):
        if self._run is None:
            if self._make is not None:
                self._run = self._make
            else:
                build = BACKENDS.get(self.params.backend)
                if build is None:
                    raise Unavailable(f"unknown backend {self.params.backend!r}: "
                                      f"{', '.join(BACKENDS)}")
                self._run = build(self.params.model)
        return self._run

    def score(self, passages: Iterable[str]) -> Score:
        """One verdict for a set of passages, or :data:`UNCLEAR`.

        The passages are averaged rather than voted on, so one strongly worded sentence in a long
        filing does not decide the whole thing, and a filing that is mostly neutral reads neutral.
        """
        if not self.enabled:
            return UNCLEAR
        text = [p for p in passages if p and p.strip()][: self.params.max_headlines]
        if not text:
            return UNCLEAR
        judged = self._ready()(text)
        if not judged:
            return UNCLEAR

        lean = 0.0
        confidence = 0.0
        for label, probability in judged:
            if label == "positive":
                lean += probability
            elif label == "negative":
                lean -= probability
            confidence += probability
        lean /= len(judged)
        confidence /= len(judged)

        if confidence < self.params.min_confidence or abs(lean) < self.params.neutral_band:
            # Below the floor the honest answer is "unclear", never a weak guess dressed as a call.
            return Score("unclear", lean, confidence, len(judged)) if confidence < self.params.min_confidence \
                else Score("neutral", lean, confidence, len(judged))
        return Score("positive" if lean > 0 else "negative", lean, confidence, len(judged))

    def of_filing(self, html: str | bytes) -> Score:
        """The verdict on one 8-K, from its own prose with the SEC's furniture removed."""
        return self.score(readable(html))


def engine(cfg: Config | None = None, backend=None) -> Sentiment:
    return Sentiment((cfg or Config()).sentiment, backend)
