"""'음표 뒤에 바로 쉼표' 패턴을 센다.

악보 관습으로는 스타카토를 16분음표+16분쉼표로 적지 않는다. 리듬 값(8분음표)을
적고 길이는 아티큘레이션으로 표현한다. 검출된 물리적 길이를 그대로 적으면
악보가 잘게 쪼개져 읽기 어려워진다.

여기서 세는 것: 음표 바로 뒤에 쉼표가 오는 쌍. 이게 많으면 '음길이를 다음
온셋까지로 늘리는' 처리가 필요하다는 뜻이다.
"""
import sys
from collections import Counter
from pathlib import Path

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "data/975e4e588d282666/score.alphatex")
tex = PATH.read_text(encoding="utf-8")

bars = []
for ln in tex.splitlines():
    s = ln.strip()
    if not s or s == "." or s.startswith("\\") or s.startswith("//"):
        continue
    bars.append(s.rstrip("|").strip())

pat = Counter()
note_then_rest = 0
adjacent = 0
rest_after_short = 0

for bar in bars:
    toks = bar.split()
    for a, b in zip(toks, toks[1:]):
        adjacent += 1
        a_is_rest = a.startswith("r.")
        b_is_rest = b.startswith("r.")
        if not a_is_rest and b_is_rest:
            note_then_rest += 1
            a_dur = a.split(".", 2)[-1] if a.count(".") >= 2 else a
            b_dur = b.split(".", 1)[-1]
            pat[(a_dur, b_dur)] += 1
            if a_dur == "16":
                rest_after_short += 1

print("악보: %s / 마디 %d개" % (PATH.name, len(bars)))
print()
print("음표 → 쉼표 인접 쌍: %d개 (전체 인접쌍 %d, %.1f%%)"
      % (note_then_rest, adjacent, 100 * note_then_rest / max(1, adjacent)))
print("그중 16분음표 뒤 쉼표: %d개" % rest_after_short)
print()
print("상위 패턴 (음길이 → 쉼표길이):")
for (an, bn), c in pat.most_common(10):
    print("  %-10s → r.%-10s %4d회" % (an, bn, c))
print()

# 음표 바로 뒤 쉼표를 음길이에 흡수시키면 토큰이 몇 개 줄어드나
total_tokens = sum(len(b.split()) for b in bars)
print("현재 토큰 %d개 → 음표 뒤 쉼표를 흡수하면 최대 %d개 (%.0f%% 감소 여지)"
      % (total_tokens, total_tokens - note_then_rest,
         100 * note_then_rest / max(1, total_tokens)))
