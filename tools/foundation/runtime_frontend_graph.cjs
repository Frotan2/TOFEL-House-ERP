// Instrument a separate production build via Vite's public API, not core edits.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
if(process.env.GITHUB_ACTIONS!=='true')throw new Error('Disposable runner only');
const root=process.env.FOUNDATION_FRONTEND_ROOT;
process.chdir(root);
const vite=require(path.join(root,'node_modules/vite'));
const packages=new Map();
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
   for(const chunk of Object.values(bundle))if(chunk.type==='chunk')for(const [id,module]of Object.entries(chunk.modules)){
    const p=owner(id);if(!p)continue;
    const key=p.name+'@'+p.version;
    const row=packages.get(key)||{name:p.name,version:p.version,rendered_bytes:0,modules:0};
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
 const report={status:'pass',scope:'Production build module inclusion only; not a vulnerability waiver or exploit proof',packages:rows,findings,
  source_config_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'vite.config.js'))).digest('hex')};
 fs.writeFileSync(process.env.FOUNDATION_FRONTEND_GRAPH_REPORT,JSON.stringify(report,null,2));
})().catch(e=>{fs.writeFileSync(process.env.FOUNDATION_FRONTEND_GRAPH_REPORT,JSON.stringify({status:'fail',message:String(e.message).slice(0,250)}));process.exitCode=1;});
