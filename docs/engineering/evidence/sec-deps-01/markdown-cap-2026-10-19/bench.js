const showdown = require('./node_modules/showdown');
const conv = new showdown.Converter({ tables: true });
const shapes = {
  open_brackets: n => '['.repeat(n),
  link_open_nested: n => '[a'.repeat(n),
  bracket_paren: n => '[]('.repeat(n),
  bracket_space_paren: n => '[ ]( '.repeat(n),
  nested_anchor: n => '[' + '['.repeat(n) + 'x](y',
  mixed_link: n => ('[x](y '.repeat(n)),
  ref_defs: n => ('[a]: <b> "c"\n').repeat(n) + '[a]',
  angle_html: n => '<a href="'.repeat(n),
};
const sizes = (process.argv[2] || '500,1000,2000,4000').split(',').map(Number);
for (const [name, gen] of Object.entries(shapes)) {
  const row = [];
  for (const n of sizes) {
    const s = gen(n);
    const t0 = process.hrtime.bigint();
    conv.makeHtml(s);
    const ms = Number(process.hrtime.bigint() - t0) / 1e6;
    row.push(`${n * 1}:${s.length}ch:${ms.toFixed(1)}ms`);
  }
  console.log(name.padEnd(20), row.join('  '));
}
