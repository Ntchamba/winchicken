"""Deterministic column-header matching for the Excel imports.

Users rarely upload the template untouched: headers come back accented differently, abbreviated,
pluralised, reordered, padded with spaces, or simply typed from memory. Before this module the
importers looked headers up in a flat exact-match alias dict, so "Categorie " or "Qté / jour"
simply wasn't found and the whole file was rejected.

This layer runs *before* the existing validation: it maps each incoming header to a canonical
internal key and reports how it got there, so the UI can show the user what was understood.

It is 100% local and deterministic — a synonym table plus edit distance. No network call, no
model, no learning. The same file always produces the same mapping, and every decision is
inspectable in the report this returns.

Matching is three passes, best-first, each column consumed at most once:
  1. exact      — the normalised header is the canonical label or a listed synonym
  2. fuzzy      — edit-distance similarity against label+synonyms, above FUZZY_THRESHOLD
  3. unmatched  — reported as a default (if the field has one) or as needing attention

See docs/excel-import.md.
"""
import unicodedata
from dataclasses import dataclass, field

# Below this similarity a fuzzy candidate is not trusted. 0.80 accepts real-world noise
# ("quantite jour" vs "quantite/jour", "fornisseur" vs "fournisseur") while staying clear of
# genuinely different columns — "detail" vs "total" sits at 0.6, "de" vs "a" at 0.
FUZZY_THRESHOLD = 0.80

# A fuzzy match on a very short header is meaningless ("de" vs "a" would be one edit away from
# several things), so short headers must match exactly.
MIN_FUZZY_LENGTH = 4


@dataclass(frozen=True)
class Column:
    """One column the importer understands.

    `key`       internal name the parser reads (unchanged from before this module existed).
    `label`     the French header the template ships with.
    `synonyms`  other spellings a user might reasonably type. Normalised on comparison, so
                accents/case/spacing variants don't need listing — only real word differences do.
    `required`  a file with no match for this column cannot be imported at all.
    `default`   value used when the column is absent. ONLY set this where the app already
                applies that default elsewhere — never invent a new one.
    `default_note` French, user-facing, explains what the default does.
    """
    key: str
    label: str
    synonyms: tuple = ()
    required: bool = False
    default: object = None
    default_note: str = ''

    @property
    def has_default(self):
        return bool(self.default_note)


@dataclass
class ColumnMatch:
    """How one canonical column was resolved. Rendered as-is in the preview screen."""
    key: str
    label: str
    header: str = ''          # what the file actually had, '' when nothing matched
    index: int = None         # position in the file's header row
    method: str = 'missing'   # exact | fuzzy | default | missing
    confidence: float = 0.0
    note: str = ''
    required: bool = False

    def as_dict(self):
        return {
            'key': self.key, 'label': self.label, 'header': self.header, 'index': self.index,
            'method': self.method, 'confidence': round(self.confidence, 3),
            'note': self.note, 'required': self.required,
        }


@dataclass
class MatchReport:
    index: dict = field(default_factory=dict)      # {key: column position} — what parsers use
    matches: list = field(default_factory=list)    # [ColumnMatch] in canonical order
    unknown_headers: list = field(default_factory=list)  # headers in the file we ignored

    @property
    def unresolved(self):
        """Required columns with no match — these block the import."""
        return [m for m in self.matches if m.required and m.method == 'missing']

    def as_dict(self):
        return {
            'matches': [m.as_dict() for m in self.matches],
            'unknownHeaders': self.unknown_headers,
            'unresolved': [m.label for m in self.unresolved],
        }


def normalize(text) -> str:
    """Fold a header to its comparable form: no accents, no case, no punctuation, single spaces.

    'Qté / Jour ' -> 'qte jour';  "Seuil d'alerte" -> 'seuil d alerte'.
    """
    if text is None:
        return ''
    text = unicodedata.normalize('NFKD', str(text))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = ''.join(c if c.isalnum() else ' ' for c in text)
    return ' '.join(text.split())


def levenshtein(a: str, b: str) -> int:
    """Edit distance, iterative two-row. Pure local computation."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(
                previous[j] + 1,        # deletion
                current[j - 1] + 1,     # insertion
                previous[j - 1] + (ca != cb),  # substitution
            ))
        previous = current
    return previous[-1]


def similarity(a: str, b: str) -> float:
    """1.0 identical, 0.0 nothing in common."""
    if not a and not b:
        return 1.0
    longest = max(len(a), len(b))
    if longest == 0:
        return 0.0
    return 1.0 - levenshtein(a, b) / longest


def match_columns(header_row, columns) -> MatchReport:
    """Map a file's header row onto `columns` ([Column]). Never raises — a file with nothing
    recognisable comes back with every column 'missing', which the caller reports to the user."""
    headers = [(i, normalize(cell), '' if cell is None else str(cell).strip())
               for i, cell in enumerate(header_row)]

    report = MatchReport()
    taken = set()

    # Pass 1 — exact on the canonical label or any listed synonym.
    for column in columns:
        wanted = {normalize(column.label)} | {normalize(s) for s in column.synonyms}
        for i, norm, raw in headers:
            if i in taken or not norm:
                continue
            if norm in wanted:
                report.index[column.key] = i
                report.matches.append(ColumnMatch(
                    key=column.key, label=column.label, header=raw, index=i,
                    method='exact', confidence=1.0, required=column.required,
                ))
                taken.add(i)
                break

    # Pass 2 — fuzzy, for headers that are close but not listed (typos, spacing, word order).
    # Best candidate across all remaining headers wins, so two similar columns can't swap.
    resolved = {m.key for m in report.matches}
    for column in columns:
        if column.key in resolved:
            continue
        candidates = [normalize(column.label)] + [normalize(s) for s in column.synonyms]
        best_index, best_score, best_raw = None, 0.0, ''
        for i, norm, raw in headers:
            if i in taken or len(norm) < MIN_FUZZY_LENGTH:
                continue
            score = max(similarity(norm, c) for c in candidates if c)
            if score > best_score:
                best_index, best_score, best_raw = i, score, raw
        if best_index is not None and best_score >= FUZZY_THRESHOLD:
            report.index[column.key] = best_index
            report.matches.append(ColumnMatch(
                key=column.key, label=column.label, header=best_raw, index=best_index,
                method='fuzzy', confidence=best_score, required=column.required,
                note='Correspondance approximative — vérifiez que la colonne est la bonne.',
            ))
            taken.add(best_index)
            resolved.add(column.key)

    # Pass 3 — everything still unmatched: a documented default, or needs attention.
    for column in columns:
        if column.key in resolved:
            continue
        report.matches.append(ColumnMatch(
            key=column.key, label=column.label,
            method='default' if column.has_default else 'missing',
            note=column.default_note, required=column.required,
        ))

    report.matches.sort(key=lambda m: [c.key for c in columns].index(m.key))
    report.unknown_headers = [raw for i, norm, raw in headers if i not in taken and raw]
    return report
