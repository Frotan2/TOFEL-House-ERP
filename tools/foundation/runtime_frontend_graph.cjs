// Instrument a separate production build via Vite's public API, not core edits.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
if(process.env.GITHUB_ACTIONS!=='true')throw new Error('Disposable runner only');
const root=process.env.FOUNDATION_FRONTEND_ROOT;
process.chdir(root);
const vite=require(path.join(root,'node_modules/vite'));
const packages=new Map(),formats=new Set();
function owner(id){
 if(id.includes('\0')||!id.includes('node_modules'))return null;
 let dir=path.dirname(id.split('?')[0]);
 while(dir!==path.dirname(dir)){
  const file=path.join(dir,'package.json');
  if(fs.existsSync(file)){const p=JSON.parse(fs.readFileSync(file));if(p.name&&p.version)return p;}
  dir=path.dirname(dir);
 }
 return null;
}
(async()=>{
 await vite.build({root,base:'/assets/education/frontend/',build:{outDir:process.env.FOUNDATION_GRAPH_BUILD,emptyOutDir:true},plugins:[{
  name:'foundation-rendered-module-evidence',generateBundle(options,bundle){
   formats.add(options.format);
   for(const chunk of Object.values(bundle))if(chunk.type==='chunk')for(const [id,module]of Object.entries(chunk.modules)){
    const p=owner(id);if(!p)continue;
    const key=p.name+'@'+p.version;
    const row=packages.get(key)||{name:p.name,version:p.version,rendered_bytes:0,modules:0};
    if(!Number.isFinite(module.renderedLength))throw new Error('Missing rendered-length evidence');
    row.rendered_bytes+=module.renderedLength;row.modules++;packages.set(key,row);
   }
  }
 }]});
 const audit=JSON.parse(fs.readFileSync(process.env.FOUNDATION_AUDIT_REPORT));
 const rows=[...packages.values()];
 const findings=Object.entries(audit.advisories).flatMap(([name,items])=>items.map(a=>({id:a.id,url:a.url,package:name,
  browser_artifact:rows.some(r=>r.name===name&&r.rendered_bytes>0)?'rendered-code-present':'no-rendered-package-code',
  exploit_reachability:'requires-advisory-specific-input-and-callsite-proof',
  caveat:['vite','rollup','postcss'].includes(name)?'Generator can affect emitted code without itself being bundled':'Build/Node surfaces remain independently applicable'})));
 const sourceFiles=[];
 function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,entry.name);if(entry.isDirectory())walk(p);else if(/\.(vue|js|ts)$/.test(p))sourceFiles.push(p);}}
 walk(path.join(root,'src'));
 const sinkMatches=sourceFiles.flatMap(file=>['v-html','innerHTML','TextEditor','markdownToHTML','initSocket'].filter(token=>fs.readFileSync(file,'utf8').includes(token)).map(token=>({file:path.relative(root,file),token})));
 const dependencySources={};
 for(const relative of ['src/index.js','src/utils/plugin.js','src/resources/plugin.js','src/utils/markdown.js','src/components/FormControl.vue','src/components/TextEditor/TextEditor.vue']){
  dependencySources[relative]=crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'node_modules/frappe-ui',relative))).digest('hex');
 }
 const report={output_formats:[...formats],first_party_source_files:sourceFiles.length,direct_sink_matches:sinkMatches,frappe_ui_source_sha256:dependencySources,status:'pass',scope:'Production build module inclusion only; not a vulnerability waiver or exploit proof',packages:rows,findings,
  source_config_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'vite.config.js'))).digest('hex')};
 fs.writeFileSync(process.env.FOUNDATION_FRONTEND_GRAPH_REPORT,JSON.stringify(report,null,2));
})().catch(e=>{fs.writeFileSync(process.env.FOUNDATION_FRONTEND_GRAPH_REPORT,JSON.stringify({status:'fail',message:String(e.message).slice(0,250)}));process.exitCode=1;});
