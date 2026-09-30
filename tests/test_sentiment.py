"""FinBERT over what was published.

A fake backend throughout: the point of these tests is what the engine does with three numbers, not
whether a 440 MB download can be re-downloaded in CI. What the model says is the model's business;
what the engine says when the model is unsure, missing, or switched off is ours, and that is where
every mistake in a thing like this lives.
"""
import pytest

from miratrade.config import Config
from miratrade.news import sentiment
from miratrade.news.sentiment import Score, Sentiment, Unavailable, readable


def engine(backend, **changes) -> Sentiment:
    cfg = Config()
    cfg.sentiment.enabled = True
    for key, value in changes.items():
        setattr(cfg.sentiment, key, value)
    return Sentiment(cfg.sentiment, backend=backend)


def saying(label, probability=0.9):
    return lambda passages: [(label, probability)] * len(passages)


# --------------------------------------------------------------------------- off, missing, unsure

def test_it_is_off_by_default_and_that_is_the_honest_setting():
    """No news signal here has survived an out-of-sample test. Off is what the evidence supports."""
    assert Config().sentiment.enabled is False
    called = []
    quiet = Sentiment(Config().sentiment, backend=lambda p: called.append(p) or [])
    assert quiet.score(["anything at all"]).unclear
    assert called == []                       # and it does not even load the model


def test_a_missing_model_is_a_state_to_report_not_a_crash():
    """An interface that will not open because a 440 MB file is absent is a worse failure than a
    missing score."""
    cfg = Config()
    cfg.sentiment.enabled = True
    cfg.sentiment.backend = "something-else"
    with pytest.raises(Unavailable, match="unknown backend"):
        Sentiment(cfg.sentiment).score(["text"])


def test_the_model_is_never_loaded_at_import():
    """The app has to start on a machine where the model was never downloaded."""
    import inspect

    source = inspect.getsource(sentiment)
    head = source.split("class Sentiment")[0]
    assert "from transformers import" not in head.replace("        from transformers", "")


def test_below_the_confidence_floor_the_answer_is_unclear_not_a_weak_guess():
    """A weak guess dressed as a verdict is worse than no verdict."""
    weak = engine(saying("positive", 0.40), min_confidence=0.65).score(["a sentence here"])
    assert weak.unclear and "does not lean either way" in weak.say()


def test_a_lean_inside_the_neutral_band_reads_neutral_not_positive():
    mixed = engine(lambda p: [("positive", 0.9), ("negative", 0.88)],
                   neutral_band=0.15).score(["one", "two"])
    assert mixed.label == "neutral"


def test_nothing_to_read_is_unclear():
    e = engine(saying("positive"))
    assert e.score([]).unclear and e.score(["", "   "]).unclear


# --------------------------------------------------------------------------- the verdict

def test_a_clear_lean_is_called():
    good = engine(saying("positive", 0.93)).score(["a clearly worded sentence"])
    assert good.label == "positive" and good.confidence == pytest.approx(0.93)
    bad = engine(saying("negative", 0.93)).score(["a clearly worded sentence"])
    assert bad.label == "negative" and bad.score < 0


def test_passages_are_averaged_so_one_loud_sentence_does_not_decide():
    """A filing that is mostly neutral should read neutral, however strongly one line is worded."""
    loud = [("negative", 0.99)] + [("neutral", 0.8)] * 9
    out = engine(lambda p: loud[:len(p)]).score([f"sentence {i}" for i in range(10)])
    assert out.label != "negative"
    assert out.passages == 10


def test_only_so_many_passages_are_read():
    seen = []

    def backend(passages):
        seen.append(len(passages))
        return [("neutral", 0.9)] * len(passages)

    engine(backend, max_headlines=3).score([f"sentence number {i}" for i in range(50)])
    assert seen == [3]


def test_what_it_says_never_claims_a_forecast():
    said = engine(saying("positive", 0.93)).score(["a sentence"]).say()
    assert "what was published" in said and "not what will happen" in said


# --------------------------------------------------------------------------- reading a filing

def test_the_secs_own_furniture_is_thrown_away_before_scoring():
    """Every 8-K opens with the same three hundred words of form. Feeding that to a classifier
    measures the form rather than the company — identically for every filing, which looks like a
    signal precisely because it never changes."""
    html = """<html><body>
      <p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION Washington, D.C. 20549</p>
      <p>Check the appropriate box below if the Form 8-K filing is intended to simultaneously
         satisfy the filing obligation of the registrant.</p>
      <p>On 10 June the Company entered into a credit agreement providing for a revolving
         facility of two hundred million dollars.</p>
    </body></html>"""
    kept = readable(html)
    assert len(kept) == 1 and "credit agreement" in kept[0]
    assert not any("SECURITIES AND EXCHANGE" in k for k in kept)


def test_tags_go_and_short_fragments_go():
    kept = readable("<p>Short.</p><div>The Company announced the resignation of its chief "
                    "financial officer, effective immediately.</div>")
    assert len(kept) == 1 and "chief financial officer" in kept[0]


def test_a_filing_is_scored_from_its_own_prose():
    html = ("<p>The Company announced that its chief financial officer has resigned, effective "
            "immediately, and that a search for a successor has begun.</p>")
    out = engine(saying("negative", 0.9)).of_filing(html)
    assert out.label == "negative" and out.passages == 1


def test_a_filing_with_nothing_but_boilerplate_is_unclear():
    html = "<p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION Washington, D.C. 20549</p>"
    assert engine(saying("positive", 0.99)).of_filing(html).unclear


# --------------------------------------------------------------------------- the settings

def test_every_setting_is_offered_and_storable():
    from miratrade import params, prefs

    assert params.validate(params.NEWS_GROUPS) == []
    assert "sentiment" in prefs.USER_SECTIONS
    assert "sentiment" in params.offered()


def test_the_settings_say_it_claims_nothing():
    from miratrade import params

    group = params.NEWS_GROUPS[0]
    assert "OFF by default" in group.note and "never a forecast" in group.note
    switch = next(f for f in group.fields if f.key == "enabled")
    assert "no number on any screen depends on it" in switch.help


def test_the_light_backend_is_the_default():
    """2.5 GB of framework for a model that runs on a CPU in milliseconds is a choice, and the
    default should be the one that does not make the container four times bigger."""
    assert Config().sentiment.backend == "onnx"
    assert set(sentiment.BACKENDS) == {"onnx", "transformers"}
