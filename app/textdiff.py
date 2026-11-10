"""Redistribute edited paragraph text across the original runs so run formatting survives edits."""
from difflib import SequenceMatcher


def redistribute(run_texts: list[str], new_text: str) -> list[str]:
    """Return per-run texts whose concatenation is new_text.

    Unchanged characters stay in their run; inserted characters join the run of the
    preceding kept character (or the first run when inserted at the very start)."""
    if not run_texts:
        return [new_text]
    owner = [i for i, t in enumerate(run_texts) for _ in t]  # run index of every old char
    out = [""] * len(run_texts)
    old = "".join(run_texts)
    last = 0
    for op, i1, i2, j1, j2 in SequenceMatcher(None, old, new_text, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                last = owner[i1 + k]
                out[last] += old[i1 + k]
        elif j2 > j1:  # insert / replace: new chars go to the run that held the replaced text, else the previous run
            last = owner[i1] if i1 < i2 else last
            out[last] += new_text[j1:j2]
    return out


if __name__ == "__main__":
    assert redistribute(["Hello ", "World"], "Hello World") == ["Hello ", "World"]
    assert redistribute(["Hello ", "World"], "Hello big World") == ["Hello big ", "World"]
    assert redistribute(["ab", "cd"], "abXd") == ["ab", "Xd"]
    assert redistribute(["ab", "cd"], "") == ["", ""]
    assert redistribute(["ab", "cd"], "Zabcd") == ["Zab", "cd"]
    assert redistribute([], "x") == ["x"]
    assert "".join(redistribute(["가나", "다라", "마"], "가X다라바")) == "가X다라바"
    print("ok")
