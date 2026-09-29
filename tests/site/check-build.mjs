import assert from 'node:assert/strict';
import {execFileSync,spawnSync} from 'node:child_process';
import {readFileSync,existsSync} from 'node:fs';
const environment={...process.env,PUBLIC_SUPABASE_URL:'https://test-project.supabase.co',PUBLIC_SUPABASE_PUBLISHABLE_KEY:'sb_secret_FORBIDDEN_SENTINEL'};
const bad=spawnSync(process.execPath,['scripts/build-web.mjs'],{env:environment,encoding:'utf8'});
assert.notEqual(bad.status,0,'A secret key must never enter the public build');
execFileSync(process.execPath,['scripts/build-web.mjs'],{env:{...process.env,PUBLIC_SUPABASE_URL:'',PUBLIC_SUPABASE_PUBLISHABLE_KEY:''},stdio:'pipe'});
assert(existsSync('dist/account.js'));
assert(!existsSync('dist/COPY.md')&&!existsSync('dist/.env')&&!existsSync('dist/account-source.js'));
assert(!readFileSync('dist/public-config.js','utf8').includes('FORBIDDEN_SENTINEL'));
const sql=readFileSync('supabase/migrations/202609290001_meeting_profiles.sql','utf8');
assert(sql.includes('enable row level security'));
for(const action of ['select','insert','update','delete'])assert(sql.includes(`for ${action} to authenticated`));
assert(sql.includes('with check ((select auth.uid())=user_id)'));
assert(sql.includes('references auth.users(id) on delete cascade'));
execFileSync(process.execPath,['scripts/build-web.mjs'],{env:{...process.env,PUBLIC_SUPABASE_URL:'',PUBLIC_SUPABASE_PUBLISHABLE_KEY:'',PUBLIC_SITE_URL:'https://vocalgrid.com'},stdio:'pipe'});
for(const lang of ['en','it','de','fr']){const route=lang==='en'?'':lang+'/';const html=readFileSync('dist/'+route+'index.html','utf8');assert(html.includes('rel="canonical" href="https://vocalgrid.com/'+route+'"'));}
execFileSync(process.execPath,['scripts/build-web.mjs'],{env:{...process.env,PUBLIC_SUPABASE_URL:'',PUBLIC_SUPABASE_PUBLISHABLE_KEY:'',PUBLIC_SITE_URL:''},stdio:'pipe'});
console.log('PASS: privileged key rejection, public-only output, account bundle, RLS migration contract. Live isolation still requires a database test.');
