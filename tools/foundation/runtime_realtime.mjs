// Actual Socket.IO room delivery, not merely an Engine.IO handshake.
import { io } from 'socket.io-client';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
if(process.env.GITHUB_ACTIONS!=='true') throw new Error('Disposable runner only');
const records=JSON.parse(fs.readFileSync(process.env.FOUNDATION_BUSINESS_REPORT)).records;
const report={status:'running',scope:'Owned synthetic Socket.IO subscriptions and delivered events',checks:[],security_gate_passed:false};
const sockets=[];
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function check(name,fn){try{report.checks.push({name,status:'pass',observation:await fn()});}catch(e){report.checks.push({name,status:'fail',message:String(e.message).slice(0,400)});}}
function dump(obj){return JSON.stringify(obj,(k,v)=>v instanceof Set?[...v]:(v instanceof Error?{message:v.message,stack:String(v.stack).slice(0,400)}:v),2);}
async function connect(label){
 const r=await fetch('http://foundation.localhost:8000/api/method/login',{method:'POST',headers:{Host:'foundation.localhost','Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({usr:`validation-${label}@example.test`,pwd:process.env.FOUNDATION_TEST_PASSWORD})});
 if(r.status!==200)throw new Error('Login HTTP '+r.status);
 const cookie=r.headers.getSetCookie().map(c=>c.split(';')[0]).find(c=>c.startsWith('sid='));
 if(!cookie)throw new Error('No authenticated cookie');
 const socket=io('http://foundation.localhost:9000/foundation.localhost',{transports:['websocket'],extraHeaders:{Host:'foundation.localhost',Origin:'http://foundation.localhost:8080',Cookie:cookie},reconnection:false,timeout:10000});
 sockets.push(socket);
 let err=null;
 await new Promise((resolve,reject)=>{
   socket.once('connect',resolve);
   socket.once('connect_error',e=>{err=e;reject(new Error('Authenticated socket connection failed: '+String(e.message).replaceAll(cookie.slice(4),'[REDACTED]').slice(0,300)));});
 });
 socket.user=`validation-${label}@example.test`;
 // Record every inbound event name so a failure message can distinguish
 // "realtime plumbing delivered nothing at all" from "our guard filtered it".
 socket.seen=[];
 socket.onAny((name,payload)=>{ if(socket.seen.length<50) socket.seen.push({name,payload}); });
 return socket;
}
function publish(kind){execFileSync(process.env.FOUNDATION_BENCH_PYTHON,[process.env.FOUNDATION_EVENT_HELPER,kind],{cwd:process.env.FOUNDATION_SITES_DIR,stdio:'pipe'});}
try{
 publish('prepare');
 const task=JSON.parse(fs.readFileSync(process.env.FOUNDATION_REALTIME_TASK)).id;
 let alpha,beta;
 await check('authenticated-student-sockets',async()=>{alpha=await connect('alpha');beta=await connect('beta');return {connected:2,alphaId:alpha.id,betaId:beta.id};});
 await check('document-room-cross-student-isolation',async()=>{
  if(!alpha||!beta)throw new Error('Socket setup unavailable');
  const a=[],b=[];alpha.on('foundation_probe',m=>a.push(m));beta.on('foundation_probe',m=>b.push(m));
  alpha.emit('doc_subscribe','Student',records.students[0]);beta.emit('doc_subscribe','Student',records.students[0]);
  await delay(2500);publish('document');await delay(2500);
  const gotA=a.some(m=>m.marker==='owned-alpha-document'), gotB=b.some(m=>m.marker==='owned-alpha-document');
  if(!gotA)throw new Error('Positive-control document event absent (alpha='+a.length+', beta='+b.length+'): '+dump({a,b,alphaSeen:alpha.seen,betaSeen:beta.seen}));
  if(gotB)throw new Error('Cross-student document event disclosed: '+dump({b}));
  return {own_delivery:true,other_delivery:false,a_received:a.length,b_received:b.length};
 });
 await check('unrelated-task-progress-subscription-denied',async()=>{
  if(!alpha||!beta)throw new Error('Socket setup unavailable');
  const a=[],b=[];alpha.on('foundation_probe',m=>a.push(m));beta.on('foundation_probe',m=>b.push(m));
  alpha.emit('task_subscribe',task);beta.emit('task_subscribe',task);
  await delay(1000);publish('task');await delay(2500);
  const gotA=a.some(m=>m.marker==='owned-task-progress'), gotB=b.some(m=>m.marker==='owned-task-progress');
  if(!gotA)throw new Error('Positive-control task event absent: a='+a.length+' b='+b.length+' '+dump({a,b,alphaSeen:alpha.seen,betaSeen:beta.seen}));
  if(gotB)throw new Error('Unrelated authenticated user received task marker when task identifier was known: '+dump({b}));
  return {other_delivery:false,a_received:a.length,b_received:b.length};
 });
 await check('live-session-revocation-stops-document-and-task-delivery',async()=>{
  if(!alpha?.connected||!beta?.connected)throw new Error('Positive socket setup unavailable');
  const messages=[];alpha.on('foundation_probe',m=>messages.push(m));
  publish('revoke');await delay(500);publish('document');publish('task');await delay(2500);
  if(messages.length)throw new Error('Revoked session received resource data: '+dump({messages,alphaSeen:alpha.seen}));
  return {revoked_delivery:false};
 });
}catch(e){report.checks.push({name:'uncaught',status:'fail',message:String(e&&e.stack||e).slice(0,600)});
}finally{for(const s of sockets){try{s.removeAllListeners();s.disconnect();}catch{}}report.status=report.checks.some(c=>c.status==='fail')?'fail':'pass';fs.writeFileSync(process.env.FOUNDATION_REALTIME_REPORT,JSON.stringify(report,null,2));}
if(report.status!=='pass')process.exitCode=1;
