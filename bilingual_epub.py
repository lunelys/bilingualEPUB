# -*- coding: utf-8 -*-
"""
bilingualEPUB Core Engine & CLI/UI Backend (v6)
===============================================
Key Features & Fixes in v6:
1. True EPUB <spine> Reading Order + Natural Sorting:
   - Parses the EPUB's `.opf` `<manifest>` and `<spine>` to process chapters in the exact
     page-1-to-end reading order (never processing Chapter 10 before Chapter 2!).
2. Bulletproof Single-Tag HTML Walker:
   - Splits HTML only on individual tags `<[^>]+>` and entities `&...;`, tracking a
     `skip_depth` counter for `<head>`, `<style>`, `<script>`, `<title>`, `<svg>`, and `<h1..h6>`.
   - Works on all EPUB structures (`<p>`, `<P>`, `<div>`, `<span>`, `<blockquote>`, `<section>`)
     and can never be tripped up by self-closing `<svg/>` ornaments.
3. Even Chapter Slice Distribution & Guaranteed Toolbox-to-Inline Match:
   - Uses the exact same walker for candidate discovery and replacement so 100% of words
     shown in a chapter's toolbox are guaranteed to appear with inline translations in that chapter,
     distributed evenly starting from Page 1.
"""

import zipfile
import re
import difflib
import uuid
from pathlib import Path, PurePosixPath
from collections import Counter
from vocab_data import (
    EN_TO_DE_VOCAB,
    DE_HARD_GLOSSES,
    DE_NOUN_WITH_ARTICLE,
    DE_THEME_KEYWORDS,
    get_de_word_level,
)


VERB_PRECEDERS = {
    "to", "will", "would", "can", "could", "should", "must", "may", "might",
    "do", "does", "did", "don", "doesn", "didn", "won", "wouldn", "couldn", "shouldn",
    "not", "never", "always", "just", "also", "even", "still",
    "i", "you", "we", "they", "he", "she", "who",
}

NOUN_PRECEDERS = {
    "the", "a", "an", "my", "your", "his", "her", "its", "our", "their",
    "this", "that", "these", "those", "every", "each", "no", "some", "any", "many", "few",
    "into", "from", "in", "on", "at", "of", "with", "without", "through", "under", "over",
    "behind", "between", "against", "across", "around", "inside", "outside", "beneath",
    "dark", "black", "white", "red", "blue", "cold", "warm", "deep", "long", "short",
    "heavy", "sharp", "soft", "bare", "empty", "full", "own", "other", "another",
    "first", "last", "next", "old", "new", "young", "little", "small", "great", "good",
    "sudden", "faint", "loud", "quiet", "silent", "single", "final", "quick", "slow",
}

AMBIGUOUS_EN_NOUNS = {
    "light", "lights", "hand", "hands", "face", "faces", "head", "heads",
    "arm", "arms", "back", "backs", "step", "steps", "turn", "turns",
    "look", "looks", "smile", "smiles", "whisper", "whispers", "scream", "screams",
    "fight", "fights", "attack", "attacks", "escape", "escapes", "rescue", "rescues",
    "order", "orders", "force", "forces", "place", "places", "room", "rooms",
    "water", "fire", "fires", "trust", "doubt", "promise", "promises", "lie", "lies",
    "mark", "marks", "lock", "locks", "trap", "traps", "guard", "guards",
    "ring", "rings", "coat", "coats", "dress", "dresses", "shield", "shields",
    "touch", "sense", "taste", "smell", "sound", "sounds", "attempt", "attempts",
    "challenge", "challenges", "access", "trigger", "triggers", "circle", "circles",
    "desire", "pressure", "wave", "waves", "stream", "streams", "spark", "sparks",
    "bruise", "bruises", "curse", "curses", "regret", "regrets",
}

BILINGUAL_CSS = """
/* bilingualEPUB Styling for E-Ink (Seamless Normal Text + Whisper-Thin Faded Hint) */
.bk-vocab-box {
    border: 1px solid #888;
    border-radius: 4px;
    padding: 0.55em 0.75em;
    margin: 0.8em 0 1.2em 0;
    font-size: 0.82em;
    line-height: 1.35;
    background-color: #f6f6f6;
}
.bk-vocab-title {
    font-weight: bold;
    font-size: 0.92em;
    margin-bottom: 0.3em;
    border-bottom: 1px solid #aaa;
    padding-bottom: 0.15em;
}
.bk-vocab-list {
    margin: 0;
    padding: 0;
}
.bk-de-word {
    font-weight: inherit;
}
.bk-hint {
    font-size: 0.72em;
    font-style: italic;
    font-weight: 300;
    color: #777777;
}
"""

# Single-tag / entity splitter (never spans across multiple tags)
TOKEN_SPLIT_RE = re.compile(r'(<[^>]+>|&[a-zA-Z0-9#]+;)')
SKIP_TAG_OPEN_RE = re.compile(r'^<(h[1-6]|head|style|script|title|svg)\b', flags=re.I)
SKIP_TAG_CLOSE_RE = re.compile(r'^</(h[1-6]|head|style|script|title|svg)\s*>', flags=re.I)
BLOCK_BOUNDARY_RE = re.compile(r'^</?(?:p|div|h[1-6]|li|blockquote|section|article|tr|td|br)\b', flags=re.I)


def ensure_folders(workspace: Path):
    folders = {
        "in_en": workspace / "Input_English_Books",
        "in_de": workspace / "Input_German_Books",
        "out_en": workspace / "Output_English_Augmented",
        "out_de": workspace / "Output_German_Augmented",
    }
    for p in folders.values():
        p.mkdir(parents=True, exist_ok=True)
    return folders


def clean_book_slug(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r'\s*\([^)]*\)', '', stem).strip()
    stem = re.sub(r'\s*\[[^\]]*\]', '', stem).strip()
    slug = re.sub(r'[^A-Za-z0-9ÄÖÜäöüß]+', '_', stem).strip('_')
    return slug or "Book"


def natural_sort_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]


def normalize_for_cognate(s: str) -> str:
    s = s.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss"), ("sch", "sh"), ("k", "c"), ("z", "t")):
        s = s.replace(a, b)
    return s


def is_transparent_cognate(de_word: str, en_gloss: str) -> bool:
    de_norm = normalize_for_cognate(de_word)
    for part in re.findall(r'[A-Za-z]+', en_gloss):
        en_norm = normalize_for_cognate(part)
        if len(en_norm) < 3:
            continue
        if de_norm == en_norm:
            return True
        if len(de_norm) >= 4 and len(en_norm) >= 4 and de_norm[:4] == en_norm[:4]:
            return True
        ratio = difflib.SequenceMatcher(None, de_norm, en_norm).ratio()
        if ratio >= 0.68:
            return True
    return False


def walk_and_transform_html(raw_html: str, text_transformer) -> str:
    """
    Walks an XHTML/HTML document by splitting on single tags `<[^>]+>` and entities `&...;`.
    Skips text inside `<head>`, `<style>`, `<script>`, `<title>`, `<svg>`, and `<h1..h6>`.
    Passes `(text_node, rolling_prev_list)` to `text_transformer` for every story text node.
    """
    parts = TOKEN_SPLIT_RE.split(raw_html)
    skip_depth = 0
    rolling_prev = [""]

    for i in range(len(parts)):
        part = parts[i]
        if i % 2 == 1:
            # Tag or entity
            if part.startswith("<") and not part.startswith("<!--"):
                if not part.endswith("/>") and SKIP_TAG_OPEN_RE.match(part):
                    skip_depth += 1
                elif SKIP_TAG_CLOSE_RE.match(part):
                    skip_depth = max(0, skip_depth - 1)
                if BLOCK_BOUNDARY_RE.match(part):
                    rolling_prev[0] = ""
        else:
            # Text node
            if skip_depth == 0 and part.strip():
                parts[i] = text_transformer(part, rolling_prev)

    return "".join(parts)


def extract_story_text_nodes(raw_html: str) -> list:
    """Returns a list of all story text nodes in reading order (excluding head/headings/style)."""
    nodes = []

    def _collect(text_node, _rolling_prev):
        nodes.append(text_node)
        return text_node

    walk_and_transform_html(raw_html, _collect)
    return nodes


def load_known_words(workspace: Path) -> set:
    kw_file = workspace / "known_words.txt"
    if not kw_file.exists():
        kw_file.write_text(
            "# Add any German or English words you already know by heart (one per line).\n"
            "# They will never be translated in future books.\n",
            encoding="utf-8",
        )
        return set()
    words = set()
    for line in kw_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.lower())
    return words


def allowed_levels(user_level: str) -> set:
    user_level = (user_level or "B2").upper()
    if user_level == "B1":
        return {"B1", "B2", "C1"}
    elif user_level == "C1":
        return {"C1"}
    else:
        return {"B2", "C1"}


def level_display_label(user_level: str) -> str:
    user_level = (user_level or "B2").upper()
    if user_level == "B1":
        return "B1/B2/C1"
    elif user_level == "C1":
        return "C1"
    return "B2/C1"


def format_gloss_clean(gloss: str) -> str:
    return re.sub(r'\s*/\s*', ', ', gloss.strip())


def write_en_vocab_txt_stacks(
    book_slug: str,
    output_dir: Path,
    unlocked_sequence: list,
    stack_size: int = 50,
    export_anki: bool = False,
) -> list:
    stack_size = max(5, min(200, int(stack_size)))
    lists_dir = output_dir / f"{book_slug}_Vocab_Lists"
    lists_dir.mkdir(parents=True, exist_ok=True)
    for old_f in lists_dir.glob("*.txt"):
        old_f.unlink()

    created_files = []
    total_words = len(unlocked_sequence)
    if total_words == 0:
        return created_files

    num_stacks = (total_words + stack_size - 1) // stack_size
    for s_idx in range(num_stacks):
        chunk = unlocked_sequence[s_idx * stack_size : (s_idx + 1) * stack_size]
        txt_name = f"{book_slug}_{s_idx + 1}.txt"
        txt_path = lists_dir / txt_name

        lines = [
            f"{entry['base_de']} : {format_gloss_clean(entry['meaning'])}"
            for _, entry in chunk
        ]
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        created_files.append(txt_path)

    if export_anki:
        anki_path = lists_dir / f"{book_slug}_Anki_TSV.txt"
        anki_lines = [
            f"{entry['base_de']}\t{format_gloss_clean(entry['meaning'])}\tChapter_{ch_num} {entry.get('level', 'B2')}"
            for ch_num, entry in unlocked_sequence
        ]
        anki_path.write_text("\n".join(anki_lines) + "\n", encoding="utf-8")
        created_files.append(anki_path)

    return created_files


def write_de_thematic_txt_lists(
    book_slug: str,
    output_dir: Path,
    matched_words_info: dict,
    encounter_counts: Counter,
    max_lists: int = 4,
    words_per_list: int = 50,
    export_anki: bool = False,
) -> list:
    max_lists = max(1, min(8, int(max_lists)))
    words_per_list = max(5, min(200, int(words_per_list)))

    lists_dir = output_dir / f"{book_slug}_Vocab_Lists"
    lists_dir.mkdir(parents=True, exist_ok=True)
    for old_f in lists_dir.glob("*.txt"):
        old_f.unlink()

    themed_buckets = {k: [] for k in DE_THEME_KEYWORDS.keys()}
    themed_buckets["8_Narrative_&_Modifiers"] = []

    sorted_lemmas = [k for k, _ in encounter_counts.most_common()]
    seen_glosses = set()

    for lemma_key in sorted_lemmas:
        if lemma_key not in matched_words_info:
            continue
        de_disp, gloss = matched_words_info[lemma_key]
        de_formatted = DE_NOUN_WITH_ARTICLE.get(de_disp, de_disp)
        clean_g = format_gloss_clean(gloss)
        if clean_g in seen_glosses:
            continue
        seen_glosses.add(clean_g)
        gloss_tokens = set(re.findall(r'[a-z]+', clean_g.lower()))

        placed = False
        for theme_key, kw_set in DE_THEME_KEYWORDS.items():
            if gloss_tokens & kw_set:
                themed_buckets[theme_key].append((de_formatted, clean_g))
                placed = True
                break
        if not placed:
            themed_buckets["8_Narrative_&_Modifiers"].append((de_formatted, clean_g))

    # Rank the 7 primary thematic buckets by prominence first; keep catch-all 8_Narrative_&_Modifiers last
    ordered_themes = sorted(
        [(k, items) for k, items in themed_buckets.items() if items],
        key=lambda x: (0 if x[0].startswith("8_") else 1, len(x[1])),
        reverse=True,
    )
    chosen_themes = ordered_themes[:max_lists]
    overflow_pool = []
    for _, items in ordered_themes[max_lists:]:
        overflow_pool.extend(items)
    for idx, (k, items) in enumerate(chosen_themes):
        if len(items) > words_per_list:
            overflow_pool.extend(items[words_per_list:])
            chosen_themes[idx] = (k, items[:words_per_list])

    for idx, (k, items) in enumerate(chosen_themes):
        while len(items) < words_per_list and overflow_pool:
            items.append(overflow_pool.pop(0))

    created_files = []
    all_selected_for_anki = []

    for list_idx, (theme_key, items) in enumerate(chosen_themes, start=1):
        pretty_slug = theme_key.split("_", 1)[1]
        txt_name = f"{book_slug}_{list_idx}_{pretty_slug}.txt"
        txt_path = lists_dir / txt_name

        lines = [f"{de_w} : {clean_g}" for de_w, clean_g in items]
        for de_w, clean_g in items:
            all_selected_for_anki.append((de_w, clean_g, pretty_slug))

        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        created_files.append(txt_path)

    if export_anki and all_selected_for_anki:
        anki_path = lists_dir / f"{book_slug}_Anki_TSV.txt"
        anki_lines = [f"{de_w}\t{clean_g}\t{theme}" for de_w, clean_g, theme in all_selected_for_anki]
        anki_path.write_text("\n".join(anki_lines) + "\n", encoding="utf-8")
        created_files.append(anki_path)

    return created_files


def is_front_or_back_matter_html(raw_html: str) -> bool:
    """Detects copyright, impressum, or table-of-contents pages by content."""
    sample = raw_html[:4000].lower()
    copyright_markers = (
        "all rights reserved",
        "library of congress",
        "alle rechte vorbehalten",
        "impressum",
        "urheberrecht",
        "first published in",
        "printed in the united states",
        "printed in great britain",
    )
    return any(m in sample for m in copyright_markers)


def detect_story_chapters(zin: zipfile.ZipFile) -> list:
    """
    Determines the ordered list of story XHTML/HTML chapters in the EPUB:
    1. First parses the `.opf` `<manifest>` and `<spine>` for exact reading order.
    2. Filters out frontmatter/backmatter files (cover, toc, nav, copyright, dedication,
       epigraph, titlepage, halftitle, map, acknowledgments, about-the-author) even when
       prefixed by ISBN/publisher strings like `Author_97812345_epub3_cop_r1.xhtml`.
    3. Falls back to natural-sorted XHTML/HTML files if no `.opf` spine is found.
    """
    namelist = zin.namelist()
    name_set = set(namelist)
    skip_re = re.compile(
        r'(?:^|[_\-\.])(?:'
        r'cov(?:er)?|toc|nav|cop(?:y(?:right)?)?|tp|htp|title(?:page)?|halftitle|'
        r'ack(?:nowledg[e]?ments)?|ded(?:ication)?|epi(?:graph)?|map|front(?:matter)?|'
        r'back(?:matter)?|adcard|ata|about|author|bio|next[\-_]?reads|also[\-_]?by|'
        r'hinweis|copyr|karte|impressum'
        r')(?:$|[_\-\.\d])',
        re.I,
    )

    spine_files = []
    opf_files = [n for n in namelist if n.lower().endswith('.opf')]
    if opf_files:
        opf_path = opf_files[0]
        opf_dir = PurePosixPath(opf_path).parent
        opf_raw = zin.read(opf_path).decode('utf-8', errors='replace')

        id_to_href = {}
        for item_m in re.finditer(r'<item\b([^>]+)>', opf_raw, flags=re.I):
            attrs = item_m.group(1)
            id_m = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.I)
            href_m = re.search(r'\bhref\s*=\s*["\']([^"\'#]+)', attrs, flags=re.I)
            if id_m and href_m:
                raw_href = href_m.group(1)
                resolved = str(opf_dir / raw_href) if str(opf_dir) != "." else raw_href
                parts = []
                for seg in resolved.split('/'):
                    if seg == '..':
                        if parts:
                            parts.pop()
                    elif seg and seg != '.':
                        parts.append(seg)
                norm_path = "/".join(parts)
                if norm_path in name_set:
                    id_to_href[id_m.group(1)] = norm_path
                elif raw_href in name_set:
                    id_to_href[id_m.group(1)] = raw_href

        for ref_m in re.finditer(r'<itemref\b([^>]+)>', opf_raw, flags=re.I):
            attrs = ref_m.group(1)
            idref_m = re.search(r'\bidref\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.I)
            if idref_m and idref_m.group(1) in id_to_href:
                p = id_to_href[idref_m.group(1)]
                if p.lower().endswith(('.xhtml', '.html', '.htm')) and p not in spine_files:
                    spine_files.append(p)

    candidates = spine_files if len(spine_files) >= 2 else sorted(
        [n for n in namelist if n.lower().endswith(('.xhtml', '.html', '.htm'))],
        key=natural_sort_key,
    )

    story_files = [
        n for n in candidates
        if not skip_re.search(PurePosixPath(n).stem)
    ]
    return story_files if story_files else candidates


def is_valid_en_noun_context(word: str, gender: str, prev_w: str) -> bool:
    if gender in ("der", "die", "das"):
        if prev_w in VERB_PRECEDERS:
            return False
        if word in AMBIGUOUS_EN_NOUNS and prev_w not in NOUN_PRECEDERS:
            return False
    return True


def strip_kobo_kepub_wrappers(raw_html: str) -> str:
    """
    Removes leftover Kobo store KEPUB wrappers (`koboSpan`, `js/kobo.js`, `css/kobo.css`,
    `kobostylehacks`) from Kobo-ripped EPUBs so that nested `<span class="bk-hint">`
    elements never conflict with Kobo's firmware renderer.
    """
    if 'koboSpan' not in raw_html and 'kobo.js' not in raw_html and 'kobostylehacks' not in raw_html:
        return raw_html

    cleaned = re.sub(r'<script\b[^>]*kobo\.js[^>]*/>\s*', '', raw_html, flags=re.I)
    cleaned = re.sub(r'<script\b[^>]*kobo\.js[^>]*>.*?</script>\s*', '', cleaned, flags=re.I | re.S)
    cleaned = re.sub(r'<link\b[^>]*kobo\.css[^>]*/?>\s*', '', cleaned, flags=re.I)
    cleaned = re.sub(r'<style\b[^>]*id="kobostylehacks"[^>]*>.*?</style>\s*', '', cleaned, flags=re.I | re.S)

    # Safely unwrap <span ... class="koboSpan" ...>...</span> while preserving all inner content & XML validity
    if 'koboSpan' in cleaned:
        parts = TOKEN_SPLIT_RE.split(cleaned)
        span_stack = []
        out = []
        for idx, part in enumerate(parts):
            if idx % 2 == 1 and part.startswith("<"):
                if re.match(r'^<span\b', part, flags=re.I) and not part.endswith("/>"):
                    is_kobo = 'class="koboSpan"' in part or "class='koboSpan'" in part
                    span_stack.append(is_kobo)
                    if is_kobo:
                        continue  # Drop opening koboSpan tag
                elif re.match(r'^</span\s*>', part, flags=re.I):
                    if span_stack:
                        was_kobo = span_stack.pop()
                        if was_kobo:
                            continue  # Drop matching closing </span>
            out.append(part)
        cleaned = "".join(out)

    return cleaned


def strip_previous_bilingual_markup(raw_html: str) -> str:
    """Strips leftover Kobo KEPUB wrappers and any prior bilingualEPUB markup."""
    cleaned = strip_kobo_kepub_wrappers(raw_html)
    if 'class="bk-vocab-box"' not in cleaned and 'class="bk-hint"' not in cleaned:
        return cleaned
    cleaned = re.sub(
        r'<div class="bk-vocab-box">\s*<div class="bk-vocab-title">.*?</div>\s*<div class="bk-vocab-list">.*?</div>\s*</div>\s*',
        '',
        cleaned,
        flags=re.S,
    )
    cleaned = re.sub(r'\s*<span class="bk-hint">\[[^\]]*\]</span>', '', cleaned)
    cleaned = re.sub(r'<span class="bk-de-word">(.*?)</span>', r'\1', cleaned)
    return cleaned


def update_opf_metadata(opf_text: str, title_suffix: str, force_de_lang: bool = False) -> str:
    """
    Updates OPF metadata for the generated EPUB:
    - Optionally sets <dc:language> to 'de' so e-readers use the German dictionary.
    - Appends title_suffix inside <dc:title> without duplicating it.
    - Assigns a fresh UUID <dc:identifier> so Kobo never loads a stale cached copy.
    - Removes leftover Kobo KEPUB manifest items (kobo.js / kobo.css).
    """
    if force_de_lang:
        opf_text = re.sub(
            r'(<dc:language\b[^>]*>).*?(</dc:language>)',
            r'\1de\2',
            opf_text,
            flags=re.I | re.S,
        )

    def _append_title(m: re.Match) -> str:
        open_tag, title_body, close_tag = m.group(1), m.group(2), m.group(3)
        if title_suffix in title_body:
            return m.group(0)
        return f"{open_tag}{title_body} {title_suffix}{close_tag}"

    opf_text = re.sub(
        r'(<dc:title\b[^>]*>)(.*?)(</dc:title>)',
        _append_title,
        opf_text,
        count=1,
        flags=re.I | re.S,
    )

    fresh_uuid = f"urn:uuid:{uuid.uuid4()}"
    opf_text = re.sub(
        r'(<dc:identifier\b[^>]*>).*?(</dc:identifier>)',
        lambda m: f"{m.group(1)}{fresh_uuid}{m.group(2)}",
        opf_text,
        count=1,
        flags=re.I | re.S,
    )

    # Remove leftover Kobo KEPUB manifest entries if present
    opf_text = re.sub(
        r'<item\b[^>]*href="[^"]*(?:kobo\.js|kobo\.css)"[^>]*/?>\s*',
        '',
        opf_text,
        flags=re.I,
    )
    return opf_text


def transform_en_to_progressive_de(
    input_epub: Path,
    output_epub: Path,
    words_per_chapter: int = 10,
    hint_max_encounters: int = 2,
    user_level: str = "B2",
    show_chapter_box: bool = True,
    export_txt_lists: bool = True,
    words_per_txt_list: int = 50,
    export_anki: bool = False,
    known_words: set = None,
):
    words_per_chapter = max(1, min(30, int(words_per_chapter)))
    hint_max_encounters = max(1, min(10, int(hint_max_encounters)))
    words_per_txt_list = max(5, min(200, int(words_per_txt_list)))
    known_words = known_words or set()
    valid_levels = allowed_levels(user_level)
    lvl_label = level_display_label(user_level)

    vocab_pool = [
        e for e in EN_TO_DE_VOCAB
        if e["id"].lower() not in known_words
        and e["base_de"].lower() not in known_words
    ]
    form_to_cand = {}
    for entry in vocab_pool:
        for en_f, de_f in entry["forms"].items():
            if en_f not in form_to_cand:
                form_to_cand[en_f] = (entry, de_f)

    with zipfile.ZipFile(input_epub, 'r') as zin:
        chapter_files = detect_story_chapters(zin)

        unlocked_ids = set()
        unlocked_base_de = set()
        unlocked_sequence = []
        active_forms = {}
        encounter_counts = Counter()
        transformed_files = {}

        for ch_idx, ch_path in enumerate(chapter_files, start=1):
            raw_html = strip_previous_bilingual_markup(
                zin.read(ch_path).decode('utf-8', errors='replace')
            )

            # PASS 1: Walk exact story text nodes to discover candidate words in this chapter
            valid_counts = Counter()
            first_pos = {}
            token_cursor = [0]

            def _discover_node(text_node: str, rolling_prev: list) -> str:
                for m in re.finditer(r"(?<![A-Za-z\-’'])([a-z]{3,})(?![A-Za-z\-’'])", text_node):
                    w = m.group(1)
                    prefix = text_node[:m.start()]
                    prev_words = re.findall(r"[A-Za-z]+", prefix)
                    prev_w = prev_words[-1].lower() if prev_words else rolling_prev[0]
                    token_cursor[0] += 1

                    if w in form_to_cand:
                        entry, _ = form_to_cand[w]
                        eid = entry["id"]
                        bde = entry["base_de"]
                        if eid not in unlocked_ids and bde not in unlocked_base_de:
                            if is_valid_en_noun_context(w, entry["gender"], prev_w):
                                valid_counts[eid] += 1
                                if eid not in first_pos:
                                    first_pos[eid] = token_cursor[0]

                tail_words = re.findall(r"[A-Za-z]+", text_node)
                if tail_words:
                    rolling_prev[0] = tail_words[-1].lower()
                return text_node

            walk_and_transform_html(raw_html, _discover_node)

            # Skip short frontmatter/divider pages (epigraphs, dedications, part titles, quotes)
            # or copyright/impressum pages
            if is_front_or_back_matter_html(raw_html) or (token_cursor[0] < 120 and len(chapter_files) > 3) or (token_cursor[0] < 15 and not valid_counts):
                transformed_files[ch_path] = raw_html.encode('utf-8')
                continue

            avail_entries = []
            seen_bde = set()
            for entry in vocab_pool:
                eid = entry["id"]
                bde = entry["base_de"]
                if eid in unlocked_ids or bde in unlocked_base_de or bde in seen_bde:
                    continue
                if valid_counts[eid] >= 1:
                    seen_bde.add(bde)
                    is_primary = 1 if entry.get("level", "B2") in valid_levels else 0
                    avail_entries.append((first_pos[eid], is_primary, valid_counts[eid], entry))

            # Sort by first appearance in the chapter and pick evenly across slices
            avail_entries.sort(key=lambda x: x[0])
            newly_unlocked = []
            if len(avail_entries) <= words_per_chapter:
                newly_unlocked = [x[3] for x in avail_entries]
            else:
                n_avail = len(avail_entries)
                for s_i in range(words_per_chapter):
                    start_i = (s_i * n_avail) // words_per_chapter
                    end_i = ((s_i + 1) * n_avail) // words_per_chapter
                    slice_cands = avail_entries[start_i:end_i]
                    if slice_cands:
                        best = max(slice_cands, key=lambda x: (x[1], x[2], -x[0]))
                        newly_unlocked.append(best[3])

            for entry in newly_unlocked:
                unlocked_ids.add(entry["id"])
                unlocked_base_de.add(entry["base_de"])
                unlocked_sequence.append((ch_idx, entry))
                for en_form, de_form in entry["forms"].items():
                    active_forms[en_form] = (entry, de_form)

            if active_forms:
                sorted_en_forms = sorted(active_forms.keys(), key=len, reverse=True)
                word_pattern = re.compile(
                    r"(?<![A-Za-z\-’'])(" + '|'.join(re.escape(w) for w in sorted_en_forms) + r")(?![A-Za-z\-’'])"
                )
            else:
                word_pattern = None

            # PASS 2: Walk the exact same story text nodes and perform inline replacements
            def _replace_node(text_node: str, rolling_prev: list) -> str:
                if not word_pattern:
                    return text_node

                def _repl(match):
                    word = match.group(1)
                    if word not in active_forms:
                        return word
                    entry, de_form = active_forms[word]
                    eid = entry["id"]
                    gender = entry["gender"]

                    prefix = text_node[:match.start()]
                    prev_words = re.findall(r"[A-Za-z]+", prefix)
                    prev_w = prev_words[-1].lower() if prev_words else rolling_prev[0]

                    if not is_valid_en_noun_context(word, gender, prev_w):
                        return word

                    encounter_counts[eid] += 1
                    cnt = encounter_counts[eid]

                    if cnt <= hint_max_encounters:
                        return f'<span class="bk-de-word">{de_form}</span> <span class="bk-hint">[{format_gloss_clean(entry["meaning"])}]</span>'
                    else:
                        return f'<span class="bk-de-word">{de_form}</span>'

                out = word_pattern.sub(_repl, text_node)
                tail_words = re.findall(r"[A-Za-z]+", text_node)
                if tail_words:
                    rolling_prev[0] = tail_words[-1].lower()
                return out

            new_html = walk_and_transform_html(raw_html, _replace_node)

            if 'bilingualEPUB Styling' not in new_html and re.search(r'</head>', new_html, flags=re.I):
                new_html = re.sub(
                    r'(</head>)',
                    lambda m: f'<style type="text/css">{BILINGUAL_CSS}</style>{m.group(1)}',
                    new_html,
                    count=1,
                    flags=re.I,
                )

            new_html = re.sub(r'lang="en(?:-[A-Za-z]+)?"', 'lang="de"', new_html, flags=re.I)

            if show_chapter_box and newly_unlocked:
                items_html = " · ".join(
                    f'<b>{e["base_de"]}</b> (<i>{format_gloss_clean(e["meaning"])}</i>)' for e in newly_unlocked
                )
                vocab_box_html = (
                    f'<div class="bk-vocab-box">'
                    f'<div class="bk-vocab-title">🇩🇪 Neues Vokabular: +{len(newly_unlocked)} neue {lvl_label}-Wörter '
                    f'(Gesamt aktiv: {len(unlocked_ids)})</div>'
                    f'<div class="bk-vocab-list">{items_html}</div>'
                    f'</div>'
                )
                if re.search(r'</h1>', new_html, flags=re.I):
                    new_html = re.sub(r'(</h1>)', lambda m: f'{m.group(1)}\n{vocab_box_html}', new_html, count=1, flags=re.I)
                elif re.search(r'</h2>', new_html, flags=re.I):
                    new_html = re.sub(r'(</h2>)', lambda m: f'{m.group(1)}\n{vocab_box_html}', new_html, count=1, flags=re.I)
                elif re.search(r'<body\b[^>]*>', new_html, flags=re.I):
                    new_html = re.sub(r'(<body\b[^>]*>)', lambda m: f'{m.group(1)}\n{vocab_box_html}', new_html, count=1, flags=re.I)

            transformed_files[ch_path] = new_html.encode('utf-8')

        output_epub.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_epub, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                fn = item.filename
                fn_low = fn.lower()
                if fn_low.endswith('kobo.js') or fn_low.endswith('kobo.css'):
                    continue
                if fn == 'mimetype':
                    zout.writestr(item, zin.read(fn), compress_type=zipfile.ZIP_STORED)
                elif fn in transformed_files:
                    zout.writestr(item, transformed_files[fn])
                elif fn_low.endswith('.opf'):
                    opf_text = zin.read(fn).decode('utf-8', errors='replace')
                    opf_text = update_opf_metadata(opf_text, '[Progressive Deutsch]', force_de_lang=True)
                    zout.writestr(item, opf_text.encode('utf-8'))
                elif fn_low.endswith(('.xhtml', '.html', '.htm')):
                    raw_other = zin.read(fn).decode('utf-8', errors='replace')
                    cleaned_other = strip_kobo_kepub_wrappers(raw_other)
                    zout.writestr(item, cleaned_other.encode('utf-8'))
                else:
                    zout.writestr(item, zin.read(fn))

    book_slug = clean_book_slug(input_epub.name)
    txt_files = []
    if export_txt_lists:
        txt_files = write_en_vocab_txt_stacks(
            book_slug=book_slug,
            output_dir=output_epub.parent,
            unlocked_sequence=unlocked_sequence,
            stack_size=words_per_txt_list,
            export_anki=export_anki,
        )

    result = {
        "book_slug": book_slug,
        "output_epub": str(output_epub),
        "chapters": len(chapter_files),
        "unlocked_words": len(unlocked_ids),
        "level": lvl_label,
        "total_replacements": sum(encounter_counts.values()),
        "txt_files": [p.name for p in txt_files],
        "txt_folder": str(output_epub.parent / f"{book_slug}_Vocab_Lists") if txt_files else "",
    }
    print(f"[EN -> DE Done] {output_epub.name} | Level {lvl_label} | {result['unlocked_words']} words | {result['total_replacements']} inline replacements")
    return result


def transform_de_to_b1_assisted(
    input_epub: Path,
    output_epub: Path,
    max_hints_per_word: int = 3,
    user_level: str = "B2",
    show_chapter_box: bool = True,
    export_txt_lists: bool = True,
    words_per_txt_list: int = 50,
    max_thematic_lists: int = 4,
    export_anki: bool = False,
    known_words: set = None,
):
    max_hints_per_word = max(1, min(10, int(max_hints_per_word)))
    words_per_txt_list = max(5, min(200, int(words_per_txt_list)))
    max_thematic_lists = max(1, min(8, int(max_thematic_lists)))
    known_words = known_words or set()
    valid_levels = allowed_levels(user_level)
    lvl_label = level_display_label(user_level)

    exact_lookup = {
        k: format_gloss_clean(v)
        for k, v in DE_HARD_GLOSSES.items()
        if k.lower() not in known_words and get_de_word_level(k) in valid_levels
    }
    lower_lookup = {k.lower(): (k, v) for k, v in exact_lookup.items()}

    def _try_stem_lookup(wl_sub: str, orig_word: str):
        if wl_sub in lower_lookup:
            canon_de, gloss = lower_lookup[wl_sub]
            if not is_transparent_cognate(orig_word, gloss):
                return wl_sub, canon_de, gloss
        for suf in ('ten', 'tet', 'test', 'te', 'enden', 'ender', 'endes', 'ende', 'end', 'ern', 'en', 'em', 'er', 'es', 'et', 'st', 'e', 'n', 's', 't'):
            if wl_sub.endswith(suf) and len(wl_sub) - len(suf) >= 4:
                stem = wl_sub[:-len(suf)]
                for candidate in (stem, stem + 'en', stem + 'n'):
                    if candidate in lower_lookup:
                        canon_de, gloss = lower_lookup[candidate]
                        if not is_transparent_cognate(orig_word, gloss):
                            return candidate, canon_de, gloss
        return None, None, None

    def lookup_de_word(word: str):
        if word.lower() in known_words:
            return None, None, None
        if word in exact_lookup:
            gloss = exact_lookup[word]
            if not is_transparent_cognate(word, gloss):
                return word.lower(), word, gloss
            return None, None, None
        wl = word.lower()
        k, c_de, g = _try_stem_lookup(wl, word)
        if g:
            return k, c_de, g
        # Try stripping common separable prefixes (e.g. zurückweichen -> weichen, hinabsteigen -> steigen)
        for pref in ('zurück', 'hervor', 'hinab', 'hinauf', 'hinein', 'hinaus', 'zusammen', 'weiter', 'hinunter', 'herunter', 'heraus', 'herein', 'davon', 'daran', 'ein', 'auf', 'aus', 'ab', 'an', 'zu', 'vor', 'nach'):
            if wl.startswith(pref) and len(wl) - len(pref) >= 5:
                sub = wl[len(pref):]
                k, c_de, g = _try_stem_lookup(sub, word)
                if g:
                    return k, c_de, g
        return None, None, None

    with zipfile.ZipFile(input_epub, 'r') as zin:
        chapter_files = detect_story_chapters(zin)

        encounter_counts = Counter()  # Book-wide frequency for thematic .txt lists
        matched_words_info = {}
        transformed_files = {}

        de_word_pattern = re.compile(r'(?<![A-Za-zÄÖÜäöüß\-])([A-Za-zÄÖÜäöüß]{4,})(?![A-Za-zÄÖÜäöüß\-])')

        for ch_idx, ch_path in enumerate(chapter_files, start=1):
            raw_html = strip_previous_bilingual_markup(
                zin.read(ch_path).decode('utf-8', errors='replace')
            )
            if is_front_or_back_matter_html(raw_html):
                transformed_files[ch_path] = raw_html.encode('utf-8')
                continue
            chapter_counts = Counter()  # Per-chapter fade-out counter so every chapter is richly translated!
            chapter_new_words = []
            chapter_seen_keys = set()

            def _gloss_node(text_node: str, _rolling_prev: list) -> str:
                def _repl(match):
                    word = match.group(1)
                    lemma_key, canon_de, gloss = lookup_de_word(word)
                    if not gloss:
                        return word
                    encounter_counts[lemma_key] += 1
                    chapter_counts[lemma_key] += 1
                    if lemma_key not in matched_words_info:
                        matched_words_info[lemma_key] = (canon_de, gloss)

                    # Show inline hint up to `max_hints_per_word` times PER CHAPTER
                    if chapter_counts[lemma_key] <= max_hints_per_word:
                        if encounter_counts[lemma_key] == 1 and lemma_key not in chapter_seen_keys and len(chapter_new_words) < 14:
                            chapter_seen_keys.add(lemma_key)
                            chapter_new_words.append((word, gloss))
                        return f'<span class="bk-de-word">{word}</span> <span class="bk-hint">[{gloss}]</span>'
                    else:
                        return word

                return de_word_pattern.sub(_repl, text_node)

            new_html = walk_and_transform_html(raw_html, _gloss_node)

            if 'bilingualEPUB Styling' not in new_html and re.search(r'</head>', new_html, flags=re.I):
                new_html = re.sub(
                    r'(</head>)',
                    lambda m: f'<style type="text/css">{BILINGUAL_CSS}</style>{m.group(1)}',
                    new_html,
                    count=1,
                    flags=re.I,
                )

            if show_chapter_box and chapter_new_words:
                items_html = " · ".join(f'<b>{w}</b> (<i>{g}</i>)' for w, g in chapter_new_words)
                vocab_box_html = (
                    f'<div class="bk-vocab-box">'
                    f'<div class="bk-vocab-title">📖 Kapitel-Vokabular ({lvl_label} Hilfe — blendet nach {max_hints_per_word}× aus)</div>'
                    f'<div class="bk-vocab-list">{items_html}</div>'
                    f'</div>'
                )
                if re.search(r'</h2>', new_html, flags=re.I):
                    new_html = re.sub(r'(</h2>)', lambda m: f'{m.group(1)}\n{vocab_box_html}', new_html, count=1, flags=re.I)
                elif re.search(r'</h3>', new_html, flags=re.I):
                    new_html = re.sub(r'(</h3>)', lambda m: f'{m.group(1)}\n{vocab_box_html}', new_html, count=1, flags=re.I)
                elif re.search(r'</h1>', new_html, flags=re.I):
                    new_html = re.sub(r'(</h1>)', lambda m: f'{m.group(1)}\n{vocab_box_html}', new_html, count=1, flags=re.I)
                elif re.search(r'<body\b[^>]*>', new_html, flags=re.I):
                    new_html = re.sub(r'(<body\b[^>]*>)', lambda m: f'{m.group(1)}\n{vocab_box_html}', new_html, count=1, flags=re.I)

            transformed_files[ch_path] = new_html.encode('utf-8')

        output_epub.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_epub, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                fn = item.filename
                fn_low = fn.lower()
                if fn_low.endswith('kobo.js') or fn_low.endswith('kobo.css'):
                    continue
                if fn == 'mimetype':
                    zout.writestr(item, zin.read(fn), compress_type=zipfile.ZIP_STORED)
                elif fn in transformed_files:
                    zout.writestr(item, transformed_files[fn])
                elif fn_low.endswith('.opf'):
                    opf_text = zin.read(fn).decode('utf-8', errors='replace')
                    opf_text = update_opf_metadata(opf_text, f'[{user_level.upper()}-Assisted]', force_de_lang=False)
                    zout.writestr(item, opf_text.encode('utf-8'))
                elif fn_low.endswith(('.xhtml', '.html', '.htm')):
                    raw_other = zin.read(fn).decode('utf-8', errors='replace')
                    cleaned_other = strip_kobo_kepub_wrappers(raw_other)
                    zout.writestr(item, cleaned_other.encode('utf-8'))
                else:
                    zout.writestr(item, zin.read(fn))

    book_slug = clean_book_slug(input_epub.name)
    txt_files = []
    if export_txt_lists:
        txt_files = write_de_thematic_txt_lists(
            book_slug=book_slug,
            output_dir=output_epub.parent,
            matched_words_info=matched_words_info,
            encounter_counts=encounter_counts,
            max_lists=max_thematic_lists,
            words_per_list=words_per_txt_list,
            export_anki=export_anki,
        )

    result = {
        "book_slug": book_slug,
        "output_epub": str(output_epub),
        "chapters": len(chapter_files),
        "unlocked_words": len(encounter_counts),
        "level": lvl_label,
        "total_replacements": sum(encounter_counts.values()),
        "txt_files": [p.name for p in txt_files],
        "txt_folder": str(output_epub.parent / f"{book_slug}_Vocab_Lists") if txt_files else "",
    }
    print(f"[DE -> DE+ Done] {output_epub.name} | Level {lvl_label} | {result['unlocked_words']} words | {result['total_replacements']} inline hints")
    return result


if __name__ == "__main__":
    workspace = Path(__file__).parent
    folders = ensure_folders(workspace)
    known = load_known_words(workspace)

    for epub in sorted(folders["in_en"].glob("*.epub")):
        slug = clean_book_slug(epub.name)
        out_path = folders["out_en"] / f"{slug}_Progressive_DE.epub"
        transform_en_to_progressive_de(
            epub, out_path, words_per_chapter=10, user_level="B2", words_per_txt_list=50, known_words=known
        )

    for epub in sorted(folders["in_de"].glob("*.epub")):
        slug = clean_book_slug(epub.name)
        out_path = folders["out_de"] / f"{slug}_B2_Assisted.epub"
        transform_de_to_b1_assisted(
            epub, out_path, max_hints_per_word=3, user_level="B2", words_per_txt_list=50, max_thematic_lists=4, known_words=known
        )
