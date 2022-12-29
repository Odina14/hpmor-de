#!/usr/bin/env python3
# by Torben Menke https://entorb.net
"""
Check chapter .tex files for known issues and propose fixes.

reads hpmor.tex for list of uncommented/relevant/e.g. translated) chapter files
ignores all lines starting with '%'
improvements are proposed via chapters/*-autofix.tex files
configuration in check-chapters.json
lang: EN, DE, FR, ...
raise_error: true -> script exits with error, used for autobuild of releases
print_diff: true : print line of issues
"""
import difflib
import json
import re
from multiprocessing import Pool, cpu_count
from os import chdir
from pathlib import Path

# ensure we are in hpmor root dir
# dir_root = os.path.dirname(sys.argv[0]) + "/.."
chdir(Path(__file__).parents[1])
assert Path("./chapters").is_dir()


# pos lookahead: (?=...)
# neg lookahead: (?!...)
# pos lookbehind (?<=...)
# neg lookbehind (?<!...)

# in EN the quotations are “...” and ‘...’ (for quotations in quotations)
# in DE the quotations are „...“ and ‚...‘ (for quotations in quotations)


# TODO:
# \latersection must be at newline
# add \spell macro

# TO chars manually find and replace
# *, ", ', », «, ”,

# continue sentence in lower case
# (,“[^„]+„)([A-Z]) -> \1\l\2

# shall we modify the source file?
# USE WITH CAUTION!!!
inline_fixing = False
# inline_fixing = True


# read settings from check-chapters.json
with open(
    Path("scripts/check-chapters.json"),
    encoding="utf-8",
) as fh_settings:
    settings = json.load(fh_settings)


def get_list_of_chapter_files() -> list[Path]:
    """
    Read hpmor.tex, extract list of (not-commented out) chapter files.

    returns list of filesnames
    """
    list_of_files: list[Path] = []
    with open("hpmor.tex", encoding="utf-8") as fh:
        for line in fh.readlines():
            my_match = re.search(r"^.*include\{(chapters/.+?)\}.*$", line)
            if my_match:
                include_path = my_match.group(1)
                p = Path(include_path + ".tex")
                assert p.is_file()
                list_of_files.append(p)
    return list_of_files


def process_file(file_in: Path) -> bool:
    """
    Check file for known issues.

    returns issues_found = True if we have a finding
    a proposed fix is written to chapters/*-autofix.tex
    """
    # print(file_in.name)
    issues_found = False
    cont = file_in.read_text(encoding="utf-8")

    # end of line: LF only
    if "\r" in cont:
        issues_found = True
        cont = re.sub(r"\r\n?", r"\n", cont)
    # invisible strange spaces
    if " " in cont:
        issues_found = True
        cont = re.sub(r" +", r" ", cont)

    # more than 1 empty line
    if "\n\n\n" in cont:
        issues_found = True
        cont = re.sub(r"\n\n\n+", r"\n\n", cont)

    # now split per line
    cont_lines_orig = cont.split("\n")
    del cont
    cont_lines_new: list[str] = []
    for line in cont_lines_orig:
        line_orig = line
        # keep commented-out lines as they are
        if re.match(r"^\s*%", line):
            cont_lines_new.append(line)
        else:
            # check not commented-out lines
            line = fix_line(s=line)
            cont_lines_new.append(line)
            if issues_found is False and line_orig != line:
                issues_found = True
    if issues_found:
        # write proposal to *-autofix.tex
        print(" issues found!")
        file_out = file_in.parent / (file_in.stem + "-autofix.tex")

        # USE WITH CAUTION!!!
        if inline_fixing:
            file_out = file_in
            issues_found = False

        with open(file_out, mode="w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(cont_lines_new))

        if settings["print_diff"]:
            with open(file_in, encoding="utf-8") as file1, open(
                file_out,
                encoding="utf-8",
            ) as file2:
                diff = difflib.ndiff(file1.readlines(), file2.readlines())
            delta = "".join(l for l in diff if l.startswith("+ ") or l.startswith("- "))
            print(file_in.name + "\n" + delta)

    return issues_found


def fix_line(s: str) -> str:
    """
    Apply all fix functions on a line.
    """
    # simple and safe
    s = fix_spaces(s)
    s = fix_latex(s)
    s = fix_dots(s)
    s = fix_MrMrs(s)
    s = fix_numbers(s)
    s = fix_common_typos(s)
    s = fix_spaces(s)

    # advanced stuff
    s = fix_quotations(s)
    s = fix_emph(s)
    s = fix_hyphens(s)

    # add spell macro
    if settings["lang"] == "DE":
        s = fix_spell(s)

    # spaces, again
    s = fix_spaces(s)
    return s


def fix_spaces(s: str) -> str:
    # tabs to space
    s = re.sub(r"\t+", " ", s)
    # trailing spaces
    s = re.sub(r" +$", "", s)
    # remove spaces from empty lines
    s = re.sub(r"^\s+$", "", s)
    # multiple spaces (excluding start of new line)
    s = re.sub(r"(?<!^)  +", " ", s)
    return s


assert fix_spaces("tabs\tto\t\tspace") == "tabs to space"
assert fix_spaces("trailing spaces  ") == "trailing spaces"
assert fix_spaces("  ") == ""
assert fix_spaces("multiple  spaces") == "multiple spaces"
# rewrite using pytest
if __debug__:
    import pytest

    @pytest.mark.parametrize(
        "text, expected_output",
        (
            ("tabs\tto\t\tspace", "tabs to space"),
            ("trailing spaces  ", "trailing spaces"),
            ("  ", ""),
            ("multiple  spaces", "multiple spaces"),
        ),
    )
    def test_fix_spaces(text: str, expected_output: str) -> None:
        assert fix_spaces(s=text) == expected_output, fix_spaces(s=text)


def fix_latex(s: str) -> str:
    # Latex: \begin and \end{...} at new line
    s = re.sub(r"([^\s%]+)\s*\\(begin|end)\{", r"\1\n\\\2{", s)
    # Latex: \\ not followed by text
    s = re.sub(r"\\\\\s*(?!($|\[|%))", r"\\\\\n", s)
    return s


assert fix_latex("begin at new line\\begin{em}") == "begin at new line\n\\begin{em}"
assert fix_latex("end at new line\\end{em}") == "end at new line\n\\end{em}"
assert fix_latex("new line after \\\\ asdf") == "new line after \\\\\nasdf"
assert fix_latex("no new line after \\\\") == "no new line after \\\\"


def fix_dots(s: str) -> str:
    # ... -> …
    s = s.replace("...", "…")
    # ... with spaces around
    s = s.replace(" … ", "…")
    # NOT '… ' as in ', no… “I'
    # s = re.sub(r" *… *", r"…", s)
    # … at start of line
    s = re.sub(r"^ *… *", r"…", s)
    # … at end of line
    s = re.sub(r" *… *$", r"…", s)
    # before comma
    s = s.replace(" …,", "…,")

    if settings["lang"] == "EN":
        # … at end of quotation ' …"' -> '…"'
        s = s.replace(" …”", "…”")
        # "… " but not before “
        s = re.sub(r"… (?!“)", r"…", s)
        # " …" but after punctuation
        s = re.sub(r"(?<!(%|,|\.|!|\?|:)) …", r"…", s)  # … at start of line
    if settings["lang"] == "DE":
        # … at end of quotation ' …"' -> '…"'
        s = s.replace(" …“", "…“")
        # "… " but not before „
        s = re.sub(r"… (?!„)", r"…", s)
        # " …" but after punctuation
        s = re.sub(r"(?<!(%|,|\.|!|\?|:)) …", r"…", s)
    #  keep space between . or , and …
    s = re.sub(r"([,\.!\?])…", r"\1 …", s)

    return s


assert fix_dots("bad...dots") == "bad…dots"
assert fix_dots("bad … dots") == "bad…dots"
assert fix_dots("bad.…dots") == "bad. …dots"
assert fix_dots("bad. …dots") == "bad. …dots"
assert fix_dots("bad, …dots") == "bad, …dots"
assert fix_dots("bad! …dots") == "bad! …dots"
assert fix_dots("bad? …dots") == "bad? …dots"
assert fix_dots(" … dots") == "…dots"
assert fix_dots("some … ") == "some…"

if settings["lang"] == "DE":
    assert fix_dots("bad… dots") == "bad…dots"
    assert fix_dots("bad… „dots") == "bad… „dots"


def fix_MrMrs(s: str) -> str:
    # Mr / Mrs
    s = s.replace("Mr. H. Potter", "Mr~H.~Potter")
    # s = s.replace("Mr. Potter", "Mr~Potter")
    if settings["lang"] == "DE":
        s = re.sub(r"\b(Mr|Mrs|Miss|Dr)\b\.?\s+(?!”)", r"\1~", s)
    # Dr.~ -> Dr~Potter
    s = re.sub(r"\b(Mr|Mrs|Miss|Dr)\b\.~", r"\1~", s)
    # "Dr. " -> "Dr~"
    # s = re.sub(r"\b(Dr)\b\.?~?\s*", r"\1~", s)
    # s = s.replace("Mr~and Mrs~", "Mr and Mrs~")
    return s


assert fix_MrMrs("Mr. H. Potter") == "Mr~H.~Potter"
if settings["lang"] == "DE":
    assert fix_MrMrs("Mr. Potter") == "Mr~Potter"
    assert fix_MrMrs("Mrs. Potter") == "Mrs~Potter"
    assert fix_MrMrs("Miss. Potter") == "Miss~Potter"
    assert fix_MrMrs("Dr. Potter") == "Dr~Potter"
    assert fix_MrMrs("Dr Potter") == "Dr~Potter"
    assert fix_MrMrs("Mr Potter") == "Mr~Potter"
    # assert fix_MrMrs("Mr. and Mrs. Davis") == "Mr and Mrs~Davis"
    assert fix_MrMrs("Mr. and Mrs. Davis") == "Mr~and Mrs~Davis"
assert fix_MrMrs("it’s Doctor now, not Miss.”") == "it’s Doctor now, not Miss.”"


def fix_numbers(s: str) -> str:
    if settings["lang"] == "DE":
        s = re.sub(r"(\d) +(Uhr)", r"\1~\2", s)
    return s


assert fix_numbers("Es ist 12:23 Uhr...") == "Es ist 12:23~Uhr..."


def fix_common_typos(s: str) -> str:
    if settings["lang"] == "DE":
        s = s.replace("Adoleszenz", "Pubertät")
        s = s.replace("Avadakedavra", "Avada Kedavra")
        s = s.replace("Diagon Alley", "Winkelgasse")
        s = s.replace("Hermione", "Hermine")
        s = s.replace("Junge-der-überlebt-hatte", "Junge-der-überlebte")
        s = s.replace("Junge-der-überlebt-hat", "Junge-der-überlebte")
        s = s.replace("Junge, der lebte", "Junge-der-überlebte")
        s = s.replace("Muggelforscher", "Muggelwissenschaftler")
        s = s.replace("Stupefy", "Stupor")
        s = s.replace("Wizengamot", "Zaubergamot")
        s = s.replace("S.P.H.E.W.", r"\SPHEW")
        s = s.replace("ut mir Leid", "ut mir leid")
        # s = s.replace("das einzige", "das Einzige")
    # Apostroph
    # "word's"
    s = re.sub(r"(\w)'(s)\b", r"\1’\2", s)
    if settings["lang"] == "DE":
        s = re.sub(r"(\w)'(sche|scher|schen)\b", r"\1’\2", s)
    if settings["lang"] == "EN":
        # "wouldn't"
        s = re.sub(r"(\w)'(t)\b", r"\1’\2", s)
        # I'm
        s = re.sub(r"\bI'm\b", r"I’m", s)

    return s


assert (fix_common_typos("Test Mungo's King's Cross")) == "Test Mungo’s King’s Cross"
assert (fix_common_typos("Junge-der-überlebt-hat")) == "Junge-der-überlebte"
if settings["lang"] == "DE":
    assert (fix_common_typos("Fritz'sche Gesetz")) == "Fritz’sche Gesetz"
    assert (fix_common_typos("Fritz'schen Gesetz")) == "Fritz’schen Gesetz"
    assert (fix_common_typos("Fritz'scher Gesetz")) == "Fritz’scher Gesetz"
if settings["lang"] == "EN":
    assert (fix_common_typos("I'm happy")) == "I’m happy"
    assert (fix_common_typos("can't be")) == "can’t be"


def fix_quotations(s: str) -> str:
    # in EN the quotations are “...” and ‘...’ (for quotations in quotations)
    # in DE the quotations are „...“ and ‚...‘ (for quotations in quotations)

    # TODO: add tests

    # "..." -> “...”
    if settings["lang"] == "EN":
        s = re.sub(r'"([^"]+)"', r"“\1”", s)
    if settings["lang"] == "DE":
        s = re.sub(r'"([^"]+)"', r"„\1“", s)

    # '...' -> ‘...’
    if "nglui mglw" not in s:
        if settings["lang"] == "EN":
            s = re.sub(r"'([^']+)'", r"‘\1’", s)
        if settings["lang"] == "DE":
            s = re.sub(r"'([^']+)'", r"‚\1‘", s)

    if settings["lang"] == "DE":
        # fix bad single word quotes
        # ’Ja‘ -> ‚Ja‘
        s = re.sub(r"’([^ ]+?)‘", r"‚\1‘", s)
        # migrate EN quotations
        s = re.sub(r"“([^“”]+?)”", r"„\1“", s)
        # migrate EN single quotations
        s = re.sub(r"‘([^‘’]+?)’", r"‚\1‘", s)
        # migrate FR quotations »...«
        s = re.sub(r"»([^»«]+?)«", r"„\1“", s)

        # migrate EN quotations at first word of chapter
        s = re.sub(r"\\(lettrine|lettrinepara)\[ante=“\]", r"\\\1[ante=„]", s)

    # fixing ' "Word..."' and ' "\command..."'
    if settings["lang"] == "EN":
        s = re.sub(r'(^|\s)"((\\|\w).*?)"', r"\1“\2”", s)
    if settings["lang"] == "DE":
        s = re.sub(r'(^|\s)"((\\|\w).*?)"', r"\1„\2“", s)

    # add space between … and “
    # if settings["lang"] == "EN":
    #     s = re.sub(r"…“", r"… “", s)
    if settings["lang"] == "DE":
        s = re.sub(r"…„", r"… „", s)

    # space before closing “
    if settings["lang"] == "EN":
        s = re.sub(r" +”", r"” ", s)
    if settings["lang"] == "DE":
        s = re.sub(r" +“", r"“ ", s)

    # space between "…" and "“"
    # if settings["lang"] == "EN":
    #     s = re.sub(r"…„", r"… “", s)     # rrthomas voted againt it
    if settings["lang"] == "DE":
        s = re.sub(r"…„", r"… „", s)

    # ” } -> ”}
    if settings["lang"] == "EN":
        s = s.replace("” }", "”} ")
    if settings["lang"] == "DE":
        s = s.replace("“ }", "“} ")
    # now fix possible new double spaces created by line above
    s = re.sub(r"(?<!^)[ \t][ \t]+", " ", s)
    s = re.sub(r" +$", r"", s)

    # quotation marks should go outside of emph:
    # \emph{“.....”} -> “\emph{.....}”
    if settings["lang"] == "EN":
        s = re.sub(r"\\(emph|shout)\{“([^”]+?)”\}", r"“\\\1{\2}”", s)
    if settings["lang"] == "DE":
        s = re.sub(r"\\(emph|shout)\{„([^“]+?)“\}", r"„\\\1{\2}“", s)

    # lone “ at end of \emph
    # “...\emph{.....”} -> “...\emph{.....}”
    if settings["lang"] == "EN":
        s = re.sub(r"(\\emph\{[^“]+?)”\}", r"\1}”", s)
    if settings["lang"] == "DE":
        s = re.sub(r"(\\emph\{[^„]+?)“\}", r"\1}“", s)

    # punctuation at end of quotation (and emph)
    # attention: false positives when quoting a book titles etc.
    # for EN mostly correct already
    #    if settings["lang"] == "EN":
    #        s = re.sub(r"(?<![\.,!\?;])(?<![\.,!\?;]\})”,", r",”", s)
    if settings["lang"] == "DE":
        # not, this is wrong, it is correct to have „...“,
        # s = re.sub(r"(?<![\.,!\?;])(?<![\.,!\?;]\})“,", r",“", s)
        s = re.sub(r"(?<![\.,!\?;]),“", r"“,", s)

    # nested single quote + emph
    if settings["lang"] == "EN":
        s = re.sub(r"‘\\emph{([^}]+)}’", r"‘\1’", s)
        s = re.sub(r"\\emph{‘([^}]+)’}", r"‘\1’", s)
    if settings["lang"] == "EN":
        s = re.sub(r"‚\\emph{([^}]+)}‘", r"‚\1‘", s)
        s = re.sub(r"\\emph{‚([^}]+)‘}", r"‚\1‘", s)

    # comma at end of emph&quotation
    if settings["lang"] == "EN":
        pass
        # false positives at book titles etc.
        # s = s.replace("}”,", ",}”")
        # s = s.replace("”,", ",”")
    if settings["lang"] == "DE":
        s = s.replace(",}”", "}”,")
        s = s.replace(",”", "”,")

    # space after closing “
    if settings["lang"] == "DE":
        s = re.sub(r"(“)([\w])", r"\1 \2", s)

    return s


# assert fix_quotations("\parsel{Ich sehe nichts}“,")== "\parsel{Ich sehe nichts},“"


def fix_emph(s: str) -> str:
    # space at start of emph -> move before emph
    s = re.sub(r"(\\emph{) +", " \1", s)

    # move punctuation out of lowercase 1-word-emph
    # ... \emph{WORD.} -> \emph{WORD}.
    # Note: only for , and .
    if settings["lang"] == "EN" and "lettrinepara" not in s:
        # not \lettrinepara{W}{\emph{hat?}}:
        # s = re.sub(r"(?<!^)\\emph\{([^\}A-Z]+)([,\.])\}(?!”)", r"\\emph{\1}\2", s)
        s = re.sub(r"\\emph\{([^\}A-Z]+)([,\.;!\?])\}(?!”)", r"\\emph{\1}\2", s)
    if settings["lang"] == "DE":
        s = re.sub(r"(?<!^)\\emph\{([^ …\}]+)([,\.])\}(?!“)", r"\\emph{\1}\2", s)

    #  only after space fix ! and ?
    # " \emph{true!}" -> " \emph{true}!"
    s = re.sub(r" \\emph\{([^ …\}A-Z]+)([,\.;!\?])\}", r" \\emph{\1}\2", s)

    # Note: good, but MANY false positives
    # \emph{...} word \emph{...} -> \emph{... \emph{word} ...
    # s = re.sub(r"(\\emph\{[^\}]+)\} ([^ ]+) \\emph\{", r"\1 \\emph{\2} ", s)
    return s


assert fix_emph(r"That’s not \emph{true!}") == r"That’s not \emph{true}!"
assert fix_emph(r"she got \emph{magic,} can you") == r"she got \emph{magic}, can you"
# unchanged:
if settings["lang"] == "EN":
    assert (
        fix_emph(r"briefly. \emph{Hopeless.} Both") == r"briefly. \emph{Hopeless.} Both"
    )
if settings["lang"] == "DE":
    assert (
        fix_emph(r"briefly. \emph{Hopeless.} Both") == r"briefly. \emph{Hopeless}. Both"
    )

# if settings["lang"] == "EN":


def fix_hyphens(s: str) -> str:
    # --- -> em dash —
    s = s.replace("---", "—")
    s = s.replace("--", "—")
    # hyphens: (space-hyphen-space) should be "—" (em dash).
    # trim space around em-dash
    s = s.replace(" — ", "—")
    # shorter dash as well
    s = s.replace(" – ", "—")
    # NOT for '— ' as in ', no— “I'
    # s = re.sub(r"— ", r"—", s)
    # " - " -> "—"
    s = s.replace(" - ", "—")
    # remove space before — followed by punctuation
    s = re.sub(r" —([,\.!\?;])", r"—\1", s)

    # - at start of line
    s = re.sub(r"^[\-—] *", r"—", s)
    # if settings["lang"] == "EN":
    #     s = re.sub(r" [\-—]$", r"—", s) # rrthomas voted againt it
    if settings["lang"] == "DE":
        # end of line
        s = re.sub(r" [\-—]$", r"—", s)
    # - at end of emph
    s = re.sub(r"(\s*)\-\}", r"—}\1", s)
    # at start of quote
    # if settings["lang"] == "EN":
    #     s = re.sub(r"—“", r"— “", s) # rrthomas voted againt it
    if settings["lang"] == "DE":
        s = re.sub(r"\s*—„", r"— „", s)
        s = re.sub(r"„\s*—\s*", r"„—", s)

    # at end of quote
    if settings["lang"] == "EN":
        s = re.sub(r"(\s*)\-”", r"—”\1", s)
    if settings["lang"] == "DE":
        s = re.sub(r"(\s*)\-“", r"—“\1", s)

    # space-hyphen-quotation end
    if settings["lang"] == "EN":
        s = re.sub(r"\s+(—”)", r"\1", s)
    if settings["lang"] == "DE":
        s = re.sub(r"\s+(—“)", r"\1", s)

    # there is a shorter dash as well:
    # 2-4 -> 2–4 using mid length hyphen
    s = re.sub(r"(\d)\-(?=\d)", r"\1–", s)
    # NOT: mid-length dash ->  em dash (caution: false positives!)
    # s = s.replace("–", "—")
    return s


assert fix_hyphens("2-3-4") == "2–3–4"
assert fix_hyphens(" —,") == "—,"
assert fix_hyphens(" —.") == "—."
assert fix_hyphens(" —!") == "—!"
assert fix_hyphens(" —?") == "—?"
# start of line
assert fix_hyphens("— asdf") == "—asdf"
assert fix_hyphens("- asdf") == "—asdf"
assert fix_hyphens("-asdf") == "—asdf"
if settings["lang"] == "DE":
    # end of line
    assert fix_hyphens("Text —") == "Text—"
    # start of quote
    assert fix_hyphens("Text—„") == "Text— „"
    assert fix_hyphens("Text —„") == "Text— „"
    assert fix_hyphens("Text „ —Quote") == "Text „—Quote"
    assert fix_hyphens("Text „ — Quote") == "Text „—Quote"
    assert fix_hyphens("Text—„— Quote") == "Text— „—Quote"
    # end of quote
    assert fix_hyphens("Text -“") == "Text—“ ", "'" + fix_hyphens("Text -“") + "'"
    assert fix_hyphens("Text —“") == "Text—“", "'" + fix_hyphens("Text —“") + "'"


def fix_spell(s: str) -> str:
    spells = {
        "Accio",
        "Alohomora",
        # "Avada Kedavra", not here, since sometimes in emph ok.
        "Cluthe",
        "Colloportus",
        "Contego",
        "Crystferrium",
        "Diffindo",
        "Deligitor prodeas",
        "Dulak",
        "Elmekia",
        "Expecto Patronum",
        "Expelliarmus",
        "Finite Incantatem",
        "Flipendo",
        "Frigideiro",
        "Glisseo",
        "Gom jabbar",
        "Hyakuju montauk",
        "Impedimenta",
        # "Imperius", not as spell, as often used in text
        "Incendium",
        "Inflammare",
        "Innervate",
        "Rennervate",
        "Jellify",
        "Lagann",
        "Lucis Gladius",
        "Luminos",
        "Lumos",
        "Mahasu",
        "Obliviate",
        "Oogely boogely",
        "Prismatis",
        "Polyfluis Reverso",
        "Protego",
        "Protego Maximus",
        "Quietus",
        "Ravum Calvaria",
        "Rennervate",
        "Scourgify",
        "Ratzeputz",
        "Silencio",
        "Somnium",
        "Stupefy",
        "Stupor",
        "Thermos",
        "Tonare",
        "Ventriliquo",
        "Ventus",
        "Wingardium Leviosa",
    }
    spells_str = "(" + "|".join(spells) + ")"

    if settings["lang"] == "DE":
        # \emph{spell}
        s = re.sub(r"\\emph{„?" + spells_str + r"[!\.“]?}", r"\\spell{\1}", s)
        # „\emph{spell}“
        s = re.sub(r"„\\emph{„?" + spells_str + r"[!\.]?“?}", r"\\spell{\1}“", s)
        # ‚spell‘
        s = re.sub(r"‚" + spells_str + r"!?‘", r"\\spell{\1}", s)
        # „spell“
        s = re.sub(r"„" + spells_str + r"!?“", r"\\spell{\1}", s)
        # " spell "
        # 2 false positives
        # s = re.sub(r"(?<= )" + spells_str + r"(?= )(?!\1)", r"\\spell{\1}", s)

    # \spell without !
    s = re.sub(r"(\\spell{[^}]+)!}", r"\1}", s)
    # \spell followed by ! -> remove !
    s = re.sub(r"(\\spell{[^}]+)}!", r"\1}", s)
    # no „...“ around \spell
    s = re.sub(r"„?(\\spell{[^}]+)}“?", r"\1}", s)

    # # some false positives
    # " Alohomora "
    # for spell in spells:
    #     s = re.sub(
    #         r"( |—)" + spell + r"( |—|,|\.|!)", r"\1\\spell{" + spell + r"}\2", s
    #     )
    # Imperius not as spell
    s = s.replace("\\spell{Imperius}", "Imperius")

    return s


if settings["lang"] == "DE":
    assert fix_spell(r"‚Lumos‘") == r"\spell{Lumos}"
    assert fix_spell(r"„Lumos“") == r"\spell{Lumos}"
    assert fix_spell(r"„\emph{Lumos}“") == r"\spell{Lumos}"
    assert fix_spell(r"\emph{„Lumos“}") == r"\spell{Lumos}"
    assert fix_spell(r"\emph{Lumos!}") == r"\spell{Lumos}"
    assert fix_spell(r"„\spell{Lumos}“") == r"\spell{Lumos}"


if __name__ == "__main__":
    # cleanup first
    for file_out in Path("chapters").glob("*-autofix.tex"):
        file_out.unlink()

    list_of_chapter_files = get_list_of_chapter_files()

    # V2: using multiprocessing
    # prepare
    num_processes = min(cpu_count(), len(list_of_chapter_files))
    pool = Pool(processes=num_processes)
    # run
    results = pool.map(process_file, list_of_chapter_files)
    any_issue_found = True in results

    # V1: single processing
    # any_issue_found = False
    # for file_in in list_of_chapter_files:
    #     print(file_in.name)
    #     issue_found = process_file(file_in=file_in)
    #     if issue_found:
    #         any_issue_found = True

    if settings["raise_error"]:
        assert any_issue_found is False, "Issues found, please fix!"
