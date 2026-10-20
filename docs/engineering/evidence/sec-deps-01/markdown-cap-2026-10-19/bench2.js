const showdown = require('./node_modules/showdown');
const conv = new showdown.Converter({ tables: true });
const shapes = {
  bracket_paren: n => '[]('.repeat(n),
  angle_html: n => '<a href="'.repeat(n),
  open_brackets: n => '['.repeat(n),
};
// Target character lengths around candidate caps.
const lens = (process.argv[2] || '1000,2000,3000').split(',').map(Number);
for (const [name, gen] of Object.entries(shapes)) {
  const row = [];
  for (const L of lens) {
    const s = gen(L).slice(0, L);
    let worst = 0;
    for (let i = 0; i < 3; i++) {
      const t0 = process.hrtime.bigint();
      conv.makeHtml(s);
      worst = Math.max(worst, Number(process.hrtime.bigint() - t0) / 1e6);
    }
    row.push(`${L}ch:${worst.toFixed(1)}ms`);
  }
  console.log(name.padEnd(16), row.join('  '));
}
