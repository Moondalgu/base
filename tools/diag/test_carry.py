"""마디 넘김 타이(carry)와 쉼표 흡수 단위 검증."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("apps/worker").resolve()))
from pipeline.alphatex import _render_bar, build, slots_of
from pipeline.fretting import FrettedBar, FrettedNote, FrettedScore


def note(slot, dur, string=3, fret=0):
    return FrettedNote(slot=slot, duration_slots=dur, pitch=28, string=string,
                       fret=fret, low_confidence=False)


def bar(i, notes, spb=16):
    return FrettedBar(index=i, start_sec=float(i * 2), end_sec=float(i * 2 + 2),
                      bpm=120.0, slots_per_bar=spb, notes=notes)


def slot_sum(text, sub=4):
    total = 0
    cur, depth, toks = "", 0, []
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                toks.append(cur)
                cur = ""
            continue
        cur += ch
    if cur:
        toks.append(cur)
    for t in toks:
        p = t.split(".")
        total += slots_of(p[1] if p[0] == "r" else p[2], sub)
    return total


fails = []


def check(label, got, want):
    ok = got == want
    print("  %-46s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        fails.append(label)


print("1) 마디 끝을 4슬롯 넘는 음")
t1, c1 = _render_bar(bar(0, [note(12, 8)]), 4)
check("앞 마디", t1, "r.2{d} 0.4.4")
check("carry_out", c1, (4, 4))
t2, c2 = _render_bar(bar(1, [note(8, 4)]), 4, carry_in=c1)
# 뒤 마디의 음(슬롯8, 4슬롯)은 뒤 4슬롯이 비어 있어 흡수돼 2분음표가 된다
check("뒤 마디(앞머리 타이)", t2, "-.4.4 r.4 0.4.2")
check("carry_out 소멸", c2, None)
check("앞 마디 16슬롯", slot_sum(t1), 16)
check("뒤 마디 16슬롯", slot_sum(t2), 16)

print("2) 2.5마디를 덮는 음 (상한 4마디 이내)")
t, c = _render_bar(bar(0, [note(0, 40)]), 4)
check("1마디", t, "0.4.1")
check("carry 24", c, (4, 24))
t, c = _render_bar(bar(1, [], ), 4, carry_in=c)
check("2마디(전부 타이)", t, "-.4.1")
check("carry 8", c, (4, 8))
t, c = _render_bar(bar(2, []), 4, carry_in=c)
check("3마디(타이 8슬롯 + 쉼표)", t, "-.4.2 r.2")
check("carry 소멸", c, None)

print("3) carry 구간과 겹치는 음은 건너뛴다")
t, c = _render_bar(bar(1, [note(4, 4, fret=3), note(12, 4, fret=5)]), 4, carry_in=(4, 8))
check("겹친 음 무시, 뒤 음만 표기", t, "-.4.2 r.4 5.4.4")
check("carry 소멸", c, None)

print("4) 흡수 규칙 (앞쪽 토큰만 비교)")
cases = [
    # 16분음표 + 16분쉼표(짝수 슬롯) -> 8분음표. 스타카토 8분의 정석 표기.
    ("16 + r.16 @0   -> 8",         [note(0, 1), note(2, 1)],  1, "0.4.8"),
    # 8분 + 16분쉼표 -> 붙임점 8분
    ("8 + r.16 @0    -> 8{d}",      [note(0, 2), note(3, 1)],  1, "0.4.8{d}"),
    # 붙임점 8분 + 16분쉼표 -> 4분
    ("8{d} + r.16 @0 -> 4",         [note(0, 3), note(4, 4)],  1, "0.4.4"),
    # 4분 + 4분쉼표(같은 길이) -> 2분
    ("4 + r.4 @0     -> 2",         [note(0, 4), note(8, 8)],  1, "0.4.2"),
    # 음보다 긴 쉼표는 진짜 쉼표다 (조건 1)
    ("16 + r.8 @0    -> 흡수 안 함",  [note(0, 1), note(4, 4)],  3, "0.4.16 r.16 r.8"),
    # 홀수 슬롯의 16분은 정렬 규칙 때문에 8분으로 못 적는다. 흡수해도 토큰이
    # 줄지 않고 타이만 늘어나므로 쉼표로 남긴다 (조건 2).
    ("16 + r.16 @1   -> 흡수 안 함",  [note(1, 1), note(4, 4)],  3, "r.16 0.4.16 r.8"),
]
for label, notes, head_n, want in cases:
    t, c = _render_bar(bar(0, notes), 4)
    check(label, " ".join(t.split()[:head_n]), want)
    check("  " + label + " 16슬롯", slot_sum(t), 16)

print("5) 셋잇단(스윙) 흡수")
t, c = _render_bar(bar(0, [note(0, 1), note(2, 1), note(4, 1), note(6, 1),
                          note(8, 1), note(10, 1)], spb=12), 3)
check("8{tu 3} + 쉼표 -> 4{tu 3}",
      t, " ".join(["0.4.4{tu 3}"] * 6))
check("12슬롯", slot_sum(t, 3), 12)

print("6) build() 전체 — carry가 마디를 넘어 이어진다")
score = FrettedScore(
    bars=[bar(0, [note(12, 8)]), bar(1, [note(8, 12)]), bar(2, [])],
    tuning=[43, 38, 33, 28], tuning_name="standard", subdivision=4,
    beats_per_bar=4, median_bpm=120.0, unplayable=0,
)
tex = build(score, title="t", include_sync=False)
body = [ln for ln in tex.splitlines()
        if ln and not ln.startswith("\\") and ln != "." and not ln.startswith("//")]
for ln in body:
    print("   " + ln)
check("1마디", body[0].rstrip(" |"), "r.2{d} 0.4.4")
check("2마디", body[1].rstrip(" |"), "-.4.4 r.4 0.4.2")
check("3마디", body[2].rstrip(" |"), "-.4.4 r.4 r.2")

print()
print("실패 %d건" % len(fails))
sys.exit(1 if fails else 0)
