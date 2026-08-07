"""생성된 악보를 표기 규칙 관점에서 전수 검토한다.

격자(subdivision)는 악보 옆 manifest.json에서 읽는다. 하드코딩하면 8분 격자로
적힌 악보를 16분 표로 검산하게 되고, 4분음표처럼 두 표에 같은 슬롯 수로 들어
있는 음길이만 우연히 통과해서 **위반을 놓친다.**

찾는 것
  1) 마디 길이 불일치 (합이 마디 슬롯 수와 다른 마디)
  2) 정렬 규칙 위반 (음표/쉼표가 자기 길이의 배수 위치에서 시작하지 않음)
  3) 합칠 수 있는 연속 쉼표 (예: 슬롯 0에서 r.8 r.8 → r.4 하나로 가능)
  4) 마디 끝에서 잘린 음 (마디 넘김 타이가 있으면 살릴 수 있는 것)
  5) 표기 통계 — 음길이 분포, 타이 수, 쉼표 비중
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path("apps/worker").resolve()))
from pipeline.alphatex import _duration_table, slots_of

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "data/975e4e588d282666/score.alphatex")


def _subdivision_of(score_path: Path) -> tuple[int, int, str]:
    """악보의 격자와 마디 슬롯 수. 반환 (subdivision, slots_per_bar, 출처)."""
    if len(sys.argv) > 2:
        return int(sys.argv[2]), 0, "인자"
    manifest = score_path.parent / "manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        sub = data.get("subdivision")
        bpb = (data.get("timeSignature") or [4, 4])[0]
        if sub:
            return int(sub), int(sub) * int(bpb), "manifest"
    return 4, 16, "기본값"


SUB, _slots, SOURCE = _subdivision_of(PATH)
SLOTS_PER_BAR = _slots or 4 * SUB

tex = PATH.read_text(encoding="utf-8")
body_lines = [
    ln.strip() for ln in tex.splitlines()
    if ln.strip() and not ln.startswith("\\") and ln.strip() != "." and not ln.startswith("//")
]
bars = [ln.rstrip("|").strip() for ln in body_lines]
print("악보: %s" % PATH)
print("마디 %d개  격자 subdiv=%d (%d슬롯/마디, 출처=%s)" % (
    len(bars), SUB, SLOTS_PER_BAR, SOURCE))
print()

table = _duration_table(SUB)
align_of = {tok: al for _, tok, al in table}
size_of = {tok: sz for sz, tok, _ in table}

# 음길이 대안은 **긴 것부터** 늘어놓아야 한다. `\d+`를 먼저 두면 `8{tu 3}`에서
# `8`만 먹고 `{tu 3}`을 남겨, 셋잇단 악보의 모든 음이 "알 수 없는 음길이"가 된다.
# subdivision을 4로 하드코딩하던 동안에는 `8`이 유효한 토큰이라 조용히 통과했다.
tok_re = re.compile(r"(?:(-|\d+)\.(\d+)|r)\.(\d+\{tu 3\}|\d+\{d\}|\d+)")

bad_len, bad_align, mergeable, tie_count = [], [], [], 0
dur_hist = Counter()
rest_slots = note_slots = 0
truncated = []   # 마디 끝에서 음이 잘렸을 가능성

for bi, bar in enumerate(bars, 1):
    pos = 0
    events = []
    for m in tok_re.finditer(bar):
        fret, string, dur = m.group(1), m.group(2), m.group(3)
        try:
            sz = slots_of(dur, SUB)
        except ValueError:
            bad_align.append((bi, "알 수 없는 음길이 %r" % dur, pos))
            continue
        kind = "rest" if fret is None else ("tie" if fret == "-" else "note")
        events.append((pos, sz, kind, dur, string))
        pos += sz

    if pos != SLOTS_PER_BAR:
        bad_len.append((bi, pos))

    # 정렬 규칙
    for p, sz, kind, dur, _ in events:
        al = align_of.get(dur)
        if al and p % al != 0:
            bad_align.append((bi, "%s %s at slot %d (정렬 %d 위반)" % (kind, dur, p, al), p))
        dur_hist[dur] += 1
        if kind == "rest":
            rest_slots += sz
        else:
            note_slots += sz
        if kind == "tie":
            tie_count += 1

    # 합칠 수 있는 연속 쉼표
    i = 0
    while i < len(events):
        if events[i][2] != "rest":
            i += 1
            continue
        j = i
        total = 0
        while j < len(events) and events[j][2] == "rest":
            total += events[j][1]
            j += 1
        if j - i >= 2:
            start = events[i][0]
            # 이 구간을 더 적은 토큰으로 적을 수 있나
            best = 0
            for sz, tok, al in table:
                if sz <= total and start % al == 0:
                    best = sz
                    break
            if best == total:
                mergeable.append((bi, start, total, j - i))
        i = j

    # 마지막 이벤트가 음/타이이고 마디 끝에 딱 붙어 끝나면, 다음 마디 첫 이벤트가
    # 같은 현·프렛이면 원래 이어지던 음일 가능성이 있다
    if events and events[-1][2] in ("note", "tie") and events[-1][0] + events[-1][1] == SLOTS_PER_BAR:
        truncated.append(bi)

print("=== 1) 마디 길이 검산 ===")
print("  불일치 마디: %s" % (
    bad_len if bad_len else "없음 (전 마디 %d슬롯)" % SLOTS_PER_BAR))
print()
print("=== 2) 정렬 규칙 위반 ===")
if bad_align:
    for b in bad_align[:10]:
        print("  %d마디: %s" % (b[0], b[1]))
    print("  총 %d건" % len(bad_align))
else:
    print("  없음")
print()
print("=== 3) 합칠 수 있는 연속 쉼표 ===")
if mergeable:
    for b in mergeable[:8]:
        print("  %d마디 슬롯%d: 쉼표 %d개(%d슬롯)를 1개로 합칠 수 있음" % (b[0], b[1], b[3], b[2]))
    print("  총 %d건" % len(mergeable))
else:
    print("  없음")
print()
print("=== 4) 마디 끝까지 이어진 음 (마디 넘김 타이 후보) ===")
print("  %d개 마디: %s%s" % (len(truncated), truncated[:20], " ..." if len(truncated) > 20 else ""))
print()
print("=== 5) 표기 통계 ===")
print("  타이 토큰: %d개" % tie_count)
print("  음이 차지한 슬롯 %d / 쉼표 %d (쉼표 비중 %.1f%%)"
      % (note_slots, rest_slots, 100 * rest_slots / max(1, note_slots + rest_slots)))
print("  음길이 분포:")
for tok, n in sorted(dur_hist.items(), key=lambda kv: -kv[1]):
    print("    %-8s %4d" % (tok, n))
