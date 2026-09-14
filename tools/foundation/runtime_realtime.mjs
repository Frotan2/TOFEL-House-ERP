// Actual Socket.IO room delivery, not merely an Engine.IO handshake.
import { io } from 'socket.io-client';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
if(process.env.GITHUB_ACTIONS!=='true') throw new Error('Disposable runner only');
const records=JSON.parse(fs.readFileSync(process.env.FOUNDATION_BUSINESS_REPORT)).records;
const report={status:'running',scope:'Owned synthetic Socket.IO subscriptions and delivered events',checks:[],security_gate_passed:false};
const sockets=[];
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function check(name,fn){try{report.checks.push({name,status:'pass',observation:await fn()});}catch(e){report.checks.push({name,status:'fail',message:String(e.message).slice(0,200)});}}
async function connect(label){
 const r=await fetch('http://127.0.0.1:8000/api/method/login',{method:'POST',headers:{Host:'foundation.localhost','Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({usr:`validation-${label}@example.test`,pwd:process.env.FOUNDATION_TEST_PASSWORD})});
 if(r.status!==200)throw new Error('Login HTTP '+r.status);
 const cookie=r.headers.getSetCookie().map(c=>c.split(';')[0]).find(c=>c.startsWith('sid='));
 if(!cookie)throw new Error('No authenticated cookie');
 const socket=io('http://127.0.0.1:9000/foundation.localhost',{transports:['websocket'],extraHeaders:{Host:'foundation.localhost',Origin:'http://foundation.localhost',Cookie:cookie},reconnection:false,timeout:10000});
 sockets.push(socket);
 await new Promise((resolve,reject)=>{socket.once('connect',resolve);socket.once('connect_error',()=>reject(new Error('Authenticated socket connection failed')));});
 return socket;
}
function publish(kind){execFileSync(process.env.FOUNDATION_BENCH_PYTHON,[process.env.FOUNDATION_EVENT_HELPER,kind],{cwd:process.env.FOUNDATION_SITES_DIR,stdio:'pipe'});}
try{
 let alpha,beta;
 await check('authenticated-student-sockets',async()=>{alpha=await connect('alpha');beta=await connect('beta');return {connected:2};});
 await check('document-room-cross-student-isolation',async()=>{
  if(!alpha||!beta)throw new Error('Socket setup unavailable');
  const a=[],b=[];alpha.on('foundation_probe',m=>a.push(m));beta.on('foundation_probe',m=>b.push(m));
  alpha.emit('doc_subscribe','Student',records.students[0]);beta.emit('doc_subscribe','Student',records.students[0]);
  await delay(1500);publish('document');await delay(1500);
  if(!a.some(m=>m.marker==='owned-alpha-document'))throw new Error('Positive-control document event absent');
  if(b.some(m=>m.marker==='owned-alpha-document'))throw new Error('Cross-student document event disclosed');
  return {own_delivery:true,other_delivery:false};
 });
 await check('unrelated-task-progress-subscription-denied',async()=>{
  if(!alpha||!beta)throw new Error('Socket setup unavailable');
  const a=[],b=[];alpha.on('foundation_probe',m=>a.push(m));beta.on('foundation_probe',m=>b.push(m));
  alpha.emit('task_subscribe','foundation-owned-secret-task');beta.emit('task_subscribe','foundation-owned-secret-task');
  await delay(500);publish('task');await delay(1500);
  if(!a.some(m=>m.marker==='owned-task-progress'))throw new Error('Positive-control task event absent');
  if(b.some(m=>m.marker==='owned-task-progress'))throw new Error('Unrelated authenticated user received task marker when task identifier was known');
  return {other_delivery:false};
 });
}finally{for(const s of sockets)s.disconnect();report.status=report.checks.some(c=>c.status==='fail')?'fail':'pass';fs.writeFileSync(process.env.FOUNDATION_REALTIME_REPORT,JSON.stringify(report,null,2));}
if(report.status!=='pass')process.exitCode=1;
