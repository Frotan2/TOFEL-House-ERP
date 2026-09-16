const path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
const root=path.resolve(process.argv[2]),load=n=>require(path.join(root,'node_modules',n));
(async()=>{
 assert(load('minimatch').minimatch('src/App.vue','**/*.vue'));
 assert.deepEqual(load('micromatch')(['src/App.vue','file.txt'],'**/*.vue'),['src/App.vue']);
 assert(load('glob').globSync('src/**/*.vue',{cwd:root}).includes('src/App.vue'));
 assert(load('picomatch')('**/*.vue')('src/App.vue'));
 const css=await load('postcss')([load('autoprefixer')]).process('a { display: flex }',{from:undefined});
 assert(css.css.includes('display: flex'));
 assert.equal(typeof load('nanoid').nanoid(),'string');
 assert.deepEqual(load('yaml').parse('enabled: true'),{enabled:true});
 const parser=load('socket.io-parser'),decoder=new parser.Decoder();let decoded;
 decoder.on('decoded',value=>decoded=value);
 new parser.Encoder().encode({type:2,nsp:'/',data:['qualification','synthetic']}).forEach(p=>decoder.add(p));
 assert.deepEqual(decoded.data,['qualification','synthetic']);decoder.destroy();
 fs.writeFileSync(process.argv[3],JSON.stringify({status:'pass',checks:8,scope:'Basic retained package API contracts only; not exploit regression, browser/backend integration or production approval'})+'\n');
})().catch(e=>{fs.writeFileSync(process.argv[3],JSON.stringify({status:'fail',message:String(e.message)}));process.exitCode=1});
