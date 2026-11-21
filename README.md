# <img src="favicon.svg" width="34" valign="middle" /> bilingualEPUB

**Progressive German Diglot-Weave & B1/B2/C1 Assisted EPUB Generator for All E-Readers (Kobo, Kindle, PocketBook, Tolino, KOReader)**

**bilingualEPUB** transforms standard English or German `.epub` books into low-friction, context-driven German learning books optimized for **any e-reader**, complete with customizable **`word : translation` `.txt` vocabulary stacks**!

---

## 2 Learning Modes

### 1. `EN ➔ DE` Mode 1: English Books (`Progressive German Weave`)
* **Progressive Ramp-Up:** Unlocks **5 to 30 new German words per chapter** (default: `10`), chosen from B1/B2/C1 words that actually appear in that chapter.
* **Permanent Immersion:** Once a word is unlocked in Chapter $N$, it stays German for **the entire rest of the book**.
* **Whisper-Thin Fading Training Wheels:**
  * **First 2 encounters:** `Dunkelheit [darkness]` (normal font weight for the German word so it doesn't break eye flow, paired with a small, thin, faded-gray inline translation).
  * **3rd encounter onward:** `Dunkelheit` (the inline hint disappears permanently so your brain retains the word effortlessly).
* **Automatic E-Reader German Dictionary Trick:** Automatically switches the EPUB metadata (`<dc:language>de</dc:language>`) so **long-pressing any German word on your e-reader opens your built-in German dictionary automatically**.
* **Customizable `.txt` Stacks:** Automatically generates numbered `.txt` files in stacks of `N` words (default `50`: `BookName_1.txt`, `BookName_2.txt`, ...) in clean `das Gewehr : rifle` format.

### 2. `DE ➔ DE+` Mode 2: German Books (`B1/B2/C1 Assisted Reader`)
* **100% Authentic German Text:** Keeps the original German text intact while filtering out A1/A2 basics and transparent English/French cognates (*Soldat, Gnomen, Tempel, Kamera, etc.*).
* **Fading Inline Glosses by CEFR Level (`B1` / `B2` / `C1`):** Adds a subtle inline translation (`zerbarst [shattered]`) for the first **3 encounters** of vocabulary matching your chosen CEFR level, then fades away.
* **Thematic `.txt` Lists (`1` to `8` Lists × `N` Words):** Automatically extracts the book's most important vocabulary into thematic `.txt` lists (`Weapons & Combat`, `Fantasy & Magic`, `Action & Movement`, `Mind & Emotion`, `Body & Senses`, `World & Nature`, `Society & Intrigue`, `Narrative & Modifiers`) in clean `stürzte : collapsed, fell` format.

---

## 📁 Folder Structure

```text
bilingualEPUB/
├── Launch_bilingualEPUB.bat      # Double-click on Windows to open the Studio UI
├── launch_bilingualEPUB.sh       # Run on macOS / Linux to open the Studio UI
├── app.py                        # Local Black & Deep-Purple Web Studio UI
├── bilingual_epub.py             # Core EPUB processor & .txt stack generator
├── vocab_data.py                 # Categorized B1/B2/C1 vocabulary database
├── favicon.svg                   # Minimalist purple rune-book icon
├── known_words.txt               # Your personal ignore-list of already mastered words
├── Input_English_Books/          # Drop English .epub books here (or drag into UI)
├── Input_German_Books/           # Drop German .epub books here (or drag into UI)
├── Output_English_Augmented/     # Converted [Progressive Deutsch] EPUBs + .txt stacks
└── Output_German_Augmented/      # Converted [Assisted] EPUBs + thematic .txt lists
```

---

## Quick Start (Windows, macOS & Linux)

1. **Zero Dependencies:** Uses only Python 3's standard library—works out of the box on **Windows, macOS, and Linux**.
2. **Launch the UI:**
   * **Windows:** Double-click `Launch_bilingualEPUB.bat` (or run `python app.py`).
   * **macOS / Linux:** Run `./launch_bilingualEPUB.sh` (or `python3 app.py`).
3. **Drop Your Books:** Drag and drop your English or German `.epub` files into the left (`EN ➔ DE`) or right (`DE ➔ DE+`) panel, adjust your level (`B1 / B2 / C1`) and sliders, and click **Convert**.
