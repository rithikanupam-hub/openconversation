import {cpSync,mkdirSync,rmSync,writeFileSync,readFileSync} from 'node:fs';
import path from 'node:path';
import {build} from 'esbuild';
const url=process.env.PUBLIC_SUPABASE_URL||'',key=process.env.PUBLIC_SUPABASE_PUBLISHABLE_KEY||'';
if (!!url !== !!key) throw Error('Set both Supabase public configuration values.');
if (url && !/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(url)) throw Error('Invalid Supabase project URL');
if (key && !key.startsWith('sb_publishable_')) {
 let payload;try{payload=JSON.parse(Buffer.from(key.split('.')[1],'base64url').toString())}catch{}
 if(payload?.role!=='anon')throw Error('Only a Supabase publishable or legacy anon key may enter the browser build.');
}
rmSync('dist',{recursive:true,force:true});mkdirSync('dist');
// Copy only public site assets, never the repository, .env files, private tests or audio.
cpSync('frontend/site','dist',{recursive:true,filter:p=>!['COPY.md','README.md','account-source.js'].includes(path.basename(p))&&!path.basename(p).startsWith('.')});
writeFileSync('dist/public-config.js',`window.VOCALGRID_CONFIG=${JSON.stringify({supabaseUrl:url,supabaseKey:key})};\n`);
await build({entryPoints:['frontend/site/account-source.js'],outfile:'dist/account.js',bundle:true,format:'esm',minify:true,target:'es2022'});
const base=(process.env.PUBLIC_SITE_URL||'').replace(/\/$/,'');
if(base){
 const parsed=new URL(base);if(parsed.protocol!=='https:'||parsed.username||parsed.password||parsed.search||parsed.hash||parsed.pathname!=='/')throw Error('PUBLIC_SITE_URL must be the final HTTPS URL');
 const langs=['en','it','de','fr'],link=l=>`${base}/${l==='en'?'':l+'/'}`;
 for(const lang of langs){const p=`dist/${lang==='en'?'':lang+'/'}index.html`;let html=readFileSync(p,'utf8');const tags=`<link rel="canonical" href="${link(lang)}">`+langs.map(l=>`<link rel="alternate" hreflang="${l}" href="${link(l)}">`).join('')+`<link rel="alternate" hreflang="x-default" href="${base}/">`;html=html.replace(/<!-- locale-seo -->[\s\S]*?<!-- \/locale-seo -->/,`<!-- locale-seo -->${tags}<!-- /locale-seo -->`);writeFileSync(p,html);}
 writeFileSync('dist/sitemap.xml',`<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${langs.map(l=>`<url><loc>${link(l)}</loc></url>`).join('')}</urlset>`);
 writeFileSync('dist/robots.txt',`User-agent: *\nAllow: /\nDisallow: /account\nSitemap: ${base}/sitemap.xml\n`);
}
console.log(`Built VocalGrid website; Supabase ${url?'configured':'not configured (account page will explain)'}.`);
