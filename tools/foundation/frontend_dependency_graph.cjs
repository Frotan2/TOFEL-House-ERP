// Installed-tree constraints, not an assertion of API or security compatibility.
const fs=require('node:fs'),path=require('node:path');
const semver=require(path.join(process.env.FOUNDATION_REVIEW_TOOLS,'node_modules/semver'));
const root=path.resolve(process.argv[2]);
function resolve(from,name){
 for(let p=from;;p=path.dirname(p)){
  const file=path.join(p,'node_modules',name,'package.json');
  if(fs.existsSync(file))return file;
  if(p===path.dirname(p))return null;
 }
}
const manifests=[path.join(root,'package.json')];
function walk(modules){if(!fs.existsSync(modules))return;for(const name of fs.readdirSync(modules)){
 const folder=path.join(modules,name);
 const packages=name.startsWith('@')?fs.readdirSync(folder).map(x=>path.join(folder,x)):[folder];
 for(const p of packages){if(fs.existsSync(path.join(p,'package.json'))){manifests.push(path.join(p,'package.json'));walk(path.join(p,'node_modules'));}}
}}
walk(path.join(root,'node_modules'));
const edges=[],issues=[];
for(const file of manifests){const p=JSON.parse(fs.readFileSync(file));
 const types=['dependencies','optionalDependencies','peerDependencies'];
 if(file===manifests[0])types.push('devDependencies');
 for(const type of types)for(const [name,range]of Object.entries(p[type]||{})){
  const target=resolve(path.dirname(file),name),optional=type==='optionalDependencies'||(type==='peerDependencies'&&p.peerDependenciesMeta?.[name]?.optional);
  const resolved=target?JSON.parse(fs.readFileSync(target)):null, actual=resolved?.version;
  const alias=range.startsWith('npm:')?range.slice(4).match(/^(.+)@([^@]+)$/):null;
  const evaluatedRange=alias?alias[2]:range;
  const alternatives=evaluatedRange.split('||').map(x=>x.trim()).filter(x=>semver.validRange(x));
  const satisfies=actual&&alternatives.some(x=>semver.satisfies(actual,x));
  const status=!actual?(optional?'optional_absent':'missing'):alias&&resolved.name!==alias[1]?'alias_name_mismatch':!alternatives.length?'unsupported_range':satisfies?'satisfied':'range_mismatch';
  const edge={parent:p.name+'@'+p.version,parent_path:path.relative(root,path.dirname(file)),dependency:name,range,type,resolved_version:actual,status};
  edges.push(edge);if(!['satisfied','optional_absent'].includes(status))issues.push(edge);
 }
}
const result={scope:'Actual installed dependency/peer resolution; semver satisfaction is not runtime compatibility',edges,issues};
fs.writeFileSync(process.argv[3],JSON.stringify(result,null,2)+'\n');
console.log('Dependency edges',edges.length,'issues',issues.length);
