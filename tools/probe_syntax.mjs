/** AlphaTex 문법 요소를 하나씩 켜보며 무엇이 거부되는지 찾는다. */
import * as alphaTab from "@coderline/alphatab";

const HEAD = `\\title "t"
\\tempo 120
.

\\track "Bass"
\\staff{tabs} \\tuning E1 A1 D2 G2
\\ts 4 4

`;

// 셋잇단 표기 후보. 8분음표 셋잇단 3개 = 4분음표 1박.
const CASES = {
  "tu 3 (8분 셋잇단 한 박)":
    `0.4.8{tu 3} 0.4.8{tu 3} 0.4.8{tu 3} 0.4.4 0.4.4 0.4.4`,
  "tu 3 네 박 전부":
    `0.4.8{tu 3} 0.4.8{tu 3} 0.4.8{tu 3} 0.4.8{tu 3} 0.4.8{tu 3} 0.4.8{tu 3} ` +
    `0.4.8{tu 3} 0.4.8{tu 3} 0.4.8{tu 3} 0.4.8{tu 3} 0.4.8{tu 3} 0.4.8{tu 3}`,
  "tu 3 + 쉼표 혼합":
    `0.4.8{tu 3} r.8{tu 3} 0.4.8{tu 3} 0.4.4 0.4.4 0.4.4`,
  "tuplet 3 (풀네임)":
    `0.4.8{tuplet 3} 0.4.8{tuplet 3} 0.4.8{tuplet 3} 0.4.4 0.4.4 0.4.4`,
  "tu 3 4분 셋잇단":
    `0.4.4{tu 3} 0.4.4{tu 3} 0.4.4{tu 3} 0.4.2`,
  "셋잇단 없이 8분 6개(비교군)":
    `0.4.8 0.4.8 0.4.8 0.4.8 0.4.8 0.4.8 0.4.4 0.4.4`,
};

const AlphaTexImporter = alphaTab.importer.AlphaTexImporter;

for (const [name, body] of Object.entries(CASES)) {
  const tex = HEAD + body;
  try {
    const imp = new AlphaTexImporter();
    imp.initFromString(tex, new alphaTab.Settings());
    const score = imp.readScore();
    const bars = score.tracks[0].staves[0].bars;
    let notes = 0;
    let tuplets = 0;
    for (const bar of bars)
      for (const v of bar.voices)
        for (const b of v.beats) {
          notes += b.notes.length;
          if (b.tupletNumerator > 1) tuplets++;
        }
    console.log(
      `OK    ${name.padEnd(26)} bars=${bars.length} notes=${notes} tupletBeats=${tuplets}`,
    );
  } catch (e) {
    console.log(`FAIL  ${name.padEnd(26)} ${e?.message ?? e}`);
  }
}
