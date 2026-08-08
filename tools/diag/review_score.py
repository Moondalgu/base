"""생성된 악보를 표기 규칙 관점에서 전수 검토한다.

격자(subdivision)는 악보 옆 manifest.json에서 읽는다. 하드코딩하면 8분 격자로
적힌 악보를 16분 표로 검산하게 되고, 4분음표처럼 두 표에 같은 슬롯 수로 들어
있는 음길이만 우연히 통과해서 **위반을 놓친다.**

**멀티트랙(3단 악보) 대응** — `\\track` 단위로 나눠 트랙마다 따로 검산한다.
보컬 트랙의 피치 토큰(`c#4.8`)도 읽는다. 트랙을 무시하고 한 줄로 이어 붙이면
마디 수가 배가 되고 보컬 토큰이 전부 "알 수 없는 음길이"로 떨어진다(2026-08-08).

찾는 것
  1) 마디 길이 불일치 (합이 마디 슬롯 수와 다른 마디)
  2) 정렬 규칙 위반 (음표/쉼표가 자기 길이의 배수 위치에서 시작하지 않음)
  3) 합칠 수 있는 연속 쉼표 (예: 슬롯 0에서 r.8 r.8 → r.4 하나로 가능)
  4) 마디 끝에서 잘린 음 (마디 넘김 타이가 있으면 살릴 수 있는 것)
  5) 표기 통계 — 음길이 분포, 타이 수, 쉼표 비중
  6) 트랙 간 마디 수 불일치 (멀티트랙이면 반드시 같아야 한다)
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path("apps/worker").resolve()))
from pipeline.alphatex import _duration_table, _strip_non_duration, slots_of

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

# 트랙별로 마디를 모은다. \track이 하나도 없으면(구버전 단일 트랙) "Bass" 하나.
tracks: list[tuple[str, list[str]]] = []
current = ("Bass", [])
for ln in tex.splitlines():
    s = ln.strip()
    if s.startswith("\\track"):
        if current[1]:
            tracks.append(current)
        name = s.split('"')[1] if '"' in s else s
        current = (name, [])
        continue
    if not s or s.startswith("\\") or s == "." or s.startswith("//"):
        continue
    current[1].append(s.rstrip("|").strip())
if current[1]:
    tracks.append(current)

print("악보: %s" % PATH)
print("트랙 %d개, 격자 subdiv=%d (%d슬롯/마디, 출처=%s)" % (
    len(tracks), SUB, SLOTS_PER_BAR, SOURCE))
print()

table = _duration_table(SUB)
align_of = {tok: al for _, tok, al in table}

# 음길이 뒤에는 임의의 중괄호가 붙을 수 있다 — 붙임점과 코드 심볼이
# `4{d ch "E"}` 한 덩어리로 합쳐 적히기 때문이다(alphaTex가 연달은 중괄호를
# 거부한다). `{d}`만 허용하는 좁은 패턴을 쓰면 그 토큰이 `4`로 잘려
# **붙임점 슬롯이 사라진 것으로 오독**한다(2026-08-08 실제로 그랬다).
# 중괄호 전체를 먹이고 slots_of(_strip_non_duration)가 정규화한다.
# 토큰 머리는 네 갈래: 프렛.현(`4.3`) / 타이(`-.3`) / 피치 이름(`c#4`) / 쉼표(`r`).
tok_re = re.compile(
    r"(?:(?P<fret>-|\d+)\.(?P<string>\d+)|(?P<pitch>[a-g](?:#|b)?\d+)|(?P<rest>r))"
    r"\.(?P<dur>\d+\{[^}]*\}|\d+)"
)

bad_len, bad_align, mergeable, tie_count = [], [], [], 0
dur_hist = Counter()
rest_slots = note_slots = 0
truncated = []
bar_counts = []

for tname, bars in tracks:
    bar_counts.append((tname, len(bars)))
    for bi, bar in enumerate(bars, 1):
        pos = 0
        events = []
        for m in tok_re.finditer(bar):
            dur = _strip_non_duration(m.group("dur"))
            try:
                sz = slots_of(dur, SUB)
            except ValueError:
                bad_align.append((tname, bi, "알 수 없는 음길이 %r" % dur, pos))
                continue
            if m.group("rest"):
                kind = "rest"
            elif m.group("fret") == "-":
                kind = "tie"
            else:
                kind = "note"
            events.append((pos, sz, kind, dur))
            pos += sz

        if pos != SLOTS_PER_BAR:
            bad_len.append((tname, bi, pos))

        for p, sz, kind, dur in events:
            al = align_of.get(dur)
            if al and p % al != 0:
                bad_align.append(
                    (tname, bi, "%s %s at slot %d (정렬 %d 위반)" % (kind, dur, p, al), p)
                )
            dur_hist[dur] += 1
            if kind == "rest":
                rest_slots += sz
            else:
                note_slots += sz
            if kind == "tie":
                tie_count += 1

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
                best = 0
                for sz, tok, al in table:
                    if sz <= total and start % al == 0:
                        best = sz
                        break
                if best == total:
                    mergeable.append((tname, bi, start, total, j - i))
            i = j

        if events and events[-1][2] in ("note", "tie") \
                and events[-1][0] + events[-1][1] == SLOTS_PER_BAR:
            truncated.append((tname, bi))

print("=== 1) 마디 길이 검산 ===")
print("  불일치 마디: %s" % (
    bad_len[:20] if bad_len else "없음 (전 마디 %d슬롯)" % SLOTS_PER_BAR))
if len(bad_len) > 20:
    print("  총 %d건" % len(bad_len))
print()
print("=== 2) 정렬 규칙 위반 ===")
if bad_align:
    for b in bad_align[:10]:
        print("  [%s] %d마디: %s" % (b[0], b[1], b[2]))
    print("  총 %d건" % len(bad_align))
else:
    print("  없음")
print()
print("=== 3) 합칠 수 있는 연속 쉼표 ===")
if mergeable:
    for b in mergeable[:8]:
        print("  [%s] %d마디 슬롯%d: 쉼표 %d개(%d슬롯)를 1개로" % (b[0], b[1], b[2], b[4], b[3]))
    print("  총 %d건" % len(mergeable))
else:
    print("  없음")
print()
print("=== 4) 마디 끝까지 이어진 음 (마디 넘김 타이 후보) ===")
print("  %d개: %s%s" % (len(truncated), truncated[:12], " ..." if len(truncated) > 12 else ""))
print()
print("=== 5) 표기 통계 ===")
print("  타이 토큰: %d개" % tie_count)
print("  음이 차지한 슬롯 %d / 쉼표 %d (쉼표 비중 %.1f%%)"
      % (note_slots, rest_slots, 100 * rest_slots / max(1, note_slots + rest_slots)))
print("  음길이 분포:")
for tok, n in sorted(dur_hist.items(), key=lambda kv: -kv[1]):
    print("    %-8s %4d" % (tok, n))
print()
print("=== 6) 트랙 간 마디 수 ===")
print("  " + ", ".join("%s=%d" % t for t in bar_counts)
      + ("  <- 불일치!" if len({n for _, n in bar_counts}) > 1 else "  (일치)"))
