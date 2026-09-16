// Publish only the checked synthetic PDFs and the short team checklist.
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const root = path.resolve(__dirname, '..');
const modules = path.join(root, 'frontend_v2/node_modules');
const out = path.join(root, 'frontend_v2/public/docs/financial-testing');
const source = fs.readFileSync(path.join(root, 'docs/user-guide/financial-team-checklist.md'), 'utf8');
if (source.includes('\u2014')) throw Error('Use plain punctuation in the team checklist.');
(async () => {
  const React = require(path.join(modules, 'react'));
  const {renderToStaticMarkup} = require(path.join(modules, 'react-dom/server'));
  const {default: Markdown} = await import(pathToFileURL(require.resolve('react-markdown', {paths:[modules]})));
  const {default: gfm} = await import(pathToFileURL(require.resolve('remark-gfm', {paths:[modules]})));
  const {zipSync, strToU8} = require(path.join(modules, 'fflate'));
  const body = renderToStaticMarkup(React.createElement(Markdown, {remarkPlugins:[gfm], children:source}));
  const html = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Loupe financial team testing</title><style>body{font:17px/1.65 system-ui,sans-serif;color:#20252b;background:#f4f5f7;margin:0}main{max-width:900px;margin:24px auto;background:white;padding:32px}h1,h2{line-height:1.3}h2{margin-top:2.2em;border-top:1px solid #ddd;padding-top:1em}a{color:#a71330}li{margin:.5em 0}table{border-collapse:collapse;width:100%;font-size:.9em}th,td{padding:9px;border:1px solid #ccc;text-align:left}th{background:#f5f5f5}@media(max-width:640px){main{padding:18px;margin:0}table{display:block;overflow:auto}}@media print{body{background:white}main{margin:0;padding:0}h2{break-after:avoid}tr{break-inside:avoid}}</style><main>${body}</main></html>`;
  fs.mkdirSync(out, {recursive:true});
  const checking = fs.readFileSync(path.join(out,'checking.pdf'));
  const savings = fs.readFileSync(path.join(out,'savings.pdf'));
  fs.writeFileSync(path.join(out,'index.html'), html);
  fs.writeFileSync(path.join(out,'financial-team-checklist.md'), source);
  fs.writeFileSync(path.join(out,'financial-test-pack.zip'), zipSync({'checking.pdf':checking,'savings.pdf':savings,'checklist.html':strToU8(html),'checklist.md':strToU8(source)}, {level:6}));
  console.log(JSON.stringify({words:source.split(/\s+/).length,files:5,html_bytes:Buffer.byteLength(html)}));
})().catch(error=>{console.error(error);process.exitCode=1});
