# -*- coding: utf-8 -*-
"""
bilingualEPUB Core Engine & CLI/UI Backend (v5)
===============================================
Updates in v5:
1. Clean `word : translation` .txt format (no headers, no numbering, no chapter dividers)
   ready to feed directly into external flashcard/learning tools:
       das Gewehr : rifle
       stürzte : collapsed, fell
2. Configurable `words_per_txt_list` (10..100, default 50) and `max_thematic_lists` (1..8, default 4).
3. `user_level` ("B1", "B2", "C1") piped to BOTH Mode 1 (EN -> DE) and Mode 2 (DE -> DE+).
"""

import zipfile
import re
import difflib
from pathlib import Path
from collections import Counter
from vocab_data import (
    EN_TO_DE_VOCAB,
    DE_HARD_GLOSSES,
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
}

AMBIGUOUS_EN_NOUNS = {
    "light", "lights", "mind", "minds", "hand", "hands", "face", "faces",
    "head", "heads", "arm", "arms", "shoulder", "shoulders", "back", "backs",
    "step", "steps", "footstep", "footsteps", "turn", "turns", "look", "looks",
    "glance", "glances", "gaze", "gazes", "smile", "smiles", "whisper", "whispers",
    "scream", "screams", "sigh", "sighs", "groan", "groans", "fight", "fights",
    "attack", "attacks", "escape", "escapes", "rescue", "rescues", "test", "tests",
    "order", "orders", "rule", "rules", "plan", "plans", "force", "forces",
    "power", "powers", "place", "places", "room", "rooms", "water", "fire", "fires",
    "rain", "snow", "wind", "storm", "dust", "smoke", "blood", "sweat", "tear", "tears",
    "wound", "wounds", "scar", "scars", "fear", "fears", "dread", "panic", "hate",
    "love", "hope", "hopes", "trust", "doubt", "doubts", "dream", "dreams", "sleep",
    "promise", "promises", "lie", "lies", "question", "questions", "answer", "answers",
    "name", "names", "word", "words", "sign", "signs", "mark", "marks", "lock", "locks",
    "trap", "traps", "target", "targets", "guard", "guards", "master", "masters",
    "camp", "camps", "base", "bases", "corner", "corners", "edge", "edges",
    "bridge", "mirror", "mirrors", "book", "books", "page", "pages", "map", "maps",
    "picture", "pictures", "image", "images", "ring", "rings", "coat", "coats",
    "dress", "dresses", "shield", "shields", "poison", "poisons", "taste", "smell",
    "scent", "sound", "sounds", "noise", "silence", "touch", "sense", "senses",
    "feeling", "feelings", "thought", "thoughts", "memory", "memories",
    "choice", "end", "ends", "beginning", "gift", "gifts", "rock", "rocks",
    "stone", "stones", "ground", "land", "earth", "supply", "supplies", "exchange",
    "hint", "hints", "strap", "straps", "regret", "regrets", "curse", "curses",
    "attempt", "attempts", "challenge", "challenges", "access", "trigger", "triggers",
    "decoy", "circle", "circles", "detail", "details", "desire", "pressure",
    "wave", "waves", "stream", "streams", "spark", "sparks", "bruise", "bruises",
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


def strip_tags(html_str: str) -> str:
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', html_str, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    return text


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
    """Ensures slashes become clean comma-spaces: 'collapsed/fell' -> 'collapsed, fell'."""
    return re.sub(r'\s*/\s*', ', ', gloss.strip())


def write_en_vocab_txt_stacks(
    book_slug: str,
    output_dir: Path,
    unlocked_sequence: list,
    stack_size: int = 50,
    export_anki: bool = False,
) -> list:
    """
    Writes .txt files in stacks of `stack_size` words:
      <BookSlug>_1.txt, <BookSlug>_2.txt, ...
    Format inside each .txt file (strictly one pair per line, no headers or chapter dividers):
      das Gewehr : rifle
      der Blick : gaze
    """
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
    """
    For German books: generates up to `max_lists` (1..8) thematic .txt lists
    of `words_per_list` (10..100) words each.
    Format inside each .txt file (strictly `word : translation`, one per line):
      Dolch : dagger
      stürzte : collapsed, fell
    """
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
        clean_g = format_gloss_clean(gloss)
        if clean_g in seen_glosses:
            continue
        seen_glosses.add(clean_g)
        gloss_tokens = set(re.findall(r'[a-z]+', clean_g.lower()))

        placed = False
        for theme_key, kw_set in DE_THEME_KEYWORDS.items():
            if gloss_tokens & kw_set:
                themed_buckets[theme_key].append((de_disp, clean_g))
                placed = True
                break
        if not placed:
            themed_buckets["8_Narrative_&_Modifiers"].append((de_disp, clean_g))

    ordered_themes = sorted(
        [(k, items) for k, items in themed_buckets.items() if items],
        key=lambda x: len(x[1]),
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


def detect_story_chapters(namelist: list) -> list:
    for pattern in (r'c\d+.*\.xhtml$', r'part_\d+\.xhtml$', r'ch(?:ap(?:ter)?)?[_\-]?\d+.*\.x?html$'):
        matches = sorted([n for n in namelist if re.search(pattern, n, flags=re.I)])
        if len(matches) >= 3:
            return matches
    skip_re = re.compile(r'(cover|toc|nav|copy|title|ack|ded|front|back)', re.I)
    htmls = sorted([n for n in namelist if n.endswith(('.xhtml', '.html', '.htm'))])
    filtered = [n for n in htmls if not skip_re.search(Path(n).name)]
    return filtered if filtered else htmls


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
    """
    Mode 1: Converts an English EPUB into a Progressive German Ramp-Up EPUB
    filtered by `user_level` ("B1", "B2", "C1"), and generates .txt stacks.
    """
    words_per_chapter = max(1, min(30, int(words_per_chapter)))
    hint_max_encounters = max(1, min(10, int(hint_max_encounters)))
    words_per_txt_list = max(5, min(200, int(words_per_txt_list)))
    known_words = known_words or set()
    valid_levels = allowed_levels(user_level)
    lvl_label = level_display_label(user_level)

    primary_pool = [
        e for e in EN_TO_DE_VOCAB
        if e.get("level", "B2") in valid_levels
        and e["id"].lower() not in known_words
        and e["base_de"].lower() not in known_words
    ]
    if user_level.upper() == "C1":
        fallback_pool = [
            e for e in EN_TO_DE_VOCAB
            if e.get("level", "B2") == "B2"
            and e["id"].lower() not in known_words
            and e["base_de"].lower() not in known_words
        ]
    else:
        fallback_pool = []
    vocab_pool = primary_pool + fallback_pool

    with zipfile.ZipFile(input_epub, 'r') as zin:
        namelist = zin.namelist()
        chapter_files = detect_story_chapters(namelist)

        unlocked_ids = set()
        unlocked_base_de = set()
        unlocked_sequence = []
        active_forms = {}
        encounter_counts = Counter()
        transformed_files = {}

        for ch_idx, ch_path in enumerate(chapter_files, start=1):
            raw_html = zin.read(ch_path).decode('utf-8', errors='replace')
            plain_text = strip_tags(raw_html)

            tokens = re.findall(r'\b[a-z]{3,}\b', plain_text)
            token_counts = Counter(tokens)

            candidates = []
            seen_cand_base_de = set()
            for entry in vocab_pool:
                eid = entry["id"]
                bde = entry["base_de"]
                if eid in unlocked_ids or bde in unlocked_base_de or bde in seen_cand_base_de:
                    continue
                freq = sum(token_counts[f] for f in entry["forms"])
                if freq >= 1:
                    seen_cand_base_de.add(bde)
                    is_primary = 1 if entry.get("level", "B2") in valid_levels else 0
                    candidates.append((is_primary, freq, entry))

            candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            newly_unlocked = [entry for _, _, entry in candidates[:words_per_chapter]]

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

            def replace_in_text_node(text_node: str) -> str:
                if not word_pattern or not text_node.strip():
                    return text_node

                def _repl(match):
                    word = match.group(1)
                    if word not in active_forms:
                        return word
                    entry, de_form = active_forms[word]
                    eid = entry["id"]
                    gender = entry["gender"]

                    prefix = text_node[:match.start()]
                    prev_words = re.findall(r"[A-Za-z']+", prefix)
                    prev_w = prev_words[-1].lower().rstrip("'") if prev_words else ""

                    if gender in ("der", "die", "das"):
                        if prev_w in VERB_PRECEDERS:
                            return word
                        if word in AMBIGUOUS_EN_NOUNS and prev_w not in NOUN_PRECEDERS:
                            return word

                    encounter_counts[eid] += 1
                    cnt = encounter_counts[eid]

                    if cnt <= hint_max_encounters and not is_transparent_cognate(de_form, word):
                        return f'<span class="bk-de-word">{de_form}</span> <span class="bk-hint">[{format_gloss_clean(entry["meaning"])}]</span>'
                    else:
                        return f'<span class="bk-de-word">{de_form}</span>'

                return word_pattern.sub(_repl, text_node)

            def process_paragraph(p_match):
                p_open = p_match.group(1)
                p_inner = p_match.group(2)
                p_close = p_match.group(3)
                parts = re.split(r'(<[^>]+>|&[a-zA-Z0-9#]+;)', p_inner)
                for i in range(0, len(parts), 2):
                    parts[i] = replace_in_text_node(parts[i])
                return p_open + "".join(parts) + p_close

            new_html = re.sub(r'(<p\b[^>]*>)(.*?)(</p>)', process_paragraph, raw_html, flags=re.S)

            if '</head>' in new_html:
                new_html = new_html.replace('</head>', f'<style type="text/css">{BILINGUAL_CSS}</style></head>', 1)

            new_html = re.sub(r'lang="en(?:-[A-Za-z]+)?"', 'lang="de"', new_html)

            if show_chapter_box and newly_unlocked:
                items_html = " · ".join(
                    f'<b>{e["base_de"]}</b> (<i>{format_gloss_clean(e["meaning"])}</i>)' for e in newly_unlocked
                )
                vocab_box_html = (
                    f'<div class="bk-vocab-box">'
                    f'<div class="bk-vocab-title">🇩🇪 Kapitel {ch_idx}: +{len(newly_unlocked)} neue {lvl_label}-Wörter '
                    f'(Gesamt aktiv: {len(unlocked_ids)})</div>'
                    f'<div class="bk-vocab-list">{items_html}</div>'
                    f'</div>'
                )
                if '</h1>' in new_html:
                    new_html = new_html.replace('</h1>', '</h1>\n' + vocab_box_html, 1)
                elif '</h2>' in new_html:
                    new_html = new_html.replace('</h2>', '</h2>\n' + vocab_box_html, 1)
                elif '<body' in new_html:
                    new_html = re.sub(r'(<body[^>]*>)', r'\1\n' + vocab_box_html, new_html, count=1)

            transformed_files[ch_path] = new_html.encode('utf-8')

        output_epub.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_epub, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                fn = item.filename
                if fn == 'mimetype':
                    zout.writestr(item, zin.read(fn), compress_type=zipfile.ZIP_STORED)
                elif fn in transformed_files:
                    zout.writestr(item, transformed_files[fn])
                elif fn.endswith('.opf'):
                    opf_text = zin.read(fn).decode('utf-8', errors='replace')
                    opf_text = re.sub(r'<dc:language>.*?</dc:language>', '<dc:language>de</dc:language>', opf_text)
                    opf_text = re.sub(
                        r'<dc:title>(.*?)</dc:title>',
                        r'<dc:title>\1 [Progressive Deutsch]</dc:title>',
                        opf_text,
                        count=1
                    )
                    zout.writestr(item, opf_text.encode('utf-8'))
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
    print(f"[EN -> DE Done] {output_epub.name} | Level {lvl_label} | {result['unlocked_words']} words | {len(txt_files)} .txt files")
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
    """
    Mode 2: Takes an original German EPUB, adds fading inline English hints for
    vocabulary matching `user_level` ("B1" -> B1/B2/C1, "B2" -> B2/C1, "C1" -> C1),
    and generates up to `max_thematic_lists` thematic .txt lists of `words_per_txt_list` words!
    """
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

    def lookup_de_word(word: str):
        if word.lower() in known_words:
            return None, None, None
        if word in exact_lookup:
            gloss = exact_lookup[word]
            if not is_transparent_cognate(word, gloss):
                return word.lower(), word, gloss
            return None, None, None
        wl = word.lower()
        if wl in lower_lookup:
            canon_de, gloss = lower_lookup[wl]
            if not is_transparent_cognate(word, gloss):
                return wl, canon_de, gloss
            return None, None, None
        for suf in ('en', 'em', 'er', 'es', 'e', 'n', 's'):
            if wl.endswith(suf) and len(wl) - len(suf) >= 4:
                stem = wl[:-len(suf)]
                if stem in lower_lookup:
                    canon_de, gloss = lower_lookup[stem]
                    if not is_transparent_cognate(word, gloss):
                        return stem, canon_de, gloss
                    return None, None, None
        return None, None, None

    with zipfile.ZipFile(input_epub, 'r') as zin:
        namelist = zin.namelist()
        chapter_files = detect_story_chapters(namelist)

        encounter_counts = Counter()
        matched_words_info = {}
        transformed_files = {}

        de_word_pattern = re.compile(r'(?<![A-Za-zÄÖÜäöüß\-])([A-Za-zÄÖÜäöüß]{4,})(?![A-Za-zÄÖÜäöüß\-])')

        for ch_idx, ch_path in enumerate(chapter_files, start=1):
            raw_html = zin.read(ch_path).decode('utf-8', errors='replace')
            chapter_new_words = []
            chapter_seen_keys = set()

            def gloss_text_node(text_node: str) -> str:
                if not text_node.strip():
                    return text_node

                def _repl(match):
                    word = match.group(1)
                    lemma_key, canon_de, gloss = lookup_de_word(word)
                    if not gloss:
                        return word
                    encounter_counts[lemma_key] += 1
                    if lemma_key not in matched_words_info:
                        matched_words_info[lemma_key] = (canon_de, gloss)
                    cnt = encounter_counts[lemma_key]
                    if cnt <= max_hints_per_word:
                        if cnt == 1 and lemma_key not in chapter_seen_keys and len(chapter_new_words) < 14:
                            chapter_seen_keys.add(lemma_key)
                            chapter_new_words.append((word, gloss))
                        return f'<span class="bk-de-word">{word}</span> <span class="bk-hint">[{gloss}]</span>'
                    else:
                        return word

                return de_word_pattern.sub(_repl, text_node)

            def process_paragraph(p_match):
                p_open = p_match.group(1)
                p_inner = p_match.group(2)
                p_close = p_match.group(3)
                parts = re.split(r'(<[^>]+>|&[a-zA-Z0-9#]+;)', p_inner)
                for i in range(0, len(parts), 2):
                    parts[i] = gloss_text_node(parts[i])
                return p_open + "".join(parts) + p_close

            new_html = re.sub(r'(<p\b[^>]*>)(.*?)(</p>)', process_paragraph, raw_html, flags=re.S)

            if '</head>' in new_html:
                new_html = new_html.replace('</head>', f'<style type="text/css">{BILINGUAL_CSS}</style></head>', 1)

            if show_chapter_box and chapter_new_words:
                items_html = " · ".join(f'<b>{w}</b> (<i>{g}</i>)' for w, g in chapter_new_words)
                vocab_box_html = (
                    f'<div class="bk-vocab-box">'
                    f'<div class="bk-vocab-title">📖 Kapitel-Vokabular ({lvl_label} Hilfe — blendet nach {max_hints_per_word}× aus)</div>'
                    f'<div class="bk-vocab-list">{items_html}</div>'
                    f'</div>'
                )
                if '</h2>' in new_html:
                    new_html = new_html.replace('</h2>', '</h2>\n' + vocab_box_html, 1)
                elif '</h3>' in new_html:
                    new_html = new_html.replace('</h3>', '</h3>\n' + vocab_box_html, 1)
                elif '</h1>' in new_html:
                    new_html = new_html.replace('</h1>', '</h1>\n' + vocab_box_html, 1)
                elif '<body' in new_html:
                    new_html = re.sub(r'(<body[^>]*>)', r'\1\n' + vocab_box_html, new_html, count=1)

            transformed_files[ch_path] = new_html.encode('utf-8')

        output_epub.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_epub, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                fn = item.filename
                if fn == 'mimetype':
                    zout.writestr(item, zin.read(fn), compress_type=zipfile.ZIP_STORED)
                elif fn in transformed_files:
                    zout.writestr(item, transformed_files[fn])
                elif fn.endswith('.opf'):
                    opf_text = zin.read(fn).decode('utf-8', errors='replace')
                    opf_text = re.sub(
                        r'<dc:title>(.*?)</dc:title>',
                        f'\\1 [{user_level.upper()}-Assisted]',
                        opf_text,
                        count=1
                    )
                    zout.writestr(item, opf_text.encode('utf-8'))
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
    print(f"[DE -> DE+ Done] {output_epub.name} | Level {lvl_label} | {result['unlocked_words']} words | {len(txt_files)} .txt files")
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
