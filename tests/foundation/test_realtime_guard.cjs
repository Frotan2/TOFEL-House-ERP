const assert=require('node:assert/strict');
const guard=require('../../apps/foundation_security/realtime/handlers.js');
const sent=[];const nsp={sockets:new Map(),adapter:{broadcast:(p,o)=>sent.push(o)}};
let allow=true;let calls=0;
function socket(id,user){const s={id,user,nsp,connected:true,rooms:new Set([id,`user:${user}`,'all','website']),handlers:{},on(e,f){this.handlers[e]=f},removeAllListeners(e){delete this.handlers[e]},leave(r){this.rooms.delete(r)},join(r){this.rooms.add(r)},async frappe_request(path,args){calls++;return {ok:true,json:async()=>({message:allow&&user==='alpha'&&args.kind==='document'&&args.name==='a'})}}};nsp.sockets.set(id,s);guard(s);return s;}
(async()=>{
 const a=socket('a-id','alpha'),b=socket('b-id','beta');
 assert(!a.rooms.has('all'));assert(!b.rooms.has('website'));
 await a.handlers.doc_subscribe('Student','a');await b.handlers.doc_subscribe('Student','a');
 assert(a.rooms.has('doc:Student/a'));assert(!b.rooms.has('doc:Student/a'));
 // Force stale memberships to verify delivery enforcement independently of join.
 b.rooms.add('doc:Student/a');
 const packet={data:['event',{private:true}]},opts={rooms:new Set(['doc:Student/a']),except:new Set()};
 nsp.adapter.broadcast(packet,opts);await new Promise(setImmediate);
 assert.deepEqual([...sent[0].rooms],['a-id']);
 allow=false;nsp.adapter.broadcast(packet,opts);await new Promise(setImmediate);
 assert.equal(sent.length,1);assert(calls>=6);
 nsp.adapter.broadcast(packet,{rooms:new Set(['all'])});
 nsp.adapter.broadcast(packet,{rooms:new Set(['doc:Student/a','user:alpha'])});
 await new Promise(setImmediate);assert.equal(sent.length,1);
 assert.equal(guard.resource('task_progress:site||id').resource,'site||id');
 assert.equal(guard.resource('doctype:Student'),null);
 console.log('Realtime guard: subscription, fresh delivery, revocation, broad and mixed-room denial PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
