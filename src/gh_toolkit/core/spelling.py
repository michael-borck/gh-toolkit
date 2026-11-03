"""American to Australian spelling checks for repository prose.

This is deliberately a small, curated mapping. It is used for auditing and
reporting, not for blind find-and-replace: names, code, URLs, and identifiers
must be preserved, and words like ``license`` or ``catalog`` are context
dependent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Unambiguous American spellings. Context-dependent words such as license,
# catalog, dialog, artifact, and program are deliberately absent.
AMERICAN_TO_AUSTRALIAN: dict[str, str] = {
    "organization": "organisation",
    "organizations": "organisations",
    "organize": "organise",
    "organized": "organised",
    "organizer": "organiser",
    "organizers": "organisers",
    "organizing": "organising",
    "color": "colour",
    "colors": "colours",
    "colored": "coloured",
    "coloring": "colouring",
    "behavior": "behaviour",
    "behaviors": "behaviours",
    "behavioral": "behavioural",
    "center": "centre",
    "centers": "centres",
    "centered": "centred",
    "centralize": "centralise",
    "centralized": "centralised",
    "centralizing": "centralising",
    "analyze": "analyse",
    "analyzed": "analysed",
    "analyzing": "analysing",
    "initialize": "initialise",
    "initialized": "initialised",
    "initializing": "initialising",
    "customize": "customise",
    "customized": "customised",
    "customizing": "customising",
    "optimize": "optimise",
    "optimized": "optimised",
    "optimizing": "optimising",
    "summarize": "summarise",
    "summarized": "summarised",
    "summarizing": "summarising",
    "prioritize": "prioritise",
    "prioritized": "prioritised",
    "prioritizing": "prioritising",
    "recognize": "recognise",
    "recognized": "recognised",
    "recognizing": "recognising",
    "authorize": "authorise",
    "authorized": "authorised",
    "authorizing": "authorising",
    "utilize": "utilise",
    "utilized": "utilised",
    "utilizing": "utilising",
    "minimize": "minimise",
    "minimized": "minimised",
    "minimizing": "minimising",
    "maximize": "maximise",
    "maximized": "maximised",
    "maximizing": "maximising",
    "normalize": "normalise",
    "normalized": "normalised",
    "normalizing": "normalising",
    "serialize": "serialise",
    "serialized": "serialised",
    "serializing": "serialising",
    "modeling": "modelling",
    "modeled": "modelled",
    "canceled": "cancelled",
    "canceling": "cancelling",
    "traveling": "travelling",
    "traveled": "travelled",
    "traveler": "traveller",
    "travelers": "travellers",
    "fulfill": "fulfil",
    "fulfillment": "fulfilment",
    "enroll": "enrol",
    "enrollment": "enrolment",
    "defense": "defence",
    "offense": "offence",
    "practicing": "practising",
    "fiber": "fibre",
    "liter": "litre",
    "gray": "grey",
    "grayscale": "greyscale",
    "analyzes": "analyses",
    "visualization": "visualisation",
    "visualizations": "visualisations",
    "visualize": "visualise",
    "visualized": "visualised",
    "visualizing": "visualising",
    "personalize": "personalise",
    "personalized": "personalised",
    "personalizing": "personalising",
    "personalization": "personalisation",
    "categorization": "categorisation",
    "categorizations": "categorisations",
    "categorize": "categorise",
    "categorized": "categorised",
    "categorizing": "categorising",
    "optimization": "optimisation",
    "optimizations": "optimisations",
    "prioritization": "prioritisation",
    "normalization": "normalisation",
    "serialization": "serialisation",
    "initialization": "initialisation",
    "customization": "customisation",
    "summarization": "summarisation",
    "authorization": "authorisation",
    "utilization": "utilisation",
    "minimization": "minimisation",
    "maximization": "maximisation",
    "realization": "realisation",
    "finalization": "finalisation",
    "modernization": "modernisation",
    "standardization": "standardisation",
    "specialization": "specialisation",
    "generalization": "generalisation",
    "capitalization": "capitalisation",
    "emphasize": "emphasise",
    "emphasized": "emphasised",
    "emphasizing": "emphasising",
    "standardize": "standardise",
    "standardized": "standardised",
    "standardizing": "standardising",
    "modernize": "modernise",
    "modernized": "modernised",
    "modernizing": "modernising",
    "finalize": "finalise",
    "finalized": "finalised",
    "finalizing": "finalising",
    "realize": "realise",
    "realized": "realised",
    "realizing": "realising",
    "specialize": "specialise",
    "specialized": "specialised",
    "specializing": "specialising",
    "generalize": "generalise",
    "generalized": "generalised",
    "generalizing": "generalising",
    "capitalize": "capitalise",
    "capitalized": "capitalised",
    "capitalizing": "capitalising",
    "sanitize": "sanitise",
    "sanitized": "sanitised",
    "sanitizing": "sanitising",
    "parameterize": "parameterise",
    "parameterized": "parameterised",
    "parameterizing": "parameterising",
    "tokenize": "tokenise",
    "tokenized": "tokenised",
    "tokenizing": "tokenising",
    "vectorize": "vectorise",
    "vectorized": "vectorised",
    "vectorizing": "vectorising",
    "containerize": "containerise",
    "containerized": "containerised",
    "containerizing": "containerising",
    "practiced": "practised",
    "favor": "favour",
    "favors": "favours",
    "favored": "favoured",
    "favoring": "favouring",
    "favorite": "favourite",
    "favorites": "favourites",
    "favorable": "favourable",
    "favorably": "favourably",
    "unfavorable": "unfavourable",
    "honor": "honour",
    "honors": "honours",
    "honored": "honoured",
    "honoring": "honouring",
    "honorable": "honourable",
    "honorably": "honourably",
    "labor": "labour",
    "labors": "labours",
    "labored": "laboured",
    "laboring": "labouring",
    "neighbor": "neighbour",
    "neighbors": "neighbours",
    "neighboring": "neighbouring",
    "neighborhood": "neighbourhood",
    "neighborhoods": "neighbourhoods",
    "rumor": "rumour",
    "rumors": "rumours",
    "humor": "humour",
    "humors": "humours",
    "vapor": "vapour",
    "vapors": "vapours",
    "savior": "saviour",
    "saviors": "saviours",
    "armor": "armour",
    "armors": "armours",
    "armored": "armoured",
    "flavor": "flavour",
    "flavors": "flavours",
    "flavored": "flavoured",
    "flavoring": "flavouring",
    "savor": "savour",
    "savors": "savours",
    "savored": "savoured",
    "savoring": "savouring",
    "endeavor": "endeavour",
    "endeavors": "endeavours",
    "endeavored": "endeavoured",
    "endeavoring": "endeavouring",
    "colorful": "colourful",
    "colorless": "colourless",
    "categorizes": "categorises",
    "organizes": "organises",
    "customizes": "customises",
    "optimizes": "optimises",
    "summarizes": "summarises",
    "prioritizes": "prioritises",
    "recognizes": "recognises",
    "authorizes": "authorises",
    "utilizes": "utilises",
    "minimizes": "minimises",
    "maximizes": "maximises",
    "normalizes": "normalises",
    "serializes": "serialises",
    "initializes": "initialises",
    "personalizes": "personalises",
    "visualizes": "visualises",
    "standardizes": "standardises",
    "modernizes": "modernises",
    "finalizes": "finalises",
    "realizes": "realises",
    "specializes": "specialises",
    "generalizes": "generalises",
    "capitalizes": "capitalises",
    "sanitizes": "sanitises",
    "parameterizes": "parameterises",
    "tokenizes": "tokenises",
    "vectorizes": "vectorises",
    "containerizes": "containerises",
    "emphasizes": "emphasises",
    "customizable": "customisable",
    "summarizer": "summariser",
    "summarizers": "summarisers",
    "visualizer": "visualiser",
    "visualizers": "visualisers",
    "organizational": "organisational",
    "characterize": "characterise",
    "characterized": "characterised",
    "characterizing": "characterising",
}

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_CODE_RE = re.compile(r"`[^`]*`")

_WORD_RE = re.compile(
    r"\b("
    + "|".join(
        re.escape(word)
        for word in sorted(AMERICAN_TO_AUSTRALIAN, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SpellingIssue:
    """One American spelling found in prose."""

    word: str
    suggestion: str


def _strip_non_prose(text: str) -> str:
    """Remove URLs, emails, and inline code before scanning words."""
    text = _URL_RE.sub(" ", text)
    text = _EMAIL_RE.sub(" ", text)
    return _CODE_RE.sub(" ", text)


def suggest_australian(word: str) -> str:
    """Return the Australian spelling, preserving the original case style."""
    suggestion = AMERICAN_TO_AUSTRALIAN[word.lower()]
    if word.isupper():
        return suggestion.upper()
    if word[:1].isupper():
        return suggestion.capitalize()
    return suggestion


_PROTECT_RE = re.compile(
    r"https?://\S+|www\.\S+|\b[\w.+-]+@[\w.-]+\.\w+\b|`[^`]*`",
    re.IGNORECASE,
)


def apply_australian_spelling(text: str) -> str:
    """Replace American spellings in prose, preserving protected spans."""
    if not text:
        return text

    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    masked = _PROTECT_RE.sub(protect, text)
    converted = _WORD_RE.sub(lambda match: suggest_australian(match.group(0)), masked)
    return re.sub(
        r"\x00(\d+)\x00",
        lambda match: protected[int(match.group(1))],
        converted,
    )


def truncate_at_word(text: str, max_length: int) -> str:
    """Trim to a word boundary without adding an ellipsis."""
    text = text.strip()
    if len(text) <= max_length:
        return text
    cut = text[:max_length].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut or text[:max_length]


def find_american_spellings(text: str | None) -> list[SpellingIssue]:
    """Return unique American spellings found in text, in first-seen order."""
    if not text:
        return []

    issues: list[SpellingIssue] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(_strip_non_prose(text)):
        word = match.group(0)
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        issues.append(SpellingIssue(word=word, suggestion=suggest_australian(word)))
    return issues
