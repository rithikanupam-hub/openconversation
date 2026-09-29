// Run only against the dedicated VocalGrid project. Creates and removes two disposable test users; sends no email.
import {createClient} from '@supabase/supabase-js';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const keys=JSON.parse(readFileSync('.env.supabase-keys.json','utf8'));
const url='https://peejgnwzxqjjhetdhudu.supabase.co';
const options={auth:{persistSession:false,autoRefreshToken:false}};
const admin=createClient(url,keys.find(k=>k.name==='service_role').api_key,options);
const pub=keys.find(k=>k.type==='publishable').api_key;
const users=[];
try{
 const clients=[];
 for(let i=0;i<2;i++){
  const email=`vocalgrid-test-${crypto.randomUUID()}@example.com`;
  const created=await admin.auth.admin.createUser({email,email_confirm:true});assert.ifError(created.error);users.push(created.data.user.id);
  const generated=await admin.auth.admin.generateLink({type:'magiclink',email});assert.ifError(generated.error);
  const client=createClient(url,pub,options);
  const login=await client.auth.verifyOtp({token_hash:generated.data.properties.hashed_token,type:'magiclink'});assert.ifError(login.error);assert(login.data.session);clients.push(client);
 }
 const [a,b]=clients;
 const inserted=await a.from('meeting_profiles').insert({name:'Disposable isolation test',source_language:'it',target_language:'en',meeting_type:'room'}).select().single();assert.ifError(inserted.error);
 const id=inserted.data.id;assert.equal(inserted.data.user_id,users[0]);
 const other=await b.from('meeting_profiles').select().eq('id',id);assert.ifError(other.error);assert.equal(other.data.length,0);
 const forged=await b.from('meeting_profiles').insert({name:'forged',source_language:'it',target_language:'en',meeting_type:'room',user_id:users[0]});assert(forged.error);
 for(const op of ['update','delete']){let q=b.from('meeting_profiles');q=op==='update'?q.update({name:'tampered'}):q.delete();const r=await q.eq('id',id).select();assert.ifError(r.error);assert.equal(r.data.length,0);}
 const anonymous=await createClient(url,pub,options).from('meeting_profiles').select();assert(anonymous.error);
 const own=await a.from('meeting_profiles').select().eq('id',id).single();assert.ifError(own.error);assert.equal(own.data.name,'Disposable isolation test');
 assert.ifError((await a.from('meeting_profiles').delete().eq('id',id)).error);
 for(const c of clients)assert.ifError((await c.auth.signOut()).error);
 console.log('PASS: real magic-link token exchange, account save/read/delete, cross-user read/write denial, anonymous denial and sign-out. No email delivery was tested.');
}finally{
 for(const id of users){const result=await admin.auth.admin.deleteUser(id);assert.ifError(result.error);}
 console.log('Disposable test users removed.');
}
