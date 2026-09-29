import {createClient} from '@supabase/supabase-js';
const $=s=>document.querySelector(s),status=$('#account-status');
const config=window.VOCALGRID_CONFIG||{};
const message=text=>{status.textContent=text;};
if(!config.supabaseUrl||!config.supabaseKey){
 message('Account services are not connected in this preview yet. You can still explore the website.');
}else{
 const client=createClient(config.supabaseUrl,config.supabaseKey,{auth:{flowType:'pkce',storageKey:'vocalgrid-auth',detectSessionInUrl:true,persistSession:true,autoRefreshToken:true}});
 let user=null,version=0;
 async function profiles(){
  const current=++version;
  const {data,error}=await client.from('meeting_profiles').select('id,name,source_language,target_language,meeting_type').order('created_at',{ascending:false});
  if(current!==version||!user)return;
  if(error){message('Could not load preferences. Please try again.');return;}
  const list=$('#saved-profiles');list.replaceChildren();
  if(!data.length){const item=document.createElement('li');item.textContent='No saved preferences yet.';list.append(item);}
  for(const row of data){
   const item=document.createElement('li'),title=document.createElement('strong'),detail=document.createElement('p'),remove=document.createElement('button');
   title.textContent=row.name;detail.textContent=`${row.source_language.toUpperCase()} → ${row.target_language.toUpperCase()} · ${row.meeting_type}`;
   remove.type='button';remove.className='text-btn';remove.textContent='Delete';remove.setAttribute('aria-label',`Delete ${row.name}`);
   remove.addEventListener('click',async()=>{if(!confirm(`Delete “${row.name}”?`))return;remove.disabled=true;try{const {error}=await client.from('meeting_profiles').delete().eq('id',row.id);if(error)throw error;await profiles();message('Preferences deleted.');}catch{message('Could not delete preferences. Please try again.');remove.disabled=false;}});
   item.append(title,detail,remove);list.append(item);
  }
 }
 async function showSession(session){
  user=session?.user||null;version++;
  $('#sign-in').hidden=!!user;$('#workspace').hidden=!user;$('#saved-profiles').replaceChildren();
  $('#account-email').textContent=user?.email||'';
  message(user?'Signed in. Your saved preferences are private.':'Sign in to save meeting preferences.');
  if(user)await profiles();
 }
 client.auth.onAuthStateChange((_event,session)=>{setTimeout(()=>showSession(session),0);});
 $('#login-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=event.submitter;button.disabled=true;
  try{const {error}=await client.auth.signInWithOtp({email:$('#email').value.trim(),options:{emailRedirectTo:location.origin+location.pathname,shouldCreateUser:true}});if(error)throw error;message('If sign-in is available for this address, a link will arrive shortly. Check your inbox and spam folder.');}catch{message('Could not send the sign-in link. Please wait a moment and try again.');}finally{button.disabled=false;}
 });
 $('#sign-out').addEventListener('click',async()=>{const {error}=await client.auth.signOut();if(error){message('Sign-out failed. Please retry.');return;}await showSession(null);});
 $('#profile-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!user)return;const button=event.submitter;button.disabled=true;
  try{const fields=Object.fromEntries(new FormData(event.target));fields.name=fields.name.trim();if(!fields.name)throw Error('Name required');const {error}=await client.from('meeting_profiles').insert({...fields,user_id:user.id});if(error)throw error;event.target.reset();await profiles();message('Preferences saved.');}catch{message('Could not save preferences. Check the name and try again.');}finally{button.disabled=false;}
 });
 const {data,error}=await client.auth.getSession();
 if(error)message('Could not restore your sign-in. Please try again.');else await showSession(data.session);
}
