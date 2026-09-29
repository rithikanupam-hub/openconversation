// Run: node tests/site/check-trust.cjs
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const site=path.resolve(__dirname,'../../frontend/site');
for(const lang of ['','it','de','fr']) {
 const html=fs.readFileSync(path.join(site,lang,'index.html'),'utf8');
 for(const anchor of ['privacy','terms','refunds','cookies','requests'])assert(html.includes(`trust.html#${anchor}`));
 assert(!/sessionStorage|localStorage|document\.cookie/.test(html));
}
const js=fs.readFileSync(path.join(site,'site.js'),'utf8');
assert(!/sessionStorage|localStorage|document\.cookie/.test(js));
assert(js.includes('panel.inert = i !== index'));
const policy=fs.readFileSync(path.join(site,'trust.html'),'utf8');
assert(policy.includes('noindex,nofollow'));
assert(policy.includes('Not connected yet:'));
for(const id of ['privacy','terms','refunds','cookies','requests','business','accessibility'])assert(policy.includes(`id="${id}"`));
for(const font of ['instrumentsans','instrumentserif','jetbrainsmono','caveat'])assert(fs.readFileSync(path.join(site,'assets/fonts',font+'-OFL.txt'),'utf8').includes('SIL OPEN FONT LICENSE'));
console.log('PASS: policy navigation, draft status, no marketing storage, inactive-scene keyboard guard, bundled font licences.');
